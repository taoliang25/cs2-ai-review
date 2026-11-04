# Streamlit Community Cloud 部署方案

- 更新日期：2026-11-04
- 目标：任何电脑通过公网网址访问，无需安装 Python 或项目依赖
- 费用目标：优先使用免费额度
- 当前状态：已部署并通过公网主流程验收

## 1. 为什么不用临时 SSH 隧道

已验证 localhost.run、Serveo 和 Tunnelmole 的 HTTP 健康接口可以返回 200，
但实际浏览器无法完成 Streamlit 的实时页面连接或出现中间警告页。
因此这些隧道不适合最终答辩展示。

终端能访问健康接口不代表浏览器能正常使用。最终验收必须看浏览器中的完整页面。

## 2. 为什么选择 Streamlit Community Cloud

- 可以直接运行当前 Streamlit 应用，不需要改成前后端分离。
- 提供 HTTPS 公网地址。
- 支持 GitHub 部署和 Streamlit Secrets。
- 当前网络可以访问 `https://share.streamlit.io`。
- 免费额度适合数量很少的答辩演示。

限制：

- 需要用户自己的 GitHub 和 Streamlit 账号。
- 免费应用长时间无访问会休眠，首次打开可能等待几十秒。
- 免费计算资源有限，5 个用户同时解析 1 GB Demo 不保证流畅。
- 平台可能限制超大上传或长时间分析。
- 是否能从学校网络稳定访问仍需实际测试。

## 3. 已为云端准备的内容

- `app.py` 支持读取 Streamlit Secrets。
- `.streamlit/secrets.toml.example` 提供云端配置模板。
- `.env` 和 `.streamlit/secrets.toml` 均被 Git 忽略。
- 地图资源已放入 `assets/maps/2000940/`。
- 公开演示 Demo 已放入 `assets/demo/public_sample.dem`。
- 报告导出依赖已写入 `requirements.txt`。
- 访问口令、并发和每日任务限制已实现。

## 4. 用户需要完成的账号步骤

这属于账号授权，必须由用户本人完成。

1. 注册并登录 GitHub。
2. 新建一个仓库，例如 `cs2-ai-review`。
3. 将本项目代码上传到该仓库。
4. 打开 `https://share.streamlit.io`，使用 GitHub 登录。
5. 创建新应用，选择该仓库、分支和入口 `app.py`。
6. 在应用的 Secrets 设置中粘贴配置模板。
7. 部署并等待构建。
8. 把生成的 `*.streamlit.app` 地址发给老师和同学测试。

不要把 DeepSeek 密钥、访问口令或个人 Demo 提交到 GitHub。

### 4.1 朋友访问时不需要准备什么

朋友不需要 GitHub 账号、Streamlit 账号、Python 环境或 DeepSeek API。
部署完成后，朋友只需要：

1. 在任意电脑的浏览器中打开项目的 `*.streamlit.app` 地址。
2. 输入你设置的访问口令。
3. 上传自己想分析的 `.dem` 文件并完成分析。

所有访客使用项目维护者配置的同一套 DeepSeek API。朋友不能看到 API 密钥，
也不能读取其他访客的分析数据。

`http://localhost:8501` 只在这台电脑上有效，不能直接发给朋友。

## 5. Streamlit Cloud Secrets

在 Streamlit Cloud 的应用设置中填写：

```toml
DEEPSEEK_API_KEY = "你的密钥"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"
LLM_TIMEOUT_SECONDS = "60"
LLM_MAX_TOKENS = "8000"

APP_REQUIRE_ACCESS = "true"
APP_ACCESS_CODE = "你的访问口令"
APP_ENFORCE_USAGE_LIMITS = "true"
```

密钥只保存在 Streamlit Cloud Secrets，不进入源码或仓库。

## 6. 云端测试要求

部署完成后必须完成：

1. 在普通浏览器打开公网地址。
2. 验证访问口令。
3. 载入内置演示 Demo。
4. 选择玩家并完成解析。
5. 使用 DeepSeek 生成报告。
6. 下载 Markdown、Word、PDF。
7. 用手机流量再次访问。
8. 请另一位用户同时访问。
9. 检查应用休眠后首次打开所需时间。

## 7. 当前阻塞

在没有 GitHub 仓库和 Streamlit 账号授权的情况下，无法由代码直接生成最终
`*.streamlit.app` 地址。下一步需要用户确认账号准备情况。

### 2026-11-04 20:24 部署进度

- 用户已完成 GitHub 账号注册，但浏览器尚未登录。
- 本地项目已经初始化为 `main` 分支 Git 仓库。
- 已暂存 142 个部署文件，合计约 74.9 MB。
- 已确认 `.env`、Streamlit Secrets、SQLite、个人 Demo、可执行文件和运行日志
  不会进入提交。
- 会话隔离、上传文件删除、DeepSeek 默认报告引擎修改已完成，16 项测试通过。
- 当前等待用户本人在浏览器中登录 GitHub。
- 登录后还需创建远端仓库、推送代码、授权 Streamlit Cloud，并在云端填写
  DeepSeek 密钥和访问口令。

### 2026-11-04 21:00 部署完成

- GitHub 仓库：`taoliang25/cs2-ai-review`，为支持免费 Cloud 部署已设为公开。
- Streamlit Cloud 应用：`cs2-tactical-review-taoliang25.streamlit.app`。
- 云端运行 Python 3.13.18，全部依赖安装成功。
- 公网页面加载和访问口令验证成功。
- 内置 `public_sample.dem` 解析成功，能够读取 10 名玩家。
- DeepSeek 云端报告真实生成成功，页面显示
  `openai-compatible / deepseek-chat`。
- 已修复 DeepSeek 响应格式兼容问题并加入自动重试。
- 自动化测试由 16 项增加到 18 项，全部通过。

安全待办：

- 部署过程中内部表单回显了 DeepSeek 密钥和访问口令，应将旧密钥和口令视为
  已暴露。
- 待用户在 DeepSeek 控制台撤销旧 API Key 并创建新 Key 后，需要同时更新
  Streamlit Secrets 和本地 `.env`。
- 更换访问口令后，需要同时更新 Streamlit Secrets 和本地 `.env`。
- 完成轮换前不要将公网地址和访问口令发送给朋友。

