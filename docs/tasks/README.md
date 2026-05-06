# 多 Agent 任务卡

每份 `Mx_*.md` 是一个独立任务，可被任意 agent（Claude Code / Cursor / ChatGPT）单独承接。

## 任务状态全景

| ID | 任务 | 状态 | 依赖 | 文件 |
|---|---|---|---|---|
| M1 | DB schema 初始化 | ✅ 完成 | — | (done in main) |
| M2 | 症状字典 seed | ✅ 完成 | M1 | (done in main) |
| M3 + M4 | 决策层（规则引擎 + CompletenessChecker + 测试）| 🔄 任务卡更新到 v2 | M2 | [`M3_rule_engine.md`](M3_rule_engine.md) |
| M5 | LLM 抽取器 | 🚧 feat 分支已交付，待 merge | — | [`M5_llm_extractor.md`](M5_llm_extractor.md) |
| **M6** | **Orchestrator** | **📋 任务卡就绪** | M3 + M5 | [`M6_orchestrator.md`](M6_orchestrator.md) |
| **M7** | **POST /assessments** | **📋 任务卡就绪** | M6 | [`M7_post_assessments.md`](M7_post_assessments.md) |
| **M8** | **GET /assessments/{id}** | **📋 任务卡就绪** | M6（M7 不强依赖）| [`M8_get_assessment.md`](M8_get_assessment.md) |
| **M_smoke** | **真实患者语料冒烟集** | **📋 任务卡就绪** | M5（M3 完成后能跑更多）| [`M_smoke_corpus.md`](M_smoke_corpus.md) |
| M9 | 补全其余 ORM 模型 | 已并入 M6 | — | — |
| M10 | InputPage 接通 | 待写任务卡 | M7 | — |
| M11 | ResultPage 渲染 | 待写任务卡 | M8 | — |

## 依赖图

```
M1 (DB) ──┐
          ├─→ M2 (Dictionary) ──→ M3 (Rules + Checker) ──┐
          │                                              ├─→ M6 (Orchestrator) ──┬──→ M7 (POST API)
          │                                              │                       └──→ M8 (GET API)
          └────────────────────→ M5 (LLM Extract) ──────┘                            │      │
                                       │                                             └──┬───┘
                                       ▼                                                ▼
                                    M_smoke ─────────────────────────────────→ (full pipeline)
```

## 当前可派出的并行任务（建议）

### Wave 1（现在就能派）
- **M3+M4** —— 决策层完整版（含 CompletenessChecker），无外部依赖
- **M_smoke** —— 真实患者语料，仅依赖已完成的 M5
- **M5 review/merge** —— 不是 agent 任务，是你的事：把 `feat/m5-llm-extractor` 分支合到 main

### Wave 2（M3 + M5 都到 main 后）
- **M6** —— Orchestrator
- 同时可继续派 M_smoke 的 e2e 部分

### Wave 3（M6 到 main 后）
- **M7** + **M8** 可以并行（不同接口）

---

## 给 Agent 的 spawn 提示词模板

复制下面任一段直接喂给 agent。

### 派 M3+M4

```
你接到 OncoTriage 项目的 M3+M4 任务（v2 含 CompletenessChecker）。

仓库：https://github.com/Pumpkin-3906/oncotriage
本地路径：/Users/pumpkin/projects/sz

你的任务卡：docs/tasks/M3_rule_engine.md

严格按任务卡执行：
1. 先读完任务卡列出的所有"必读"文件
2. 严格遵守"不要做的"清单
3. 完成 Definition of Done 全部勾选
4. 跑通"验收命令"全部绿
5. 提交 PR，body 按规范填写

环境已就绪：DB schema 已应用、字典已 seed、Python venv 在 backend/.venv 依赖已装。
进入 venv: cd backend && source .venv/bin/activate
不需要任何外部服务（不调 LLM、不需要 ANTHROPIC_API_KEY）。

完成后回报：改动文件列表 + pytest 输出 + commit hash。
```

### 派 M_smoke（可与 M3 并行）

```
你接到 OncoTriage 项目的 M_smoke 任务（构造真实患者语料）。

仓库：https://github.com/Pumpkin-3906/oncotriage
本地路径：/Users/pumpkin/projects/sz

你的任务卡：docs/tasks/M_smoke_corpus.md

严格按任务卡执行。重点：
- 至少 18 条 case，覆盖 A.1-A.10 全部分类
- LLM 抽取断言用宽松匹配（must_include / confidence_min），不要过严
- 跑真实 API（不要 mock），单次跑成本约 $0.04
- 默认 pytest 跑不进 smoke（用 @pytest.mark.smoke 隔离）

需要：ANTHROPIC_API_KEY 已写入 backend/.env

完成后回报：18+ case 列表 + 完整 pytest -v 输出 + token 成本估算。
```

### 派 M6（M3+M5 合到 main 后）

```
你接到 OncoTriage 项目的 M6 任务。

仓库：https://github.com/Pumpkin-3906/oncotriage
本地路径：/Users/pumpkin/projects/sz

你的任务卡：docs/tasks/M6_orchestrator.md

依赖前置：M3 (rule_engine + completeness_checker) 和 M5 (llm_extractor) 已合到 main。

严格按任务卡执行。重点：
- Plan C 双事务（DESIGN.md §3 决策 #6）
- 幂等性 (user_id, idempotency_key) UNIQUE 索引（DESIGN.md §15）
- 补全 3 个 ORM 模型（symptom_observation / advice / evidence）
- CompletenessChecker 仅日志记录，不返回 ClarificationNeeded（v2 再做）

环境：cd backend && source .venv/bin/activate

完成后回报：改动文件 + pytest 输出 + 手工 smoke 输出。
```

### 派 M7（M6 合到 main 后）

```
你接到 OncoTriage 项目的 M7 任务。

仓库：https://github.com/Pumpkin-3906/oncotriage
本地路径：/Users/pumpkin/projects/sz
任务卡：docs/tasks/M7_post_assessments.md
依赖：M6 已 merge

完成后回报：curl 输出 + pytest 结果 + event_log SQL 输出
```

### 派 M8（M6 合到 main 后，可与 M7 并行）

```
你接到 OncoTriage 项目的 M8 任务。

仓库：https://github.com/Pumpkin-3906/oncotriage
本地路径：/Users/pumpkin/projects/sz
任务卡：docs/tasks/M8_get_assessment.md
依赖：M6 已 merge（M7 不强依赖，但有 M7 的 EventEmitter 实现会更顺）

完成后回报：curl POST + GET 链路输出 + pytest 结果
```

---

## 协作约束（来自 docs/MVP_PLAN.md §5）

所有 agent 必须遵守：

- ❌ 不要顺手"优化"非本任务文件
- ❌ 不要在 MVP 阶段引入新依赖（除非任务卡明确允许）
- ❌ 不要修改 `docs/DESIGN.md` / `docs/data_model/schema.sql` 除非任务明确要求
- ❌ 不要碰 `.env.example` / `.env` 中标 ⚕️ 的临床阈值
- ❌ 不要直接 push 到 main —— 走 PR 流程

PR 标题格式：`[Mx] 简短描述`
PR body 必须列：改动文件、DoD 是否满足、运行了哪些命令验证。

## 关于 worktree（M3+M5 经验复盘）

每个并行任务建议用独立 worktree：
```bash
git worktree add ../oncotriage-m3 -b feat/m3-rules
```
完成后从 worktree 内 push 到 origin，开 PR，主仓 review + merge。
M3 上一轮跑 worktree 但 agent 没产出 commit —— 派任务时确认 agent 知道要 commit + push。
