# Task M8 — GET /api/v1/assessments/{id} 实现

> 这是一个独立任务卡。无需查看对话历史。
> 依赖：M6（Orchestrator 写库完成）+ M7（EventEmitter 可用）已完成

## 目标

实现 `GET /assessments/{id}` 接口：从 4 张表（assessment / advice / evidence /
symptom_observation）联表查询并组装出完整 `AssessmentResult`，含审计三件套。
触发 `result_viewed` 埋点。

## 必读（按顺序）

1. `docs/MVP_PLAN.md` — MVP 范围 + 协作约定
2. `docs/DESIGN.md` §7 — API 契约
3. `docs/DESIGN.md` §10 — 审计三件套（命中规则 + 时间 + 版本号）
4. `backend/app/api/assessments.py` — 你要改的文件中的 `get_assessment()`
5. `backend/app/schemas/assessment.py` — `AssessmentResult` / `AuditInfo` / `MatchedRule`
6. `backend/app/models/*.py` — 所有 ORM 模型
7. `backend/app/services/event_emitter.py` — M7 完成后已可用

## 范围

### Part A — 实现 `get_assessment()`

```python
@router.get("/assessments/{assessment_id}", response_model=AssessmentResult)
def get_assessment(
    assessment_id: UUID,
    db: Session = Depends(get_db),
) -> AssessmentResult:
    # 1. 查 assessment 主表
    assessment = db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    # 2. 查 evidence (一对多)
    evidence_rows = db.query(Evidence).filter_by(assessment_id=assessment_id).all()

    # 3. 查 advice (一对一，但表结构是一对多——取最新的)
    advice_row = db.query(Advice).filter_by(assessment_id=assessment_id) \
                   .order_by(Advice.created_at.desc()).first()

    # 4. 查 symptom_observation (一对多)
    obs_rows = db.query(SymptomObservation).filter_by(assessment_id=assessment_id).all()

    # 5. 组装 AssessmentResult（参考 Orchestrator._build_result 结构）
    result = self._build_from_db(assessment, advice_row, evidence_rows, obs_rows)

    # 6. 埋点
    EventEmitter(db).emit(
        event_type="result_viewed",
        session_id="N/A",  # GET 没有 session_id 入参，可记为 N/A 或从 query string 读
        user_id=assessment.user_id,
        assessment_id=assessment_id,
        payload={"risk_level": assessment.risk_level},
    )

    return result
```

### Part B — 处理状态边界

| 场景 | 期望响应 |
|---|---|
| 评估存在且 decision_status='completed' | 200 + 完整 AssessmentResult |
| 评估存在但 status='pending' | 200 + AssessmentResult（risk_level 可能为 null）+ 但更建议返回 409 'still processing' |
| 评估存在但 status='failed' | 200 + AssessmentResult，audit 中含 evidence 但 advice 为空 |
| ID 不存在 | 404 |
| ID 格式不合法 | 422（FastAPI 自动） |

**MVP 推荐做法**：直接 200 返回当前状态；前端按 `audit.matched_rules` 是否为空判断。
不要为了"严谨"加复杂的状态机。

### Part C — 集成测试 `tests/test_get_assessment_api.py`

**至少 3 个 case**：

| Case | 期望 |
|---|---|
| Happy path：先 POST 再 GET 同 id | 200 + AssessmentResult.audit.matched_rules 非空 |
| 不存在的 UUID | 404 |
| 完整字段：matched_rules / generated_at / rule_engine_version 都不为 null | 断言 |

## 不要做的

- ❌ **不要做权限校验** — MVP 不实现登录态
- ❌ **不要做缓存（Redis 等）** — 直接查库
- ❌ **不要 N+1 查询优化** — MVP 数据量小，4 个查询直接发即可
- ❌ **不要改 schemas/assessment.py 的 AssessmentResult 结构**
- ❌ **不要触发其他 4 个事件** — 这个接口只触发 `result_viewed`
- ❌ **不要在 GET 里做规则重新评估** — 数据已经在表里，组装即可

## Definition of Done

```
[ ] get_assessment() 联表查询 4 张表
[ ] 404 当 assessment 不存在
[ ] result_viewed 事件写入 event_log
[ ] 测试 3 个 case 全绿
[ ] curl POST + GET 链路跑通（见验收）
```

## 验收命令

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v

# 起服务
uvicorn app.main:app --port 8000 &
SERVER_PID=$!
sleep 2

# 1. POST 创建
RESP=$(curl -s -X POST http://localhost:8000/api/v1/assessments \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "00000000-0000-0000-0000-000000000001",
    "session_id": "smoke-session",
    "input_source": "free_text",
    "idempotency_key": "m8-test-001",
    "raw_input_text": "昨天化疗后今天发烧38.5度"
  }')
ID=$(echo $RESP | python -c "import json,sys; print(json.loads(sys.stdin.read())['assessment_id'])")
echo "Created: $ID"

# 2. GET 查询
curl -s http://localhost:8000/api/v1/assessments/$ID | python -m json.tool

# 3. GET 不存在
curl -s -w "%{http_code}\n" http://localhost:8000/api/v1/assessments/00000000-0000-0000-0000-deadbeef0000

# 4. 验证 result_viewed 入库
psql postgresql://sz:sz_dev_password@localhost:5432/sz_dev -c \
  "SELECT event_type, occurred_at FROM event_log WHERE event_type='result_viewed' ORDER BY occurred_at DESC LIMIT 3;"

kill $SERVER_PID
```

## 提交规范

- **PR 标题**：`[M8] GET /assessments/{id} 实现 + result_viewed 埋点`
- **Commit 数**：1-2
- **PR body** 列：改动文件 + curl 输出（POST 后 GET 的完整 JSON）+ pytest 结果

## 设计提示

`_build_from_db` 几乎是 `Orchestrator._build_result` 的反向操作，组装 AssessmentResult。
可以把这个组装逻辑抽到 `services/assessment_assembler.py`（或保持简单写在 api 文件里），
M6 的 `_build_result` 也可以共用。**不强制重构**，看情况。
