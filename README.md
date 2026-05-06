# OncoTriage

> 乳腺癌副作用自评分诊智能体 MVP
> 设计文档：[`docs/DESIGN.md`](docs/DESIGN.md)

最小可运行原型：患者输入副作用描述 → LLM 抽取症状 → 规则引擎决策 → 返回风险等级 + 建议 + 审计依据。

## 项目结构

```
sz/
├── docs/                 ← 设计文档（schema / rules / api / consent）
├── backend/              ← FastAPI + SQLAlchemy
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models/       ← SQLAlchemy 模型
│   │   ├── schemas/      ← Pydantic schemas (API 入参/出参)
│   │   ├── api/          ← FastAPI 路由
│   │   ├── services/     ← 感知/决策/执行 业务逻辑
│   │   └── rules/        ← 规则加载器
│   ├── alembic/          ← 数据库迁移
│   └── tests/
├── frontend/             ← React + Vite + TypeScript
│   └── src/
│       ├── pages/        ← 输入页 / 结果页 / 历史页
│       ├── api/          ← API client
│       └── lib/          ← analytics (5 events 埋点)
└── docker-compose.yml    ← Postgres for local dev
```

## 快速开始

### 前置依赖
- Python 3.11+
- Node.js 20+
- Docker + Docker Compose

### 一次性初始化

```bash
# 1. 启动 Postgres
docker compose up -d

# 2. 后端
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# 编辑 .env，填入 ANTHROPIC_API_KEY

# 3. 数据库迁移（首次）
alembic upgrade head

# 4. 启动后端
uvicorn app.main:app --reload --port 8000
```

```bash
# 5. 前端（新终端）
cd frontend
npm install
npm run dev
# 浏览器打开 http://localhost:5173
```

## 测试

```bash
cd backend && pytest
cd frontend && npm test
```

## 设计映射：闭环 → 代码模块

| 闭环环节 | 代码位置 | 状态 |
|---|---|---|
| **感知** | `backend/app/services/llm_extractor.py` | 🚧 stub |
| **决策** | `backend/app/services/rule_engine.py` | 🚧 stub |
| **执行** | `backend/app/services/orchestrator.py` | 🚧 stub |
| **学习** | （L3 离线，仅依赖 `event_log` 表） | 设计阶段 |

## 待你决策的关键设计点

代码中标记为 `# TODO(decision):` 的位置都是 5-10 行级别的设计决策：

1. `services/orchestrator.py` — LLM 抽取失败时的事务边界（部分保存 vs 全部回滚）
2. `services/rule_engine.py` — 多条规则同时命中时的冲突解决策略
3. `frontend/src/lib/analytics.ts` — 埋点失败时的本地缓存策略

每一处都附了 trade-off 说明。
