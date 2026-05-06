# Task M3+M4 — 决策层：规则引擎 + 完整性检查 + 单元测试

> 这是一个独立任务卡。无需查看对话历史，只读以下文件即可上手。
> 版本: v2 (2026-05-07)，新增 CompletenessChecker 部分

## 目标

实现决策层的两个独立组件 + 它们的单元测试：

1. **规则引擎核心** — `services/rule_engine.py` 中 `_matches()` 和 `_to_match()`
2. **完整性检查器** — 新建 `services/completeness_checker.py`，检查抽到的症状是否
   带齐了"足以判断"的字段（如 fever 必须带 numeric_value）

其余架构（Plan D 评估全部、Risk 排序、EvaluationResult 数据结构）已经实现，
**不要动**。

## 背景（为什么这件事重要）

### 为什么需要规则引擎（不用 LLM 直接判断）

医疗 CDSS 的硬约束：判断必须**确定性 + 可审计 + 可枚举**。LLM 即使 temp=0 也有
变异，且无法对它的行为做单元测试。详见 `docs/DESIGN.md` §3 决策 #1。

### 为什么需要 CompletenessChecker

LLM 抽取出的 `ParsedSymptoms` 不一定信息完整：
- 用户说"我发烧了"但没说几度 → fever 缺 `numeric_value`
- 用户说"恶心"但没量化严重程度 → nausea 缺 `ctcae_grade`

直接送进规则引擎的后果：所有需要那个字段的规则会 **silently 不匹配**，最后命中
R999 兜底"中风险，联系团队"。**这是临床上不优雅的失败** — 用户实际有具体症状，
我们却模糊处理。

正确做法：**显式检查 → 显式信号给 Orchestrator → 由它决定追问 / 兜底**。

为什么不用 LLM 判断完整性？三条原则（同上）：判断"够不够"是结构化问题，规则查表
毫秒搞定 + 可审计 + 可枚举。

## 必读（按顺序）

1. `docs/MVP_PLAN.md` — 整个 MVP 范围 + 多 agent 协作约定
2. `docs/DESIGN.md` §5 — 感知-决策-执行-学习闭环
3. `docs/DESIGN.md` §3 — 关键架构决策表（**决策 #1 LLM=翻译/规则=判官，决策 #7 Plan D**）
4. `docs/rules/rules.yaml` — 完整规则集（12 条规则 + 4 模板）
5. `backend/app/services/rule_engine.py` — 已有 Plan D 框架，你要补 `_matches()` / `_to_match()`
6. `backend/app/schemas/assessment.py` — `ParsedSymptoms` / `SymptomItem` 类型定义
7. `backend/app/rules/seed_dictionary.py` — 12 条字典；CompletenessChecker 的判断标准就来自每条字典的 `value_type`

---

## Part A — 规则引擎

### A.1 `_matches(rule, parsed, trends) -> bool`

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
- trend:                              # Advanced 时序（trends=None 时跳过）
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

### A.2 `_to_match(rule, parsed, trends) -> RuleMatch`

打包成 `RuleMatch`。重点：填好 `matched_fields`（命中时具体值），用于审计：
```python
matched_fields = {
    "symptom_fever_numeric_value": 38.5,
    "context_days_since_chemo": 3,
}
```

---

## Part B — CompletenessChecker（新文件）

### B.1 创建 `backend/app/services/completeness_checker.py`

**数据结构**：

```python
from dataclasses import dataclass

@dataclass
class MissingSlot:
    symptom_id: str
    missing_fields: list[str]  # 缺这些里任意一个有值就 OK；都缺才视为 incomplete

@dataclass
class CompletenessResult:
    is_complete: bool
    missing_slots: list[MissingSlot]
```

**判断规则**（基于字典的 `value_type`）：

| value_type | 至少要有以下字段之一 |
|---|---|
| numeric | `numeric_value` |
| categorical | `ctcae_grade` 或 `categorical_value` |
| binary | （存在即可，无字段要求）|

**边界情况**：
- 空 symptoms 列表 → `is_complete=True`（让规则引擎 R999 兜底处理）
- symptom_id 不在字典里 → 列入 missing_slots，`missing_fields=["unknown_symptom_in_dictionary"]`

**API**：

```python
class CompletenessChecker:
    def __init__(self, dictionary: list[dict]):
        # dictionary 是 seed_dictionary.SYMPTOMS 形态，含 id / value_type 等
        ...

    def check(self, parsed: ParsedSymptoms) -> CompletenessResult:
        ...
```

### B.2 单元测试 `backend/tests/test_completeness_checker.py`

**至少覆盖以下 8 个 case**：

| Case | 输入 | 期望 |
|---|---|---|
| numeric 字段全 | fever, numeric_value=38.5 | complete |
| numeric 字段缺 | fever, 没 numeric_value | incomplete, missing=["numeric_value"] |
| categorical 用 grade | nausea, ctcae_grade=2 | complete |
| categorical 用 categorical_value | nausea, categorical_value="moderate" | complete |
| categorical 都没 | nausea, 两个都 None | incomplete |
| 未知 symptom_id | symptom_id="diabetes" | incomplete, missing=["unknown_symptom_in_dictionary"] |
| 空 symptoms | symptoms=[] | complete |
| 混合 | fever 完整 + nausea 缺信息 | incomplete, len(missing_slots)==1 |

---

## Part C — 规则引擎单元测试

### `backend/tests/test_rule_engine.py`

**必须覆盖以下 7 个 case**：

| Case | 输入 | 期望命中 | 期望 risk |
|---|---|---|---|
| 化疗后高烧 | fever 38.5℃ + days_since_chemo=3 | R001 | high |
| 化疗后持续低烧 | fever 38.1℃ duration 2h + days_since_chemo=5 | R002 | high |
| 严重腹泻 | severe_diarrhea ctcae_grade=3 | R004 | high |
| 中度手足综合征 | hand_foot_skin_reaction ctcae_grade=2 | R010 | medium |
| 轻度恶心 | nausea ctcae_grade=1 | R020 | low |
| 完全空输入 | symptoms=[] | R999 兜底 | medium |
| **多规则同时命中**（Plan D 关键）| fever 38.5℃ + days_since_chemo=3 + nausea grade=1 | primary=R001 + len(all_matches) ≥ 2 | high |

每个 case 都断言：
- `result.final_risk_level`
- `result.primary.rule_id`
- 多规则 case 还要断 `len(result.all_matches) >= 2`

---

## 不要做的

- ❌ **不要让 CompletenessChecker 修改 ParsedSymptoms** — 它只检查，不改
- ❌ **不要让 CompletenessChecker 调 LLM** — 纯规则查表
- ❌ **不要写"自动追问"逻辑** — 那是 Orchestrator (M6) 的事，本任务只产出 CompletenessResult
- ❌ **不要改 `evaluate()` 主流程** — Plan D 已在
- ❌ **不要改 `EvaluationResult` / `ParsedSymptoms` 数据结构**
- ❌ **不要改 `rules.yaml`** — 阈值是临床决策，碰它要走临床委员会
- ❌ **不要引入新依赖** — pyyaml 已经够用
- ❌ **不要 catch Exception 然后 pass** — 让真正的 bug 暴露
- ❌ **不要写性能优化**（缓存、提前 return 之外的）— MVP 12 条规则不需要
- ❌ **不要写 Advanced 时序的复杂逻辑** — `requires_feature: timeseries` 的规则在 trends=None 时已被 evaluate() 跳过

## Definition of Done

```
规则引擎:
[ ] _matches() 实现 all_of / any_of / always
[ ] _eval_clause() 或类似辅助函数处理 symptom / context / trend 三类子条件
[ ] _to_match() 填充 matched_fields 用于审计

完整性检查:
[ ] services/completeness_checker.py 含 CompletenessChecker 类
[ ] 处理 numeric / categorical / binary 三种 value_type
[ ] 处理未知 symptom_id 与空列表两种边界

测试:
[ ] tests/test_rule_engine.py 覆盖 7 个 case
[ ] tests/test_completeness_checker.py 覆盖 8 个 case
[ ] cd backend && .venv/bin/python -m pytest tests/ -v 全绿（含之前 3 个测试）

LOC 预算:
[ ] rule_engine.py 增量 ≤ 100 行
[ ] completeness_checker.py ≤ 100 行
[ ] 两份测试合计 ≤ 250 行
```

## 验收命令

```bash
cd backend
source .venv/bin/activate

# 1. 测试全绿（应有 3+7+8 = 18 个测试通过）
pytest tests/ -v

# 2. 手工：规则引擎 smoke
python -c "
from app.rules.loader import load_rules
from app.services.rule_engine import RuleEngine
from app.schemas.assessment import ParsedSymptoms, SymptomItem
from app.config import settings

bundle = load_rules(settings.rules_path)
engine = RuleEngine(bundle.rules, bundle.engine_version)

parsed = ParsedSymptoms(
    symptoms=[SymptomItem(symptom_id='fever', numeric_value=38.5)],
    context={'days_since_chemo': 3},
)
result = engine.evaluate(parsed)
assert result.final_risk_level == 'high'
assert result.primary.rule_id.startswith('R001')
print('✓ Rule engine smoke:', result.primary.rule_id)
"

# 3. 手工：CompletenessChecker smoke
python -c "
from app.services.completeness_checker import CompletenessChecker
from app.rules.seed_dictionary import SYMPTOMS
from app.schemas.assessment import ParsedSymptoms, SymptomItem

checker = CompletenessChecker(SYMPTOMS)

# 完整: fever 带温度
r1 = checker.check(ParsedSymptoms(
    symptoms=[SymptomItem(symptom_id='fever', numeric_value=38.5)], context={}
))
assert r1.is_complete, 'fever with temp should be complete'

# 不完整: fever 没温度
r2 = checker.check(ParsedSymptoms(
    symptoms=[SymptomItem(symptom_id='fever')], context={}
))
assert not r2.is_complete
assert r2.missing_slots[0].symptom_id == 'fever'
assert 'numeric_value' in r2.missing_slots[0].missing_fields
print('✓ Completeness checker smoke passed')
"
```

## 提交规范

- **PR 标题**：`[M3+M4] 决策层：规则引擎 + CompletenessChecker + 单元测试`
- **Commit 数**：2-3 个（建议拆：rule_engine / completeness_checker / tests）
- **PR body** 必须列：
  - 改动文件
  - 7+8 = 15 个新测试 case 的运行结果（粘贴 pytest -v 输出）
  - 每个文件的 LOC

## 设计提示（不强制）

### 规则引擎 `_matches()` 推荐拆三层

```
_matches(rule, parsed, trends)
  └─ _eval_clause(clause_dict, parsed, trends)         # 派发
       ├─ _eval_symptom_clause(clause, parsed)         # 处理 symptom: ...
       ├─ _eval_context_clause(clause, parsed)         # 处理 context: ...
       └─ _eval_trend_clause(clause, trends)           # 处理 trend: ...
            └─ _eval_value_constraint(actual, spec)    # 处理 {gte: X}/{in: [...]}
```

`_eval_value_constraint(actual=38.5, spec={'gte': 38.3})` 返回 True。
建议它能处理**所有 6 种操作符** + **直接值简写**（spec 不是 dict 时视为 eq）。

### CompletenessChecker 实现思路

```python
# 把字典索引化，O(1) 查找
self.dictionary_index = {s["id"]: s for s in dictionary}

# 每种 value_type 对应"满足条件之一即可"的字段集合
REQUIRED_BY_VALUE_TYPE = {
    "numeric":     [["numeric_value"]],
    "categorical": [["ctcae_grade"], ["categorical_value"]],  # 任一组满足即可
    "binary":      [],
}

# 对每个 symptom：找到 value_type → 检查是否满足任一组要求
```

## 卡住时

- **rules.yaml 不确定字段意义**：看 R001-R022 各自的注释和 rationale
- **ParsedSymptoms 哪些字段会有值**：看 `seed_dictionary.SYMPTOMS` 的 value_type
  （numeric → numeric_value 有值；categorical → ctcae_grade 或 categorical_value）
- **Plan D 不理解**：看 `evaluate()` 里 `final_risk = max(... RISK_RANK ...)`
- **CompletenessChecker 不知道为啥要做**：看本卡片"背景"段落 + DESIGN.md §3 决策 #1
