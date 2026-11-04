# CS2 Demo 实验汇总

- 实验运行：`20261104T092853Z`
- Python：`3.13.5`
- Awpy：`3.1.1`
- demoparser2：`0.42.1`
- Demo 数量：15
- 达到常规完整终局：3

> 本文件是真实运行的描述性汇总，不是战术识别准确率。

## 1. 每场数据质量

| 地图 | 回合 | 比赛结束 | 常规终局 | 玩家 | 位置采样 | 解析秒数 | 质量警告 |
|---|---:|:---:|:---:|---:|---:|---:|---|
| de_dust2 | 16 | 是 | 否 | 10 | 9557 | 5.51 | regulation_round_target_reached |
| de_dust2 | 18 | 是 | 否 | 10 | 8417 | 5.58 | regulation_round_target_reached |
| de_dust2 | 19 | 是 | 否 | 10 | 9178 | 5.65 | regulation_round_target_reached |
| de_dust2 | 19 | 是 | 否 | 10 | 11507 | 7.16 | regulation_round_target_reached |
| de_nuke | 42 | 是 | 是 | 10 | 44232 | 31.54 | 无 |
| de_dust2 | 36 | 是 | 是 | 10 | 39877 | 28.02 | 无 |
| de_overpass | 12 | 否 | 否 | 10 | 14106 | 8.51 | match_end_event, regulation_round_target_reached |
| de_mirage | 23 | 是 | 是 | 10 | 27689 | 18.37 | 无 |
| de_anubis | 4 | 是 | 否 | 10 | 4837 | 4.17 | regulation_round_target_reached |
| de_inferno | 16 | 是 | 否 | 10 | 17496 | 11.83 | regulation_round_target_reached |
| de_dust2 | 16 | 是 | 否 | 10 | 15371 | 11.05 | regulation_round_target_reached |
| de_nuke | 9 | 是 | 否 | 10 | 9510 | 6.26 | regulation_round_target_reached |
| de_overpass | 23 | 是 | 否 | 10 | 26110 | 17.08 | regulation_round_target_reached |
| de_mirage | 10 | 是 | 否 | 10 | 6536 | 2.94 | regulation_round_target_reached |
| de_ancient | 4 | 否 | 否 | 10 | 5664 | 4.13 | match_end_event, regulation_round_target_reached |

## 2. 汇总

- 覆盖地图：de_ancient, de_anubis, de_dust2, de_inferno, de_mirage, de_nuke, de_overpass。
- 有效参赛玩家：150。
- 常规完整终局地图：de_dust2, de_mirage, de_nuke。
- 片段或提前结束样本：12。

## 3. 完整对局的玩家指标分布

| 指标 | 样本数 | 均值 | 中位数 | 最小值 | 最大值 |
|---|---:|---:|---:|---:|---:|
| 击杀 | 30 | 22.633 | 24.000 | 8.000 | 43.000 |
| 死亡 | 30 | 22.767 | 25.000 | 10.000 | 35.000 |
| 首轮交火参与率 | 30 | 0.194 | 0.192 | 0.071 | 0.435 |
| 贴近队友比例 | 30 | 0.638 | 0.647 | 0.541 | 0.735 |
| 远离队友比例 | 30 | 0.213 | 0.201 | 0.093 | 0.331 |
| 队友接敌时就近比例 | 30 | 0.364 | 0.382 | 0.143 | 0.634 |
| 就近后 5 秒响应率 | 30 | 0.215 | 0.200 | 0.000 | 0.667 |
| 最后存活回合数 | 30 | 3.300 | 3.000 | 0.000 | 9.000 |
| 可观测道具效果回合数 | 30 | 17.567 | 17.000 | 10.000 | 29.000 |

## 4. 解释边界

- 统计单位是玩家，但玩家来自较少的完整 Demo，不能当作总体分布。
- 职业赛事选手与普通玩家存在明显水平差异，不能代表目标用户群体。
- 没有人工行为标签，因此没有分类准确率。
- 片段可以用来说明解析兼容性，不应与完整对局混合做比赛结局分析。
