"""Structured model-output parsing, evidence validation, and Markdown rendering."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from agent_utils import normalize_content


ALLOWED_CONFIDENCE = {"high", "medium", "low"}
ALLOWED_RATINGS = {"S", "A", "B", "C", "NA"}


@dataclass(frozen=True)
class EvidenceClaim:
    category: str
    claim: str
    old_quote: str = ""
    new_quote: str = ""
    confidence: str = "low"
    needs_review: bool = False
    validation_issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalysisResult:
    summary: str
    claims: tuple[EvidenceClaim, ...] = ()
    recommendations: tuple[str, ...] = ()
    rating: str = "NA"
    parse_fallback: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def structured_output_instruction(*, mode: str) -> str:
    quote_rule = (
        "变化项可填写 old_quote、new_quote 或两者；删除内容必须填写 old_quote，新增内容必须填写 new_quote。"
        if mode == "change"
        else "每条事实 claim 必须填写可在网页正文中精确找到的 new_quote。"
    )
    return f"""仅输出一个 JSON 对象，不要输出 Markdown 或代码围栏。结构必须是：
{{
  "summary": "一句话摘要",
  "rating": "S|A|B|C|NA",
  "claims": [
    {{
      "category": "定位|功能|定价|运营|新增|删除调整|其他",
      "claim": "单一、可核验的事实陈述",
      "old_quote": "上次正文逐字引文，没有则为空字符串",
      "new_quote": "本次正文逐字引文，没有则为空字符串",
      "confidence": "high|medium|low"
    }}
  ],
  "recommendations": ["与事实分离、可执行的建议"]
}}
{quote_rule}
每个数组最多 8 项；不得把推测写入 claims。页面未披露的信息不要创建事实 claim。"""


def _clean(value: object, *, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()[:limit]


def _extract_json(raw: str) -> dict:
    candidate = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        candidate = fenced.group(1)
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型未返回 JSON 对象") from None
        try:
            value = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError("模型返回的 JSON 无法解析") from exc
    if not isinstance(value, dict):
        raise ValueError("模型输出顶层必须是 JSON 对象")
    return value


# 模型常把差异块的行首标记（"+ " / "- "）一并抄进引文。
_DIFF_MARKER_RE = re.compile(r"^[+-]\s+")


def _strip_diff_marker(quote: str) -> str:
    return _DIFF_MARKER_RE.sub("", quote, count=1)


def _quote_matches(quote: str, source: str) -> bool:
    if not quote or not source:
        return False
    compact_quote = " ".join(quote.split())
    # 差异块基于规范化正文生成（图片替换为 alt、链接去追踪参数），
    # 所以引文既可能出现在原文里，也可能只在规范化正文里连续出现。
    for candidate in (source, normalize_content(source)):
        if quote in candidate or compact_quote in " ".join(candidate.split()):
            return True
    return False


def parse_and_validate_analysis(
    raw: str,
    *,
    old_source: str = "",
    new_source: str = "",
) -> AnalysisResult:
    """Parse bounded JSON and mark every unsupported factual claim for review."""
    try:
        payload = _extract_json(raw)
    except ValueError:
        excerpt = _clean(raw, limit=500) or "模型未返回可用内容"
        claim = EvidenceClaim(
            category="格式异常",
            claim=excerpt,
            needs_review=True,
            validation_issues=("模型输出不是有效的结构化 JSON",),
        )
        return AnalysisResult(
            summary="结构化解析失败，原始输出仅供人工复核。",
            claims=(claim,),
            parse_fallback=True,
        )

    claims: list[EvidenceClaim] = []
    raw_claims = payload.get("claims", [])
    if not isinstance(raw_claims, list):
        raw_claims = []
    for item in raw_claims[:8]:
        if not isinstance(item, dict):
            continue
        category = _clean(item.get("category"), limit=30) or "其他"
        claim_text = _clean(item.get("claim"), limit=500)
        if not claim_text:
            continue
        old_quote = _strip_diff_marker(_clean(item.get("old_quote"), limit=300))
        new_quote = _strip_diff_marker(_clean(item.get("new_quote"), limit=300))
        confidence = _clean(item.get("confidence"), limit=10).lower()
        if confidence not in ALLOWED_CONFIDENCE:
            confidence = "low"
        issues: list[str] = []
        if not old_quote and not new_quote:
            issues.append("缺少逐字证据")
        if old_quote and not _quote_matches(old_quote, old_source):
            issues.append("上次正文引文未匹配")
        if new_quote and not _quote_matches(new_quote, new_source):
            issues.append("本次正文引文未匹配")
        claims.append(
            EvidenceClaim(
                category=category,
                claim=claim_text,
                old_quote=old_quote,
                new_quote=new_quote,
                confidence=confidence,
                needs_review=bool(issues),
                validation_issues=tuple(issues),
            )
        )

    recommendations = payload.get("recommendations", [])
    if not isinstance(recommendations, list):
        recommendations = []
    clean_recommendations = tuple(
        text for item in recommendations[:8] if (text := _clean(item, limit=500))
    )
    rating = _clean(payload.get("rating"), limit=2).upper()
    if rating not in ALLOWED_RATINGS:
        rating = "NA"
    return AnalysisResult(
        summary=_clean(payload.get("summary"), limit=500) or "模型未提供摘要。",
        claims=tuple(claims),
        recommendations=clean_recommendations,
        rating=rating,
    )


def render_analysis_markdown(result: AnalysisResult, *, title: str) -> str:
    lines = [f"#### 【{title}】", f"- **摘要**：{result.summary}"]
    if result.rating != "NA":
        lines.append(f"- **竞争力评级**：{result.rating}")
    if not result.claims:
        lines.append("- **事实项**：无可用的结构化事实，需人工复核。")
    for claim in result.claims:
        status = "⚠️ 需人工复核" if claim.needs_review else "✅ 证据已匹配"
        lines.append(f"- **{claim.category}**：{claim.claim}（{status}，置信度 {claim.confidence}）")
        if claim.old_quote:
            lines.append(f"  - 上次证据：“{claim.old_quote}”")
        if claim.new_quote:
            lines.append(f"  - 本次证据：“{claim.new_quote}”")
        if claim.validation_issues:
            lines.append(f"  - 校验说明：{'；'.join(claim.validation_issues)}")
    if result.recommendations:
        lines.append("- **行动建议（非事实）**：")
        lines.extend(f"  - {item}" for item in result.recommendations)
    return "\n".join(lines)
