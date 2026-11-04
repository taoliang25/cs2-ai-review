# 多地图赛事 Demo 验证

- 验证日期：2026-11-04
- 公开实验输出：[19 场实验 JSON](../experiments/results/experiment_20261104T095547Z.json)、[匿名玩家指标 CSV](../experiments/results/player_metrics_20261104T095547Z.csv)、[论文用汇总表](../experiments/results/experiment_20261104T095547Z_summary.md)
- 原始 Demo：仅保存在本地 `data/demo/`，不提交 Git

## 1. 数据来源

本轮获得用户明确授权后，使用了两组公开 CS2 数据：

1. [skkwowee/chimera-cs2](https://huggingface.co/datasets/skkwowee/chimera-cs2)
   - 公开、无需登录、数据集卡标注 MIT。
   - 说明记录其来源为公开 HLTV 赛事 Demo。
   - 本轮从该数据集下载 14 个不同地图与长度的文件。
2. [Vasy7777/cs2-demo-archive](https://huggingface.co/datasets/Vasy7777/cs2-demo-archive)
   - 公开、无需登录、许可为 CC BY 4.0。
   - 本轮下载 4 个 `.dem`。
3. 原先的 LaihoE/demoparser 官方测试 Demo 继续保留。

所有下载均通过公开直链完成，没有绕过登录、付费或其他访问控制。

## 2. 验证规模

当前 `data/demo/` 共 19 个 `.dem`，约 6.92 GB。

| 项目 | 结果 |
|---|---:|
| Demo 文件 | 19 |
| 地图 | 7 |
| 地图列表 | Ancient、Anubis、Dust2、Inferno、Mirage、Nuke、Overpass |
| 选手-对局记录 | 190 |
| 全部唯一参赛玩家 | 114 |
| 完整对局唯一参赛玩家 | 45 |
| 完整对局选手-对局记录 | 60 |
| 玩家指标记录 | 3,610 |
| 基础结构检查全部通过 | 19 / 19 |
| 达到常规赛目标得分 | 6 |

常规完整样本：

| 地图 | 回合 | 逐秒位置采样 | 解析耗时 |
|---|---:|---:|---:|
| Nuke | 42 | 44,232 | 31.54 秒 |
| Dust2 | 36 | 39,877 | 28.02 秒 |
| Mirage | 23 | 27,689 | 18.37 秒 |
| Inferno | 30 | 36,004 | 22.70 秒 |
| Anubis | 24 | 29,157 | 16.88 秒 |
| Ancient | 24 | 23,465 | 15.44 秒 |

完整样本的 SHA-256：

- Nuke：`95594d8c20e415f5ad489f9a2ffe6f017320af4527a36fa472ea7ebcdc6d6de3`
- Dust2：`5eefa107b659e1e737c243138e64cf00376582c5296eb7ee2f1f00149703f756`
- Mirage：`3d2d9d8f1e7556bc4850d5c68ebd1948e29a96fb3a4cf2cd458739356e22d72f`
- Inferno：`b594d745e3dd5e3592329c25d4c94efe59fbbc86c51aa0a53827d65714d39f8d`
- Anubis：`e2feb7a9ea5a2b28386f041e9b9eca9bab842372c2b44b1a792db196b1de0990`
- Ancient：`21351a60746307807935e6e2ce799d51fe366daaf92c7538195daaf72561fec1`

## 3. 本轮修复

职业赛事 Demo 包含教练和旁观者。原玩家过滤只检查 `side` 非空，会把教练误算为参赛者。现已改为：

- 只保留 `terrorist` 与 `counter-terrorist`。
- 排除 `m_iCoachingTeam` 非零的教练。
- 排除 `DemoRecorder` 和 `spectator`。
- 对 16 名原始记录的 Mirage 样本，最终正确保留 10 名选手。

同时新增两个完整性字段：

- `has_match_end`：是否检测到 `cs_win_panel_match`。
- `regulation_complete`：比赛有结束事件，且任一方回合胜场达到 13。

只有 `regulation_complete=true` 的样本才视为完整常规终局。投降、片段和未检测到比赛结束的文件仍可用于兼容性测试，但不会被写成完整比赛实验。

## 4. 当前能支持的结论

- 主解析链路可以在 7 张地图的真实赛事 Demo 上运行。
- 玩家、教练和旁观者过滤规则得到真实赛事数据验证。
- SQLite、位置、地点、经济和核心事件检查在通过过滤后的 190 条
  选手-对局记录上全部成立；全部数据来自 114 名唯一选手，
  其中完整终局部分来自 45 名唯一选手。
- 系统对 23–42 回合的完整对局均可解析。

## 5. 不能支持的结论

- 19 个文件并不等于 19 场完整比赛，其中只有 6 场达到常规终局条件。
- 这些是职业赛事样本，不能替代普通玩家自己的 Demo。
- 目前没有人工战术标签，不能计算战术识别准确率。
- 当前 10 名玩家筛选规则尚未覆盖所有可能的比赛平台、断线重连和替补情况。

## 6. 下一步

1. 再补充至少 5–10 份完整、不同地图、不同胜负走势的 Demo。
2. 对短片段和完整对局分层统计，不混合报告。
3. 在完整对局上重新运行距离和早期路线敏感性实验。
4. 获取用户本人真实 Demo，验证普通玩家场景。
5. 在导师确认算法要求后，再建立人工标签和多场训练实验。

