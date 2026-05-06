# Task M_smoke — 真实用户语料的冒烟测试集

> 这是一个独立任务卡。无需查看对话历史。
> 依赖：M5 (LLM Extractor) 已完成；M3 (Rule Engine) 完成后能跑更多断言

## 目标

构造一份**真实患者会怎么说**的中文输入语料库（≥18 条），覆盖：高风险急症、模糊/口语、
方言/俗称、多症状、信息缺失、上下文时间表达、超界/不在 MVP 范围 等关键场景。

每条都标注**期望行为**，并写成 pytest 用例。这是 LLM 抽取层的回归基准（regression baseline）。

## 背景

LLM 抽取是系统里唯一的非确定性组件。它的好坏不是看单元测试有几个绿，而是看
**面对真实患者描述能不能稳定抽对**。MVP 阶段我们没钱做真实临床试验，但至少要
准备一份"如果团队成员把它当用户"会蹦出来的输入集合。

每次改 prompt / 换模型 / 调字典之后，跑这个冒烟集合就能立刻看到回归。

## 必读（按顺序）

1. `docs/MVP_PLAN.md` — MVP 范围 + 协作约定
2. `docs/DESIGN.md` §5.① 感知环节
3. `backend/app/rules/seed_dictionary.py` — 12 条字典 + 别名（aliases_zh 决定能识别什么）
4. `docs/rules/rules.yaml` — 规则集（决定哪些症状会触发什么风险）
5. `backend/app/services/llm_extractor.py` — 抽取实现
6. `backend/app/services/rule_engine.py` — M3 完成后可用（断言风险等级要用）
7. `backend/tests/test_llm_extractor.py` — 已有 mock 测试，参考结构

## 范围

### Part A — 构造语料 `backend/tests/smoke_cases.yaml`

YAML 格式，每条结构：

```yaml
- id: SMOKE_001_clear_fever_post_chemo
  category: clear_high_risk
  input: "昨天打完化疗第三天，今天下午开始发烧38.5度，浑身发冷"
  expected:
    extracted_symptoms_must_include: [fever]
    extracted_context_keys: [days_since_chemo]
    risk_level: high
    primary_rule_starts_with: R001
    confidence_min: 0.7
  notes: "北极星 case"
```

**至少 18 条**，按下面分类各凑够（中括号是建议条数）：

#### A.1 高风险急症（清晰）[3]
- 化疗后高烧 38.5
- 严重呼吸困难 + 胸痛
- 严重腹泻（"今天拉了七八次水样便"）

#### A.2 化疗常见副作用（清晰）[3]
- 手足综合征中度（"手掌脱皮疼，影响拿东西"）
- 持续呕吐 >24h（"昨天晚上开始一直吐到现在"）
- 周围神经病变（"手指麻得没法系扣子"）

#### A.3 低风险（清晰）[2]
- 轻度恶心（"有点想吐但能吃饭"）
- 轻度疲劳（"就是有点累，活动还行"）

#### A.4 信息缺失（CompletenessChecker 应触发）[3]
- "我发烧了"（fever 缺 numeric_value）
- "今天有点恶心"（缺 grade / categorical_value）
- "胸口不舒服"（缺 severity）

#### A.5 模糊/口语 [2]
- "整个人不太对劲"（symptoms 应为空或低置信度）
- "感觉怪怪的，说不出哪里"（应触发 R999 兜底）

#### A.6 方言/俗称 [2]
- "上火了，嘴里起泡"（mucositis）
- "脸有点烫"（fever 但用了非标准描述）

#### A.7 多症状（多规则同时命中，验证 Plan D）[2]
- "化疗后第3天发烧38.5度，还一直恶心吐"
  → primary R001 (high), all_matches 还含 R020/R011
- "手脚都麻了，皮肤还起红疹"
  → R012 + 字典命中 rash

#### A.8 时间/上下文表达 [1]
- "前天打完红药水昨天就开始拉，今天还在拉"
  → severe_diarrhea + days_since_chemo=2 应抽出来

#### A.9 超界（不在 MVP 范围）[1]
- "最近老是失眠睡不着"（anxiety/insomnia 不在 MVP 字典）
  → symptoms 应为空，confidence 可能仍然不低

#### A.10 LLM 易错 [1]
- "脖子上长了个肿块"（不是字典里任何条目，且语义上像 lymphadenopathy）
  → symptoms 应为空，case 写明 LLM 可能想塞 rash，要明确不接受

YAML 字段约定：

| 字段 | 含义 |
|---|---|
| `id` | 唯一标识，便于追踪回归 |
| `category` | A.1-A.10 分类 |
| `input` | 患者原始描述 |
| `expected.extracted_symptoms_must_include` | 抽取结果**必须含**这些 symptom_id |
| `expected.extracted_symptoms_must_not_include` | 抽取结果**绝不能含**这些（防过度抽取） |
| `expected.extracted_context_keys` | context 必须含的键 |
| `expected.risk_level` | 期望规则引擎给出的风险（仅 M3 完成后断言）|
| `expected.primary_rule_starts_with` | 期望主命中规则 ID 前缀（仅 M3 完成后断言） |
| `expected.confidence_min` / `confidence_max` | 置信度区间 |
| `expected.is_complete` | CompletenessChecker 应返回 True/False（仅 M3 完成后） |
| `notes` | 给 reviewer 看的说明 |

某字段不适用就省略。**绝大多数 case 应只写 1-3 条断言**，避免过度规约。

### Part B — 测试运行器 `backend/tests/test_smoke_corpus.py`

```python
import yaml
import pytest
from pathlib import Path
from app.services.llm_extractor import LLMExtractor
from app.rules.seed_dictionary import SYMPTOMS

SMOKE_FILE = Path(__file__).parent / "smoke_cases.yaml"
CASES = yaml.safe_load(SMOKE_FILE.read_text())


@pytest.mark.smoke           # 标记，可独立运行：pytest -m smoke
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_llm_extraction(case):
    """对每条 smoke 输入，验证 LLM 抽取结果符合预期断言"""
    extractor = LLMExtractor()
    result = extractor.extract(case["input"], SYMPTOMS)

    expected = case.get("expected", {})

    # 必含的 symptom_id
    if "extracted_symptoms_must_include" in expected:
        actual_ids = {s.symptom_id for s in result.symptoms}
        for must in expected["extracted_symptoms_must_include"]:
            assert must in actual_ids, \
                f"[{case['id']}] missing symptom: {must} (got {actual_ids})"

    # 绝不能含的
    if "extracted_symptoms_must_not_include" in expected:
        actual_ids = {s.symptom_id for s in result.symptoms}
        for forbidden in expected["extracted_symptoms_must_not_include"]:
            assert forbidden not in actual_ids, \
                f"[{case['id']}] should not extract: {forbidden}"

    # context 必含的键
    if "extracted_context_keys" in expected:
        for key in expected["extracted_context_keys"]:
            assert key in (result.context or {}), \
                f"[{case['id']}] missing context key: {key}"

    # 置信度区间
    if "confidence_min" in expected:
        assert result.confidence >= expected["confidence_min"]
    if "confidence_max" in expected:
        assert result.confidence <= expected["confidence_max"]
```

如果 M3 已完成，**额外加一组测试** `test_smoke_full_pipeline`：跑 LLM → CompletenessChecker
→ RuleEngine 三层，断言 risk_level / primary_rule_starts_with / is_complete。

```python
@pytest.mark.smoke
@pytest.mark.skipif(not RULE_ENGINE_AVAILABLE, reason="M3 not done yet")
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_full_pipeline(case):
    ...
```

### Part C — README

写一份 `backend/tests/SMOKE.md` 说明：
- 怎么跑：`pytest tests/test_smoke_corpus.py -m smoke -v`
- 怎么加新 case
- 怎么处理"LLM 偶尔翻车"（建议至少跑 3 次取多数；MVP 阶段单次跑过即可）
- 跑一次成本（约 N 次 API 调用 × 单价）

## 不要做的

- ❌ **不要把 case 写得太严格** — 比如要求"必须只抽出 1 个 symptom"。LLM 经常多抽
  邻近症状，应该容忍
- ❌ **不要给所有 case 写 risk_level 断言** — 信息缺失/模糊的 case 走 R999，断言意义不大
- ❌ **不要 mock LLM** — 这是冒烟测试，必须打真实 API
- ❌ **不要把 smoke 测试放到 default pytest run 里** — 用 `@pytest.mark.smoke` 标记，
  默认 `pytest` 跳过；CI/PR 可以加 `pytest -m smoke` 单独跑
- ❌ **不要在 case 里写复杂的多轮对话** — slot filling 是 v2，目前都是单轮输入
- ❌ **不要构造对抗样本（adversarial / 越狱 prompt）**— 那是安全测试，不是 MVP smoke

## Definition of Done

```
[ ] backend/tests/smoke_cases.yaml 含 ≥18 条 case，覆盖 A.1-A.10 全部分类
[ ] backend/tests/test_smoke_corpus.py 跑通：
    pytest tests/test_smoke_corpus.py -m smoke -v 全绿
[ ] backend/tests/SMOKE.md 含运行说明
[ ] PR body 贴出运行结果（pytest -v 输出）
[ ] 单次完整跑的 token 成本估算（写在 SMOKE.md 末尾）
```

## 验收命令

```bash
cd backend
source .venv/bin/activate

# 1. 跑 smoke（需要 ANTHROPIC_API_KEY）
pytest tests/test_smoke_corpus.py -m smoke -v

# 2. 跑常规测试（应不受影响，smoke 不在默认 set 里）
pytest tests/ -v
```

## 提交规范

- **PR 标题**：`[M_smoke] 真实患者语料冒烟测试集 (≥18 cases)`
- **Commit 数**：2（语料 + 测试代码 / 文档）
- **PR body** 列：
  - 18+ case 列表（id + category）
  - pytest 输出
  - token 成本估算
  - 哪些 case 需要"运气好"才能稳定通过（marginal cases）

## 设计提示

### 怎么挑选 case

想象你的目标用户：化疗中的乳腺癌患者，30-60 岁，多数不熟悉医学术语。她们会怎么说？
- 不会说"我有 Grade 3 腹泻"，会说"今天拉了好多次水"
- 不会说"我体温 38.5"，可能说"我感觉烧起来了"或"额头烫"
- 会用方言："上火"（口腔黏膜炎可能）、"虚火"、"内热"
- 会含糊："不舒服"、"怪怪的"、"难受"

挑 case 优先级（高 → 低）：
1. **能区分系统对错的**（同一描述，错抽 vs 对抽差很多）
2. **覆盖各 risk_level 的**（high/medium/low + R999 兜底）
3. **覆盖字典各 value_type 的**（numeric / categorical）
4. **代表方言 / 口语 / 时间表达的**（系统的"语言鲁棒性"）

### 容忍 LLM 不稳定

LLM 即使 temp=0 偶尔会有：
- 抽出额外的"近邻"症状（用户说发烧，它可能也抽 fatigue）— 用 must_include 而不是
  must_only_include
- confidence 浮动 ±0.1 — 用 confidence_min 不要写 == 0.85

如果某 case 跑 5 次有 1 次失败，那是 LLM 本身不稳定，可以加注释 `notes: marginal,
expect 80% pass rate`。

### Token 成本估算

```
prompt tokens ≈ 2000 (含字典 grounding) × 18 = 36k
output tokens ≈ 200 × 18 = 3.6k
按 Sonnet 4.5 价格：~$0.04 一次完整跑
```
