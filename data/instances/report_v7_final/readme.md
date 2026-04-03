## report_v7_final

基于 report_v6_more_choice 的变更：

1. **去掉午休限制**：`lunch_break_no_class` 从 `true` → `false`，12:00–13:00 时段允许排课。
2. **去掉16:00之后的 late_slot_penalty**：运行前需将 `config/objective_config.json` 中 `late_slot_penalty_weight` 设为 `0`。
3. **早九改为五天里有两天有**：去掉 `no_first_period_prefixes: ["MATH"]`（不再全面禁止MATH 9am），改用 `no_first_period_days: [0, 2, 4]`（Mon/Wed/Fri 禁止所有非OUTSIDE课程9am排课），Tue/Thu 可以有9am课。

### 运行前需修改全局配置

`config/objective_config.json` 中：
```json
"late_slot_penalty_weight": 0
```

### 运行命令
```bash
python3 main.py --instance report_v7_final
```
