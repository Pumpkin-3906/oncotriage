# OncoTriage MVP — 批判性审视与生产化路径

> Version: 1.0.0 (M7 完成时草稿，M8 + 前端联调后补完)
> Last Updated: 2026-05-07
>
> 这份文档对项目做诚实的、批判性的审视。"做完了 MVP"不等于"做出了好系统"——
> 我们刻意把很多事推迟了，这里把它们集中列出，标明 **MVP 缺陷** vs **未来必须改进**。

---

## 1. 原始要求验收

业务背景里要求的 7 大类，逐项核对：

| 要求 | 状态 | 落地位置 |
|---|---|---|
| 风险等级返回 | ✅ | `assessment.risk_level` (high/medium/low) |
| 下一步建议 | ✅ | `advice.rendered_text` + `advice.urgency` |
| 是否建议联系团队 | ✅ | `advice.contact_team` (boolean) |
| 简单依据说明 | ✅ | `audit.matched_rules[].rationale_text` |
| 用户输入页 | ✅ | `frontend/src/pages/InputPage.tsx` |
| 结果页 | ✅ | `frontend/src/pages/ResultPage.tsx` |
| 历史记录页 | 🚧 | 路由存在，数据接通待 M8 + 前端联调 |
| 提交评估 API | ✅ | `POST /api/v1/assessments` (M7) |
| 获取结果 API | 🚧 | `GET /api/v1/assessments/{id}` (M8 进行中) |
| 获取历史 API | 🚧 | `GET /api/v1/users/{id}/assessments` 未实现 (Stretch) |
| 创建协同请求 API | 🚧 | stub 存在，未实现（后端 stretch） |
| 风险逻辑 - 高/中/低分层 | ✅ | `rules.yaml` 12 条规则覆盖三层 |
| 数据存储 - 5 张核心表 | ✅ | assessment / advice / evidence / rule_source / event_log 全建 |
| 5 个事件埋点 | 🚧 | assessment_submitted ✅ (M7)；result_viewed 🚧 (M8)；其他 3 个待前端补 |
| 审计三件套（命中规则/时间/版本号）| ✅ | `audit` 字段 + `rule_source` 表的 YAML 快照 |
| 系统架构图 + 数据流 | ✅ | `DESIGN.md` §4 |
| 感知-决策-执行-学习闭环描述 | ✅ | `DESIGN.md` §5 + `CLOSED_LOOP_EXAMPLE.md` |

**结论**：MVP 核心要求**约 85% 完成**，剩余 15% 是历史记录 / 协同请求接口 / 前端 4 个事件，技术上没有难度，是我们刻意按 Stretch 推迟的。

---

## 2. 这个项目"很 MVP"的地方（坦白讲不足）

### 2.1 LLM 应用浮于表面

**现状**：LLM 仅作 NLP 翻译器。约 90% 的"智能"藏在医生写的规则里。

**为什么这是缺陷**：
- LLM 的强项（推理、上下文理解）几乎没用上
- 规则覆盖 12 条症状 + 11 条规则，远远不能涵盖真实临床场景
- 多轮追问（slot filling）只设计了，没实现

**生产差距**：
- 真实临床 CDSS 规则集通常 500-2000 条（CTCAE 全本 800+ 条目）
- 患者描述 80% 以上是模糊 / 多症状混合，单轮抽取覆盖不了
- 缺少 RAG（检索 NCCN/ESMO 指南原文）来生成更精准的 rationale

### 2.2 没有真正的"学习"环节

**现状**：`case_review` 表设计了，自动 flag 7 类触发源也设计了，但 MVP 实际**只 print 日志**，没真写表。

**为什么这是缺陷**：
- 没有 case_review，L3 学习闭环就是空话
- Stretch 任务把它推后了，但**这是闭环的核心环节**

**生产差距**：
- 应有专门的 review dashboard（医生看到 queue + 一键标 verdict + 一键开 PR 改规则）
- 应有 outcome tracking（用户最终去医院了吗？医生诊断和系统建议一致吗？）
- 应有 prompt / dictionary / rule 的 A/B 测试基础设施（评估改动是否真的提升了准确率）

### 2.3 用户体验单薄

**现状**：
- 单轮输入，无追问
- 无登录态，写死 user_id
- LLM 失败的 checklist 兜底只设计了，前端没真实现 fallback UI
- 高风险时只在结果页加红色提示，没有真正的紧急 UX（不闪、不响、不发短信）

**生产差距**：
- 注册 + 登录 + 多设备同步
- 推送通知 / 短信 / 主动监测（用户连续 2 天没登录但前一次是 high 风险，应主动 follow-up）
- 移动端原生体验（医疗用户老年人多，浏览器 + Tailwind 默认样式不够友好）
- 多语言（粤语 / 闽南语等方言识别）
- 无障碍（视障 / 老年用户）

### 2.4 缺乏真正的临床验证

**现状**：
- 12 条规则是工程师从 CTCAE / NCCN 转写的，**没经过临床委员会签字**
- 20 条 smoke 语料是工程师人工构造的，**不是真实患者描述**
- 阈值（38.3°C / 14 天 / G2 等）直接用 CTCAE 数字，没和实际乳腺癌科室对齐

**生产差距**：
- 临床顾问委员会（≥3 名肿瘤科医生）签字每条规则
- IRB 批准的回顾性数据集（300+ 真实匿名病例）做精度评估
- 前向小规模试点（在 1-2 家医院的志愿患者中跑 3 个月，对比"系统建议 vs 医生建议"）
- 某些临界值（如 38.3 vs 38.0）应基于该医院的历史 FN 数据 calibrate，不是全国统一

### 2.5 安全 / 合规 / PHI

**现状**：基本没做。
- `.env` 含明文 API key
- 数据库密码明文 `sz_dev_password`
- 无 PHI 加密（DB 列、传输、备份）
- 无 audit log 谁访问了哪条 assessment
- 同意管理只设计了表，没强制执行（任何代码都能查任何用户数据）
- CORS 全开（开发模式）

**生产差距**：
- HIPAA / GDPR / 中国《个人信息保护法》合规审查
- DB 列加密（pgcrypto / Vault transit secret）
- TLS 1.3 全链路（含 DB 连接）
- WAF / DDoS / 速率限制
- BAA（Business Associate Agreement）签订（与所有 PHI 接触方包括 LLM provider）
- SOC 2 Type II 审计
- DPO（数据保护官）岗位
- 渗透测试

### 2.6 可观测性是骨架不是肌肉

**现状**：
- 5 个事件写 event_log 表 + stdout
- 没有仪表盘
- 没有报警
- 没有性能监控（p95 延迟 / DB 查询慢日志 / LLM 调用失败率）
- 没有 distributed tracing

**生产差距**：
- Grafana / Datadog 仪表盘（funnel: started → submitted → result_viewed → contact_team_clicked）
- PagerDuty 报警（high-risk 评估处理失败、LLM provider 整体不可用、DB 主从延迟过高）
- OpenTelemetry trace 串起 frontend → API → LLM → DB
- 业务指标（每日评估量 / 各风险级分布 / case_review queue 积压）

### 2.7 测试只覆盖了 happy path

**现状**：
- 47 个单元测试（M3 + M5 + M6 + M7）
- 20 个 smoke 语料
- 几乎全是 happy path

**生产差距**：
- 性能测试（100 并发提交 / DB 连接池耗尽 / LLM 限流）
- 混沌工程（kill DB 中途的 Tx2 → 数据一致性如何）
- 故障注入（LLM 返回畸形 JSON / DeepSeek 5xx 持续 5 分钟）
- 压测（每秒 100 个评估能不能扛）
- 跨浏览器测试（前端只在 Chrome 测过）

### 2.8 部署 / 运维空白

**现状**：本地 brew 装 Postgres 跑 uvicorn，**没任何部署能力**。

**生产差距**：
- Dockerfile + docker-compose for staging
- Kubernetes manifests + Helm chart
- GitHub Actions / GitLab CI（PR 触发测试、main 触发部署）
- 蓝绿 / 金丝雀部署
- 数据库备份 / 灾备 / 恢复演练
- 多区域 / 多 AZ
- 监控指标导出（Prometheus）
- 日志聚合（Loki / ELK）

### 2.9 数据飞轮空有设计没数据

**现状**：consent 表建了，三方关系（患者-医院-药企）画了图，但**实际没有任何数据流出过**。

**生产差距**：
- 真实接入 1-2 家医院（医生工作流嵌入）
- 至少 1 家药企的 PV（药物警戒）数据合作合同
- IRB 批准的脱敏管道（k-anonymity ≥ 20 的 SQL 视图）
- 第三方审计（数据治理 / 合规）
- 数据使用说明书（用户可看到自己数据被用于什么）

---

## 3. 架构层面的隐藏风险

### 3.1 Schema 与 ORM 模型双源真理

**已发现**：M2 阶段写了 User + Assessment 两个 ORM，schema.sql 后续加了 `idempotency_key` / `decision_status` 字段没回头同步。M6 agent 修了，但**根因还在**。

**应做**：
- 用 alembic autogenerate 反向生成迁移（ORM 是真理）
- 或用 sqlc / sqlmodel 等工具单源生成
- CI 加一步 `pytest schema_drift_test`

### 3.2 LLM 抽取不是真的"agent"

**坦白讲**：MVP 的"智能体"严格说是 **agentic workflow**，不是 **autonomous agent**：
- 决策路径固定（extract → check → evaluate → decide）
- LLM 不能决定"我需要查指南"或"我要追问用户"
- 没有 tool use（虽然 Anthropic SDK 支持）

**未来方向**：
- 把 RAG（NCCN 指南检索）作为 LLM 的工具
- 让 LLM 主动追问（slot filling 用 tool call 实现）
- 多 agent 协作（症状抽取 + 药品交互检查 + 病史 RAG 三个 agent）
- 但仍要 keep on rails：决策（risk level）永远由规则引擎，不让 LLM 直接判

### 3.3 规则引擎的可表达性瓶颈

**现状**：YAML + 6 个 operator (`gte/lte/lt/gt/eq/in`)，能表达约 80% 的规则。
剩下 20% 是含**时序**和**派生量**的：
- "过去 72 小时疲劳趋势 + 当前 G2" → 需要 SQL 视图 + 派生字段
- "化疗后 14 天 vs 28 天的不同阈值" → 需要分段函数

**未来**：
- 接 [Drools](https://www.drools.org/) 或 [json-logic](https://jsonlogic.com/) 做更强表达
- 但要小心不让规则 DSL 太图灵完备，否则 reviewer 看不懂规则是审计噩梦

### 3.4 Plan D 的"sliding"风险

**现状**：Plan D = 评估全部 + 决策一条 + 审计全部。Primary 取 `max(risk) + min(priority)`。

**潜在问题**：当多条规则在同一 risk level 命中时，priority 选哪条决定了用户看到的建议。
如果 R012 (G2 周围神经病变 → 联系团队) 和 R030 (疲劳趋势加重 → 联系团队) 都命中，
用户只看到 R012 的建议文本，**R030 在审计里但用户不知道**。

**未来**：
- advice 渲染层应能合并多条建议（"您的症状有两点需要注意：1) ..., 2) ..."）
- 或者在结果页折叠区显式列出"本次评估还触发了 N 条次级规则"

### 3.5 同意管理是空架子

**现状**：`consent` 表建了，`ConsentScope` enum 有 4 种，但**没有任何代码真的查 consent 才放数据出去**。

**反过来风险**：现在的 SQL 查询全部能跨用户拿数据。如果未来真的接入聚合查询（药企报表），
忘了加 consent check 就会越权。

**未来**：
- 抽出 `ConsentGuard` 中间件，所有出库 SELECT 强制过它
- DB 层 RLS（Row-Level Security）兜底
- 单元测试覆盖每个 scope 的越权场景

---

## 4. 短期改进路线（按优先级）

### P0（前 30 天必须做）

1. **真实临床顾问签字 rules.yaml**：找肿瘤科医生 review 12 条规则的阈值
2. **PHI 加密 at rest**：DB 列加密（pgcrypto），密钥进 Vault
3. **同意管理强制执行**：实现 `ConsentGuard.can_share()`，所有跨用户查询过它
4. **CI 跑测试**：GitHub Actions 触发 unit + integration 测试（不跑 smoke）
5. **history 接口 + 历史页接通**：完成最后 15% 的功能要求

### P1（30-90 天）

1. **Slot filling 真实实现**（CompletenessChecker → ClarificationNeeded → 前端追问 UI）
2. **case_review 自动 flag 真写库**（不只是 print）+ 简单的医生 review dashboard
3. **多轮对话支持**（assessment_session 表 + 前端会话 UI）
4. **真实 smoke 语料**（IRB 批准 50 条匿名真实患者描述替换工程师构造的 20 条）
5. **Docker 化 + CI/CD 流水线**（staging 环境）
6. **观测仪表盘**（Grafana + 漏斗 + 报警）

### P2（90 天+，需要业务推进）

1. **临床试点**：1 家医院 / 50 患者 / 3 个月对比研究
2. **NMPA 二类医疗器械软件注册** 准备（如果定位为 CDSS）
3. **药企数据合作**（PV 数据上报，签 BAA / DUA）
4. **多模态**（皮疹照片 / 检验报告 PDF）
5. **领域微调模型**（如果通用 LLM + RAG 还不够准）

---

## 5. 一句话总结

**做出来的部分**：合规友好的医疗 CDSS 骨架，决策路径完全可审计，扩展和改造空间清晰。

**没做的部分**：真正的临床对齐、安全合规硬功夫、用户体验深度、生产可运维。

**MVP 的真正价值不在于"做完了多少"，在于"建立了多少能让后续工作变快的资产"**：
- 数据模型确定（`schema.sql` 11 表 + 1 视图）
- 决策路径定型（LLM 翻译 + 规则判官 + L3 学习）
- 任务卡和协作模式可复用（worktree + 负向约束 + stacked PR）
- 设计文档显式（每个决策都能反查为什么）

接下来的 30/90/365 天，**每一步增量都是在稳定地基上加层**，而不是返工重做。
