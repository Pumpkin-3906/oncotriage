# Task MVP+1 — 后端 API 改造（Extract 端点 + POST 接收 confirmed）

> 独立任务卡。无需对话历史，按以下文件 + 任务卡执行。
> 是其他 MVP+ 任务的前置（提供 API 契约）。

## 目标

按 `docs/UX_DESIGN.md` §3 实现 **Option III** 的 API 改造：
1. 新增 `POST /api/v1/assessments/extract` —— **无状态预览**（仅抽取，不写库）
2. 现有 `POST /api/v1/assessments` 加可选入参 `parsed_symptoms` —— 接收用户确认/编辑后的结构化症状，跳过 LLM 直接进规则引擎
3. 新增 `GET /api/v1/users/{user_id}/assessments` —— 返历史列表（当前是 stub）

## 必读

1. `docs/UX_DESIGN.md` §3 (API 改造)、§2.4 (HistoryPage)
2. `docs/CLOSED_LOOP_EXAMPLE.md`（理解整体闭环）
3. `backend/app/services/orchestrator.py`（要改这个）
4. `backend/app/api/assessments.py`（要改这个）
5. `backend/app/schemas/assessment.py`
6. `backend/app/services/llm_extractor.py` + `completeness_checker.py`
7. `docs/api/openapi.yaml`（API 契约源）

## 范围

### Part A — 新增 `POST /assessments/extract`

**用途**：仅做 LLM 抽取 + CompletenessCheck，**不写任何库**，返回让前端预览。

#### Schema（`schemas/assessment.py` 新增）

```python
class CompletenessInfo(BaseModel):
    is_complete: bool
    missing_slots: list[dict]   # [{"symptom_id": "fever", "missing_fields": ["numeric_value"]}]

class ExtractRequest(BaseModel):
    user_id: UUID
    input_source: Literal["free_text", "checklist"]
    raw_input_text: str | None = Field(None, max_length=4000)
    form_payload: dict | None = None   # checklist 时传，结构对应 ParsedSymptoms

class ExtractResponse(BaseModel):
    parsed_symptoms: ParsedSymptoms
    completeness: CompletenessInfo
    extraction_model_version: str
```

#### 逻辑

```
if input_source == "free_text":
    parsed = LLMExtractor().extract(raw_input_text, dict)
elif input_source == "checklist":
    parsed = ParsedSymptoms.model_validate(form_payload)  # 直接构造，跳过 LLM

completeness = CompletenessChecker(dict).check(parsed)
return ExtractResponse(parsed_symptoms=parsed, completeness=..., extraction_model_version=...)
```

#### 错误处理

| 异常 | HTTP | Body |
|---|---|---|
| `LLMExtractionError` | 422 | `{"reason": "extraction_failed", "message": "无法解析您的描述，建议改用清单模式"}` |
| `ValidationError` | 422 | FastAPI 自动 |

### Part B — 现有 `POST /assessments` 加 `parsed_symptoms` 入参

#### Schema 改动

`AssessmentRequest` 新增可选字段：
```python
class AssessmentRequest(BaseModel):
    # ... 现有字段
    parsed_symptoms: ParsedSymptoms | None = None  # 用户确认后的结构化症状
```

#### Orchestrator 改动

`Orchestrator.run()` 在 Step 2（抽取）开头判断：

```python
if req.parsed_symptoms is not None:
    parsed = req.parsed_symptoms
    extraction_source = "user_confirmed"
else:
    # 原 LLM 抽取流程（向后兼容）
    parsed = self._get_extractor().extract(req.raw_input_text, dictionary)
    extraction_source = "llm"
```

`_persist_extraction()` 时把 `extraction_source` 用上面的值（之前硬编码 `"llm"`）。

`assessment.extraction_model_version` 保留 `LLMExtractor.model` 值（即使是 user_confirmed 也记录 LLM 版本，便于审计追溯）。

### Part C — `GET /users/{user_id}/assessments` 实现

返回该用户的 assessment 列表，按时间倒序。

```yaml
GET /api/v1/users/{user_id}/assessments?limit=100
Response 200:
  {
    "items": [
      {
        "assessment_id": "...",
        "created_at": "2026-05-07T...",
        "risk_level": "high",
        "primary_symptom": "fever",      # 从 evidence 表第一条 rule 反查；可空
      }
    ],
    "next_cursor": null
  }
```

`primary_symptom` 取**主命中规则中第一个 symptom 字段**。从 evidence.matched_fields 解析：找形如 `symptom_<id>_<field>` 的 key，取 `<id>`。如果是兜底规则 R999，primary_symptom 为 null。

### Part D — 测试

#### `tests/test_extract_api.py`（新建）

```python
def test_extract_free_text_returns_parsed_and_completeness(client, db, fake_extractor):
    """free_text mode 返抽取结果 + completeness"""

def test_extract_checklist_skips_llm(client, db):
    """checklist mode 直接用 form_payload 构造，不调 LLM"""

def test_extract_llm_failure_returns_422_with_reason(client, db, fake_extractor_fails):
    """LLM 抛 LLMExtractionError → 422 + reason"""

def test_extract_does_not_write_db(client, db):
    """extract 不写任何业务表"""
```

#### `tests/test_assessments_api.py`（已有，扩展）

```python
def test_post_with_parsed_symptoms_skips_llm(client, db, fake_extractor):
    """传 parsed_symptoms 时 Orchestrator 不调 LLM extract，直接进规则"""

def test_post_extraction_source_user_confirmed(client, db):
    """传 parsed_symptoms 时 symptom_observation.extraction_source='user_confirmed'"""
```

#### `tests/test_get_history_api.py`（新建）

```python
def test_list_assessments_returns_user_history_desc()
def test_list_assessments_unknown_user_returns_empty()
def test_list_assessments_primary_symptom_from_evidence()
def test_list_assessments_default_rule_primary_symptom_is_null()
```

## 不要做的

- ❌ 不要去主仓 `/Users/pumpkin/projects/sz` 干活
- ❌ 不要修改 `services/llm_extractor.py` / `rule_engine.py` / `completeness_checker.py`
- ❌ 不要修改 `docs/`
- ❌ 不要碰 `.env` / `.env.example`
- ❌ 不要 push（只本地 commit）
- ❌ 不要装新依赖
- ❌ 不要给 extract endpoint 加幂等键 / 数据库写入 / 埋点（设计就是无状态）
- ❌ 不要破坏现有 POST /assessments 的向后兼容（不传 parsed_symptoms 仍走 LLM）

## Definition of Done

```
[ ] POST /assessments/extract 实现（free_text + checklist 两种 input_source）
[ ] POST /assessments 接收 parsed_symptoms 入参，跳过 LLM
[ ] GET /users/{user_id}/assessments 实现 + primary_symptom 反查
[ ] schemas/assessment.py 新增 CompletenessInfo / ExtractRequest / ExtractResponse
[ ] tests/test_extract_api.py 4+ case
[ ] tests/test_assessments_api.py 扩展 2+ case
[ ] tests/test_get_history_api.py 4 case
[ ] pytest tests/ -m "not smoke" 全绿
[ ] 总改动 LOC ≤ 400
```

## 验收

```bash
cd /Users/pumpkin/projects/oncotriage-mvp1/backend
source .venv/bin/activate
pytest tests/ -m "not smoke" -v

# 起服务
uvicorn app.main:app --port 8000 &

# extract 预览（free_text）
curl -X POST http://localhost:8000/api/v1/assessments/extract \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "00000000-0000-0000-0000-000000000001",
    "input_source": "free_text",
    "raw_input_text": "我发烧了"
  }'
# 期望返回 parsed_symptoms.symptoms=[{symptom_id:fever, numeric_value:null}]
#         completeness.is_complete=false, missing_slots=[{symptom_id:fever, missing_fields:[numeric_value]}]

# 用确认后的 parsed_symptoms POST 决策
curl -X POST http://localhost:8000/api/v1/assessments \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "00000000-0000-0000-0000-000000000001",
    "session_id": "test",
    "input_source": "free_text",
    "idempotency_key": "test-confirmed-1",
    "raw_input_text": "我发烧了 38.5度",
    "parsed_symptoms": {
      "symptoms": [{"symptom_id":"fever","numeric_value":38.5}],
      "context": {"days_since_chemo": 3},
      "confidence": 1.0
    }
  }'
# 期望 risk_level=high, R001 命中（不调 LLM）
```

## 提交规范

- **PR 标题**：`[MVP+1] backend: extract endpoint + POST accepts parsed_symptoms + history list`
- **Commit 数**：2-3
- **PR body**：3 段（Part A/B/C 各自的实现概要 + 验收 curl 输出）
