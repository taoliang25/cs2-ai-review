# 基于对局事件的《CS2》战术识别与赛后智能复盘系统

> 项目恢复入口：[上下文交接与恢复说明](docs/PROJECT_CONTEXT_HANDOFF.md)

本科毕业设计项目。当前已跑通单场 Demo 解析、事实指标、规则模式识别、DeepSeek 真实复盘、证据校验和网页主流程，并支持 Markdown、Word、PDF 导出；尚未开始战术识别准确率实验。

## 当前进展

- 已部署到 Streamlit Community Cloud：
  <https://cs2-tactical-review-taoliang25.streamlit.app>
- 仅在 Python 3.13 下验证。
- Awpy 3.1.1 作为主解析器。
- demoparser2 0.42.1 用于交叉校验。
- 已将一场公开测试 Demo 导入 SQLite。
- 已获得 19 份公开授权或公开测试 Demo，覆盖 7 张地图。
- 已保存真实玩家、回合、事件、逐秒位置、区域名称和队伍经济。
- 已实现首批透明行为指标和关键回合候选。
- 已实现规则版战术模式、可选大模型接口、证据校验和无网络模板降级。
- 已完成 19 场数据质量实验和 6 张完整地图的规则敏感性实验，其中 6 场达到常规完整终局；尚不能宣称任何战术识别准确率。
- 当前 MVP 不强制引入独立机器学习模型；核心为事件特征、可解释规则、证据约束大模型/模板报告。

## 文档

- [需求基线](docs/01_requirements_baseline.md)
- [Demo 验证方案](docs/02_demo_validation_plan.md)
- [技术方案](docs/03_technical_design.md)
- [数据库设计](docs/04_database_design.md)
- [页面流程、MVP 与里程碑](docs/05_page_flow_and_milestones.md)
- [首次 Demo 验证报告](docs/06_demo_validation_report.md)
- [事实层实现记录](docs/07_m1_fact_layer_report.md)
- [开题论证工作稿](docs/08_opening_proposal_outline.md)
- [项目简介](docs/09_project_introduction.md)
- [AI 复盘与证据校验](docs/10_ai_reporting_and_validation.md)
- [基线数据质量实验](docs/11_baseline_experiment.md)
- [可解释战术模式识别](docs/12_tactical_patterns.md)
- [规则阈值敏感性实验](docs/13_threshold_sensitivity.md)
- [多地图赛事 Demo 验证](docs/14_multimap_dataset_validation.md)
- [公开 Demo 数据来源与使用边界](docs/15_demo_provenance.md)
- [论文技术章节初稿](docs/16_thesis_technical_chapter_draft.md)
- [本地系统使用说明](docs/17_user_guide.md)
- [当前进度与需求确认问题](docs/18_current_status_and_decision_questions.md)
- [AI 使用方式、他人访问与报告导出](docs/19_ai_access_deployment_and_exports.md)
- [公网访问需求](docs/20_public_access_requirement.md)
- [临时公网演示操作说明](docs/21_public_demo_operations.md)
- [Streamlit Community Cloud 部署方案](docs/22_streamlit_cloud_deployment.md)

## 安装

```powershell
cd D:\毕业设计
D:\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 使用

最简单的方式是双击项目根目录下的 `start_app.cmd`。脚本会检查网页服务，
必要时在后台启动服务，并在浏览器中打开 `http://localhost:8501`。

也可以在 PowerShell 中启动本地网页：

```powershell
.\run_app.ps1
```

然后在浏览器打开 `http://localhost:8501`。

公网版本需要通过项目维护者提供的访问口令进入。

临时公网演示：

```powershell
.\start_public_demo.ps1
```

停止公网演示：

```powershell
.\stop_public_demo.ps1
```

网页默认使用本地模板报告。若要启用可选大模型，请参考
[AI 复盘与证据校验](docs/10_ai_reporting_and_validation.md)
配置环境变量；未配置或校验失败时不会阻断主流程。

查看 Demo 基础信息：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_demo.py data\demo\match.dem
```

导入 SQLite：

```powershell
.\.venv\Scripts\python.exe scripts\import_demo.py data\demo\match.dem
```

列出玩家：

```powershell
.\.venv\Scripts\python.exe scripts\analyze_player.py data\processed\<id>.sqlite --list-players
```

分析一个玩家：

```powershell
.\.venv\Scripts\python.exe scripts\analyze_player.py data\processed\<id>.sqlite --steamid <steamid> --output data\interim\facts.json
```

运行真实数据质量实验：

```powershell
.\.venv\Scripts\python.exe scripts\run_experiments.py `
  --demo-dir data\demo `
  --output-dir experiments\results
```

运行规则阈值敏感性实验：

```powershell
.\.venv\Scripts\python.exe scripts\run_sensitivity.py `
  data\processed\84a1a4191302.sqlite `
  --output-dir experiments\results
```

生成论文可用的实验汇总表：

```powershell
.\.venv\Scripts\python.exe scripts\summarize_experiment.py `
  experiments\results\experiment_20261104T092853Z.json
```

## 数据说明

原始 Demo、SQLite、中间事实和地图缓存都在 `.gitignore` 中。它们可能包含玩家标识，不应直接提交到公开仓库。当前公开测试样本也仅用于开发验证。

