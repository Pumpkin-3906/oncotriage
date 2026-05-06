# OncoTriage Smoke Test —— 真实 LLM 抽取冒烟集

> 这是 LLM 抽取层（M5）的回归基准。每次改 prompt / 换模型 / 调字典之后，
> 跑这个集合就能立刻看到回归。

## 怎么跑

```bash
cd backend
source .venv/bin/activate

# 确保 .env 里有 ANTHROPIC_API_KEY
pytest tests/test_smoke_corpus.py -m smoke -v
```

默认 `pytest` 不会跑这些用例（被 `@pytest.mark.smoke` 隔离）。
只有显式 `-m smoke` 才会触发。CI 不应自动跑（见下面成本说明）。

## 关键文件

| 文件 | 作用 |
|---|---|
| `smoke_cases.yaml` | 语料库（≥18 条），按 A.1-A.10 分类 |
| `test_smoke_corpus.py` | 参数化 pytest 用例 |
| `SMOKE.md` | 本文档 |

## 怎么加新 case

在 `smoke_cases.yaml` 末尾追加一条：

```yaml
- id: SMOKE_AX_NNN_short_description     # AX = A.1-A.10 分类编号
  category: <one of the 10 categories>
  input: "患者会怎么说"
  expected:
    extracted_symptoms_must_include: [<symptom_id>, ...]   # 可选
    extracted_symptoms_must_not_include: [<symptom_id>, ...]   # 可选，防过度抽取
    extracted_context_keys: [days_since_chemo]   # 可选
    confidence_min: 0.6   # 可选
    confidence_max: 0.95   # 可选
  notes: "给 reviewer 的说明"
```

**关键约束（避免脆弱测试）**：
- 用 `must_include` 而不是 `must_only_include` —— LLM 经常多抽近邻症状
- `confidence` 用区间断言 —— LLM 即使 temp=0 也会 ±0.1 浮动
- 1 条 case 只写 1-3 条断言 —— 避免过度规约
- 模糊/缺失信息的 case：只断言 `confidence_max`，不断言 symptoms

## 怎么处理"LLM 偶尔翻车"

LLM 即使 temp=0 仍然不稳定。以下场景可视为正常：
- 邻近症状被多抽（如说"发烧 + 难受"，LLM 也抽 fatigue）
- confidence 浮动 ±0.1
- 模糊输入偶尔被强行抽出某个症状

**操作建议**：
- MVP 阶段：单次跑过即可发布。失败 case 重跑 1-2 次确认是否稳定失败
- 改 prompt / 换模型时：跑 3 次取多数。≥2 次 pass 视为通过
- 长期：考虑把 marginal case 自动跑 N 次取多数（v2）

`smoke_cases.yaml` 中标了 `notes: "marginal, expect ~80% pass rate"` 的 case 是已知不稳定。
不要因为它偶尔失败就从语料里删掉 —— 它们是 LLM 能力边界的证据。

## 当前已知 marginal cases

| ID | 失败模式 | 期望通过率 |
|---|---|---|
| `SMOKE_A4_003_chest_discomfort_vague` | LLM 可能因 '不舒服' 太弱不抽 chest_pain | ~80% |
| `SMOKE_A5_001_vague_unwell` | LLM 偶尔会瞎猜 fatigue | ~70% |
| `SMOKE_A5_002_indescribable` | symptoms 应为空，LLM 偶尔强抽 | ~70% |
| `SMOKE_A6_002_face_hot_fever` | 非标准发烧描述，confidence 不易控制 | ~80% |
| `SMOKE_A8_001_relative_time_diarrhea` | "红药水" 推断 days_since_chemo | ~80% |
| `SMOKE_A10_001_neck_lump_not_dict` | LLM 可能错抽 rash | ~75% |

## 单次完整跑的成本估算

**模型**：`claude-sonnet-4-5-20250929`（默认）
**调用次数**：每条 case 一次 → 20 次 API 调用

**Token 估算**：
- system prompt（含 12 条字典 grounding）≈ 800 tokens
- user message（患者中文描述）≈ 30-50 tokens
- 单次 input ≈ **850 tokens**
- 单次 output（JSON 抽取结果）≈ **150 tokens**

**总量**：
- input: 850 × 20 ≈ **17k tokens**
- output: 150 × 20 ≈ **3k tokens**

**成本**（Anthropic Sonnet 4.5 公开价格 $3 / MTok input、$15 / MTok output）：
- input: 17k × $3/M ≈ **$0.051**
- output: 3k × $15/M ≈ **$0.045**
- **每次完整跑 ≈ $0.10**

**实测**（M_smoke 提交时跑的真实数据，见 commit body）：
- 20 次调用全部命中
- 估算花费：约 $0.08-0.12（与上述估算一致）

## 不要做的

- ❌ **不要 mock LLM** —— 这是冒烟测试的本质
- ❌ **不要把 smoke 加到默认 pytest 集** —— 跑一次成本约 $0.10，CI 会爆
- ❌ **不要给所有 case 写 risk_level 断言** —— M3 完成前规则引擎不可用，
  M3 完成后再补 `test_smoke_full_pipeline`
- ❌ **不要把 case 写得太严格** —— 比如要求"必须只抽出 1 个 symptom"
