# OncoTriage MVP — 开发与测试计划

> Status: ready to execute
> Last Updated: 2026-05-06

---

## 0. 核心原则

1. **跑通 happy path 优先**，不追求 feature-complete
2. **不写花架子代码**：能用 100 行解决就不用 200 行；能用配置就不用类
3. **每个任务必须有"Definition of Done"**，否则不算完
4. **测试只覆盖关键路径**：规则引擎 + 主 API；前端组件测试 MVP 阶段不写

---

## 1. MVP 验收标准（北极星）

患者打开网页 → 输入 *"昨天打完化疗第三天，今天下午开始发烧 38.5 度"* → 系统在 ≤10 秒内返回：
- ✅ 风险等级 = HIGH
- ✅ 建议文本提及"立即急诊"
- ✅ 审计区可看到命中的 `R001_febrile_neutropenia_suspected` + 版本 + 时间

**只要这一条 demo 跑通，MVP 就算交付。**

---

## 2. 明确不做的事（Scope guard）

以下都**有意推迟**到 MVP 之后，避免被诱惑去做：

| 推迟项 | 理由 |
|---|---|
| 用户登录 / 多用户 | MVP 用硬编码 `user_id="00000000-..."` 走通流程即可 |
| Alembic auto-generate 迁移 | 直接 `psql -f docs/data_model/schema.sql` 建表 |
| Checklist 兜底 UI | LLM 失败时返回 422，前端弹窗提示即可，不做 fallback 表单 |
| 历史记录页真实数据 | 路由保留，页面显示"暂无记录"也算过 |
| Contact request 真实通知（短信/IM） | 写 DB + 埋点即可，不发任何外部消息 |
| Consent 强制执行 | 默认 scope 自动写入即可，出站校验留 TODO |
| Advanced 时序规则 | `FEATURE_TIMESERIES=false`，R030 不启用 |
| Bad case 自动 flagging 完整流程 | 仅写日志 + 标 TODO，不实际写 case_review |
| 前端 polish（动画/loading skeleton/移动端适配）| Tailwind 默认样式即可 |
| Docker 化后端 | 本地 `uvicorn` 跑就行 |
| CI/CD | 后续单独搞 |

---

## 3. 任务清单（按依赖排序）

### Phase 1：基础（可并行 ≥3 个 agent 同时干）

| ID | 任务 | Files | DoD | 估算 LOC |
|---|---|---|---|---|
| **M1** | 应用 schema 到本地 DB | `docs/data_model/schema.sql` (用) + 建一个 `backend/scripts/init_db.sh` | `psql` 能从空库建出 11 表 + 1 视图，无报错 | 20 |
| **M2** | 症状字典 seed | `backend/app/rules/seed_dictionary.py` | 12 条 `INSERT` 语句执行后 `SELECT COUNT(*) FROM symptom_dictionary` = 12 | 50 |
| **M3** | 规则引擎 `_matches()` 实现 | `backend/app/services/rule_engine.py` | 支持 `all_of` / `any_of` / `always` 求值；支持 `numeric_value` 操作符（`gte/lte/lt/gt/eq`/`in`）和 `ctcae_grade`、`categorical_value`、`context.days_since_chemo` 字段 | 80 |
| **M4** | 规则引擎单元测试 | `backend/tests/test_rule_engine.py` | 覆盖：R001 命中（高烧+化疗后）、R020 命中（轻度恶心）、R999 兜底、Plan D 多规则同时命中 | 100 |
| **M5** | LLM extractor 实现 | `backend/app/services/llm_extractor.py` | 给定描述能返回合法 ParsedSymptoms；超时/JSON 解析失败抛 `LLMExtractionError` | 80 |

**Phase 1 验收**：
```bash
cd backend
psql $DATABASE_URL -f ../docs/data_model/schema.sql
python -m app.rules.seed_dictionary
pytest tests/test_rule_engine.py -v        # 全绿
python -c "from app.services.llm_extractor import LLMExtractor; print(LLMExtractor().extract('发烧38.5度', []))"
```

---

### Phase 2：后端集成（依赖 Phase 1）

| ID | 任务 | Files | DoD |
|---|---|---|---|
| **M6** | Orchestrator 串起感知+决策+执行（Plan C 双事务）| `services/orchestrator.py` | 输入 AssessmentRequest，输出 AssessmentResult；写入 assessment + symptom_observation + evidence + advice 共 4 表 |
| **M7** | `POST /api/v1/assessments` 接通 Orchestrator | `api/assessments.py` | curl 提交描述能拿到完整 AssessmentResult JSON |
| **M8** | `GET /api/v1/assessments/{id}` 实现 | `api/assessments.py` | 能从 4 张表 join 出完整 AssessmentResult（含审计三件套）|
| **M9** | Models 补全（其余 8 张表）| `app/models/*.py` | `from app.models import *` 不报错；Alembic 跳过，直接用 schema.sql 建表 |

**Phase 2 验收**：
```bash
curl -X POST http://localhost:8000/api/v1/assessments \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"00000000-0000-0000-0000-000000000001",
       "session_id":"test-session",
       "input_source":"free_text",
       "idempotency_key":"test-key-001",
       "raw_input_text":"昨天化疗后今天发烧38.5度"}'
# 应返回 risk_level=high, audit.matched_rules 含 R001
```

---

### Phase 3：前端串联（依赖 Phase 2）

| ID | 任务 | Files | DoD |
|---|---|---|---|
| **M10** | InputPage → POST → 跳转 ResultPage | `frontend/src/pages/InputPage.tsx` | 文本提交后自动跳到 `/result/{id}` |
| **M11** | ResultPage 渲染真实数据 | `frontend/src/pages/ResultPage.tsx` | 显示风险等级 + 建议 + 审计区可展开 |
| **M12** | E2E demo 视频/截图 | — | 录一段 30 秒 demo 证明北极星案例跑通 |

**Phase 3 验收**：浏览器 → 输入文本 → 看到红色高风险标签 + "立即急诊"建议。

---

### Phase 4：Stretch（如果 Phase 1-3 提前完成才做）

- S1：HistoryPage 真实数据
- S2：Contact request 接口 + 按钮
- S3：Event log 写 DB（不只 stdout）
- S4：低置信度自动写 case_review

---

## 4. 测试计划

### 4.1 测试金字塔（MVP 版）

```
        ┌──────────┐
        │  Manual  │ ← 1 个北极星 e2e（M12）
        ├──────────┤
        │   API    │ ← 2-3 个 happy path（M7/M8 验收时写）
        ├──────────┤
        │   Unit   │ ← 主要在规则引擎（M4）
        └──────────┘
```

### 4.2 必须写的测试

| 测试文件 | 覆盖 | 目标 |
|---|---|---|
| `tests/test_rules_loader.py` | rules.yaml 完整性 | ✅ 已写 |
| `tests/test_rule_engine.py` | Plan D 决策逻辑 | M4 任务 |
| `tests/test_orchestrator.py` | 双事务 + 幂等 | M6 任务（mock LLM）|
| `tests/test_assessments_api.py` | POST + GET 端到端 | M7/M8 任务（用 testclient + 真实 DB）|

### 4.3 必须做的手工测试场景

| 场景 | 期望 |
|---|---|
| 化疗后高烧 38.5 | risk=high, R001 |
| 轻度恶心可进食 | risk=low, R020 |
| 模糊描述（"不太舒服"）| LLM 低置信度 → 提示用户重输 |
| 重复提交同一表单 | 第二次返回相同 assessment_id（幂等）|

### 4.4 不做的测试

- ❌ 前端组件测试（vitest 配好但不写测试）
- ❌ E2E 自动化（Playwright/Cypress）
- ❌ 性能 / 压测
- ❌ 多用户并发
- ❌ 安全测试（SQLAlchemy 已防 SQL 注入）

---

## 5. 多 Agent 协作约定

如果有多个 agent 并行干活：

### 5.1 任务认领
在本文件的"任务清单"表格里把 `Owner` 列加上 agent 名。同一任务不要被多人认领。

### 5.2 PR 边界
- 每个 M 任务 → 一个独立 PR
- PR 标题格式：`[M3] 实现规则引擎 _matches()`
- PR body 必须列：改动文件、DoD 是否满足、运行了哪些命令验证

### 5.3 不要做的事
- ❌ 不要顺手"优化"非本任务文件
- ❌ 不要在 MVP 阶段引入新的依赖（除非任务明确允许）
- ❌ 不要修改 `docs/DESIGN.md` / `docs/data_model/schema.sql` 除非任务明确要求
- ❌ 不要碰 `.env.example` 里标 ⚕️ 的临床阈值

### 5.4 必读文件（任何 agent 接任务前都要读）

1. `README.md` — 项目结构 + 快速开始
2. `docs/DESIGN.md` §3-5 — 架构决策 + 闭环
3. `docs/data_model/schema.sql` — 数据模型
4. `docs/api/openapi.yaml` — API 契约
5. 任务对应的 stub 文件（已经写了大量注释）

---

## 6. Definition of "MVP 完成"

跑这一条命令链能拿到正确结果：

```bash
# 1. 启动
docker compose up -d
cd backend && source .venv/bin/activate && uvicorn app.main:app --port 8000 &
cd frontend && npm run dev &

# 2. 浏览器打开 http://localhost:5173
# 3. 输入"昨天打完化疗第三天，今天下午开始发烧 38.5 度"
# 4. 点提交
# 5. 看到红色 HIGH 标签 + 立即就医建议 + 审计区显示 R001
```

完成 → 提 PR `chore: MVP demo ready` → close。
