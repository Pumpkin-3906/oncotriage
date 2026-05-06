# Task M3+M4 — 规则引擎核心 + 单元测试

> 这是一个独立任务卡。无需查看对话历史，只读以下文件即可上手。

## 目标

让 `backend/app/services/rule_engine.py` 中的 `_matches()` 和 `_to_match()`
真正能跑，并写单元测试覆盖关键 case。其余架构（Plan D 评估全部、Risk 排序、
EvaluationResult 数据结构）已经实现，**不要动**。

## 背景（为什么这件事重要）

规则引擎是整个 MVP 决策环节的唯一权威。所有"用户输入哪种症状 → 系统返回什么风险"
的逻辑都在这里。任何 bug 都会直接影响临床判断，所以**正确性 > 简洁性 > 性能**。

## 必读（按顺序）

1. `docs/MVP_PLAN.md` — 整个 MVP 范围 + 多 agent 协作约定（§5.3 不要做的事）
2. `docs/DESIGN.md` §5 — 感知-决策-执行-学习闭环，特别是 §5.② 决策环节
3. `docs/DESIGN.md` §3 — 关键架构决策表，决策 #7 是 Plan D
4. `docs/rules/rules.yaml` — 完整规则集（12 条规则 + 4 模板）
5. `backend/app/services/rule_engine.py` — 你要改的文件，已有 Plan D 框架
6. `backend/app/schemas/assessment.py` — `ParsedSymptoms` / `SymptomItem` 类型定义
7. `backend/app/rules/seed_dictionary.py` — 12 条字典（理解症状值的形态）

## 范围

### 你要实现的

#### 1. `_matches(rule, parsed, trends) -> bool`
判断一条规则的 `when` 子句是否被命中。需支持：

**when 子句结构**：
```yaml
when:
  all_of: [...]      # 全部子条件满足
  any_of: [...]      # 任一子条件满足
  always: true       # 兜底（永远匹配）
```

**子条件结构**：
```yaml
- symptom: fever
  numeric_value: { gte: 38.3 }       # 数值比较
  duration_hours: { gte: 1 }
  ctcae_grade: { gte: 2 }
  categorical_value: { in: [moderate, severe] }
- context:
    days_since_chemo: { lte: 14 }    # 上下文字段
- trend:                              # Advanced 时序（trends 参数为 None 时跳过）
    symptom: fatigue
    window_days: 7
    trend_direction: increasing
    current_grade: { gte: 2 }
```

**操作符**（值约束的 dict 形式）：
- `{ gte: X }` 大于等于
- `{ gt: X }` 严格大于
- `{ lte: X }` 小于等于
- `{ lt: X }` 严格小于
- `{ eq: X }` 等于
- `{ in: [X, Y, Z] }` 在列表中

字段如果直接是值（不是 dict），视为 `eq` 简写。

#### 2. `_to_match(rule, parsed, trends) -> RuleMatch`
打包成 `RuleMatch`。重点：填好 `matched_fields`（命中时具体值），用于审计：
```python
matched_fields = {
    "symptom_fever_temperature_c": 38.5,
    "context_days_since_chemo": 3,
}
```

#### 3. 单元测试 `backend/tests/test_rule_engine.py`
**必须覆盖以下 6 个 case**：

| Case | 输入 | 期望命中 | 期望 risk |
|---|---|---|---|
| 化疗后高烧 | fever 38.5℃ + days_since_chemo=3 | R001 | high |
| 化疗后持续低烧 | fever 38.1℃ duration 2h + days_since_chemo=5 | R002 | high |
| 严重腹泻 | severe_diarrhea ctcae_grade=3 | R004 | high |
| 中度手足综合征 | hand_foot_skin_reaction ctcae_grade=2 | R010 | medium |
| 轻度恶心 | nausea ctcae_grade=1 | R020 | low |
| 完全空输入 | symptoms=[] | R999 兜底 | medium |
| **多规则同时命中**（Plan D 关键）| fever 38.5℃ + days_since_chemo=3 + nausea grade=1 | R001 主 + R020 也在 all_matches | high (取最高) |

每个 case 都断言：
- `result.final_risk_level`
- `result.primary.rule_id`
- 多规则 case 还要断 `len(result.all_matches) >= 2`

### 不要做的

- ❌ **不要改 `evaluate()` 主流程** — Plan D 已在
- ❌ **不要改 `EvaluationResult` 数据结构**
- ❌ **不要改 `rules.yaml`** — 阈值是临床决策，碰它要走临床委员会
- ❌ **不要引入新依赖** — pyyaml 已经够用
- ❌ **不要 catch Exception 然后 pass** — 让真正的 bug 暴露
- ❌ **不要写性能优化**（缓存、提前 return 之外的）— MVP 12 条规则不需要
- ❌ **不要写 Advanced 时序的复杂逻辑** — `requires_feature: timeseries` 的规则在 trends=None 时已被 evaluate() 跳过；你只要保证 _matches() 在 trends 非 None 时能简单求 trend 子句即可

## Definition of Done

```
[ ] _matches() 实现 all_of / any_of / always
[ ] _eval_clause() 或类似辅助函数处理 symptom / context / trend 三类子条件
[ ] _to_match() 填充 matched_fields 用于审计
[ ] tests/test_rule_engine.py 覆盖上述 7 个 case
[ ] cd backend && .venv/bin/python -m pytest tests/ -v 全绿（包括之前已有的 3 个测试）
[ ] 代码总行数 ≤ 150 行（rule_engine.py 增量）
```

## 验收命令

```bash
cd backend
source .venv/bin/activate

# 1. 测试全绿
pytest tests/ -v

# 2. 手工验证：rules.yaml 实际跑通
python -c "
from app.rules.loader import load_rules
from app.services.rule_engine import RuleEngine
from app.schemas.assessment import ParsedSymptoms, SymptomItem
from app.config import settings

bundle = load_rules(settings.rules_path)
engine = RuleEngine(bundle.rules, bundle.engine_version)

# 高烧 + 化疗后 → R001 high
parsed = ParsedSymptoms(
    symptoms=[SymptomItem(symptom_id='fever', numeric_value=38.5)],
    context={'days_since_chemo': 3},
)
result = engine.evaluate(parsed)
assert result.final_risk_level == 'high'
assert result.primary.rule_id.startswith('R001')
print('✓ Smoke test passed:', result.primary.rule_id)
"
```

## 提交规范

- **PR 标题**：`[M3+M4] 规则引擎 _matches() 实现 + 单元测试`
- **Commit 数**：1-2 个（实现 + 测试 可分可合）
- **PR body** 必须列：
  - 改动文件
  - 7 个 case 的运行结果（粘贴 pytest -v 输出）
  - 总行数

## 设计提示（不强制）

`_matches()` 推荐拆三层：
```
_matches(rule, parsed, trends)
  └─ _eval_clause(clause_dict, parsed, trends)         # 派发
       ├─ _eval_symptom_clause(clause, parsed)         # 处理 symptom: ...
       ├─ _eval_context_clause(clause, parsed)         # 处理 context: ...
       └─ _eval_trend_clause(clause, trends)           # 处理 trend: ...
            └─ _eval_value_constraint(actual, spec)    # 处理 {gte: X}/{in: [...]}
```

`_eval_value_constraint` 是最底层：传入 actual=38.5, spec={'gte': 38.3} 返回 True。
建议它能处理**所有 6 种操作符** + **直接值简写**（spec 不是 dict 时视为 eq）。

## 卡住时

- **rules.yaml 不确定字段意义**：看 R001-R022 各自的注释和 rationale
- **ParsedSymptoms 不知道哪些字段会有值**：看 `symptom_dictionary` 的 value_type
  （numeric → numeric_value 有值；categorical → ctcae_grade 或 categorical_value）
- **Plan D 不理解**：看 `evaluate()` 里 `final_risk = max(... RISK_RANK ...)`
