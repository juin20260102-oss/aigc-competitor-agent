# Cloudflare Pages 静态看板部署指南

本项目支持将抓取与模型分析生成的竞品数据（16 个站点的深度画像、最新版本动态、高清截图证据、4 期历史综合日报）**一键编译为独立的纯静态 Web 看板**，并直接部署至 **Cloudflare Pages**。

---

## 🌟 核心优势

1. **免费分配 `*.pages.dev` 域名**：完全不需要购买任何自有域名；
2. **国内免翻墙秒开**：依托 Cloudflare 全球 CDN 静态资源加速，访问体验大幅优于境外动态容器；
3. **100% 绝对安全（零 API Key 泄露风险）**：纯静态前端呈现已有分析结果，不包含任何大模型 API Key 和后端长连接，彻底杜绝被他人盗刷扣费；
4. **一键构建生成**：本地日常执行 Agent 产出新报告后，双击 `build_site.bat` 即可秒级完成打包更新。

---

## 一、 本地一键构建

在项目根目录下执行以下任一方式：

* **方式 1（Windows 双击快捷方式）**：双击运行 [`build_site.bat`](../build_site.bat)。
* **方式 2（命令行）**：
  ```bash
  python tools/build_static_site.py
  ```

构建完成后，会在根目录生成 `dist/` 文件夹：
* `dist/index.html`：包含暗黑科技风设计、三大功能 Tab（每日情报、竞品全景、截图证据）与大图灯箱预览的单页看板。
* `dist/screenshots/`：18 张最新抓取保存的竞品高保真存证截图。

---

## 二、 部署至 Cloudflare Pages

### 途径 A：网页端 1 分钟拖拽部署（最推荐，零配置）

1. 登录 [Cloudflare 控制台](https://dash.cloudflare.com/)；
2. 点击左侧导航栏 **“Workers 和 Pages”** -> 点击 **“创建应用程序 (Create application)”** -> 选择 **“Pages”** 标签；
3. 选择 **“上传资产 (Upload assets)”**；
4. 项目名称填写：例如 `aigc-intel-hub`（可自定义）；
5. 将本地的 **`D:\Anti\Agent_Daily_Report\dist`** 文件夹整体拖入上传区域；
6. 点击 **“部署站点 (Deploy site)”**！
7. 部署完成后，Cloudflare 会立即为您生成类似：
   `https://aigc-intel-hub.pages.dev`
   您可以将此链接直接发给领导、投资人或团队成员访问！

---

### 途径 B：关联 GitHub 仓库自动持续部署 (CI/CD)

如果您希望每次向 GitHub push 代码时自动完成网页构建与上线：

1. 在 Cloudflare Pages 创建页面时选择 **“连接到 Git (Connect to Git)”**；
2. 授权并选择您的仓库：`aigc-competitor-agent`；
3. 构建设置填写：
   * **框架预设 (Framework preset)**：选择 `None`
   * **构建命令 (Build command)**：`python tools/build_static_site.py`
   * **构建输出目录 (Build output directory)**：`dist`
4. 点击 **“保存并部署”**。之后每次更新日报并 push 到 GitHub，Cloudflare 都会自动运行 Python 脚本生成静态站并同步刷新！

---

### 途径 C：命令行 Wrangler 部署

如果本地已安装 Node.js，可以直接运行：
```bash
npx wrangler pages deploy dist --project-name aigc-intel-hub
```
按照终端提示授权后即可直接完成上线。
