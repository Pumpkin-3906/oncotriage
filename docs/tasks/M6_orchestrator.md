# Task M6 — Orchestrator（编排器）

> 这是一个独立任务卡。无需查看对话历史，只读以下文件即可上手。

## 目标

实现 `services/orchestrator.py` 的 `Orchestrator.run()`，把整个评估流程串起来：
**幂等检查 → LLM 抽取 → 完整性检查 → 写库（Tx1）→ 规则评估 → 写库（Tx2）→ 返回结果**。

外加补全本流程必需的 SQLAlchemy 模型（symptom_observation / advice / evidence）。

## 背景

Orchestrator 是 MVP 的"黑色幕后"——它把已经实现好的 LLM Extractor、CompletenessChecker、
RuleEngine 三个独立组件串起来，加上数据持久化和幂等保护，对外提供单一入口。

事务策略是 **Plan C（两阶段独立事务）**（见 `DESIGN.md` §3 决策 #6）：
- **Tx1**：抽取 + 写 assessment + symptom_observation（`decision_status='pending'`）
- **Tx2**：评估 + 写 evidence + advice + 更新 status 为 `'completed'`

→ Tx2 失败也不会让"已抽取症状"丢，临床上很重要。

幂等性是 **(user_id, idempotency_key) UNIQUE 索引**（见 `DESIGN.md` §15）：
- 同 key 第二次提交直接返回首次结果，**不重新调 LLM**
- 防重复点提交污染 trend 分析

## 必读（按顺序）

1. `docs/MVP_PLAN.md` — MVP 范围 + 协作约定
2. `docs/DESIGN.md` §4 — 主路径数据流（含完整时序图）
3. `docs/DESIGN.md` §15 — 幂等性与一致性
4. `docs/DESIGN.md` §3 — 关键架构决策（**特别是 #6 双事务、#9 幂等键**）
5. `backend/app/services/orchestrator.py` — 你要改的文件，已有详细 stub 注释
6. `backend/app/services/llm_extractor.py` — 已实现，调用方式参考
7. `backend/app/services/rule_engine.py` — M3 完成后已实现
8. `backend/app/services/completeness_checker.py` — M3 完成后已实现
9. `backend/app/schemas/assessment.py` — `AssessmentRequest` / `AssessmentResult` / `Advice` / `AuditInfo` / `MatchedRule`
10. `backend/app/models/assessment.py` + `user.py` — 现有模型参考
11. `docs/data_model/schema.sql` — 完整 schema，特别看 symptom_observation / advice / evidence

## 范围

### Part A — 补全 SQLAlchemy 模型

新建以下 3 个文件（参考 `models/assessment.py` 风格）：

#### A.1 `backend/app/models/symptom_observation.py`

字段全部对应 `schema.sql` 的 symptom_observation 表。注意：
- `numeric_value` 用 `Numeric(8, 2)`
- `ctcae_grade` 是 `SmallInteger` 加 CheckConstraint(1-5)
- 索引由 schema.sql 已建，模型里加 `__table_args__` 是可选（避免 alembic 冲突，可不加）

#### A.2 `backend/app/models/advice.py`
对应 `advice` 表。

#### A.3 `backend/app/models/evidence.py`
对应 `evidence` 表，`matched_fields` 是 JSONB。

更新 `backend/app/models/__init__.py` 导出新模型。

### Part B — Orchestrator 核心实现

#### B.1 改写 `Orchestrator.run()`

```python
def run(self, req: AssessmentRequest) -> AssessmentResult:
    # 0. 幂等检查
    existing = self._lookup_existing(req.user_id, req.idempotency_key)
    if existing:
        return self._build_result_from_db(existing.id)

    # 1. 加载字典（每次调用查一次 DB；后续可加缓存）
    dictionary = self._load_dictionary()

    # 2. Tx1: LLM 抽取 + 写 assessment + symptom_observation
    parsed = self._extract_with_fallback(req)
    assessment = self._persist_extraction(req, parsed)  # decision_status='pending'

    # 3. 完整性检查（MVP: 仅记日志，不阻塞）
    completeness = CompletenessChecker(dictionary).check(parsed)
    if not completeness.is_complete:
        # MVP: 仅 print/log，不返回 ClarificationNeeded
        # v2 时改为返回特殊响应让前端追问
        print(f"[completeness] incomplete: {completeness.missing_slots}")

    # 4. Tx2: 规则评估 + 写 evidence + advice + 更新状态
    try:
        eval_result = self._evaluate_rules(parsed)
        self._persist_decision(assessment, eval_result)
    except Exception:
        # 决策失败：标记 status=failed，但 Tx1 的数据保留
        self._mark_decision_failed(assessment.id)
        raise

    # 5. 组装并返回 AssessmentResult
    return self._build_result(assessment, eval_result, parsed)
```

#### B.2 关键辅助方法

下面这些方法**不必严格同名**，但功能必备：

| 方法 | 职责 |
|---|---|
| `_lookup_existing(user_id, idempotency_key)` | 查 assessment 表唯一索引 |
| `_load_dictionary()` | `SELECT * FROM symptom_dictionary` 转成 list[dict] |
| `_extract_with_fallback(req)` | LLM 抽取，失败抛 `LLMExtractionError` 给上层 |
| `_persist_extraction(req, parsed)` | Tx1: 写 assessment + N 条 symptom_observation |
| `_evaluate_rules(parsed)` | 调 `RuleEngine.evaluate(parsed)` 返回 `EvaluationResult` |
| `_persist_decision(assessment, result)` | Tx2: 写 evidence + advice，更新 assessment.risk_level / decision_status |
| `_build_result(...)` | 组装 `AssessmentResult` Pydantic 对象返回 |

#### B.3 错误传播规则

| 错误类型 | Orchestrator 行为 |
|---|---|
| `LLMExtractionError` | 不写库；直接 raise（M7 接住返回 422） |
| Tx1 数据库错误 | 不写库；raise（M7 返回 500） |
| 规则引擎异常 | Tx1 已 commit；mark `decision_status='failed'`；raise |
| Tx2 数据库错误 | mark `decision_status='failed'`；raise |

#### B.4 单元测试 `backend/tests/test_orchestrator.py`

用 mock 替掉 LLM Extractor。**至少 4 个 case**：

| Case | 期望 |
|---|---|
| Happy path（化疗后高烧）| 返回 risk='high'，DB 里 4 张表都有数据 |
| 幂等：同 key 提交两次 | 第二次直接返回首次结果；DB assessment 行数 == 1 |
| LLM 失败 | raise `LLMExtractionError`；DB 无新记录 |
| 规则引擎崩溃（mock 它 raise）| Tx1 数据保留，assessment.decision_status='failed' |

测试需要真实 DB（可以用现有 dev DB 的事务回滚 fixture）。

### 不要做的

- ❌ **不要实现 EventEmitter 写库** — 那是 M7 的事
- ❌ **不要返回 ClarificationNeeded** — slot filling 是 v2，MVP 仅日志记录
- ❌ **不要实现 case_review 自动写入** — 留 TODO 给 stretch 任务
- ❌ **不要改 schemas/assessment.py 的接口** — 输入输出契约不动
- ❌ **不要改 services/llm_extractor.py / rule_engine.py / completeness_checker.py** — 它们是黑盒
- ❌ **不要修改现有 schema.sql / models 已有字段** — 只新增模型文件
- ❌ **不要写 retries / 熔断 / circuit breaker** — MVP 不需要
- ❌ **不要把 dictionary 存全局变量** — 每次 run() 查一次 DB（小开销，简单可靠）

## Definition of Done

```
模型:
[ ] models/symptom_observation.py / advice.py / evidence.py 三个文件
[ ] models/__init__.py 导出新模型
[ ] from app.models import * 不报错

Orchestrator:
[ ] Orchestrator.run() 实现完整 happy path
[ ] 幂等检查通过 (user_id, idempotency_key) 唯一索引
[ ] Plan C 双事务实现：Tx1 抽取 / Tx2 决策
[ ] 4 类错误传播规则正确
[ ] CompletenessChecker 调用 + 日志（不阻塞流程）

测试:
[ ] tests/test_orchestrator.py 含 4 个 case
[ ] cd backend && .venv/bin/python -m pytest tests/ -v 全绿

LOC 预算:
[ ] orchestrator.py 总长 ≤ 250 行
[ ] 三个 model 文件合计 ≤ 150 行
[ ] 测试 ≤ 200 行
```

## 验收命令

```bash
cd backend
source .venv/bin/activate

# 1. 测试（含之前所有任务的测试）
pytest tests/ -v

# 2. 手工验证 happy path
python -c "
from uuid import UUID, uuid4
from app.db import SessionLocal
from app.services.orchestrator import Orchestrator
from app.schemas.assessment import AssessmentRequest

# 准备一个测试用户
import sqlalchemy as sa
with SessionLocal() as db:
    user_id = uuid4()
    db.execute(sa.text('INSERT INTO users (id, external_id) VALUES (:id, :ext) ON CONFLICT DO NOTHING'),
               {'id': user_id, 'ext': f'smoke_{user_id}'})
    db.commit()

req = AssessmentRequest(
    user_id=user_id,
    session_id='test-session',
    input_source='free_text',
    idempotency_key=str(uuid4()),
    raw_input_text='昨天打完化疗第三天，今天下午开始发烧38.5度，浑身发冷',
)
with SessionLocal() as db:
    result = Orchestrator(db).run(req)
    print('Risk:', result.risk_level)
    print('Primary rule:', result.audit.matched_rules[0].rule_id)
    assert result.risk_level == 'high'
    assert result.audit.matched_rules[0].rule_id.startswith('R001')
    print('✓ Smoke test passed')
"
```

## 提交规范

- **PR 标题**：`[M6] Orchestrator 实现 + 补全 ORM 模型`
- **Commit 数**：2-3（建议拆 models / orchestrator / tests）
- **PR body** 列：
  - 改动文件
  - pytest -v 输出
  - 手工 smoke 输出（risk_level + rule_id）
  - 各文件 LOC

## 设计提示（不强制）

### Plan C 双事务的 SQLAlchemy 写法

```python
def _persist_extraction(self, req, parsed):
    with self.db.begin():  # Tx1
        a = Assessment(
            user_id=req.user_id,
            idempotency_key=req.idempotency_key,
            raw_input_text=req.raw_input_text,
            input_source=req.input_source,
            parsed_symptoms=parsed.model_dump(),
            extraction_confidence=parsed.confidence,
            extraction_model_version=settings.anthropic_model,
            decision_status='pending',
            rule_engine_version=None,  # 决策前为空
        )
        self.db.add(a)
        self.db.flush()  # 拿 a.id
        for sym in parsed.symptoms:
            self.db.add(SymptomObservation(
                assessment_id=a.id, user_id=req.user_id, ...
            ))
    return a
```

### 幂等查询

```python
def _lookup_existing(self, user_id, key):
    return self.db.query(Assessment).filter(
        Assessment.user_id == user_id,
        Assessment.idempotency_key == key,
    ).first()
```

### 组装审计三件套

```python
def _build_result(self, assessment, eval_result, parsed):
    return AssessmentResult(
        assessment_id=assessment.id,
        created_at=assessment.created_at,
        risk_level=eval_result.final_risk_level,
        advice=Advice(
            text=rendered_advice_text,  # 用 advice_renderer 或简单 fstring
            contact_team=eval_result.primary.contact_team,
            urgency=eval_result.primary.urgency,
        ),
        audit=AuditInfo(
            matched_rules=[
                MatchedRule(
                    rule_id=m.rule_id,
                    rule_version=m.rule_version,
                    source_doc=m.source_doc,
                    matched_fields=m.matched_fields,
                    rationale_text=m.rationale_text,
                ) for m in eval_result.all_matches
            ],
            generated_at=assessment.created_at,
            rule_engine_version=eval_result.engine_version,
            extraction_model_version=settings.anthropic_model,
        ),
        parsed_symptoms=parsed,
    )
```

## 卡住时

- **不知道 Plan C 怎么写**：看 DESIGN.md §3 决策 #6 + DESIGN.md §4 时序图
- **不确定 advice text 怎么生成**：MVP 可以直接从 rules.yaml 的 advice_templates 取字符串，不需要 Jinja2 渲染（简单 `.format()` 即可）
- **不确定 v2 slot filling 怎么对接**：本任务只 print 日志，留个 TODO 注释，未来改 return ClarificationNeeded
- **测试 DB 干净问题**：用 conftest.py fixture 在 setup 时清空数据 / teardown 时回滚事务
