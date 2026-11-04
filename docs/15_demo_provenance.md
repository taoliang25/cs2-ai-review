# 公开 Demo 数据来源与使用边界

- 记录日期：2026-11-04
- 用户授权：已明确允许筛选和下载公开 CS2 赛事 Demo 用于解析与验证
- 本地目录：`data/demo/`，已被 `.gitignore` 排除

## 1. 来源

### 1.1 LaihoE/demoparser 官方测试仓库

- 仓库：[LaihoE/demoparser](https://github.com/LaihoE/demoparser)
- 固定提交：`314a253ed51488093b5f28f648694e42b561079f`
- 文件：`src/parser/test_demo.dem`
- 仓库许可：MIT
- 用途：首轮解析能力验证。

### 1.2 skkwowee/chimera-cs2

- 数据集：[skkwowee/chimera-cs2](https://huggingface.co/datasets/skkwowee/chimera-cs2)
- 数据集卡：公开、非 gated，标注 MIT。
- 项目说明：其管线从公开 HLTV 赛事页面获取 `.dem` 并保存来源清单。
- 本轮使用：14 个文件，覆盖 Ancient、Anubis、Dust2、Inferno、Mirage、Nuke、Overpass。

已使用文件：

```text
spirit-vs-g2-m1-ancient.dem
g2-vs-aurora-m2-anubis.dem
natus-vincere-vs-aurora-m4-nuke.dem
mouz-vs-spirit-m1-dust2.dem
furia-vs-vitality-m1-overpass.dem
g2-vs-big-m1-inferno.dem
g2-vs-aurora-m1-mirage.dem
furia-vs-falcons-m3-dust2.dem
parivision-vs-vitality-m1-overpass.dem
the-mongolz-vs-natus-vincere-m1-ancient.dem
natus-vincere-vs-vitality-m2-anubis.dem
vitality-vs-natus-vincere-m1-inferno.dem
gamerlegion-vs-astralis-m2-inferno.dem
furia-vs-falcons-m2-nuke.dem
```

### 1.3 Vasy7777/cs2-demo-archive

- 数据集：[Vasy7777/cs2-demo-archive](https://huggingface.co/datasets/Vasy7777/cs2-demo-archive)
- 数据集卡：公开、非 gated，许可为 CC BY 4.0。
- 本轮使用：4 个标记为 `complete` 的 `.dem`。

已使用文件：

```text
complete_9216090725219723660_0.dem
complete_9216442468516664724_20000032.dem
complete_9216935118755906828_0.dem
complete_9217216615240319756_0.dem
```

## 2. 合规与隐私

- 只使用公开直链，不绕过登录、付费或访问控制。
- 不将原始 Demo 提交到 Git 或公网仓库。
- 公开实验输出不包含玩家名称和 Steam ID。
- 实验 JSON 中的玩家仅以 `P01`–`P10` 表示。
- 大模型调用前会进一步移除玩家标识、原始坐标和 Demo 文件信息。
- 数据集卡许可不等于对第三方赛事内容作法律结论；正式公开发布系统或打包 Demo 前仍需由用户和导师确认学校与平台要求。

## 3. 文件校验

每个 Demo 的 SHA-256、原始文件名、地图、回合、玩家索引、解析耗时和字段质量均记录在：

`experiments/results/experiment_20261104T095547Z.json`

后续重新运行时，以每次生成的实验 JSON 为准，并保留运行标识和环境版本。

## 4. 完整性判定

- `has_match_end=true`：观察到 `cs_win_panel_match`。
- `regulation_complete=true`：同时观察到比赛结束，且任一方回合胜场达到 13。
- 文件名为 `complete` 不能单独作为完整比赛依据。
- 只有 `regulation_complete=true` 的记录进入完整对局指标分布。

