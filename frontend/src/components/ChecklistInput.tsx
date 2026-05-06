import {
  CATEGORY_LABEL,
  CATEGORY_ORDER,
  ParsedSymptomsForm,
  SymptomItem,
  SymptomSpec,
  symptomsByCategory,
} from "../lib/symptom_dict";

/**
 * ChecklistInput —— 按字典 value_type / grading_scheme 动态生成字段。
 *
 * 输入 / 输出严格匹配 backend ParsedSymptoms：
 *   { symptoms: SymptomItem[], context: { days_since_chemo: number | null } }
 *
 * 规则：
 *   - 顶部："距离上次化疗 N 天" + 互斥的"未化疗"复选框
 *   - 三个分组（urgent / chemo_common / endocrine）按 SymptomSpec.category
 *   - 勾选症状后展开字段：
 *       numeric (fever)              → number input + 单位
 *       categorical + ctcae_v5       → G1 / G2 / G3 radio + "影响日常活动" toggle
 *       categorical + severity_3     → mild / moderate / severe radio
 *
 * 用 props.value / props.onChange 受控；上层可以用 useState 直接接入。
 */
export interface ChecklistInputProps {
  value: ParsedSymptomsForm;
  onChange: (next: ParsedSymptomsForm) => void;
}

export default function ChecklistInput({ value, onChange }: ChecklistInputProps) {
  const checkedIds = new Set(value.symptoms.map((s) => s.symptom_id));

  function patchContext(patch: Partial<ParsedSymptomsForm["context"]>) {
    onChange({ ...value, context: { ...value.context, ...patch } });
  }

  function toggleSymptom(spec: SymptomSpec, checked: boolean) {
    if (checked) {
      const item: SymptomItem = { symptom_id: spec.id };
      onChange({ ...value, symptoms: [...value.symptoms, item] });
    } else {
      onChange({
        ...value,
        symptoms: value.symptoms.filter((s) => s.symptom_id !== spec.id),
      });
    }
  }

  function patchSymptom(id: string, patch: Partial<SymptomItem>) {
    onChange({
      ...value,
      symptoms: value.symptoms.map((s) =>
        s.symptom_id === id ? { ...s, ...patch } : s
      ),
    });
  }

  const days = value.context.days_since_chemo;
  const noChemo = days === null;

  return (
    <div className="space-y-6">
      {/* 距离上次化疗 */}
      <div className="flex items-center gap-3 flex-wrap">
        <label className="text-sm">距离上次化疗</label>
        <input
          type="number"
          min={0}
          max={120}
          value={noChemo ? "" : (days ?? "")}
          disabled={noChemo}
          onChange={(e) => {
            const v = e.target.value;
            patchContext({
              days_since_chemo: v === "" ? null : Number(v),
            });
          }}
          className="w-20 px-2 py-1 border rounded-md text-sm disabled:bg-gray-100"
        />
        <span className="text-sm">天</span>
        <label className="flex items-center gap-1 text-sm cursor-pointer ml-2">
          <input
            type="checkbox"
            checked={noChemo}
            onChange={(e) =>
              patchContext({ days_since_chemo: e.target.checked ? null : 0 })
            }
          />
          <span>未化疗</span>
        </label>
      </div>

      {/* 三个分组 */}
      {CATEGORY_ORDER.map((cat) => {
        const items = symptomsByCategory(cat);
        if (items.length === 0) return null;
        return (
          <section key={cat} className="space-y-2">
            <h3 className="text-sm font-medium text-gray-700">
              ▼ {CATEGORY_LABEL[cat]}
            </h3>
            <div className="border rounded-md divide-y">
              {items.map((spec) => {
                const checked = checkedIds.has(spec.id);
                const item = value.symptoms.find(
                  (s) => s.symptom_id === spec.id
                );
                return (
                  <div key={spec.id} className="p-3">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => toggleSymptom(spec, e.target.checked)}
                      />
                      <span className="text-sm">{spec.display_name_zh}</span>
                    </label>

                    {checked && item && (
                      <div className="mt-2 ml-6">
                        <SymptomFields
                          spec={spec}
                          item={item}
                          onPatch={(p) => patchSymptom(spec.id, p)}
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}

// ── 单个症状勾选后展开的字段 ──────────────────────────────

function SymptomFields({
  spec,
  item,
  onPatch,
}: {
  spec: SymptomSpec;
  item: SymptomItem;
  onPatch: (patch: Partial<SymptomItem>) => void;
}) {
  if (spec.value_type === "numeric") {
    return (
      <div className="flex items-center gap-2 text-sm">
        <span>数值：</span>
        <input
          type="number"
          step="0.1"
          value={item.numeric_value ?? ""}
          onChange={(e) => {
            const v = e.target.value;
            onPatch({
              numeric_value: v === "" ? null : Number(v),
              numeric_unit: spec.unit ?? null,
            });
          }}
          className="w-24 px-2 py-1 border rounded-md"
        />
        {spec.unit && <span>{spec.unit}</span>}
      </div>
    );
  }

  // categorical
  if (spec.grading_scheme === "ctcae_v5") {
    return (
      <div className="space-y-2 text-sm">
        <div className="flex gap-3 items-center flex-wrap">
          <span>严重程度：</span>
          {[1, 2, 3].map((g) => (
            <label key={g} className="flex items-center gap-1 cursor-pointer">
              <input
                type="radio"
                name={`grade-${spec.id}`}
                checked={item.ctcae_grade === g}
                onChange={() => onPatch({ ctcae_grade: g })}
              />
              <span>G{g}</span>
            </label>
          ))}
        </div>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={item.interferes_with_adl ?? false}
            onChange={(e) =>
              onPatch({ interferes_with_adl: e.target.checked })
            }
          />
          <span>影响日常活动</span>
        </label>
      </div>
    );
  }

  if (spec.grading_scheme === "severity_3") {
    const opts: Array<{ v: string; label: string }> = [
      { v: "mild", label: "轻" },
      { v: "moderate", label: "中" },
      { v: "severe", label: "重" },
    ];
    return (
      <div className="flex gap-3 items-center flex-wrap text-sm">
        <span>严重程度：</span>
        {opts.map((o) => (
          <label key={o.v} className="flex items-center gap-1 cursor-pointer">
            <input
              type="radio"
              name={`sev-${spec.id}`}
              checked={item.categorical_value === o.v}
              onChange={() => onPatch({ categorical_value: o.v })}
            />
            <span>{o.label}</span>
          </label>
        ))}
      </div>
    );
  }

  // binary or other —— 暂无 UI，留空
  return null;
}
