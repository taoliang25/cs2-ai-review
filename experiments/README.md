# 实验记录

本目录保存可公开、去标识化的真实运行结果。实验使用 `data/demo/` 中的本地 Demo 重新解析，并在临时数据库中对全部有效玩家运行指标计算。

## 运行

```powershell
.\.venv\Scripts\python.exe scripts\run_experiments.py `
  --demo-dir data\demo `
  --output-dir experiments\results
```

## 输出

- `experiment_<UTC时间>.json`：环境版本、Demo 哈希、解析耗时、数据质量检查和玩家级汇总。
- `player_metrics_<UTC时间>.csv`：匿名玩家 `P01...` 的真实指标值。

实验输出不包含玩家名称或 Steam ID。原始 Demo、临时 SQLite 和中间数据保留在本地忽略目录，不提交到 Git。

## 当前能证明与不能证明的内容

能够证明：

- 代码可以在真实 Demo 上运行。
- 文件能够被解析和规范化。
- 数据库约束、位置字段、地点名称和经济记录是否完整。
- 所有有效玩家都能完成指标计算。
- 解析与指标计算的真实耗时。

不能证明：

- 战术分类准确率。
- 模型对未见 Demo 的泛化能力。
- 玩家的长期稳定打法。
- 大模型生成内容的事实准确率。

只有在加入更多真实、合规 Demo 和明确标签后，才能开展上述评价实验。

