# Task M5 — LLM 抽取器实现

> 这是一个独立任务卡。无需查看对话历史，只读以下文件即可上手。

## 目标

让 `backend/app/services/llm_extractor.py` 中的 `LLMExtractor.extract()`
真正能跑：把患者中文自由描述转成结构化 `ParsedSymptoms`，
并强制映射到 `symptom_dictionary` 中的 12 个 ID 之一。

## 背景（为什么这件事重要）

LLM 是整个系统唯一一个"非确定性组件"。它的输出会直接喂给规则引擎做决策，
所以**抽取的精确性 = 临床安全性的上限**。需要做对三件事：
1. **受控词表 grounding** — 让 LLM 必须从字典选 ID，不能自由发挥
2. **结构化输出** — JSON Schema 约束，不允许散文回答
3. **失败要响亮** — 解析不出来直接抛 `LLMExtractionError`，让调用方走 checklist 兜底

## 必读（按顺序）

1. `docs/MVP_PLAN.md` — 整个 MVP 范围 + 多 agent 协作约定（§5.3 不要做的事）
2. `docs/DESIGN.md` §5.① 感知环节 + §3 决策 #1（LLM 抽取 + 规则决策）
3. `backend/app/services/llm_extractor.py` — 你要改的文件，已有 stub 和异常类
4. `backend/app/schemas/assessment.py` — `ParsedSymptoms` / `SymptomItem` 类型
5. `backend/app/rules/seed_dictionary.py` — 12 条字典（aliases_zh 是 grounding 关键）
6. `backend/app/config.py` — settings 字段（llm_timeout_seconds, llm_temperature, ...）
7. `backend/.env.example` — 哪些 env 配 LLM 行为

## 范围

### 你要实现的

#### 1. `LLMExtractor.extract(raw_text, dictionary_snapshot) -> ParsedSymptoms`

**入参**：
- `raw_text: str` — 患者原始描述，例如"昨天打完化疗第三天，今天下午开始发烧 38.5 度"
- `dictionary_snapshot: list[dict]` — 12 条字典，每条形如：
  ```python
  {
    "id": "fever",
    "display_name_zh": "发热",
    "aliases_zh": ["发烧", "高热", "低烧", ...],
    "value_type": "numeric",         # 'numeric' | 'categorical' | 'binary'
    "grading_scheme": "ctcae_v5",    # 影响 ctcae_grade 字段是否填
  }
  ```

**返回**：合法的 `ParsedSymptoms` 实例。

**Prompt 构造要点**：
- System prompt 必须包含 12 条字典的 ID + aliases，作为受控词表
- 必须显式约束：症状 ID 只能从给定列表选，否则丢弃
- 输出 JSON Schema 必须含：`symptoms`（list）、`context.days_since_chemo`（可空 int）、`confidence`（0-1 float）
- 用 Anthropic SDK 的结构化输出（messages.create + response_format 或 prompt 中明示 JSON）

**调用要点**：
```python
from anthropic import Anthropic
client = Anthropic(api_key=settings.anthropic_api_key)

response = client.messages.create(
    model=settings.anthropic_model,
    max_tokens=settings.llm_max_tokens,
    temperature=settings.llm_temperature,         # 必须 0.0
    timeout=settings.llm_timeout_seconds,
    system=...,                                    # 含字典 grounding
    messages=[{"role": "user", "content": raw_text}],
)
# response.content[0].text 是 JSON 字符串
```

**错误处理**（统一抛 `LLMExtractionError`）：
- API 调用超时
- API 返回 429 / 5xx
- 响应不是合法 JSON
- JSON 不符合 ParsedSymptoms 结构（Pydantic 校验失败）
- 抽取出的 symptom_id 不在字典里

#### 2. 单元测试 `backend/tests/test_llm_extractor.py`

**至少 3 个 case**（用 `unittest.mock` 把 Anthropic API 桩掉）：

| Case | mock LLM 返回 | 期望 |
|---|---|---|
| 高烧+化疗描述 | 合法 JSON 含 fever symptom_id + days_since_chemo | 返回 ParsedSymptoms，confidence ≥ 0.8 |
| LLM 返回乱码 | "I don't know..." | raise `LLMExtractionError` |
| LLM 返回不在字典的 ID | `{"symptoms":[{"symptom_id":"diabetes",...}]}` | raise `LLMExtractionError` |

#### 3. 一次真实 API 烟测（手工，写到 PR body）

用真实 ANTHROPIC_API_KEY 跑一遍以下输入，**截图或粘贴输出到 PR**：

```python
extractor = LLMExtractor()
dictionary = list_of_12_symptoms_from_seed_dictionary
result = extractor.extract(
    "昨天打完化疗第三天，今天下午开始发烧 38.5 度，浑身发冷",
    dictionary,
)
print(result.model_dump_json(indent=2))
```

期望输出含 `symptom_id="fever"`、`numeric_value=38.5`、`days_since_chemo=3`。

### 不要做的

- ❌ **不要改 `ParsedSymptoms` / `SymptomItem`** — 这是接口契约
- ❌ **不要在 extractor 里做规则判断** — 决策是 rule_engine 的事
- ❌ **不要做流式（streaming）输出** — MVP 不需要
- ❌ **不要做 Prompt 缓存** — MVP 不需要（虽然 Anthropic 支持，但徒增复杂度）
- ❌ **不要 catch Exception 然后 pass** — 失败必须能让调用方知道
- ❌ **不要把 dictionary 改成全局变量或类成员** — 显式传参便于测试
- ❌ **不要引入新依赖** — anthropic + pydantic 已够用
- ❌ **不要直接读数据库** — extractor 不关心数据来源，dictionary 由调用方传入

## Definition of Done

```
[ ] LLMExtractor.extract() 可正常返回合法 ParsedSymptoms
[ ] Prompt 中嵌入 12 条字典作为 grounding
[ ] 4 类失败路径全部抛 LLMExtractionError
[ ] tests/test_llm_extractor.py ≥ 3 个 case，mock Anthropic API
[ ] cd backend && .venv/bin/python -m pytest tests/ -v 全绿
[ ] 真实 API 烟测一次（PR body 贴输出）
[ ] 代码总行数 ≤ 150 行（llm_extractor.py 增量）
```

## 验收命令

```bash
cd backend
source .venv/bin/activate

# 1. 测试全绿（含 mock）
pytest tests/ -v

# 2. 真实 API 烟测（需要 .env 里有 ANTHROPIC_API_KEY）
python -c "
from app.services.llm_extractor import LLMExtractor
from app.rules.seed_dictionary import SYMPTOMS

result = LLMExtractor().extract(
    '昨天打完化疗第三天，今天下午开始发烧 38.5 度，浑身发冷',
    SYMPTOMS,
)
print(result.model_dump_json(indent=2))
assert any(s.symptom_id == 'fever' for s in result.symptoms)
assert result.context.get('days_since_chemo') == 3
print('✓ Smoke test passed')
"
```

## 提交规范

- **PR 标题**：`[M5] LLM 抽取器实现`
- **Commit 数**：1-2 个
- **PR body** 必须列：
  - 改动文件
  - 真实 API 调用的输入 + 输出（贴 JSON）
  - mock 测试结果
  - 总行数

## 设计提示（不强制）

### Prompt 骨架建议

```
SYSTEM:
你是一个临床症状抽取助手。从用户描述中识别症状并映射到下表 ID。
**严格规则**：
1. symptom_id 必须从下表选择，不在表中的症状必须丢弃
2. 输出严格的 JSON，不要任何解释文字
3. 模糊或不确定的描述，降低 confidence

可用症状（id: 中文名 / 别名）：
- fever: 发热 / [发烧, 高热, 低烧, ...]
- nausea: 恶心 / [想吐, 反胃]
- ... (12 条)

字段约束：
- value_type=numeric 的症状（fever）：填 numeric_value（数字）
- value_type=categorical 的症状：填 ctcae_grade(1-5) 或 categorical_value(mild|moderate|severe)
- duration_hours: 持续时间（小时），不知道留空

输出 JSON 严格遵守：
{
  "symptoms": [
    {"symptom_id": "...", "numeric_value": null, "ctcae_grade": null,
     "categorical_value": null, "duration_hours": null,
     "interferes_with_adl": null}
  ],
  "context": {"days_since_chemo": null},
  "confidence": 0.0
}

USER:
{raw_text}
```

### 解析 JSON 的稳健做法

LLM 偶尔会在 JSON 前后加 ```json ... ``` 围栏，应该兼容：
```python
import re, json
text = response.content[0].text.strip()
match = re.search(r'\{.*\}', text, re.DOTALL)
if not match:
    raise LLMExtractionError("No JSON found in response")
data = json.loads(match.group(0))
parsed = ParsedSymptoms.model_validate(data)
```

## 卡住时

- **Anthropic SDK 不熟**：看 https://docs.anthropic.com/en/api/messages
- **不知道字段哪些可空**：看 `schemas/assessment.py` 的 `SymptomItem` —
  绝大多数字段是 `... | None = None`
- **mock API 不熟**：用 `unittest.mock.patch.object(client, 'messages')`
  替换 `client.messages.create` 返回桩对象
