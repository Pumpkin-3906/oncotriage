# Task M7 — POST /api/v1/assessments 接通 Orchestrator

> 这是一个独立任务卡。无需查看对话历史。
> 依赖：M6 已完成（Orchestrator 可用）

## 目标

把 `api/assessments.py` 的 `POST /assessments` 接到 Orchestrator，并实现 EventEmitter
的 DB 写入（用于 5 个核心事件埋点）。

## 必读（按顺序）

1. `docs/MVP_PLAN.md` — MVP 范围 + 协作约定
2. `docs/DESIGN.md` §7 — API 契约
3. `docs/DESIGN.md` §9 — 5 个核心事件
4. `docs/api/openapi.yaml` — `POST /assessments` 完整 schema
5. `backend/app/api/assessments.py` — 你要改的文件
6. `backend/app/services/orchestrator.py` — M6 完成后已实现
7. `backend/app/services/event_emitter.py` — stub，你要补 DB 写入
8. `backend/app/schemas/assessment.py` — 入参 / 出参 Pydantic 模型

## 范围

### Part A — 接通 Orchestrator

#### A.1 改 `api/assessments.py` 中的 `submit_assessment()`

```python
@router.post("/assessments", response_model=AssessmentResult, status_code=201)
def submit_assessment(
    req: AssessmentRequest,
    db: Session = Depends(get_db),
) -> AssessmentResult:
    try:
        result = Orchestrator(db).run(req)
        # 埋点（异步发，失败不影响主流程）
        EventEmitter(db).emit(
            event_type="assessment_submitted",
            session_id=req.session_id,
            user_id=req.user_id,
            assessment_id=result.assessment_id,
            payload={"input_length": len(req.raw_input_text or "")},
        )
        return result
    except LLMExtractionError as e:
        # 422 + ChecklistFallbackPrompt
        raise HTTPException(
            status_code=422,
            detail={
                "reason": "low_confidence",
                "checklist_url": "/api/v1/checklist",
                "message": "无法解析您的描述，请使用症状清单",
            },
        )
```

注意：
- `Idempotency-Key` 通过 body 字段 `idempotency_key` 传，无需读 header
- 不需要 try/except 兜住所有异常 — FastAPI 默认会把未捕获异常转 500

### Part B — EventEmitter DB 写入

#### B.1 改 `services/event_emitter.py`

把 stub 实现成真正写 `event_log` 表 + stdout（受 `settings.event_sink` 控制）：

```python
class EventEmitter:
    def __init__(self, db: Session):
        self.db = db

    def emit(self, event_type, session_id, user_id=None, assessment_id=None, payload=None):
        if event_type not in VALID_EVENTS:
            raise ValueError(f"Invalid event_type: {event_type}")

        # 写 DB（事务外，失败仅日志，不影响主流程）
        try:
            self.db.execute(text("""
                INSERT INTO event_log
                    (event_type, user_id, session_id, assessment_id, payload, occurred_at)
                VALUES (:t, :u, :s, :a, :p, NOW())
            """), {
                "t": event_type, "u": user_id, "s": session_id,
                "a": assessment_id, "p": json.dumps(payload or {}),
            })
            self.db.commit()
        except Exception as e:
            print(f"[event_emitter] DB write failed: {e}", file=sys.stderr)

        if settings.event_sink == "stdout":
            print(f"[EVENT] {event_type} {session_id}")
```

#### B.2 添加 EventLog 模型

新建 `backend/app/models/event_log.py`，结构对应 schema.sql 中的 event_log 表。
更新 `models/__init__.py` 导出。

### Part C — 集成测试 `tests/test_assessments_api.py`

用 `fastapi.testclient.TestClient` + 真实 DB（mock LLM Extractor）。

**至少 3 个 case**：

| Case | 期望 |
|---|---|
| Happy path | 201 + AssessmentResult，event_log 有 assessment_submitted 行 |
| 幂等：同 idempotency_key 提交两次 | 第一次 201 + 第二次也是 201（or 200），返回相同 assessment_id |
| LLM 失败 | 422 + checklist_url 字段 |

## 不要做的

- ❌ **不要实现 ChecklistFallbackPrompt 的 UI 兜底逻辑** — 那是前端任务
- ❌ **不要在 EventEmitter 里写复杂的批量 / 异步 flush** — MVP 用同步 commit 就好
- ❌ **不要碰 `assessment_started` / `result_viewed` / `assessment_closed` / `contact_team_clicked`**
  这 4 个事件的触发位置不在 POST /assessments —— 它们由 GET /assessments、前端、
  POST /contact-requests 触发。本任务只埋 `assessment_submitted`
- ❌ **不要给 EventEmitter 引入 Kafka / Redis** — 配置预留就行，MVP 只走 DB + stdout
- ❌ **不要用 try/except 兜住 ValueError / TypeError** — Pydantic 验证失败 FastAPI 自动 422

## Definition of Done

```
[ ] POST /assessments 调通 Orchestrator
[ ] LLMExtractionError → 422 with checklist_url
[ ] EventEmitter 写入 event_log 表 + stdout
[ ] EventLog 模型 + __init__.py 导出
[ ] tests/test_assessments_api.py 含 3 个 case
[ ] pytest tests/ -v 全绿
[ ] curl 命令（见验收）能拿到 risk_level=high 响应
```

## 验收命令

```bash
cd backend
source .venv/bin/activate

# 1. 测试
pytest tests/ -v

# 2. 起服务
uvicorn app.main:app --port 8000 &
SERVER_PID=$!
sleep 2

# 3. curl 实际跑（先建用户）
psql postgresql://sz:sz_dev_password@localhost:5432/sz_dev -c \
  "INSERT INTO users (id, external_id) VALUES ('00000000-0000-0000-0000-000000000001', 'smoke_user') ON CONFLICT DO NOTHING;"

curl -s -X POST http://localhost:8000/api/v1/assessments \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "00000000-0000-0000-0000-000000000001",
    "session_id": "smoke-session",
    "input_source": "free_text",
    "idempotency_key": "smoke-key-001",
    "raw_input_text": "昨天打完化疗第三天，今天下午开始发烧38.5度，浑身发冷"
  }' | python -m json.tool

# 4. 验证幂等：再发一次同 key
curl -s -X POST http://localhost:8000/api/v1/assessments \
  -H 'Content-Type: application/json' \
  -d '{...同上...}' | python -m json.tool   # 应返回相同 assessment_id

# 5. 验证 event_log 写入了
psql postgresql://sz:sz_dev_password@localhost:5432/sz_dev -c \
  "SELECT event_type, COUNT(*) FROM event_log GROUP BY event_type;"

# 6. 收尾
kill $SERVER_PID
```

## 提交规范

- **PR 标题**：`[M7] POST /assessments 接通 Orchestrator + EventEmitter 落库`
- **Commit 数**：1-2
- **PR body** 列：改动文件 + curl 输出 + pytest 结果 + event_log SQL 输出
