## report_v7.5

基于 report_v7_final 的变更：

1. 将学生类型由82调整为92 每个joint各新增2个

### 运行前需修改全局配置

`config/objective_config.json` 中：

```json
"late_slot_penalty_weight": 0
```

### 运行命令

```bash
python3 main.py --instance report_v7_final
```
