# OncoTriage MVP — 共同学到的工程实践

> Version: 1.0.0
> Last Updated: 2026-05-07
>
> 这份文档记录在做 OncoTriage MVP 过程中我们一起踩到 / 想清楚 / 做对的事，
> 按主题归档，方便未来项目复用。

---

## A. 环境与配置

### A.1 `.env` 跨 worktree 用软链而不是复制

**问题**：M1 阶段我直接 `cp .env.example .env`，占位符 `sk-ant-...` 进了真 .env。
M_smoke agent 跑了几个小时才发现不能调真实 API。

**解决**：所有 worktree 的 `.env` 软链到主仓 `.env`：

```bash
ln -sf /Users/pumpkin/projects/sz/backend/.env .env
```

**收益**：
- 单一密钥来源（避免某个 worktree 用错 key）
- 用户改 `LLM_PROVIDER`（如从 Anthropic 切到 DeepSeek）所有 worktree 同步生效
- `.env` 在 `.gitignore` 里，软链也不会进 git

**反过来反而要小心**：如果不同 worktree 需要不同配置（如 stage 环境变量），软链就不合适。
医疗 MVP 配置稳定，所以软链够用。

### A.2 临床阈值用 ⚕️ 标记 + 注释说"修改需要委员会签字"

**问题**：很多医疗 AI 团队把 `LOW_CONFIDENCE_THRESHOLD=0.6` 这种数字写在代码里。
有人改了，code reviewer 看不出"这是临床决策"。

**解决**：所有临床阈值放 `.env.example`，用 ⚕️ 加显眼的注释段落：

```bash
# ════════════════════════════════════════════════════════════
# ⚕️ 临床阈值 — Bad Case 自动触发条件
# ⚠️ 修改这些值需要临床委员会签字，不是纯工程决策。
# ════════════════════════════════════════════════════════════
LOW_CONFIDENCE_THRESHOLD=0.6
```

**收益**：未来上 GitHub PR template 可以加 *"Does this PR modify any value marked ⚕️? If yes, attach clinician sign-off."* 让 reviewer 自动注意。

### A.3 SQL echo 用独立开关，别绑 `app_env=dev`

**问题**：M2 时我 `echo=(app_env == "dev")` —— 跑 seed 200 行 INSERT 日志刷屏。

**解决**：echo 是调试开关，不该被环境绑定。改成 `echo=False` 默认；想看 SQL 时单独开（如加 `DEBUG_SQL=true`）。

**通用原则**：**调试日志开关 ≠ 部署环境开关**。混在一起以后想"prod 也要看 SQL"就改不动了。

---

## B. 依赖管理

### B.1 任务卡明文"不要引入新依赖"

每份任务卡里都有：
```
❌ 不要引入新依赖（除非任务明确允许）
```

**为什么医疗特别严**：每个新依赖都是潜在的供应链风险（如 npm 历史上 left-pad / event-stream 事件）。
医疗系统的依赖审查很严，引入容易撤回难。

**实操**：M5 agent 自作主张加了 `openai` SDK 用于 LLMClient 抽象。我们做的事：
1. 没立即拒绝
2. 等 M_smoke 实测验证它没引入回归（20/20 pass）
3. 综合权衡后保留（多 provider 抽象长期价值高）

**教训**：MVP 阶段不要规则化 *"任何 scope creep 必拒"*，要看实际带来的价值。但**默认要拒**，用价值证明才放过。

### B.2 优先用语言/标准库内置功能

我们没用：
- ❌ pydantic-extra-types（标准 pydantic 够用）
- ❌ orjson（Python 内置 json 够快）
- ❌ alembic-utils（普通 alembic 够用）
- ❌ langchain / langgraph（用裸 Anthropic SDK + 几个函数）

只引了真正需要的：
- ✅ FastAPI / SQLAlchemy / pydantic / anthropic / pyyaml / jinja2

**MVP 原则**：能用 50 行 Python 解决的不引框架。框架的隐性成本（学习曲线 / 升级痛 / 调试黑盒）经常 > 显性收益。

---

## C. 多 Agent 协作

### C.1 Worktree 是并行的核心抽象

```
git worktree add ../oncotriage-m6 -b feat/m6-orchestrator main
```

每个并行任务一个独立 worktree：
- 独立的 working tree（agent A 改 file X 不影响 agent B 看 file X）
- 独立的 venv（避免依赖污染）
- 共享 `.git`（节省空间）
- 自带 branch（PR 流程天然）

完成后：
```bash
git worktree remove ../oncotriage-m6
git branch -d feat/m6-orchestrator
```

**对比传统多 agent 协作**：用同一个工作树会出现 *"agent A 切到 main 但 agent B 在 feat/x"* 这种状态污染。worktree 让每个 agent 拥有完整、独立的执行上下文。

### C.2 任务卡的"不要做"清单比"要做"更重要

每份 `Mx_*.md` 任务卡都有显式的 ❌ 清单：

```
- ❌ 不要去主仓干活
- ❌ 不要修改 docs/DESIGN.md
- ❌ 不要碰 .env 中标 ⚕️ 的临床阈值
- ❌ 不要尝试 push（让 parent 决定）
```

**为什么这个比正向 spec 更重要**：负向边界防止 scope creep。Agent 会"顺手"做一堆事
（"我看到这个测试比较脆弱，顺便修了一下"）—— 单独看每条都合理，加起来 PR 不可 review。

**M3 经验**：第一次派 M3 的 agent 进了 worktree 但没 commit 就退出。后来意识到任务卡需要明示
"完成后必须 commit + 报告 commit hash"。

### C.3 Stacked PR：依赖型 PR 的最佳实践

M_smoke 依赖 M5。**正确做法**：
- M5 PR base = main
- M_smoke PR base = `feat/m5-llm-extractor`（不是 main！）

收益：M_smoke 的 PR diff 只显示 smoke 的改动，不被 M5 的 1000 行刷屏。
M5 merge 后 GitHub 自动把 M_smoke 的 base 切到 main。

**反模式**：两个 PR 都 base=main，第二个会包含第一个的所有 diff。Reviewer 崩溃。

### C.4 多 agent 的"软依赖"处理

M7 和 M8 几乎同时跑。M8 需要触发 `result_viewed` 埋点 —— 但 EventEmitter 是 M7 的产物。

**解决**：M8 任务卡里写：

```python
try:
    from app.services.event_emitter import EventEmitter
    EventEmitter(db).emit(...)
except Exception:
    pass  # M7 还没合入时不阻塞 GET
```

合入到 main 后，import 正常，埋点自动启用。**这是"乐观集成"模式** —— 不强同步，靠互相兼容的接口。

### C.5 当 agent 没产出时，验证 worktree 状态

第一次派 M3 的 agent 看似完成了但 `git status` 干净、`rule_engine.py` 还是 stub。
**教训**：派出后必须验证 worktree 实际状态：

```bash
git -C ../oncotriage-m3 status
git -C ../oncotriage-m3 log feat/m3-rules --oneline
```

如果 status 干净且无新 commit，agent 没真做事。

---

## D. AI/ML 工程实践

### D.1 LLM 当翻译器，规则当判官

**核心原则**：MVP 把 LLM 严格限制在"自然语言 → 结构化"环节，规则引擎做所有风险判断。

**为什么**：
- 临床决策必须确定性 + 可审计 + 可枚举（监管要求）
- LLM 即使 temp=0 也有微妙变异
- 规则版本号易管理，prompt 版本号难管理
- 规则可单元测试，LLM 行为不可测

**反过来 LLM 能做什么（不影响判断）**：
- ✅ 措辞优化（建议文本翻译成更人话）
- ✅ 多轮追问的问题生成
- ✅ 历史摘要

### D.2 受控词表 grounding

LLM 抽取容易写出 `"fever"` / `"发烧"` / `"高热"` / `"feverish"` 不一致的字符串。

**解决**：把 `symptom_dictionary` 全表（id + 别名）塞进 prompt：

```
【可用症状字典】
- fever: 发热 (value_type=numeric, grading=ctcae_v5) / 别名: 发烧、高热、低烧、体温升高、烧
- nausea: 恶心 (value_type=categorical, grading=ctcae_v5) / 别名: 想吐、反胃、恶心
- ...
```

并强制 *"symptom_id 必须从下表精确选择，不在表中的症状必须丢弃"*。

**额外保险**：抽取后用 `valid_ids = {s["id"] for s in dict}` 做 post-validation，
LLM 还想偷塞新 ID 直接 raise `LLMExtractionError`。

### D.3 测试金字塔（医疗 AI 版）

```
                  Smoke (真实 API + 无 DB)
                  ────────────────────
                  · 20 个真实患者描述
                  · 验证 LLM 语义抽取
                  · ~$0.10/run，~90s
                  · @pytest.mark.smoke 隔离
                            ▲
            Integration (mock LLM + 真实 DB)
            ────────────────────────────
            · Orchestrator 双事务
            · 幂等查重
            · 错误传播路径
                            ▲
                      Unit (无外部依赖)
                      ──────────────
                      · 规则引擎 _matches()
                      · CompletenessChecker
                      · LLMClient mock
```

每层覆盖**正交的 risk surface**：
- Unit 抓代码 bug
- Integration 抓 orchestration / 事务边界 / 数据契约 bug
- Smoke 抓 prompt 漂移 / 字典空白 / 模型升级回归

混在一起会让每层都跑得慢、调试难。

### D.4 Smoke 默认隔离

```toml
[tool.pytest.ini_options]
markers = [
    "smoke: real-API smoke tests against patient-language corpus (cost ~$0.10/run, slow)",
]
```

默认 `pytest tests/` 排除 smoke；CI 单独跑 `pytest -m smoke`。

**为什么**：
- 每次 PR 都跑 smoke 会烧钱（每月几百 PR × $0.10 = $$$）
- LLM 偶发不稳定，会挡 PR 通过
- 关心 smoke 的时刻：prompt / 字典 / 模型变更的 PR

### D.5 LLM 抽象层何时值得

M5 agent 自作主张引入 `LLMClient` 抽象（Anthropic + OpenAI 兼容）。

**事后看**：value 很高。用户后来切到 DeepSeek 没改一行代码。

**何时值得抽象**：
- ✅ 多 provider 是真实需求（医疗合规对国产 LLM 偶有要求）
- ✅ 抽象层薄（M5 的实现 156 行）
- ✅ 测试覆盖了抽象层本身（test_llm_client.py 8 个 case）

**何时不值得**：
- ❌ 只用一家 provider 永远不变
- ❌ 抽象层比业务代码还复杂
- ❌ 测试只 mock 抽象层，不测真实 SDK

---

## E. 数据库与 Schema

### E.1 Schema 与 ORM 模型双源真理是个坑

M6 agent 发现 `Assessment` ORM 模型缺 `idempotency_key` / `decision_status` 字段，
而 `schema.sql` 是有的。**漂移**导致 INSERT 直接报错。

**根因**：M2 阶段我只建了 User + Assessment 两个示例 ORM，schema.sql 后续在多个章节加字段没回头同步 ORM。

**MVP 解法**：手工对齐（M6 agent 修了）。

**v2 解法**（应做）：
- 用 alembic autogenerate 从 ORM 反推迁移
- ORM 模型作为单一真理源
- schema.sql 由模型生成（或 reviewer 看 ORM 而不是 SQL）

### E.2 物化视图 vs 普通视图：MVP 先用普通

`v_user_trend_7d` 用普通 VIEW 而不是 MATERIALIZED VIEW。

**理由**：
- MVP 数据量小，查询毫秒级
- 永远不会有"快照过期"的一致性问题
- 真到性能瓶颈，一行 `ALTER MATERIALIZED VIEW ... REFRESH` 就升级
- 别预先优化（YAGNI）

### E.3 软引用 vs 外键的 trade-off

`evidence.rule_id` 引用 `rule_source.rule_id` —— **没用 ForeignKey**：

```sql
-- evidence
rule_id      VARCHAR(64),
rule_version VARCHAR(16),  -- 联合软引用
```

**理由**：
- 历史 evidence 必须自包含（不能因为 rule 改了就让历史记录的依据被改）
- ForeignKey + ON UPDATE CASCADE 会让规则改动级联到历史，违反审计原则

**通用原则**：**审计相关的关系用软引用 + 完整快照**；业务相关的关系用 ForeignKey。

### E.4 冗余 user_id 用于跨实体查询

`symptom_observation` 既有 `assessment_id`（业务关系）又冗余 `user_id`（查询便利）。

```sql
-- 查"某用户最近 7 天的所有症状"
SELECT * FROM symptom_observation
WHERE user_id = :uid AND observed_at > NOW() - INTERVAL '7 days';
-- 不需要 join assessment 表
```

**MVP 阶段**：冗余 1 列 vs join 一次的 trade-off，**冗余赢**（应用层保证一致即可）。

---

## F. 设计与文档

### F.1 设计 → 骨架 → 任务卡 → 派 → review → merge

我们的实际工作流：

```
设计文档      骨架               任务卡             派 agent       review/merge
DESIGN.md → README/config → docs/tasks/Mx → worktree+spawn → PR → main
   │            │                │                │           │
   │            │                │                │           ↑
   │            │                │                ↑         user
   │            │                │              parent
   │            │                ↑              agent
   │            ↑              parent
   │          parent
   ↑
parent
```

**收益**：
- 任务卡自包含（agent 不需要看对话历史）
- 每层独立可改（设计变了不重写所有任务卡）
- "不要做的"约束在任务卡里有显式条目，不靠口头传达

### F.2 Insight 块：让协作有"教学"维度

每个回答里穿插的 `★ Insight ─────────────` 块不是装饰。它们是把**为什么这样选**的认知显式化，
让协作不只是"做事"，也是"传递判断力"。

3 个月后回头看，写过的 Insight 比写过的代码更值钱（代码能查 git，判断逻辑会忘）。

### F.3 设计文档的"我们决定的事"用编号

`DESIGN.md §3` 的"关键架构决策表"按 `决策 #N` 编号：

```markdown
| # | 决策点 | 选择 | 理由 |
| 1 | 决策层方案 | LLM 抽取 + 规则决策 | ... |
| 6 | Orchestrator 事务边界 | 抽取 / 决策 独立事务 | ... |
| 7 | 规则引擎冲突解决 | 评估全部 / 决策一条 / 审计全部 | ... |
```

任务卡里直接引用 *"见决策 #6"*。**收益**：3 个月后回看 PR diff 不需要读全 DESIGN，看决策号就理解上下文。

---

## G. 工程与流程

### G.1 命名：避免泛化

最初用户提议 `risk-assessment-system`。我推了回去 ——
*"风险评估"在金融、保险、安全领域到处都是*，搜索时容易混淆。

最终选 `oncotriage`：
- 清晰：oncology + triage
- 短：10 字符
- 专业感
- 未来从乳腺癌扩展到其他癌种不用改名

**通用原则**：**命名要带领域，不要带功能**。"风险评估"是功能（很多领域都叫这个），
"肿瘤分诊"是领域（独此一家）。

### G.2 PR 标题加任务编号

```
[M5] LLM symptom extractor with multi-provider client abstraction
[M_smoke] Real patient corpus + smoke test runner (20 cases, 100% pass)
[M6] Orchestrator with Plan C dual-tx + idempotency + ORM models
```

**收益**：3 个月后从 git log 找"实现规则引擎那个 PR" → grep `[M3]`，秒级定位。

### G.3 commit 拆分：按"如果回滚我会回滚到哪步"

M6 agent 拆了 3 个 commit：
- feat(M6): add ORM models  ← 单独可用（其他 service 还没跑通也能 import）
- feat(M6): implement Orchestrator  ← 主体
- test(M6): add integration tests   ← 可独立运行

如果实现 Orchestrator 出 bug，可以 `git revert` 第二个 commit，保留 models 给后续重试。

**反模式**："Initial implementation" 一个超大 commit，回滚要么全丢要么全留。

### G.4 不要用 "fix" 当 commit 类型除非真的修 bug

M5 agent 的 commit `fix(M5): support thinking blocks + Anthropic base_url override` —— 这是**新增能力**，不是 bug fix。
应该叫 `feat(M5): ...`。

混淆这两个会让 changelog 不准确（grep `^fix` 想看 bug 修复结果一堆 feature 假装成 fix）。

---

## H. 医疗领域特别注意

### H.1 数据保留原则 > 数据库 ACID

医疗场景里：用户已经报告的症状，**不能因系统问题消失**。这压倒了一致性洁癖。

具体实现：Plan C 双事务，Tx1 先 commit 抽取结果，Tx2 失败仍保留 Tx1 数据。
单事务 ACID 派看着不洁但临床上对。

### H.2 幂等键不只是 UX，是临床安全

重复提交导致数据库出现两条 fever 记录 → trend 分析以为是两个独立 episode → 升级处置。

**医疗系统对幂等的要求比电商更严**。Stripe 的 idempotency key 模式照搬过来。

### H.3 "兜底偏保守"

R999 (无规则匹配) 默认返回 medium 而不是 low。

**理由**：医疗里"漏判 high 当成 low"的代价远高于"误报 medium 当成 low"。
保守的 unknown 策略让用户更可能联系团队，过度报警比漏报安全。

### H.4 LLM 失败 → 立即降级，不要重试

M6 agent 注意到 DeepSeek 偶发 10-15% 漏抽率，建议加 retry。

**MVP 暂不加**：retry 可能让用户等 15-20 秒；不如返回 422 让前端展示症状清单，
用户自己勾选（更快、更准、更有掌控感）。

医疗 UX 原则：**当系统不确定时，把控制权交给用户而不是黑盒重试**。

---

## 这些经验的元认知

我们做对的事：
1. **先设计、后骨架、再实现**。设计文档 1500 行先于第一行代码。
2. **每个决策有"反对意见"**。Plan A/B/C/D 演化、Stacked PR、Plan C 双事务都讨论了多个选项。
3. **任务卡显式负向约束**。"不要做"清单防 scope creep。
4. **测试分层正交**。Unit / Integration / Smoke 各管一类风险。
5. **代码外的判断力比代码更值钱**。Insight 块、决策表、为什么这样选的注释。

我们走过的弯路：
1. 第一次 cp .env.example .env 用占位符（→ A.1）
2. M3 第一次 agent 进 worktree 没产出（→ C.5）
3. ORM 模型与 schema.sql 漂移（→ E.1）
4. SQL echo 绑 dev env（→ A.3）
5. Smoke 没默认隔离 marker（→ D.4）

每一个弯路都成了任务卡里的一条 ❌ 或文档里的一条原则。**这就是工程能力的累积过程**。
