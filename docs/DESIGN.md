# 乳腺癌副作用智能体 MVP — 设计文档

> Version: 1.1.0
> Last Updated: 2026-05-06
> Status: 设计完成，骨架就绪

---

## 目录
1. [业务背景与目标](#1-业务背景与目标)
2. [功能要求](#2-功能要求)
3. [关键架构决策](#3-关键架构决策)
4. [系统架构图与数据流](#4-系统架构图与数据流核心问题1)
5. [感知-决策-执行-学习闭环](#5-感知-决策-执行-学习闭环核心问题2)
6. [数据模型](#6-数据模型)
7. [API 契约](#7-api-契约)
8. [规则引擎](#8-规则引擎)
9. [可观测性（5 个核心事件）](#9-可观测性5-个核心事件)
10. [审计与合规](#10-审计与合规)
11. [Base / Advanced 子方案](#11-base--advanced-子方案)
12. [数据飞轮（三方关系）](#12-数据飞轮三方关系)
13. [MVP 与终态产品的差距](#13-mvp-与终态产品的差距)
14. [Bad Cases 审核机制（L3 学习闭环）](#14-bad-cases-审核机制l3-学习闭环)
15. [幂等性与一致性保证](#15-幂等性与一致性保证)

---

## 1. 业务背景与目标

为乳腺癌患者提供副作用自评工具，输入自然语言描述后返回：

- **风险等级**（高/中/低）
- **下一步建议**（人话）
- **是否建议联系团队**（布尔 + 紧急度）
- **简单依据说明**（命中规则 + 来源 + 时间戳 + 版本号）

**约束**：MVP 阶段不替代医生决策，仅做分诊辅助。所有"高风险"建议都默认导向"联系团队/急诊"。

---

## 2. 功能要求

### 前端页面
- **输入页**：自由文本框 + LLM 失败时的 checklist 兜底
- **结果页**：风险等级 + 建议 + 联系团队按钮 + 审计折叠区
- **历史记录页**：按时间倒序的评估列表

### 后端接口（详见 [§7](#7-api-契约)）
- `POST /assessments` — 提交评估
- `GET /assessments/{id}` — 获取结果
- `GET /users/{id}/assessments` — 获取历史
- `POST /contact-requests` — 创建协同请求

### 风险分层
| 等级 | 建议 |
|---|---|
| 高 | 立即线下就医 / 24h 内联系团队 |
| 中 | 联系团队（48h 内）或密切观察 |
| 低 | 继续观察与记录，下次复诊反馈 |

### 数据存储（详见 [§6](#6-数据模型)）
覆盖：assessment / advice / evidence / rule_source / event_log
扩展：consent / symptom_dictionary / symptom_observation / contact_request

### 可观测性
5 个核心事件埋点（详见 [§9](#9-可观测性5-个核心事件)）

### 审计
每次结果可追溯：命中哪条规则 + 生成时间 + 版本号（详见 [§10](#10-审计与合规)）

---

## 3. 关键架构决策

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| 1 | 决策层方案 | LLM 抽取 + 规则决策 | 决策可审计，LLM 不参与高风险判断 |
| 2 | LLM 抽取兜底 | 降级 checklist | 即使 LLM 不可用系统仍能工作 |
| 3 | 时序能力 | Base + Advanced 双子方案，feature flag 切换 | MVP 先稳，后扩展 |
| 4 | 规则来源 | 工程基于 CTCAE 5.0 写初版 | 起步快，后期再请临床委员会 review |
| 5 | 同意模型 | 分层默认 + 渐进式询问 | 平衡 UX 与合规 |
| 6 | Orchestrator 事务边界 | 抽取 / 决策 独立事务 | 已抽取症状即使决策失败也不丢 |
| 7 | 规则引擎冲突解决 | 评估全部 / 决策一条 / 审计全部 | 临床 CDSS 标准模式：最高风险定行动，所有命中入审计 |
| 8 | 埋点失败策略 | 普通事件 fetch+keepalive，关闭事件 sendBeacon | 兼顾简单性与"关页面也能发出" |
| 9 | 幂等性 | 前端 UUID + DB UNIQUE(user_id, idempotency_key) | 防重复提交污染时序分析 |
| 10 | Bad case 沉淀 | `case_review` 表 + 7 类触发源 | L3 学习闭环的具体落地 |

---

## 4. 系统架构图与数据流（核心问题①）

### 组件拓扑

```
┌──────────────────────────────────────────────────────────────────────┐
│                          用户端 (React/Vue)                          │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐      │
│  │  输入页      │   │  结果页      │   │  历史记录页          │      │
│  │ free-text +  │   │ risk + advice│   │ 时间倒序列表         │      │
│  │ checklist 兜底│   │ + 审计区    │   │                      │      │
│  └──────┬───────┘   └──────┬───────┘   └──────────┬───────────┘      │
└─────────┼──────────────────┼──────────────────────┼──────────────────┘
          │ POST /assessments│ GET /assessments/{id}│ GET /users/.../assessments
          │                  │ POST /contact-requests│
          ▼                  ▼                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       后端服务层 (FastAPI / NestJS)                   │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ ① Orchestrator（编排器）                                       │ │
│  │   控制流: 抽取 → 兜底 → 决策 → 写库 → 埋点 → 返回             │ │
│  └─────┬────────────────────┬────────────────────────┬──────────┘ │
│        ▼                    ▼                        ▼            │
│  ┌──────────────┐   ┌──────────────────┐   ┌─────────────────┐   │
│  │ ② LLM 抽取   │   │ ③ 规则引擎       │   │ ④ 同意检查      │   │
│  │ Claude API   │   │ YAML + Engine    │   │ Consent Guard   │   │
│  │ + JSON Schema│   │ priority 短路    │   │ 出站数据校验    │   │
│  │ + 词表 grounding│   │ Base/Advanced   │   │                 │   │
│  └─────┬────────┘   └─────┬────────────┘   └────────┬────────┘   │
│        │                  │                          │             │
│        ▼                  ▼                          ▼             │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ ⑤ 持久化层（Repository Pattern）                         │    │
│  └──┬─────────────────────────────────────────────────────┬─┘    │
└─────┼─────────────────────────────────────────────────────┼──────┘
      │                                                     │
      ▼                                                     ▼
┌────────────────────────────────────────┐    ┌───────────────────────┐
│  PostgreSQL 主库                       │    │  事件总线 (Kafka /    │
│  ┌──────────────┐  ┌──────────────┐    │    │   Redis Stream)       │
│  │ assessment   │  │ symptom_obs  │    │    │  ─────────────────── │
│  │ advice       │  │ consent      │    │    │  5 个核心事件         │
│  │ evidence     │  │ contact_req  │    │    │  → event_log          │
│  │ rule_source  │  │ users        │    │    │  → 实时仪表盘         │
│  │ symptom_dict │  └──────────────┘    │    └───────────────────────┘
│  │ event_log    │                      │
│  └──────────────┘                      │
│  视图: v_user_trend_7d (Advanced)      │
└────────────────────────────────────────┘
```

### 主路径数据流（一次评估的完整生命周期）

```
[用户在输入页打字]
  └─→ 前端发起 event: assessment_started   ──→ event_log
[用户点提交]
  └─→ POST /assessments {raw_input_text}
       └─→ 前端发起 event: assessment_submitted ──→ event_log
       │
       ├─→ Orchestrator 收到请求
       │     │
       │     ├─→ ② LLM 抽取（Claude + symptom_dictionary 词表 grounding）
       │     │     ├─ 成功 → 结构化 JSON (symptoms[], context{})
       │     │     └─ 失败 → 返回 422 + checklist URL → 用户重新提交
       │     │
       │     ├─→ 写入 assessment 表（含 raw_input、parsed_symptoms JSONB）
       │     │   写入 symptom_observation 表（规范化症状，N 行）
       │     │
       │     ├─→ ③ 规则引擎 evaluate(symptoms, context [, trends if Advanced])
       │     │   ├─ 按 priority 升序匹配，首条命中即停
       │     │   └─ 返回 {risk_level, matched_rule, rationale, advice_template}
       │     │
       │     ├─→ 写入 evidence 表（命中规则 + 版本 + matched_fields）
       │     │   写入 advice 表（渲染后的建议文本）
       │     │
       │     └─→ 返回 AssessmentResult (含审计三件套)
       │
       └─→ 前端展示结果页
            └─→ 发起 event: result_viewed ──→ event_log

[用户点"联系团队"]
  └─→ POST /contact-requests
       ├─→ 写入 contact_request 表
       └─→ 发起 event: contact_team_clicked ──→ event_log

[用户离开/超时]
  └─→ event: assessment_closed ──→ event_log
```

### 关键架构原则

1. **决策路径里 LLM 永远不直接产生风险等级** —— LLM 只做"自然语言 → 结构化数据"的翻译，决策在规则引擎
2. **审计数据自包含** —— evidence 表里冗余存当时的 rule_yaml 快照和 rationale，未来规则改了也能复盘
3. **同意检查在出站数据流上** —— 任何把数据发给"主治团队以外"的接收方前，必须过 Consent Guard
4. **业务事实表与行为事件表正交** —— 用户开页面没提交也要在 event_log 留痕，但 assessment 不写

---

## 5. 感知-决策-执行-学习闭环（核心问题②）

### 闭环全景

```
       ┌───────────────────────── 学习 (L3 主导) ─────────────────────────┐
       │  人在回路：临床委员会 review event_log + evidence → 改 YAML/Prompt │
       │  反哺到 → 规则版本 +1 → 字典扩充 → Prompt 迭代                    │
       │            │              │              │                       │
       └────────────┼──────────────┼──────────────┼───────────────────────┘
                    ▼              ▼              ▼
   ┌────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
   │ 用户   │─▶│  感知    │─▶│  决策    │─▶│  执行    │─▶│  反馈    │
   │ 输入   │  │ Sense    │  │ Decide   │  │ Act      │  │ 收集     │
   └────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
                  LLM 抽取    规则引擎      写库+埋点+    event_log
                  词表 grounding  YAML+短路   通知工具      用户行为
                  checklist 兜底  versioned   contact_team   依从性
```

### 各环节实现与技术选型

#### ① 感知 (Sense) — 自然语言 → 结构化症状

**目标**：把患者的自由描述转成 `(symptom_id, value, grade, context)` 元组列表。

| 维度 | 选型 | 理由 |
|---|---|---|
| 模型 | Claude Sonnet 4.6（API） | 中文医疗术语理解强，JSON 输出稳定 |
| 输出约束 | JSON Schema（响应结构强制） | 消除"自由发挥"，便于 schema 验证 |
| 词表 grounding | Prompt 中嵌入 `symptom_dictionary` 全表 | 强制 LLM 把症状映射到固定 ID，降低幻觉 |
| 失败兜底 | 降级到 checklist 表单 | 抽取失败时返回 422，前端展示固定症状清单让用户勾选 |
| 抽取置信度 | 由 LLM 自评 + 阈值过滤 | `extraction_confidence < 0.6` 自动走 checklist |
| Prompt 版本管理 | 写死在代码 + 版本号字段 | `extraction_model_version` 字段记录到 assessment |

**Prompt 骨架**（节选）：
```
你是一个临床症状抽取助手。请从用户描述中识别症状，
严格映射到下表 ID 之一（不在表中的症状必须丢弃）：
{symptom_dictionary_table}

输出 JSON:
{
  "symptoms": [{"symptom_id": ..., "numeric_value": ..., "ctcae_grade": ...}],
  "context": {"days_since_chemo": ...},
  "confidence": 0.0-1.0
}
```

#### ② 决策 (Decide) — 规则引擎

**目标**：根据结构化症状 + 用户上下文，确定风险等级和建议模板。

| 维度 | 选型 | 理由 |
|---|---|---|
| 引擎形态 | 自研轻量级 YAML rule engine | 业务规则少（<100 条），引入 Drools 等过重 |
| 匹配策略 | priority 升序，首条命中即停 | 临床决策逻辑清晰，可预测 |
| 规则来源 | CTCAE v5.0 + NCCN 指南，工程转写 | (a) 方案，待临床委员会 review |
| 版本管理 | rule_id + rule_version 联合主键 | 每次规则改动 bump version，老评估查老版本 |
| 兜底规则 | `R999_default_unmatched` → 中风险 + 联系团队 | 不命中具体规则时偏保守 |
| Advanced 时序 | 视图 `v_user_trend_7d` + `requires_feature: timeseries` 标记 | feature flag 控制启用 |

#### ③ 执行 (Act) — 写库 + 通知 + 工具调用

**目标**：把决策结果落地为可观测、可联动的"动作"。

| 动作 | 实现 |
|---|---|
| 写入 assessment / symptom_observation / advice / evidence | 一个数据库事务，保证原子性 |
| 渲染建议文本 | 模板引擎（Jinja2 / EJS），从 advice_templates 取文本 |
| 触发埋点 | 异步发到事件总线（Kafka/Redis Stream），不阻塞主路径 |
| 高风险时主动提示 | 结果页强制弹窗 + "联系团队"按钮置顶 |
| 创建 contact_request | 用户主动点击时写入 contact_request 表，未来可触发短信/IM |

#### ④ 学习 (Learn) — 主要是 L3（人在回路），不涉及训练

**坦白讲：MVP 几乎没有"自动学习"**。但闭环的"学习"环节通过下面几个机制体现：

| 层次 | MVP 做什么 | 数据来源 |
|---|---|---|
| **L1** 会话内记忆 | 不做（单次评估独立） | — |
| **L2** 用户长期记忆 | Advanced 子方案的时序视图就是一种 L2 | symptom_observation 历史 |
| **L3** 离线人在回路（核心） | 临床委员会每周/月 review，改 YAML 或 prompt | event_log + evidence + 用户反馈 |
| **L4** 模型训练 | **MVP 不做** | — |

**L3 的具体动作**（详见 [§14 Bad Cases 审核机制](#14-bad-cases-审核机制l3-学习闭环)）：
1. 系统自动 flag 异常评估到 `case_review` 表（低置信度 / 抽取失败 / 兜底命中 / 高风险无后续行动）
2. 用户主动 flag（结果页 👎 按钮）也写入 `case_review`
3. 仪表盘聚合 `event_log`：哪些用户提交后没看结果就走了？哪些规则触发率突增？
4. 临床委员会从 `case_review` 队列定期评审，标注 verdict
5. 输出：新版 `rules.yaml` (rule_engine_version +1) / 新版 prompt (extraction_model_version 更新) / 字典扩充
6. `corrective_action` 字段回写到原 case_review 行，闭环完成

> **关键认知**：LLM 时代的"智能体学习"不是梯度更新，是**改 prompt、改规则、改工具**。涉及的不是"训练数据"，而是"评估数据集"（eval set）—— 用来回归测试 prompt/规则改动是否让效果变差。

---

## 6. 数据模型

完整 SQL 见 [`data_model/schema.sql`](data_model/schema.sql)。

### ER 关系图

```
┌──────────────┐                       ┌────────────────────┐
│    users     │                       │ symptom_dictionary │ ◀── 受控词表
└──────┬───────┘                       └─────────┬──────────┘
       │ 1:N                                     │ 1:N
       ├──────────────────────────────┐          │
       ▼                              ▼          ▼
┌──────────────┐  1:N         ┌──────────────────────┐
│  assessment  │ ─────────────▶│ symptom_observation │
│  (含原始     │              │  (规范化症状记录)    │
│  parsed_     │              └──────────────────────┘
│  symptoms    │                          ▲
│  审计快照)   │                          │
└──────┬───────┘                          │
       │ 1:N                              │
       ├─────────────┬──────────────┐     │ 聚合视图
       ▼             ▼              ▼     │
   ┌────────┐  ┌──────────┐  ┌────────────────┐
   │ advice │  │ evidence │  │ contact_request │
   └────────┘  └─────┬────┘  └────────────────┘
                     │
                     │ 软引用 (rule_id + version)
                     ▼
              ┌──────────────┐
              │ rule_source  │ ◀── 规则版本 + YAML 快照
              └──────────────┘

独立表:
  consent       (数据飞轮的法律边界)
  event_log     (5 个核心事件，与业务表正交)
视图:
  v_user_trend_7d (Advanced 时序，按需聚合)
```

### 7+ 张表的职责

| 表 | 职责 | 关键设计 |
|---|---|---|
| `users` | 用户主档 + 临床上下文 | 含 `last_chemo_at` 用于规则计算 days_since_chemo |
| `symptom_dictionary` | 受控词表 | LLM 抽取的目标空间，含 aliases 用于 grounding |
| `assessment` | 一次评估主记录 | `parsed_symptoms` JSONB 保留原始抽取，用于审计 |
| `symptom_observation` | 规范化症状记录 | 一次评估 N 行，决策和分析的事实层 |
| `advice` | 渲染后的建议 | 与模板解耦，便于事后修订 |
| `evidence` | 审计核心 | 记录命中规则 + 版本 + matched_fields + rationale |
| `rule_source` | 规则版本管理 | 含完整 YAML 快照，3 年后也能复盘 |
| `contact_request` | 协同请求 | 用户点"联系团队"时创建 |
| `event_log` | 5 个核心事件 | 与业务表正交，不写主流程 |
| `consent` | 同意管理 | 一行一个 (user, scope, recipient) |
| `v_user_trend_7d` | 时序视图（Advanced） | 视图按需算，不缓存 |

---

## 7. API 契约

完整 OpenAPI 规范见 [`api/openapi.yaml`](api/openapi.yaml)。核心 4 个接口：

| 方法 | 路径 | 功能 | 关联埋点 |
|---|---|---|---|
| POST | `/assessments` | 提交评估 | `assessment_submitted` |
| GET | `/assessments/{id}` | 获取结果 | `result_viewed` |
| GET | `/users/{id}/assessments` | 获取历史 | — |
| POST | `/contact-requests` | 创建协同请求 | `contact_team_clicked` |

### `AssessmentResult` 响应中的"审计三件套"

```json
{
  "assessment_id": "...",
  "risk_level": "high",
  "advice": {...},
  "audit": {
    "matched_rules": [
      {
        "rule_id": "R001_febrile_neutropenia_suspected",
        "rule_version": "1.0.0",
        "source_doc": "CTCAE v5.0 §General + NCCN FN 2024",
        "matched_fields": {"temperature_c": 38.5, "days_since_chemo": 3},
        "rationale_text": "化疗后14天内出现≥38.3°C发热，需立即排除..."
      }
    ],
    "generated_at": "2026-05-06T15:32:11Z",
    "rule_engine_version": "1.0.0",
    "extraction_model_version": "claude-sonnet-4.6@2026-04"
  }
}
```

→ 满足审计要求："命中哪条规则 + 时间 + 版本号"。

---

## 8. 规则引擎

完整规则集见 [`rules/rules.yaml`](rules/rules.yaml)。

### 规则分布（MVP 起步集）

| 风险等级 | 规则数 | 示例 |
|---|---|---|
| 高（HIGH） | 4 | 化疗后发热、严重呼吸困难/胸痛、严重腹泻 |
| 中（MEDIUM） | 3 | G2+ 手足综合征、持续呕吐 >24h、G2+ 周围神经病变 |
| 低（LOW） | 3 | 轻度恶心、轻度疲劳、轻度潮热 |
| Advanced 时序 | 1 | 疲劳趋势恶化（feature flag 控制） |
| 兜底 | 1 | R999 未匹配 → 中风险 + 联系团队 |

### YAML schema 关键字段

```yaml
rules:
  - id: R001_xxx              # 唯一，含编号便于检索
    priority: 1               # 数字越小越优先
    source: "CTCAE v5.0 §..."  # 来源文档（必填，写入 evidence）
    requires_feature: ...     # 可选，feature flag 门控
    when:
      all_of: [...]           # 全部满足
      any_of: [...]           # 任一满足
      always: true            # 兜底
    risk: high|medium|low
    advice_template: tpl_xxx  # 引用 advice_templates
    contact_team: true|false
    urgency: now_24h|this_week|next_visit
    rationale: |              # 给用户看的人话依据
```

---

## 9. 可观测性（5 个核心事件）

| 事件 | 触发时机 | Payload 关键字段 | 业务用途 |
|---|---|---|---|
| `assessment_started` | 用户进入输入页 | `user_id, session_id` | 漏斗第 1 步 |
| `assessment_submitted` | 点击提交，**结果未出** | `+ input_length, input_hash` | 漏斗第 2 步，提交意愿 |
| `result_viewed` | 结果页渲染完成 | `+ assessment_id, risk_level, latency_ms` | 漏斗第 3 步 + 性能监控 |
| `contact_team_clicked` | 用户点"联系团队" | `+ assessment_id, risk_level` | **关键转化**——建议是否被采纳 |
| `assessment_closed` | 离开/超时 | `+ duration_ms, last_step` | 完成率 + 流失定位 |

**与业务表的关系**：
- 一次完整评估在 `assessment` 表里 1 行，但在 `event_log` 里可能 5 行
- 用户开页面就走（流失），`event_log` 有 1 条 `assessment_started` 但 `assessment` 表为空
- 这是分析"为什么用户不愿意提交"的核心数据来源

---

## 10. 审计与合规

### 审计三件套（业务硬要求）

| 要求 | 实现位置 |
|---|---|
| 命中哪条规则 | `evidence.rule_id` + `evidence.rule_version` + `rule_source.rule_yaml`（快照） |
| 生成时间 | `assessment.created_at` + `evidence.matched_at` |
| 版本号 | `assessment.rule_engine_version` + `assessment.extraction_model_version` |

### 同意模型（方案 C — 分层默认 + 渐进式询问）

完整代码见 [`data_model/consent.py`](data_model/consent.py)。

```
ConsentScope:
  CLINICAL_CARE_ONLY       (默认开 — 注册即勾选，否则无法工作)
  REGULATORY_PV_REPORTING   (默认开 — 法律强制，但必须告知)
  DEIDENTIFIED_RESEARCH     (默认关 — 用户进入研究页时弹窗询问)
  AGGREGATED_INDUSTRY       (默认关 — 每次新合作方接入重新询问)
```

**核心约束**：每次数据出站前必须过 `can_share()` 函数。`AGGREGATED_INDUSTRY` 类授权必须精确到 `data_recipient_class`（如 `pfizer_aromasin_rwe_2026`），不能用泛化"对药企"授权覆盖新合作方。

### PHI 数据分层

| 层 | 内容 | 谁能看 |
|---|---|---|
| Layer 1 | 个体可识别数据 (PHI) | 主治团队，平台内部访问全审计 |
| Layer 2 | 去标识化的个体记录 | IRB 审批后的科研项目 |
| Layer 3 | 聚合统计 | 药企（仅匿名汇总） |

---

## 11. Base / Advanced 子方案

| 维度 | Base | Advanced |
|---|---|---|
| 决策输入 | 仅当前次 assessment | + 同用户最近 7 天 symptom_observation |
| 规则形态 | when 子句仅引用当前症状 | when 子句可引用 `trend.*` |
| 数据库改动 | 无 | 启用视图 `v_user_trend_7d` |
| 触发开关 | `FEATURE_TIMESERIES=false` | `FEATURE_TIMESERIES=true` |
| 风险 | 漏掉"温水煮青蛙"型恶化 | 多一层视图查询 |
| 临床价值 | 基础分诊够用 | 显著提升慢性副作用识别 |

**实现策略**：同一份代码，规则引擎在 evaluate 时根据 feature flag 决定是否注入 trends 上下文。

---

## 12. 数据飞轮（三方关系）

### 三方付出与收获

| 角色 | 付出 | 收获 | 动机 |
|---|---|---|---|
| 患者 | 症状/依从性数据 | 24h 分诊工具、心理安全感 | 求生欲 + 实用价值 |
| 医院/医生 | 规则审核、工作流嵌入 | 减少夜间电话、随访效率、科研产出 | 减负 + 论文 |
| 药企 | **付费**（订阅 / 数据合作） | RWE、AE 上报、依从性洞察、试验招募 | 法规合规 + 商业 KPI |

### 飞轮的四个咬合循环

```
循环 1 (患者价值)：用户输入 → 分诊准确 → 用户留存 → 更多数据
                                                  │
循环 2 (临床价值)：积累数据 → 医生看到模式 → 改规则 → 分诊更准 → 更多医生信任
                                                  │
循环 3 (药企价值)：海量结构化 AE → RWE 报告 → 说明书更新/医保扩面 → 药企续费
                                                  │
循环 4 (数据价值)：药企付费 → 反哺工程 + 临床团队 → 规则更精 + 字典更全 → 循环 1 加强
```

### 合规边界

- 药企永远看不到 Layer 1 PHI
- IRB 审批 + 用户同意是 Layer 2 数据访问的硬前提
- 任何 Layer 3 聚合查询必须有 k-anonymity 阈值（如至少 N 个用户）
- 规则委员会独立于药企，规则版本和来源公开

---

## 13. MVP 与终态产品的差距

| 维度 | MVP（这次） | 终态产品 |
|---|---|---|
| LLM 角色 | NL→JSON 翻译器 | 多轮对话 + 工具调用 + 推理 |
| 症状本体 | 12 条起步集 | SNOMED CT / 完整 CTCAE |
| 规则覆盖 | 11 条 (CTCAE 转写) | 数百条 + 临床委员会持续维护 |
| 决策依据 | 朴素 rationale 文本 | RAG 引用 NCCN/ESMO 指南原文 |
| 个性化 | 无 | 化疗方案、合并症、过敏史、既往副作用 |
| 时序 | Advanced 子方案（7 天窗口） | 滚动窗口分析、恶化趋势检测、主动预警 |
| 多模态 | 仅文本 | 上传皮疹照片、检验报告 PDF |
| 数据飞轮 | 仅 event_log | 标注集 → 反哺 prompt / 微调小模型 |
| 模型 | 通用 LLM | 通用 + RAG + 可选垂域微调 |
| 评估体系 | 无 | eval set + A/B 测试 + 临床安全监控 |
| 合规 | 同意模型 + 数据分层 | + HIPAA/GDPR/PIPL 全面合规 + 医疗器械注册 |

### 关键差距：AI 应用的"粗糙感"是真实的

MVP 阶段 LLM 仅作 NLP 翻译器，90% 的"智能"藏在医生写的规则里。这不是 bug 而是**故意的工程选择**：

- 医疗决策必须可审计 → 规则比 LLM 更适合
- 临床责任必须可追溯 → 规则版本号比模型版本更易管理
- 数据飞轮转起来才能进化 → 没有数据就没有微调

通向终态的关键资产（按重要性排序）：
1. **临床标注数据集** ⭐⭐⭐⭐⭐（最贵）
2. **领域指南语料 + RAG 系统** ⭐⭐⭐⭐
3. **垂域微调模型** ⭐⭐⭐（优先级最低，因为通用 LLM 已够强）

---

## 14. Bad Cases 审核机制（L3 学习闭环）

§5 提到的"L3 离线人在回路"在数据层的具体落地是 `case_review` 表。任何"系统输出可能有问题"的评估都流入这张表，由临床委员会定期 review，输出形成 PR 改回 `rules.yaml` / prompt / 字典。

### 7 类触发源

| 来源 | 谁触发 | 触发条件 |
|---|---|---|
| `auto_low_confidence` | 系统 | LLM 抽取置信度 < 0.6 |
| `auto_extraction_failed` | 系统 | LLM 抛错或返回非法 JSON |
| `auto_outcome_mismatch` | 系统 | 同用户 24h 内：先 low 后 high 且症状重合 |
| `auto_repeat_high_no_action` | 系统 | 高风险结果但用户连续 3 次未点联系团队 |
| `auto_default_rule_hit` | 系统 | R999 兜底规则被触发（说明字典/规则有空白） |
| `user_disagreement` | 用户 | 结果页 👎 按钮 + 可选文本反馈 |
| `clinician_flag` | 临床团队 | 临床 dashboard 标"这个判断有问题" |

### 审核流转

```
   每次评估
      │
      ├─→ 满足任一 auto trigger 条件？
      │      └─→ INSERT INTO case_review (status='pending')
      │
      └─→ 用户在结果页点 👎？
             └─→ INSERT INTO case_review (trigger='user_disagreement')

   每周/每月：
      ├─→ 临床委员会从 case_review 队列取 batch（按触发源/创建时间）
      ├─→ 标注 verdict + 决定改动:
      │       'correct' / 'should_be_higher_risk' / 'should_be_lower_risk' /
      │       'extraction_wrong' / 'rule_gap' / 'dictionary_gap'
      ├─→ 形成 PR（rules.yaml / prompt / dictionary）
      └─→ 合入后回写 corrective_action
```

### 与其他表的关系

```
assessment ──┐
             ├──▶ case_review ──▶ (review_verdict + corrective_action)
event_log ───┘                         │
                                       ▼
                          指向具体 PR / config 变更
```

### 待你决策的阈值

代码里有几个数值是临床/产品决策，不是工程决策：

- LLM 置信度阈值（当前默认 0.6）
- "outcome mismatch" 的时间窗（当前 24h）
- "repeat high no action" 的次数（当前 3 次）

这些建议在临床委员会成立后由医生定。

---

## 15. 幂等性与一致性保证

### 重复提交对数据完整性的威胁

如果用户网络抖动连点两次"提交"，没有幂等保护时会污染：

| 表 | 影响 |
|---|---|
| `assessment` | 2 行（看似两次评估，实为一次意图） |
| `symptom_observation` | **2N 行同样的症状** |
| `v_user_trend_7d` | **发热 episode_count 翻倍** ← 直接误导 Advanced 趋势分析 |
| `evidence` | 2 套规则命中记录 |

### 双层幂等防御

**第一层：前端按钮防御**
- 点击后立即 `disabled`
- 进入页面时一次性生成 `idempotency_key`，整个评估周期内复用同一个 key

**第二层：API + 数据库幂等键**
- 前端为每次评估生成 UUID 作为 `idempotency_key`
- API 层将 key 写入 `assessment.idempotency_key`
- 数据库 `UNIQUE INDEX (user_id, idempotency_key)` 保证唯一性
- 服务端遇到已存在的 key 直接返回首次结果（不重复调 LLM）

### 实现位置

- `frontend/src/pages/InputPage.tsx` — `useRef<string>(crypto.randomUUID())`
- `frontend/src/api/client.ts` — `Idempotency-Key` header + body 字段
- `backend/app/schemas/assessment.py` — `AssessmentRequest.idempotency_key`
- `docs/data_model/schema.sql` — `idx_assessment_idempotency` UNIQUE 索引
- `backend/app/services/orchestrator.py` — Step 0 幂等检查

`★ 临床安全考量`：医疗系统对幂等的要求比电商更严。重复提交导致医生看到 "2 次相同高烧记录" 可能误以为是 2 个独立 episode 而升级处置。

---

## 附：文件清单

```
breast_cancer_mvp/
├── DESIGN.md                       ← 本文件（主设计文档）
├── data_model/
│   ├── schema.sql                  ← 数据库 Schema（10 表 + 1 视图）
│   └── consent.py                  ← 同意模型代码（方案 C）
├── rules/
│   └── rules.yaml                  ← 规则引擎初版（11 条规则 + 4 模板）
└── api/
    └── openapi.yaml                ← 4 个 API 的 OpenAPI 契约
```
