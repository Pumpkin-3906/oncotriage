/**
 * 症状字典前端 mirror —— 对照 backend/app/rules/seed_dictionary.py
 *
 * 12 条 + 新增 UI 分组 (category)。后端字典里没有 category 字段，
 * 这里加一层是为了 ChecklistInput 按"紧急 / 化疗常见 / 内分泌相关"分组展示。
 *
 * 任何对该列表的改动都必须同步 backend/app/rules/seed_dictionary.py，
 * 否则 LLM 抽取出来的 symptom_id 可能在前端找不到展示元数据。
 */

export type ValueType = "numeric" | "categorical";
export type GradingScheme = "ctcae_v5" | "severity_3" | "binary";
export type SymptomCategory =
  | "urgent"
  | "chemo_common"
  | "endocrine"
  | "other";

export interface SymptomSpec {
  id: string;
  display_name_zh: string;
  display_name_en: string;
  category: SymptomCategory;
  value_type: ValueType;
  grading_scheme: GradingScheme;
  unit?: string; // 仅 value_type=numeric 时有意义
}

export const SYMPTOMS: SymptomSpec[] = [
  // ── 紧急（4） ─────────────────────────────────
  {
    id: "fever",
    display_name_zh: "发热",
    display_name_en: "Fever",
    category: "urgent",
    value_type: "numeric",
    grading_scheme: "ctcae_v5",
    unit: "°C",
  },
  {
    id: "shortness_of_breath",
    display_name_zh: "呼吸困难",
    display_name_en: "Dyspnea",
    category: "urgent",
    value_type: "categorical",
    grading_scheme: "ctcae_v5",
  },
  {
    id: "severe_chest_pain",
    display_name_zh: "严重胸痛",
    display_name_en: "Chest pain",
    category: "urgent",
    value_type: "categorical",
    grading_scheme: "severity_3",
  },
  {
    id: "severe_diarrhea",
    display_name_zh: "腹泻",
    display_name_en: "Diarrhea",
    category: "urgent",
    value_type: "categorical",
    grading_scheme: "ctcae_v5",
  },

  // ── 化疗常见副作用（7） ────────────────────────
  {
    id: "nausea",
    display_name_zh: "恶心",
    display_name_en: "Nausea",
    category: "chemo_common",
    value_type: "categorical",
    grading_scheme: "ctcae_v5",
  },
  {
    id: "vomiting",
    display_name_zh: "呕吐",
    display_name_en: "Vomiting",
    category: "chemo_common",
    value_type: "categorical",
    grading_scheme: "ctcae_v5",
  },
  {
    id: "fatigue",
    display_name_zh: "疲劳",
    display_name_en: "Fatigue",
    category: "chemo_common",
    value_type: "categorical",
    grading_scheme: "ctcae_v5",
  },
  {
    id: "hand_foot_skin_reaction",
    display_name_zh: "手足综合征",
    display_name_en: "Palmar-plantar erythrodysesthesia",
    category: "chemo_common",
    value_type: "categorical",
    grading_scheme: "ctcae_v5",
  },
  {
    id: "peripheral_neuropathy",
    display_name_zh: "手脚麻木",
    display_name_en: "Peripheral neuropathy",
    category: "chemo_common",
    value_type: "categorical",
    grading_scheme: "ctcae_v5",
  },
  {
    id: "mucositis",
    display_name_zh: "口腔溃疡",
    display_name_en: "Mucositis oral",
    category: "chemo_common",
    value_type: "categorical",
    grading_scheme: "ctcae_v5",
  },
  {
    id: "rash",
    display_name_zh: "皮疹",
    display_name_en: "Rash maculo-papular",
    category: "chemo_common",
    value_type: "categorical",
    grading_scheme: "ctcae_v5",
  },

  // ── 内分泌治疗相关（1） ───────────────────────
  {
    id: "hot_flashes",
    display_name_zh: "潮热",
    display_name_en: "Hot flashes",
    category: "endocrine",
    value_type: "categorical",
    grading_scheme: "severity_3",
  },
];

export const CATEGORY_LABEL: Record<SymptomCategory, string> = {
  urgent: "紧急症状（出现请优先勾选）",
  chemo_common: "化疗常见副作用",
  endocrine: "内分泌治疗相关",
  other: "其他",
};

// 严格按字典定义顺序遍历的 category 顺序
export const CATEGORY_ORDER: SymptomCategory[] = [
  "urgent",
  "chemo_common",
  "endocrine",
];

export function symptomById(id: string): SymptomSpec | undefined {
  return SYMPTOMS.find((s) => s.id === id);
}

export function symptomsByCategory(cat: SymptomCategory): SymptomSpec[] {
  return SYMPTOMS.filter((s) => s.category === cat);
}

/** 字段中文 label —— 用于 confirm 页/checklist 缺失字段提示 */
export function fieldLabel(field: string): string {
  switch (field) {
    case "numeric_value":
      return "数值";
    case "numeric_unit":
      return "单位";
    case "ctcae_grade":
      return "严重程度 (CTCAE 1-5)";
    case "categorical_value":
      return "严重程度";
    case "duration_hours":
      return "持续时间";
    case "interferes_with_adl":
      return "影响日常活动";
    default:
      return field;
  }
}

// ── ParsedSymptoms 结构（与 backend/app/schemas/assessment.py 对应）──

export interface SymptomItem {
  symptom_id: string;
  numeric_value?: number | null;
  numeric_unit?: string | null;
  categorical_value?: string | null;
  ctcae_grade?: number | null;
  duration_hours?: number | null;
  interferes_with_adl?: boolean | null;
}

export interface ParsedSymptomsForm {
  symptoms: SymptomItem[];
  context: {
    days_since_chemo?: number | null;
    [key: string]: unknown;
  };
  confidence?: number | null;
}

export function emptyParsedSymptoms(): ParsedSymptomsForm {
  return {
    symptoms: [],
    context: { days_since_chemo: null },
    confidence: null,
  };
}
// ── 完整性检查（mirror backend completeness_checker.py）────────

/** 与后端 REQUIRED_BY_VALUE_TYPE 完全一致：内层 AND，外层 OR */
const REQUIRED_BY_VALUE_TYPE: Record<"numeric" | "categorical", string[][]> = {
  numeric: [["numeric_value"]],
  categorical: [["ctcae_grade"], ["categorical_value"]],
};

export interface MissingSlot {
  symptom_id: string;
  missing_fields: string[];
}

export interface CompletenessInfo {
  is_complete: boolean;
  missing_slots: MissingSlot[];
}

/**
 * 前端本地重算 completeness。
 * 与 backend services/completeness_checker.py 行为一致：
 *   - 空 symptoms → is_complete=true（兜底由 R999 处理）
 *   - 字典里没有的 symptom_id → missing_fields=['unknown_symptom_in_dictionary']
 *   - binary 或无要求 → 视为完整
 *   - numeric → 必须有 numeric_value
 *   - categorical → ctcae_grade 或 categorical_value 至少一个有值
 */
export function recomputeCompleteness(
  parsed: ParsedSymptomsForm
): CompletenessInfo {
  if (!parsed.symptoms || parsed.symptoms.length === 0) {
    return { is_complete: true, missing_slots: [] };
  }

  const missing: MissingSlot[] = [];

  for (const item of parsed.symptoms) {
    const spec = symptomById(item.symptom_id);
    if (!spec) {
      missing.push({
        symptom_id: item.symptom_id,
        missing_fields: ["unknown_symptom_in_dictionary"],
      });
      continue;
    }

    const groups = REQUIRED_BY_VALUE_TYPE[spec.value_type];
    if (!groups || groups.length === 0) continue;

    const satisfied = groups.some((group) =>
      group.every((f) => fieldHasValue(item, f))
    );
    if (satisfied) continue;

    // 都没填：摊平到一个去重列表
    const wanted: string[] = [];
    for (const group of groups) {
      for (const f of group) {
        if (!wanted.includes(f)) wanted.push(f);
      }
    }
    missing.push({ symptom_id: item.symptom_id, missing_fields: wanted });
  }

  return { is_complete: missing.length === 0, missing_slots: missing };
}

function fieldHasValue(item: SymptomItem, key: string): boolean {
  const v = (item as unknown as Record<string, unknown>)[key];
  return v !== null && v !== undefined && v !== "";
}

// ── 编辑助手 ─────────────────────────────────────────────────

/** 给指定 spec 创建一个空白 SymptomItem（"补充症状"用） */
export function makeEmptySymptom(spec: SymptomSpec): SymptomItem {
  return {
    symptom_id: spec.id,
    numeric_value: null,
    numeric_unit: spec.unit ?? null,
    categorical_value: null,
    ctcae_grade: null,
    duration_hours: null,
    interferes_with_adl: null,
  };
}

/** 比对 LLM 原版 vs 用户编辑版，返回被编辑过 / 新增 / 删除的症状数 */
export function countEdits(
  original: ParsedSymptomsForm,
  edited: ParsedSymptomsForm
): number {
  const origIndex = new Map(original.symptoms.map((s) => [s.symptom_id, s]));
  const editIndex = new Map(edited.symptoms.map((s) => [s.symptom_id, s]));

  let count = 0;
  // 删除：原有但当前没有
  for (const id of origIndex.keys()) {
    if (!editIndex.has(id)) count += 1;
  }
  // 新增 / 字段变更
  for (const [id, item] of editIndex) {
    const orig = origIndex.get(id);
    if (!orig) {
      count += 1;
      continue;
    }
    if (!shallowSymptomEqual(orig, item)) count += 1;
  }
  return count;
}

function shallowSymptomEqual(a: SymptomItem, b: SymptomItem): boolean {
  const keys: (keyof SymptomItem)[] = [
    "numeric_value",
    "numeric_unit",
    "categorical_value",
    "ctcae_grade",
    "duration_hours",
    "interferes_with_adl",
  ];
  return keys.every((k) => a[k] === b[k]);
}

// ── CTCAE Grade 选项（卡片渲染用）─────────────────────────────

export interface GradeOption {
  value: number | string;
  label: string;
  /** 写回到 SymptomItem 的字段名 */
  field: "ctcae_grade" | "categorical_value";
}

/**
 * categorical 症状的等级选项 —— 按 grading_scheme 区分：
 *   - ctcae_v5: 写 ctcae_grade (1/2/3)
 *   - severity_3: 写 categorical_value ("mild"/"moderate"/"severe")
 * MVP 只暴露 G1-G3，更高级别由临床流程接管。
 */
export function gradeOptions(spec: SymptomSpec): GradeOption[] {
  if (spec.grading_scheme === "ctcae_v5") {
    return [
      { value: 1, label: "轻 (G1)", field: "ctcae_grade" },
      { value: 2, label: "中 (G2)", field: "ctcae_grade" },
      { value: 3, label: "重 (G3+)", field: "ctcae_grade" },
    ];
  }
  if (spec.grading_scheme === "severity_3") {
    return [
      { value: "mild", label: "轻", field: "categorical_value" },
      { value: "moderate", label: "中", field: "categorical_value" },
      { value: "severe", label: "重", field: "categorical_value" },
    ];
  }
  return [];
}
