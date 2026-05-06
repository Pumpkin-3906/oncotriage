# 多 Agent 任务卡

每份 `Mx_*.md` 是一个独立任务，可被任意 agent（Claude Code / Cursor / ChatGPT）单独承接。

## 当前可派出的并行任务

| Task | 文件 | 依赖 | 可并行？ |
|---|---|---|---|
| M3+M4 | [`M3_rule_engine.md`](M3_rule_engine.md) | M1+M2 已完成 ✅ | 是 |
| M5    | [`M5_llm_extractor.md`](M5_llm_extractor.md) | 仅依赖 ANTHROPIC_API_KEY | 是 |

M3 和 M5 互不影响，**可同时派给两个 agent**。

---

## 给 Agent 的 spawn 提示词模板

复制下面任一段直接喂给 agent（已自包含，agent 不需要看你的对话）。

### 派 M3+M4

```
你接到 OncoTriage 项目的 M3+M4 任务。

仓库：https://github.com/Pumpkin-3906/oncotriage
本地路径：/Users/pumpkin/projects/sz

你的任务卡：docs/tasks/M3_rule_engine.md

严格按任务卡执行：
1. 先读完任务卡列出的所有"必读"文件
2. 严格遵守"不要做的"清单
3. 完成 Definition of Done 全部勾选
4. 跑通"验收命令"全部绿
5. 提交 PR，body 按规范填写

环境已就绪：
- DB schema 已应用（11 表 + 1 视图）
- 字典 seed 完成（12 条）
- Python venv 在 backend/.venv，依赖已装
- 进入 venv: cd backend && source .venv/bin/activate

不需要任何外部服务（不调 LLM、不需要 ANTHROPIC_API_KEY）。

完成后回报：改动文件列表 + pytest 输出 + commit hash。
```

### 派 M5

```
你接到 OncoTriage 项目的 M5 任务。

仓库：https://github.com/Pumpkin-3906/oncotriage
本地路径：/Users/pumpkin/projects/sz

你的任务卡：docs/tasks/M5_llm_extractor.md

严格按任务卡执行：
1. 先读完任务卡列出的所有"必读"文件
2. 严格遵守"不要做的"清单
3. 完成 Definition of Done 全部勾选
4. 跑通"验收命令"全部绿
5. 提交 PR，body 按规范填写

环境已就绪：
- Python venv 在 backend/.venv，anthropic SDK 已装
- 进入 venv: cd backend && source .venv/bin/activate
- 你需要 ANTHROPIC_API_KEY（写到 backend/.env，文件已存在但 key 是占位符）

完成后回报：改动文件列表 + pytest 输出 + 真实 API 烟测的 JSON 输出 + commit hash。
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
