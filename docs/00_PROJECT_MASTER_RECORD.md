# CS2 战术识别与智能复盘项目总档案

- 档案版本：1.0
- 最后更新：2026-11-04 21:58（Asia/Shanghai）
- 项目阶段：开题阶段，MVP 已完成公网部署和真实云端验收
- 恢复口令：用户发送 **“可以开始工作了”** 时，先阅读
  `docs/DAILY_WORK_LOG.md`、本文件和 `docs/PROJECT_CONTEXT_HANDOFF.md`
- 恢复原则：沿用已经确认的题目、范围、技术路线和用户体验，不重新设计

## 1. 项目基本信息

项目题目：

**基于对局事件的《CS2》战术识别与赛后智能复盘系统设计与实现**

项目定位：

- 本科人工智能专业毕业设计，不是商业产品。
- 目标是形成可演示、可解释、可用于论文和答辩的完整系统。
- 重点不是虚构算法创新，而是真实解析 Demo、计算可解释事实、识别行为倾向，
  再由大模型生成有证据约束的教练式复盘。
- 学校材料提交、最终 Demo 授权、结果确认和答辩由用户本人完成。

## 2. 已确认的产品范围

### 2.1 输入与用户流程

```text
用户打开公网网页
  -> 输入访问口令
  -> 上传一场 CS2 5v5 Demo
  -> 系统解析对局与玩家
  -> 用户从真实玩家列表选择一名主要分析对象
  -> 系统计算指标、路线、关键回合和证据
  -> DeepSeek 基于去标识化事实生成复盘
  -> 用户查看全场、回合或证据，并下载 Markdown/Word/PDF
```

### 2.2 支持范围

- 只支持《CS2》。
- 只支持常规 5v5，例如竞技或 Premier。
- 不支持死亡竞赛、军备竞赛、Wingman。
- 一次只分析一场 Demo。
- 一次选择一个主要分析玩家。
- 可以分析整场，也可下钻到单个回合。
- 系统分析的是行为倾向，不声称读取玩家真实想法。

### 2.3 分析维度

- 开局去向、常用路线和区域偏好。
- 跟队或远端独立行动倾向。
- 首轮交火、首杀和首死。
- 道具购买与可观测效果。
- 优势局、均势局和落后局的行为差异。
- 最后存活与残局处理。
- 团队配合和支援意识。
- 队友死亡时的地点、玩家位置、最近存活队友、双方人数和炸弹状态。
- 关键事件对回合结果的影响。

### 2.4 报告六部分

1. 本场玩家画像、优势、坏习惯和问题。
2. 回合时间线。
3. 关键决策分析：发生什么、可观测影响和可考虑方案。
4. 优秀回合与问题回合的单回合复盘。
5. 全场总结、最多三个重点问题和训练建议。
6. 证据展示：地图路线、热力图、经济图、事件和证据编号。

### 2.5 首版不做的内容

- 其他游戏。
- 多场历史账号分析。
- 用户注册体系和云端历史记录。
- 自动视频剪辑。
- 没有标签和真实验证依据的复杂机器学习模型。
- 声称百分百还原玩家心理或意图。

## 3. 已确认的使用与部署需求

- 用户和少量朋友、老师可通过浏览器公网访问，不需要安装 Python。
- 所有知道网址和访问口令的访客都能使用。
- 访客只需要浏览器、Demo 和访问口令，不需要 GitHub、Streamlit 或 DeepSeek账号。
- 所有访客共用项目维护者的 DeepSeek API。
- 单文件上传上限：1 GB。
- 使用限制：最多 5 个并发分析、每天最多 50 场。
- 原始上传 Demo 在解析完成后立即删除。
- 每个会话使用独立临时 SQLite，避免不同访客数据混用。
- 主要访问地区为中国大陆。
- 预算目标为少量演示费用，优先使用免费平台。
- 暂无自有域名，使用平台提供的 `*.streamlit.app` 地址。
- 公网版本需要访问口令。
- DeepSeek 调用失败时自动回退本地模板报告。

## 4. 当前公网部署

- GitHub 仓库：
  <https://github.com/taoliang25/cs2-ai-review>
- 仓库可见性：Public。用户已明确同意公开源代码。
- Streamlit 应用：
  <https://cs2-tactical-review-taoliang25.streamlit.app>
- 部署平台：Streamlit Community Cloud。
- 云端 Python：3.13.18。
- 入口文件：`app.py`。
- 分支：`main`。
- 云端访问口令和 DeepSeek Key 保存在 Streamlit Secrets，不在 Git 仓库。
- 本地密钥和访问口令保存在项目根目录 `.env`，不提交到 Git。

朋友使用步骤：

1. 打开公网地址。
2. 输入维护者提供的访问口令。
3. 上传自己的 Demo。
4. 从玩家列表选择一人并生成报告。

## 5. 技术路线

### 5.1 主路线

```text
Awpy 3.1.1 主解析
  + demoparser2 0.42.1 交叉验证
  -> SQLite 事实库
  -> Pandas/Polars 指标计算
  -> 可解释规则识别
  -> 结构化事实包
  -> DeepSeek deepseek-chat
  -> JSON 格式和证据校验
  -> Streamlit + Plotly 展示
  -> Markdown/Word/PDF 导出
```

### 5.2 重要技术决策

- 不强制加入独立机器学习算法；导师没有要求以算法创新作为毕业前提。
- 不使用伪造标签、伪造准确率或“用同一条规则生成并验证标签”的循环论证。
- 当前“战术识别”采用透明事件与位置规则，所有规则都有版本号。
- 大模型只负责解释结构化事实，不负责创造比赛事件。
- 模板报告是无网络或模型失败时的稳定降级路径。
- 不采用本机 Ollama；当前只使用 DeepSeek 和模板。

### 5.3 环境

本地：

- Windows。
- 主 Python：`D:\python.exe`，Python 3.13.5。
- 项目虚拟环境：`D:\毕业设计\.venv`。
- 另有 Python 3.7.13，不属于项目环境。

主要依赖：

- `awpy==3.1.1`
- `demoparser2==0.42.1`
- `pandas==3.1.0`
- `polars==2.1.0`
- `streamlit==1.66.1`
- `plotly==7.1.0`
- `python-docx==1.2.0`
- `reportlab==4.4.9`
- `python-dotenv==1.1.1`

## 6. 当前实现

### 6.0 视觉与地图点位（2026-11-04 晚更新）

- Streamlit 页面已改为深色 CS2 战术分析工作台。
- 导入页、玩家选择、教练总览、位置路线、关键回合、单回合复盘和完整报告
  已统一视觉层级。
- 报告将事实、行为推断和训练建议分开显示，原始证据默认折叠。
- DeepSeek 默认使用温和、具体、行动导向的教练式提示词。
- 地图地点通过 `src/cs2_review/map_callouts.py` 按地图独立映射为国内常用叫法。
- 原始解析名仍保留在 SQLite，不影响事实追溯。
- 详细说明见 `docs/23_ui_and_map_callouts.md`。

### 6.1 Demo 事实层

- 支持单场 `.dem` 导入 SQLite。
- 过滤教练、旁观者和 `DemoRecorder`。
- 保存玩家、回合、击杀、伤害、射击、炸弹、道具、经济、逐秒位置和地点名。
- 将赛后事件标记为 `is_post_round`，避免误计入有效回合。
- 位置只保留有效行动阶段，避免把回合间观战位置混入路线。
- 处理比赛完整性：`has_match_end` 与 `regulation_complete` 分开判断。

### 6.2 玩家分析

- 整场和逐回合事件指标。
- 开局路线、区域偏好、队友好距离。
- 首轮交火、首杀、首死。
- 队友接敌时是否在附近，以及 5 秒内是否响应。
- 有利局与落后局的差异。
- 残局和最后存活。
- 道具购买与可观测效果。
- 队友阵亡后位置上下文和可执行建议。
- 关键回合候选与影响评分。

### 6.3 战术模式

- 行为规则版本：`event-rules-v0.1`
- 战术规则版本：`tactical-rules-v0.2`
- 早期路线窗口：冻结结束后的前 15 秒。
- 最近存活队友距离：
  - `<= 500`：较近队。
  - `500–800`：过渡区。
  - `> 800`：远端独立行动。
- 支援距离 `<= 800`：就近。
- 队友首次交战采样容差：前后 2 秒。
- 就近后响应窗口：5 秒。
- 位置采样：每 1 秒。
- 这些是工程规则，不是游戏官方真值。

### 6.4 DeepSeek 报告

- 模型：`deepseek-chat`。
- OpenAI-compatible 接口。
- 输入前去标识化：不发送 Demo、玩家名、Steam ID 或原始坐标。
- 输出必须是固定 JSON。
- 事实和行为推断必须引用允许的证据 ID。
- 时间线必须逐回合覆盖。
- 禁止心理读心和百分百还原想法。
- 校验失败时先修复一次，再失败则使用模板。
- 兼容 `message.content` 字符串、内容分片和 `reasoning_content` 回退。
- JSON 模式解析失败时会自动关闭 `response_format` 重试一次。

### 6.5 网页

- 访问口令。
- 上传或载入公开测试 Demo。
- 解析后从玩家列表点击选择玩家。
- 默认优先使用 DeepSeek，模板作为降级。
- 全场总览、位置与路线、关键回合、单回合复盘、AI 报告。
- Plotly 雷达图、路线、热力图和经济图。
- Markdown、Word、PDF 下载。
- 删除当前临时分析数据。
- 并发和每日任务限制。
- 每会话独立临时目录。
- 上传文件解析后立即删除。

## 7. 真实数据与实验

### 7.1 Demo 数据

- 已获得 19 份公开授权或公开测试 Demo。
- 覆盖 7 张地图。
- 190 条选手-对局记录。
- 114 名唯一选手。
- 其中 6 场达到常规完整终局目标。
- 覆盖 Ancient、Anubis、Dust2、Inferno、Mirage、Nuke。
- 公网演示文件：`assets/demo/public_sample.dem`。
- 公网演示的授权来源和 SHA-256 见 `assets/demo/README.md`。

### 7.2 已有实验

- 基础数据质量和多地图解析实验。
- 规则阈值敏感性实验。
- 当前结果目录：`experiments/results/`。
- 最新基线：`experiment_20261104T095547Z.json`。
- 已确认 19/19 基础数据质量检查通过。
- 尚没有可靠的战术标签真值，不能宣称战术识别准确率。
- 单场、六张完整地图的阈值敏感性实验已经完成。

### 7.3 最近一次完整自动化测试

2026-11-04 晚：

- `compileall` 通过。
- 22 项 unittest 全部通过。
- 新增覆盖 DeepSeek 文本分片解析、关闭 JSON 模式后的自动重试、
  地图点位中文化和跨地图隔离。

### 7.4 最近一次公网真实验收

已实际完成：

1. 打开公网地址。
2. 输入访问口令。
3. 载入 `public_sample.dem`。
4. 成功解析 Dust2 和 10 名玩家。
5. 选择玩家。
6. 使用 DeepSeek 生成报告。
7. 页面显示 `openai-compatible / deepseek-chat`。
8. 六部分报告、时间线和证据编号正常显示。

说明：这次验收证明主流程真实可用，不构成战术识别准确率或模型总体质量证明。

## 8. 重要代码文件

- `app.py`：Streamlit 网页、访问口令、上传、云端报告调用和展示。
- `src/cs2_review/importer.py`：Demo 解析与 SQLite 事实层。
- `src/cs2_review/metrics.py`：玩家行为指标、回合事实和关键回合。
- `src/cs2_review/tactical_patterns.py`：可解释战术模式。
- `src/cs2_review/llm_report.py`：DeepSeek、兼容解析、重试和证据校验。
- `src/cs2_review/reporting.py`：模板报告。
- `src/cs2_review/exporters.py`：Word/PDF 导出。
- `src/cs2_review/access.py`：访问限制和并发/日限额。
- `src/cs2_review/visualization.py`：地图和经济可视化。
- `database/schema.sql`：SQLite 表结构。
- `start_app.cmd`：本地一键启动。
- `scripts/`：导入、分析、实验和导出脚本。
- `tests/`：自动化测试。

详细设计入口：

- `docs/01_requirements_baseline.md`
- `docs/03_technical_design.md`
- `docs/04_database_design.md`
- `docs/05_page_flow_and_milestones.md`
- `docs/10_ai_reporting_and_validation.md`
- `docs/16_thesis_technical_chapter_draft.md`
- `docs/22_streamlit_cloud_deployment.md`

## 9. 安全与数据边界

- `.env` 和 `.streamlit/secrets.toml` 均被 Git 忽略。
- API Key 和访问口令只能存在于本地 Secrets 或 Streamlit Cloud Secrets。
- 不得把密钥、访问口令、个人 Demo、SQLite、运行日志提交到 Git。
- 公网仓库可以包含源代码、论文材料、实验汇总、地图资源和公开授权 Demo。
- 上传原始 Demo 解析完成后立即删除。
- 会话 SQLite 应使用独立临时目录，避免访客数据混用。
- 发给外部的 DeepSeek 事实包不含玩家名、Steam ID、Demo 或原始坐标。

### 9.1 已知安全事件

部署时，内部工具在检查 Streamlit Secrets 表单时回显过旧 DeepSeek API Key
和旧访问口令。正常处理方式应是撤销旧 Key、重新创建 API Key 和新访问口令。

用户已在 2026-11-04 明确决定：

- 不创建新的 DeepSeek Key。
- 继续使用现有 API Key 和访问口令。

因此团队必须遵守用户决定，但应保持以下注意事项：

- 不要把访问口令发到公开群聊或公开截图。
- 不要把 `.env`、DeepSeek 控制台截图、Streamlit Secrets 截图发送到公开位置。
- 如果 API 账单异常或访问口令外泄，立即回到轮换流程。
- 不得在后续对话、文档或代码中重复输出真实密钥。

## 10. 当前已知限制

- 公开演示 Demo 是 16 回合、9:7 的片段或不完整终局，不是完整常规赛。
- Dust2 等在规则层没有完整 A/B/MID 区域映射，系统只展示真实地点名。
- 单场数据只能说明本场行为，不能推断长期习惯。
- 后手闪、无效投掷等零效果行为可能无法完整识别。
- 同一 tick 多事件顺序可能不唯一。
- Streamlit Cloud 免费资源无法保证 5 人同时解析 1 GB Demo。
- 免费应用休眠后首次打开可能需要几十秒。
- 尚未获得学校任务书、论文模板和明确答辩/开题日期。
- 尚未用用户个人真实 Demo 完成最终验收。
- 战术识别准确率、模型事实准确率和用户满意度尚无标签与正式评价。

## 11. 下一步任务

优先级从高到低：

1. 获取学校任务书、开题模板和截止时间后，放入 `docs/school/`。
2. 获取并保护用户自己的 Demo，完成普通玩家真实场景验证。
3. 再补充至少 5 个常规完整终局样本，优先补 Overpass。
4. 重新运行最终实验并生成可复现结果。
5. 用最终数据重新生成一份 DeepSeek 报告并检查事实一致性。
6. 检查 Markdown、Word、PDF 下载。
7. 用手机流量、另一台电脑和学校网络访问公网应用。
8. 让另一名访客同时访问，确认临时数据隔离。
9. 根据学校模板撰写开题报告、论文和答辩材料。
10. 准备答辩演示脚本和常见问题。

不得执行：

- 不要重新设计为其他游戏或多游戏平台。
- 不要直接伪造战术标签、准确率、实验数据或参考文献。
- 不要把同一条规则生成的标签当成独立真值评估自己。
- 不要删除已有真实 Demo、实验输出和论文工作稿。
- 不要在未确认学校要求时擅自大改题目。

## 12. 电脑损坏后的恢复步骤

### 12.1 恢复代码

在新电脑安装 Git 和 Python 3.13，然后执行：

```powershell
git clone https://github.com/taoliang25/cs2-ai-review.git
cd cs2-ai-review
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 12.2 恢复本地运行

在新电脑新建 `.env`，结构和变量名参考 `.env.example`。向维护者本人获取
DeepSeek API Key 和访问口令，不要把真实值写入代码或提交 Git。

然后双击：

```text
start_app.cmd
```

### 12.3 恢复云端

- Streamlit 应用仍从 GitHub `main` 分支部署。
- 只要 GitHub 和 Streamlit 账号可登录，云端应用不会因本地电脑损坏而消失。
- 新代码推送到 `main` 后，Streamlit 会自动重新部署。

### 12.4 恢复后必须检查

```powershell
.\.venv\Scripts\python.exe -m compileall -q app.py src tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
git status
git log --oneline -5
```

再打开公网地址，使用内置 Demo 完成一次访问口令、解析、玩家选择和报告测试。

## 13. 后续 AI 协作约束

- 用户计算机基础较弱，解释要清楚，优先执行可操作步骤。
- 已确认的问题不要重复询问。
- 每次只问当前最关键的未确认问题。
- 继续时先读本档案、交接文档和必要设计文档。
- 文档和代码改动要有真实依据，不编造实验。
- 发现方案风险时先说明证据和影响，再决定是否调整。
- 用户已经确认的方向不要因为“看起来更高级”而擅自替换。
- 真实密钥、访问口令、OTP 和私密玩家数据不得写入仓库或输出到聊天。

## 14. 关键决策时间线

1. 确认只分析单场 CS2 5v5 Demo 和单个主要玩家。
2. 确认报告以行为倾向、关键决策和可执行改进为核心。
3. 完成 Awpy + demoparser2 真实 Demo 解析验证。
4. 完成 SQLite 事实层和可解释行为指标。
5. 完成模板报告、DeepSeek 报告和证据校验。
6. 完成 Streamlit MVP 和 Word/PDF 导出。
7. 确认导师不强制要求独立机器学习算法创新。
8. 确认需要公网访问，访客使用维护者 API，只通过访问口令控制。
9. 确认使用 Streamlit Community Cloud，而不是不稳定的临时 SSH 隧道。
10. 创建 GitHub 仓库并推送项目。
11. 完成 Streamlit 账号注册、邮箱验证和 GitHub 授权。
12. 为了免费部署，经用户允许将仓库改为 Public。
13. 完成 Streamlit Secrets、Python 3.13 和公网部署。
14. 修复 DeepSeek 云端 JSON 兼容问题。
15. 完成公网 Demo 解析和 DeepSeek 报告真实验收。
16. 用户决定不轮换已回显的旧 API Key 和访问口令。

