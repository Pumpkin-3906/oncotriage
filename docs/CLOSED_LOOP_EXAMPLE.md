# OncoTriage — 感知 / 决策 / 执行 / 学习闭环（带追踪示例）

> Version: 1.0.0
> Last Updated: 2026-05-07
> 配套阅读: `DESIGN.md` §5 (闭环全景)，本文件用一个具体复杂案例把每个环节的实际行为追踪一遍。

---

## 0. 选这个案例的原因

直接选最简单的 *"化疗后第三天发烧38.5度"* 不能体现闭环价值——那是单症状、信息完整、规则秒命中。
我们用一个**多症状 + 时间相对表达 + 部分信息缺失 + 多规则同时命中**的案例：

```
"我是上周二开始第三个化疗周期的，本来还行，从前天开始手脚发麻越来越严重，
今天连扣扣子都困难了。还有点恶心，吃不下东西，感觉特别累。"
```

它会触碰到闭环的每一个环节，包括 CompletenessChecker、规则引擎 Plan D、双事务、bad case 自动 flag。

---

## 1. 感知 (Sense) — 自然语言 → 结构化症状

### 1.1 输入流转图

```
┌────────────────────────┐
│ 用户输入（自由文本）    │
│ "上周二开始第三个化疗   │
│  周期...扣扣子困难..."  │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────────────┐
│ POST /api/v1/assessments       │
│ + Idempotency-Key (UUID)       │
│ + session_id                   │
└───────────┬────────────────────┘
            │
            ▼
┌────────────────────────────────────────────────┐
│ Orchestrator.run()                              │
│   ├─ Step 0: 幂等查重 (UNIQUE 索引未命中 → 继续) │
│   ├─ Step 1: 加载 symptom_dictionary (12 条)   │
│   └─ Step 2: 调 LLMExtractor.extract(text, dict)│
└───────────┬────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────┐
│ LLMExtractor                                     │
│   ├─ 构造 system prompt：嵌入 12 条字典 grounding │
│   ├─ 通过 LLMClient 调 API（DeepSeek 或 Claude） │
│   ├─ 解析 JSON（兼容 ```json 围栏）              │
│   ├─ Pydantic schema 校验                        │
│   └─ 校验 symptom_id 全在字典里                  │
└───────────┬─────────────────────────────────────┘
            │
            ▼
ParsedSymptoms（结构化输出）
```

### 1.2 实际抽取结果

```json
{
  "symptoms": [
    {
      "symptom_id": "peripheral_neuropathy",
      "ctcae_grade": 2,
      "categorical_value": "moderate",
      "interferes_with_adl": true,
      "duration_hours": 48
    },
    {
      "symptom_id": "nausea",
      "ctcae_grade": 2,
      "categorical_value": "moderate"
    },
    {
      "symptom_id": "fatigue",
      "ctcae_grade": 2,
      "categorical_value": "moderate"
    }
  ],
  "context": {
    "days_since_chemo": 14
  },
  "confidence": 0.78
}
```

### 1.3 关键技术决策

| 决策 | 实现 | 理由 |
|---|---|---|
| **LLM 角色 = 翻译器，不当判官** | 输出严格映射到 `symptom_dictionary` 12 个 ID | 决策必须确定性 + 可审计（医疗器械注册要求）|
| **受控词表 grounding** | Prompt 中嵌入字典每条的 `id + display_name + aliases_zh` | 让 LLM 必须从 12 个 ID 选，降低幻觉 |
| **JSON Schema 强制** | Pydantic `ParsedSymptoms.model_validate()` | 结构错误立即 raise `LLMExtractionError` |
| **temperature=0.0** | settings.llm_temperature | 抽取要尽可能确定 |
| **Provider 抽象** | `LLMClient` 协议（Anthropic + OpenAI 兼容）| 可切换 DeepSeek/Qwen/本地 vLLM 不改代码 |
| **失败响亮** | 4 类失败均抛 `LLMExtractionError` | Orchestrator 据此决定降级 checklist |

### 1.4 时间相对表达的正确解析

输入 *"上周二开始第三个化疗周期"* + *"今天"* —— LLM 推断 `days_since_chemo=14`（约 2 周）。
这是 LLM 的强项之一（自然语言时间推理），用规则引擎写会很麻烦。

**注意**：即便 LLM 算错也不影响审计——规则会按它给的数字判断，错误命中会进 case_review。

---

## 2. 决策 (Decide) — CompletenessChecker → 规则引擎

### 2.1 完整性检查（MVP 仅日志，不阻塞）

```
CompletenessChecker.check(parsed)
  对每个 symptom 检查 value_type 要求的字段：
    ├─ peripheral_neuropathy (categorical) → 要 ctcae_grade 或 categorical_value
    │   → 都有 ✅ complete
    ├─ nausea (categorical) → 要 ctcae_grade 或 categorical_value
    │   → 都有 ✅ complete
    └─ fatigue (categorical) → 要 ctcae_grade 或 categorical_value
        → 都有 ✅ complete

CompletenessResult(is_complete=True, missing_slots=[])
```

> 假设输入改成 *"还发烧了"* 但没说度数 —— fever (numeric) 缺 numeric_value，
> CompletenessResult 会含 `MissingSlot(symptom_id="fever", missing_fields=["numeric_value"])`。
> MVP 仅 log（写 stdout），v2 改为返回 `ClarificationNeeded` 让前端追问 *"请问您体温多少度？"*。

### 2.2 规则引擎 Plan D 执行

按 `priority` 升序遍历所有规则，**收集所有命中**：

```
R001_febrile_neutropenia_suspected (priority=1)
  → 需 fever，无 fever 症状 → 不命中

R003_severe_dyspnea_or_chest_pain (priority=1)
  → 需 shortness_of_breath/severe_chest_pain → 不命中

R002_persistent_low_fever_post_chemo (priority=2)
  → 需 fever → 不命中

R004_severe_diarrhea_dehydration_risk (priority=2)
  → 需 severe_diarrhea → 不命中

R010_grade2_hand_foot_syndrome (priority=5)
  → 需 hand_foot_skin_reaction → 不命中

R011_persistent_vomiting (priority=5)
  → 需 vomiting → 不命中

R012_grade2_peripheral_neuropathy (priority=6)
  → 需 peripheral_neuropathy ctcae_grade ≥ 2
  → 实际 grade=2 ✅ 命中
  → matched_fields={
      "symptom_peripheral_neuropathy_ctcae_grade": 2,
      "symptom_peripheral_neuropathy_categorical_value": "moderate"
    }

R020_mild_nausea (priority=9)
  → 需 nausea ctcae_grade ≤ 1
  → 实际 grade=2 → 不命中

R021_mild_fatigue (priority=9)
  → 需 fatigue ctcae_grade ≤ 1
  → 实际 grade=2 → 不命中

R022_mild_hot_flashes (priority=9)
  → 需 hot_flashes → 不命中

R999_default_unmatched (priority=99, when:always:true)
  → 标记为 fallback，**已有具体规则命中时跳过**（M3 agent 优化点）
```

### 2.3 Plan D 决策结果

```python
EvaluationResult(
    primary=RuleMatch(
        rule_id="R012_grade2_peripheral_neuropathy",
        rule_version="1.0.0",
        risk_level="medium",
        advice_template="tpl_contact_team_48h",
        contact_team=True,
        urgency="this_week",
        source_doc="CTCAE v5.0 §Nervous system",
        rationale_text="紫杉类常见。CTCAE G2 已影响穿衣/系扣等精细动作...",
        matched_fields={...}
    ),
    all_matches=[<只有 R012>],   # 此案例其他规则都不匹配
    final_risk_level="medium",
    used_timeseries=False,
)
```

### 2.4 关键技术决策

| 决策 | 实现 | 价值 |
|---|---|---|
| **规则引擎是法官** | YAML + Python 求值器，纯确定性 | 输入 38.5 永远返回 high；可单元测试每条规则 |
| **Plan D = 评估全部 + 决策一条 + 审计全部** | `evaluate()` 收集 `all_matches`，primary 取 max risk + min priority | 临床差异诊断思维：所有警报都列，行动按最严重 |
| **`always:true` 作为 fallback** | M3 优化：兜底规则**仅在无具体规则命中时**启用 | 避免 R999 与 R020 同时触发的尴尬 |
| **Operator 表达式** | `{gte/lte/lt/gt/eq/in}` + 直接值简写 | 写规则的人不需要写 Python，YAML 即可 |

---

## 3. 执行 (Act) — 双事务写库 + 渲染建议 + 埋点

### 3.1 Plan C 双事务（医疗数据保留原则）

```
Tx1（抽取事务，先 commit）
  ├─ INSERT INTO assessment (
  │     id, user_id, idempotency_key, raw_input_text,
  │     parsed_symptoms (JSONB), extraction_confidence=0.78,
  │     extraction_model_version="deepseek-v4-flash",
  │     decision_status='pending'  ← 关键：决策未完成
  │   )
  ├─ INSERT INTO symptom_observation (3 行：peripheral_neuropathy / nausea / fatigue)
  └─ COMMIT
                                            
Tx2（决策事务）
  ├─ INSERT INTO evidence (1 行：R012)
  ├─ INSERT INTO advice (rendered_text, contact_team=true, ...)
  ├─ UPDATE assessment SET
  │     risk_level='medium',
  │     rule_engine_version='1.0.0',
  │     decision_status='completed'
  └─ COMMIT
```

**为什么要分两次提交**：

> 假设 Tx2 突发数据库连接断开（OOM、磁盘满、网络抖动）：
> - 单事务版：用户重试 → LLM 再被调用一次（$0.03 + 5s）→ 抽取结果可能略有不同（temp=0 也有微妙差异）
> - Plan C 版：Tx1 已保留抽取结果；用户重试同 idempotency_key → 命中既有 assessment_id，
>   只重跑规则引擎和 Tx2（毫秒级）
>
> 在医疗场景，这意味着：**用户的"上次报告的症状"不会因系统问题而消失**。

### 3.2 建议文本渲染

```
template_id="tpl_contact_team_48h"
template_version="1.0.0"
template_text=
  "您的症状需要团队关注。建议：
   1. 48 小时内联系您的主治团队；
   2. 期间记录症状变化（频率、严重度、影响）；
   3. 若症状加重，立即前往医院。"

→ 简单 .replace("{{assessment_id}}", id) 渲染
  （MVP 不引 Jinja2；v2 再升级）

→ 写入 advice.rendered_text
```

### 3.3 埋点（5 个核心事件）

整个评估生命周期触发的 event_log 行：

| 时刻 | 事件 | 触发位置 |
|---|---|---|
| 用户进入输入页 | `assessment_started` | 前端 onMount |
| 用户点提交、API 接到请求 | `assessment_submitted` | M7 POST 接口入口 |
| 用户点 (`primary.contact_team=true` 显示的) "联系团队"按钮 | `contact_team_clicked` | M_contact 接口（v2 实现）|
| 结果页渲染完成 | `result_viewed` | M8 GET 接口 |
| 用户离开页面 | `assessment_closed` | 前端 navigator.sendBeacon |

每条事件含：
```json
{
  "event_type": "assessment_submitted",
  "session_id": "<uuid>",
  "user_id": "<uuid>",
  "assessment_id": "<uuid>",
  "occurred_at": "2026-05-07T01:23:45Z",
  "payload": {"input_length": 67}
}
```

### 3.4 返回给前端的 AssessmentResult

包含**审计三件套**：

```json
{
  "assessment_id": "...",
  "created_at": "2026-05-07T01:23:45Z",
  "risk_level": "medium",
  "advice": {
    "text": "您的症状需要团队关注。建议：\n1. 48 小时内联系...",
    "contact_team": true,
    "urgency": "this_week"
  },
  "audit": {
    "matched_rules": [
      {
        "rule_id": "R012_grade2_peripheral_neuropathy",
        "rule_version": "1.0.0",
        "source_doc": "CTCAE v5.0 §Nervous system",
        "matched_fields": {
          "symptom_peripheral_neuropathy_ctcae_grade": 2,
          "symptom_peripheral_neuropathy_categorical_value": "moderate"
        },
        "rationale_text": "紫杉类常见。CTCAE G2 已影响穿衣/系扣..."
      }
    ],
    "generated_at": "2026-05-07T01:23:45Z",
    "rule_engine_version": "1.0.0",
    "extraction_model_version": "deepseek-v4-flash"
  },
  "parsed_symptoms": {...}
}
```

3 年后法律纠纷反查这次评估，**从 audit 字段就能完整复盘**：
- 是哪条规则把它定为 medium？R012 v1.0.0
- 这条规则当时长什么样？查 `rule_source` 表的 v1.0.0 YAML 快照
- LLM 抽取用的什么模型？deepseek-v4-flash

---

## 4. 学习 (Learn) — L3 离线人在回路

### 4.1 这次评估触发的 case_review？

`extraction_confidence=0.78`，超过默认阈值 0.6（`settings.low_confidence_threshold`）→ **不自动触发** review。
但如果阈值提到 0.8，会写入 `case_review` 表：

```sql
INSERT INTO case_review (
  assessment_id, user_id, trigger_source='auto_low_confidence',
  trigger_payload={"confidence": 0.78, "threshold": 0.8},
  status='pending'
);
```

### 4.2 假设：用户故事继续

```
Day 1 (本次评估)
  → 系统返回 medium + R012 + 建议 48h 联系团队
  → event_log: result_viewed, 但没有 contact_team_clicked
  → assessment_closed (用户 5 分钟后离开页面)

Day 2 上午
  → 用户再次输入: "手脚麻木更厉害了，今天写字都不稳"
  → 抽取: peripheral_neuropathy ctcae_grade=3
  → 命中 R012（仍然 medium，因为 R012 是 ≥G2）
  → 但实际 G3 应该升级处置！
  → event_log: 又是 result_viewed 没有 contact_team_clicked

Day 3 上午
  → 用户报告类似严重程度症状第三次
  → 系统检测：连续 N=3 次 medium+ 但用户从未点 contact_team_clicked
  → 触发 auto_repeat_high_no_action：
    INSERT INTO case_review (
      trigger_source='auto_repeat_high_no_action',
      trigger_payload={"recent_assessments": [...], "no_action_count": 3}
    )
```

### 4.3 临床委员会的周会

```
本周新增 case_review queue: 47 条
├─ auto_low_confidence: 12 条
├─ auto_default_rule_hit: 8 条 (R999 命中说明字典/规则有空白)
├─ auto_outcome_mismatch: 3 条
├─ auto_repeat_high_no_action: 5 条 (← 上面的案例在这里)
├─ user_disagreement (👎): 6 条
└─ clinician_flag: 13 条

医生 Dr. X review 了 5 条 auto_repeat_high_no_action：
- 案例 #34 (上面那个): 周围神经病变 G2→G3 progression，规则 R012 触发了但建议
  没说"如果加重立即就医"。建议改 advice_template 加这一句。
- 案例 #35: 类似 pattern，周围神经病变进展但用户没行动

输出 verdict:
{
  "verdict": "rule_gap",
  "verdict_note": "R012 的 advice_template 需要加'如继续恶化建议立即就医'",
  "corrective_action": {
    "rule_pr": "https://github.com/Pumpkin-3906/oncotriage/pull/27",
    "advice_template_change": "tpl_contact_team_48h: v1.0.0 → v1.1.0"
  }
}
```

### 4.4 闭环回到第一环节

```
新版 advice_templates 合入 main
  → rule_engine_version 不变（规则没改，模板改了）
  → advice_template_version='1.1.0' 写入下次评估的 advice 表
  → 新评估生成的 advice.text 含新建议
  → 下次类似用户得到更明确的指引
  → contact_team_clicked 触发率回升
  → auto_repeat_high_no_action 触发率下降
```

### 4.5 关键技术决策

| 决策 | 实现 | 价值 |
|---|---|---|
| **学习 = 改 prompt/规则/字典/模板**，不是梯度更新 | 所有"学习"产物是 git PR，有版本号 | 医疗审计要求"行为可追溯到具体变更" |
| **case_review 表 = L3 入口** | 7 类触发源，自动 + 用户 + 医生三路汇入 | 把"需要人审"的评估显式标出，不淹没在事件日志里 |
| **临床阈值标 ⚕️ 通过 .env 控制** | `LOW_CONFIDENCE_THRESHOLD` 等 | 改阈值不需要发版，但需要医疗委员会签字 |
| **rule_source 存完整 YAML 快照** | 每次规则改动 bump version + 冻结快照 | 3 年后能反查"当时这条规则是什么样" |

---

## 5. 闭环全景图（合并所有环节）

```
┌────────────────── 离线 / 周期性 (L3 学习) ───────────────────────┐
│  临床委员会 review case_review queue                           │
│         │                                                       │
│         └─→ verdict: 改规则 / 改 prompt / 扩字典 / 改模板        │
│                  │                                              │
│                  └─→ git PR → main → rule_engine_version++      │
│                                                                 │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼ (新版规则 + prompt 生效)
                   │
┌──────────────────┴──────────────────────────────────────────────┐
│  在线（实时，单次评估）                                          │
│                                                                 │
│  用户输入                                                        │
│     │                                                           │
│     ▼                                                           │
│  ① Sense: LLM 抽取（grounded by symptom_dictionary）            │
│     │ → ParsedSymptoms                                          │
│     ▼                                                           │
│  ② Decide:                                                      │
│     ├─ CompletenessChecker (规则查表，毫秒级)                    │
│     │  └─ MVP 仅日志；v2 返回 ClarificationNeeded                │
│     └─ RuleEngine (Plan D: 评估全部，决策一条，审计全部)         │
│         └─ EvaluationResult                                     │
│     ▼                                                           │
│  ③ Act:                                                         │
│     ├─ Tx1: 写 assessment + symptom_observation                 │
│     ├─ Tx2: 写 evidence + advice + 更新状态                     │
│     ├─ 渲染建议文本                                              │
│     ├─ 触发 5 个事件埋点                                         │
│     └─ 自动 flag bad cases → case_review                        │
│     ▼                                                           │
│  AssessmentResult (含审计三件套) 返回前端                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                   │
                   ▼ 用户行为 (contact_team_clicked? 有无后续上报?)
                   │
                   └─→ 沉淀进 event_log + 触发 case_review (L3 学习入口)
```

---

## 6. 总结：每个环节的"决定性 trade-off"

| 环节 | 关键决定 | 反对意见 | 我们为什么这样选 |
|---|---|---|---|
| 感知 | LLM 只翻译，不判断 | "LLM 越来越强，让它直接判风险更省事" | 医疗器械注册要求行为确定 + 可枚举 |
| 决策 | 规则引擎 + Plan D | "规则太死，临床细节难捕捉" | 死 = 可审计；细节用 case_review 慢慢补 |
| 执行 | Plan C 双事务 | "增加复杂度" | 医疗数据保留原则：用户报告的症状不能因系统故障消失 |
| 学习 | L3 人在回路（不是模型微调）| "应该用 RLHF / 在线学习" | 监管要求每次"模型行为变更"都可追溯到具体决策 |

---

## 配套阅读

- 项目设计：[`DESIGN.md`](./DESIGN.md)
- 数据模型：[`data_model/schema.sql`](./data_model/schema.sql)
- 规则集：[`rules/rules.yaml`](./rules/rules.yaml)
- API 契约：[`api/openapi.yaml`](./api/openapi.yaml)
- 项目反思：[`RETROSPECTIVE.md`](./RETROSPECTIVE.md)
