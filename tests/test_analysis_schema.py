import json
import unittest

from analysis_schema import parse_and_validate_analysis, render_analysis_markdown
from step3_agent import call_structured_llm


class StructuredAnalysisTests(unittest.TestCase):
    def test_every_supported_claim_is_marked_verified(self):
        raw = json.dumps(
            {
                "summary": "套餐价格有调整",
                "rating": "A",
                "claims": [
                    {
                        "category": "定价",
                        "claim": "专业套餐价格为 199 元",
                        "old_quote": "专业套餐 99 元",
                        "new_quote": "专业套餐 199 元",
                        "confidence": "high",
                    }
                ],
                "recommendations": ["复核套餐权益"],
            },
            ensure_ascii=False,
        )
        result = parse_and_validate_analysis(
            raw,
            old_source="价格表：专业套餐 99 元",
            new_source="价格表：专业套餐 199 元",
        )
        self.assertFalse(result.claims[0].needs_review)
        rendered = render_analysis_markdown(result, title="变化")
        self.assertIn("证据已匹配", rendered)
        self.assertIn("行动建议（非事实）", rendered)

    def test_missing_or_unmatched_evidence_requires_review(self):
        raw = json.dumps(
            {
                "summary": "发现新功能",
                "claims": [
                    {
                        "category": "功能",
                        "claim": "新增批量导出",
                        "old_quote": "",
                        "new_quote": "页面中不存在的引文",
                        "confidence": "high",
                    },
                    {"category": "功能", "claim": "支持 API", "confidence": "high"},
                ],
            },
            ensure_ascii=False,
        )
        result = parse_and_validate_analysis(raw, new_source="真实页面正文")
        self.assertTrue(all(claim.needs_review for claim in result.claims))
        self.assertIn("本次正文引文未匹配", result.claims[0].validation_issues)
        self.assertIn("缺少逐字证据", result.claims[1].validation_issues)

    def test_quote_taken_from_normalized_diff_matches_raw_source(self):
        # 差异块基于规范化正文生成：图片被替换为 alt 文本。模型逐字引用差异块时，
        # 引文在规范化正文里存在，但在原始 Markdown 里并不连续出现。
        raw_source = "![满299减50 全场8折](https://cdn.example.com/a.png?utm_source=x) 立即查看"
        raw = json.dumps(
            {
                "summary": "促销文案更新",
                "claims": [
                    {
                        "category": "定价",
                        "claim": "新增满减活动",
                        "new_quote": "满299减50 全场8折 立即查看",
                        "confidence": "high",
                    }
                ],
            },
            ensure_ascii=False,
        )
        result = parse_and_validate_analysis(raw, new_source=raw_source)
        self.assertFalse(result.claims[0].needs_review, result.claims[0].validation_issues)

    def test_diff_markers_copied_into_quotes_are_stripped(self):
        raw = json.dumps(
            {
                "summary": "套餐调整",
                "claims": [
                    {
                        "category": "定价",
                        "claim": "专业套餐涨价",
                        "old_quote": "- 专业套餐 99 元",
                        "new_quote": "+ 专业套餐 199 元",
                        "confidence": "high",
                    }
                ],
            },
            ensure_ascii=False,
        )
        result = parse_and_validate_analysis(
            raw, old_source="专业套餐 99 元", new_source="专业套餐 199 元"
        )
        claim = result.claims[0]
        self.assertFalse(claim.needs_review, claim.validation_issues)
        self.assertEqual(claim.new_quote, "专业套餐 199 元")

    def test_non_json_output_is_quarantined_as_fallback(self):
        result = parse_and_validate_analysis("这是未经结构化的模型结论", new_source="正文")
        self.assertTrue(result.parse_fallback)
        self.assertTrue(result.claims[0].needs_review)
        self.assertIn("结构化 JSON", result.claims[0].validation_issues[0])


class StructuredModelCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_falls_back_when_endpoint_rejects_json_mode(self):
        marker = object()

        class FakeCompletions:
            def __init__(self):
                self.calls = []

            async def create(self, **kwargs):
                self.calls.append(kwargs)
                if "response_format" in kwargs:
                    raise RuntimeError("response_format is unsupported")
                return marker

        completions = FakeCompletions()
        client = type(
            "FakeClient",
            (),
            {"chat": type("FakeChat", (), {"completions": completions})()},
        )()
        result = await call_structured_llm(
            client, model="compatible-model", prompt="return json", max_tokens=100
        )
        self.assertIs(result, marker)
        self.assertEqual(len(completions.calls), 2)
        self.assertNotIn("response_format", completions.calls[1])


if __name__ == "__main__":
    unittest.main()
