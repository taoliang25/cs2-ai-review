# 项目上下文交接与恢复说明

- 保存时间：2026-11-04
- 最近恢复工作时间：2026-11-04 18:44（Asia/Shanghai）
- 项目阶段：开题阶段；已完成技术验证、数据事实层、模板报告和网页 MVP 主体
- 恢复口令：用户下次发送 **“继续昨天的项目”**
- 恢复原则：阅读本文件后沿用已确认方案继续，不擅自更换题目、技术路线、功能范围或重新设计系统

> 2026-11-04 最新状态：项目已部署到 Streamlit Community Cloud，
> 公网主流程和 DeepSeek 报告已真实验收。完整的最新恢复入口请先阅读
> [项目总档案](00_PROJECT_MASTER_RECORD.md)。

## 1. 项目名称

**基于对局事件的《CS2》战术识别与赛后智能复盘系统设计与实现**

## 2. 项目定位

这是本科人工智能专业毕业设计项目，不是商业产品。目标是完成一个逻辑闭环、演示稳定、能够支撑论文、开题和答辩的本地网页系统。

核心闭环：

```text
上传单场 CS2 Demo
  -> 解析真实对局和玩家列表
  -> 选择一个主要分析玩家
  -> 计算行为指标与战术模式
  -> 推荐关键回合
  -> 生成有证据的模板或大模型复盘
  -> 展示全场总结、单回合和证据图
```

## 3. 已确认范围

### 3.1 游戏与对局

- 只做《CS2》。
- 只支持常规 5v5，例如竞技或 Premier。
- 不支持死亡竞赛、军备竞赛和 Wingman。
- 一次分析一场 Demo。
- 一次选择一个主要分析玩家。
- 可以分析整场，也可以下钻到单个回合。
- 只分析用户上传的当前 Demo，不做多场历史运营或长期账号。

### 3.2 行为分析维度

- 开局去向、常用路线和区域偏好。
- 单走或跟队倾向。
- 首杀尝试和主动交战倾向。
- 道具购买、可观测效果和使用方式。
- 优势局、均势局和劣势局的行为差异。
- 残局处理。
- 团队配合与支援意识。
- 关键操作对回合局势和比赛结果的影响。

### 3.3 报告六部分

1. 本场玩家画像。
2. 回合时间线。
3. 关键决策分析。
4. 单回合复盘。
5. 全场总结与最多三个重点问题和训练建议。
6. 证据展示：位置、热力图、经济变化和关键事件。

### 3.4 不纳入首版

- 王者荣耀、金铲铲之战、三角洲行动。
- 死亡竞赛、军备竞赛和 Wingman。
- 多场历史数据对比。
- 用户账号、云端上传历史和多用户权限。
- 默认公网部署。
- 自动视频剪辑。
- 没有真实验证的复杂机器学习或“创新点”。

## 4. 当前已完成内容

### 4.1 需求与方案

- 需求基线。
- Demo 解析验证方案。
- 技术方案。
- SQLite 数据库设计。
- 页面流程、MVP 和开发里程碑。
- 首次 Demo 验证报告。
- 事实层实现记录。
- 开题论证工作稿。
- 项目简介的不同长度版本。
- AI 复盘与证据校验方案。
- 基线实验记录。
- 可解释战术模式规则说明。
- 规则阈值敏感性实验说明。
- 多地图赛事 Demo 验证说明。
- 公开 Demo 来源与使用边界。
- 论文技术章节初稿。
- 本地系统使用说明。
- 当前进度与需求确认问题。
- 公网访问需求与技术影响。
- 临时公网演示操作说明。

入口见根目录 `README.md`。

### 4.2 环境

- Windows。
- 主 Python：`D:\python.exe`，Python 3.13.5。
- 项目虚拟环境：`.venv`。
- 另有 `D:\Anaconda\python.exe` 的 Python 3.7.13，不作为项目主环境。
- Awpy：3.1.1，主解析器。
- demoparser2：0.42.1，交叉校验和补充字段验证。
- Pandas：3.1.0。
- Polars：2.1.0。
- Streamlit：1.66.1。
- Plotly：7.1.0。
- SQLite 使用 Python 标准库。

### 4.3 真实 Demo 验证

首批公开授权测试 Demo：

- 路径：`data/demo/research_demoparser_test_demo.dem`
- 大小：60,601,900 字节
- SHA-256：`84a1a4191302bdd2a3bbb5a727842093744b1fb1a228aeec630369e44b622cb2`
- 来源：LaihoE/demoparser 官方仓库
- 固定提交：`314a253ed51488093b5f28f648694e42b561079f`
- 地图：`de_mirage`
- 有效玩家：10
- 回合：10
- 结束方式：CT 方投降

已确认：

- 两解析器都得到 73 次击杀和 264 条伤害记录。
- Awpy 可输出位置、回合经济、装备、炸弹、烟雾、燃烧、闪光和购买事件。
- 逐秒位置快照可关联 `m_szLastPlaceName`，获取 `TSpawn`、`CTSpawn`、`Middle`、`BombsiteA` 等真实地点名称。
- Awpy 玩家表可能包含 `DemoRecorder`、教练和旁观者；代码保留
  `terrorist`/`counter-terrorist`，并排除 `m_iCoachingTeam` 非零的教练。
- 部分击杀、射击和炸弹事件会落在 `round.end_tick` 后、下一回合开始前。代码将其归入上一回合，并在 `payload_json.is_post_round=true` 标记。

用户随后明确授权使用公开赛事 Demo。当前 `data/demo/` 共 19 个文件、
约 6.92 GB、7 张地图。职业 Demo 中的教练和旁观者过滤规则已完成修复。
当前有 6 场达到常规赛目标得分的完整样本：

- Nuke，42 回合。
- Dust2，36 回合。
- Mirage，23 回合。
- Inferno，30 回合。
- Anubis，24 回合。
- Ancient，24 回合。

### 4.4 事实数据库

当前样本数据库：

`data/processed/84a1a4191302.sqlite`

当前已验证数量：

- 10 名有效玩家。
- 10 个回合。
- 6,536 条有效行动阶段逐秒位置采样。
- 23 个有效地点名称。
- 20 条双方回合经济记录。
- 2,556 条统一事件证据。

关键事件：

- 击杀：73。
- 伤害：264。
- 射击：1,590。
- 闪光致盲：63。
- 烟雾效果：38。
- 燃烧效果：25。
- 物品购买：229。

数据库完整性：

- `PRAGMA integrity_check`：`ok`
- `PRAGMA foreign_key_check`：无错误

### 4.5 已实现代码

- `src/cs2_review/importer.py`：Demo 解析、SQLite 导入、事件与位置事实层。
- `src/cs2_review/metrics.py`：玩家行为指标、回合事实、关键回合和 FactBundle。
- `src/cs2_review/tactical_patterns.py`：可解释战术模式识别。
- `src/cs2_review/reporting.py`：确定性模板报告。
- `src/cs2_review/llm_report.py`：可选 OpenAI-compatible 报告 Provider、去标识化和校验。
- `src/cs2_review/exporters.py`：Markdown 报告转 Word/PDF。
- `src/cs2_review/report_store.py`：报告持久化。
- `src/cs2_review/visualization.py`：雷达热力图和回合经济图。
- `src/cs2_review/experiments.py`：批量实验、质量检查和匿名输出。
- `src/cs2_review/sensitivity.py`：队友距离与早期窗口敏感性实验。
- `app.py`：Streamlit 网页。
- `database/schema.sql`：SQLite 建表。
- `run_app.ps1`：启动网页。
- `start_public_demo.ps1`：启动本地网页和免费临时公网隧道。
- `stop_public_demo.ps1`：停止项目启动的公网网页服务。

命令行脚本：

- `scripts/inspect_demo.py`
- `scripts/import_demo.py`
- `scripts/analyze_player.py`
- `scripts/generate_report.py`
- `scripts/run_experiments.py`
- `scripts/run_sensitivity.py`
- `scripts/summarize_experiment.py`
- `scripts/export_report.py`

### 4.6 网页 MVP

页面已实现：

- 上传 `.dem` 或选择本地测试 Demo。
- 本地验证 Demo 下拉列表，默认选用完整的 Nuke 赛事样本。
- 解析后从真实玩家列表选择一人。
- 全场摘要和核心指标。
- 回合时间线。
- 回合经济图。
- Mirage 雷达路线和热力图。
- 优秀回合、问题复盘候选、高影响回合。
- 单回合地图、事件时间线和战术模式。
- 六部分模板复盘与 Markdown 下载。
- 可选大模型报告开关。
- 可选本地模板或 DeepSeek 云端。
- Markdown、Word 和 PDF 三种下载。
- 大模型未配置、失败或校验不通过时自动模板降级。

本地页面在最后一次检查时可通过以下地址访问：

`http://localhost:8501`

后续使用：

```powershell
.\run_app.ps1
```

## 5. 当前进度

| 模块 | 状态 |
|---|---|
| 需求边界 | 已完成基线 |
| 真实 Demo 解析 | 19 场通过，覆盖 7 张地图；6 场达到常规完整终局 |
| SQLite 事实层 | 已实现并验证 |
| 玩家行为指标 | 首批 19 项整场指标已实现 |
| 战术模式识别 | 规则版 v0.1 已实现 |
| 关键回合 | 规则排序已实现 |
| 模板报告 | 已完成 |
| 大模型 Provider | DeepSeek 已真实调用并通过证据校验 |
| 报告引擎选择 | 本地模板、DeepSeek 云端 |
| Word / PDF 导出 | 已实现并完成逐页视觉检查 |
| 队友死亡后位置指导 | 已记录死亡地点、玩家位置、距离、人数、带包/下包状态和可选行动 |
| 网页 MVP | 主流程已实现 |
| 可视化 | 雷达图、热力图和经济图已完成 |
| 批量实验脚本 | 已实现并真实运行 |
| 规则阈值敏感性 | 已在六张完整地图复跑 |
| 多场数据实验 | 已完成 19 场解析与质量实验，其中 6 场达到常规完整终局 |
| 多地图解析验证 | 已完成，覆盖 7 张地图、190 条选手-对局记录、114 名唯一选手 |
| 机器学习模型 | 不作为首版必需；导师未强制要求独立算法创新 |
| 论文/开题正式稿 | 未开始，只有工作稿和项目简介 |

## 6. 当前基线与测试

最新可公开的真实实验输出：

- `experiments/results/experiment_20261104T095547Z.json`
- `experiments/results/player_metrics_20261104T095547Z.csv`
- `experiments/results/experiment_20261104T095547Z_summary.md`
- `experiments/results/experiment_20261103T201227Z.json`
- `experiments/results/player_metrics_20261103T201227Z.csv`
- `experiments/results/sensitivity_20261104T090045Z.json`
- `experiments/results/sensitivity_distance_20261104T090045Z.csv`
- `experiments/results/sensitivity_95594d8c_20261104T094612Z.json`
- `experiments/results/sensitivity_5eefa107_20261104T094613Z.json`
- `experiments/results/sensitivity_3d2d9d8f_20261104T094614Z.json`
- `experiments/results/sensitivity_b594d745_20261104T094615Z.json`
- `experiments/results/sensitivity_e2feb7a9_20261104T094616Z.json`
- `experiments/results/sensitivity_21351a60_20261104T094617Z.json`

初始基线结果为 1 个 Demo、10 名玩家、每名玩家 19 项整场指标，
完整解析与导入约 2.2944 秒。最新 19 场实验覆盖 190 条选手-对局记录
（114 名唯一选手；完整终局部分为 45 名），
基础数据质量检查 19/19 通过；其中 6 场达到常规完整终局。

自动化测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

最近一次结果：16 项测试全部通过。

测试覆盖：

- 真实 Demo 导入和数据完整性。
- 10 名玩家均能生成证据完整的事实包。
- 模板报告六个必需章节。
- Streamlit 网页从载入 Demo 到报告显示。
- LLM 合法报告生成。
- LLM 输入去标识化。
- 虚假证据被拒绝。
- 读心表述被拒绝。
- 阈值敏感性结果可以生成。
- 职业赛事 Demo 中的教练与旁观者过滤。
- Markdown、Word 和 PDF 导出生成。

## 7. 关键参数与规则

行为规则版本：`event-rules-v0.1`

战术模式规则版本：`tactical-rules-v0.2`

当前阈值：

- 早期路线窗口：冻结结束后的前 15 秒。
- 最近存活队友距离不超过 500：较近队。
- 最近存活队友距离超过 800：远端独立行动。
- 500–800：过渡区间。
- 支援距离不超过 800：就近。
- 队友首次交战采样容差：前后 2 秒。
- 就近后响应窗口：5 秒。
- 位置采样：每 1 秒。

重要解释：

- 这些阈值是初始工程规则，不是游戏官方定义。
- 模式置信度是规则完整度提示，不是统计概率。
- 不能把“远端独立行动”说成系统确认玩家故意单走。
- 不能把“优先复盘回合”直接说成玩家失误。

当前地图区域映射：

- 已显式配置 `de_mirage` 的 A、B、MID 区域集合。
- 其他地图回退到解析器提供的原始地点名称。
- 区域映射属于项目规则资产，不是官方 ground truth。

## 8. 大模型约束

默认关闭外部调用，本地模板报告始终可用。

支持 OpenAI-compatible Chat Completions：

```powershell
$env:LLM_API_KEY = "<key>"
$env:LLM_BASE_URL = "https://api.openai.com/v1"
$env:LLM_MODEL = "<model>"
$env:LLM_TIMEOUT_SECONDS = "60"
$env:LLM_JSON_MODE = "true"
```

发送给外部模型前会移除：

- Demo 文件。
- 玩家名称。
- Steam ID。
- 原始坐标。

模型输出必须：

- 使用固定 JSON 结构。
- 包含六个章节。
- 每条事实或行为推断引用真实证据 ID。
- 引用存在的回合编号。
- 明确事实、推断和建议。
- 不得声称读心或百分百还原想法。

无效输出不展示，自动改用模板报告。

DeepSeek `deepseek-chat` 已完成真实连通性测试，并成功生成、修复和校验
一份 42 回合复盘报告。仍不能用单次结果宣称模型总体质量。

## 9. 重要文件

- 总入口：`README.md`
- 需求基线：`docs/01_requirements_baseline.md`
- Demo 验证：`docs/06_demo_validation_report.md`
- 技术方案：`docs/03_technical_design.md`
- 数据库设计：`docs/04_database_design.md`
- 页面与里程碑：`docs/05_page_flow_and_milestones.md`
- 开题工作稿：`docs/08_opening_proposal_outline.md`
- 项目简介：`docs/09_project_introduction.md`
- AI 校验：`docs/10_ai_reporting_and_validation.md`
- 基线实验：`docs/11_baseline_experiment.md`
- 战术模式规则：`docs/12_tactical_patterns.md`
- 阈值敏感性：`docs/13_threshold_sensitivity.md`
- 多地图赛事验证：`docs/14_multimap_dataset_validation.md`
- Demo 来源与许可：`docs/15_demo_provenance.md`
- 论文技术章节初稿：`docs/16_thesis_technical_chapter_draft.md`
- 本地使用说明：`docs/17_user_guide.md`
- 当前进度与待确认需求：`docs/18_current_status_and_decision_questions.md`
- 公网访问需求：`docs/20_public_access_requirement.md`
- 临时公网演示：`docs/21_public_demo_operations.md`
- 学校材料接收目录：`docs/school/README.md`

## 10. 已执行的真实验证

- 公开测试 Demo 下载与 SHA-256 校验。
- Awpy 与 demoparser2 的事件数量交叉核对。
- `de_mirage` 雷达资源和坐标元数据已缓存。
- 地图坐标转换和热力图视觉检查。
- SQLite 导入、外键、索引和完整性检查。
- 10 名玩家的指标与证据检查。
- 模板报告真实生成。
- Streamlit 主流程端到端测试。
- 可解释战术模式真实计算。
- 匿名批量实验真实运行。

不得把上述工程验证写成：

- 战术识别准确率。
- 大模型事实准确率。
- 机器学习泛化性能。
- 用户满意度。

## 11. 待完成 / 下一步任务

### 11.1 最高优先级

1. 在现有 19 场基础上继续补充至少 5 份常规完整终局 Demo，优先覆盖 Overpass。
2. 获取用户本人的完整 Demo，验证普通玩家场景。
3. 根据用户确认的云端或本地模型方案，完成一次真实 AI 报告并优化建议质量。

单场和六个完整地图的阈值敏感性分析已经完成，当前结果见
`docs/13_threshold_sensitivity.md`；明天恢复时不需要重新设计该实验。

### 11.2 算法与实验

- 导师未要求独立机器学习创新，首版不把聚类或监督学习作为必需模块。
- 如以后确需机器学习，再优先考虑可解释的无监督打法聚类或回合模式聚类。
- 任何监督模型都需要可靠标签和人工抽查。
- 数据划分必须按 Demo 分组，不能让同场回合同时进入训练和测试。
- 必须区分事件识别、战术标签和关键回合推荐的评价标准。
- 不能在规则生成标签后又用同一规则当作独立真值评估准确率。
- 所有实验数字必须来自真实运行。

### 11.3 大模型

- 等用户确认 API、网络和隐私限制后，做一次真实调用测试。
- 比较模板和 API 报告的证据覆盖率、事实矛盾数、可读性和失败率。
- 不把大模型输出质量等同于战术识别算法准确率。

### 11.4 学校材料

- 用户目前处于开题阶段。
- 尚未取得学校任务书和论文模板。
- 开题提交和答辩日期仍不清楚。
- 已起草开题论证工作稿，但未按学校模板定稿。
- 用户负责与导师确认要求、提交学校材料、授权最终 Demo 和参加最终答辩。

### 11.5 后续功能

- 公网部署：非首版必需。
- 用户账号和历史记录：非首版必需。
- Word/PDF 报告导出：等学校模板要求确定。
- 更多地图区域映射。
- 更完整的轨迹/事件交互图。

## 12. 代码注意事项

1. 所有原始 Demo、SQLite、缓存、报告输出和中间事实都由 `.gitignore` 排除。
2. 不得公开提交玩家名称、Steam ID 或个人 Demo。
3. `data/demo/demoparser_zipped_testdata.zip` 是曾下载用于检查的官方公开测试数据，但不是可直接分析的新 `.dem`，实验脚本只扫描 `*.dem`。
4. `demo.players` 会包含 `DemoRecorder`、教练和旁观者，必须过滤 `side` 为空或 `spectator` 的记录，并排除 `m_iCoachingTeam` 非零的教练。
5. 读取地点名称使用 Awpy 原始字段 `m_szLastPlaceName`，不能用普通 alias，否则是空值。
6. 事件必须考虑 `is_post_round`，不能把赛后事件误当作有效回合事件。
7. 位置采样只保留 `start_tick <= tick <= end_tick`，避免把回合间观战位置混入路线。
8. 同一 tick 多事件顺序存在歧义，报告中必须保留该限制。
9. 雷达资源版本固定为 `2000940`；缓存路径为 `data/map_assets/2000940/`。
10. Streamlit 组件使用 `width="stretch"`，不要退回已弃用的 `use_container_width=True`。
11. 现有报告 Provider 接口不应随意破坏；模板报告是无网络环境下的必用降级路径。
12. 修改指标或规则时必须提升版本号，避免旧报告与新结果无法追溯。
13. 修改数据库结构需要考虑旧数据库兼容或重新导入流程。
14. 不要把 `data/processed/84a1a4191302.sqlite` 当作通用数据库结构固定样本；最终还需要用户正式 Demo 验证。
15. 网页上传上限为 1 GB，文件采用分块写盘与流式哈希，避免整场上传文件重复占用内存。
16. `has_match_end` 只表示检测到结束事件；只有 `regulation_complete=true` 才视为达到常规终局目标。
17. Word/PDF 导出依赖已加入 `requirements.txt`。
18. 最终 MVP 已移除本机大模型入口，不要求安装 Ollama。
19. `.env` 已配置 DeepSeek 密钥、访问口令和资源限制；文件被 Git 忽略，密钥不得输出或提交。

## 13. 协作约定

- 用户计算机基础较弱，解释应尽量清楚，少用过深术语。
- 继续时优先做可执行工作，不只给概念方案。
- 每次只问当前最关键的未确认问题。
- 已经确认的问题不要重复询问。
- 不擅自扩大范围或更换技术路线。
- 学校材料提交、最终 Demo 数据授权、最终结果确认和答辩由用户本人负责。
- 有未验证内容时，明确写“拟采用”“待验证”或“证据不足”。
- 模型生成的结论必须与真实数据区分，不能伪造实验。
- 用户下次发送 **“继续昨天的项目”** 时，应先阅读本交接文件和相关文档，再从未完成任务继续。

## 14. 明日建议恢复步骤

1. 阅读本文件。
2. 检查 `README.md` 和最新实验输出。
3. 运行测试，确认环境仍可用。
4. 如用户已提供新 Demo 或授权，放入 `data/demo/` 后运行批量实验。
5. 如学校任务书或开题模板已取得，放入 `docs/school/` 后开始正式材料适配。
6. 若以上仍未提供，继续完成不依赖学校模板的核心工作：数据质量、规则敏感性、多场实验准备、论文技术章节素材。

