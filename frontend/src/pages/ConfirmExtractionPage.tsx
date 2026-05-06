import { useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { analytics } from "../lib/analytics";
import {
  ExtractResponse,
  submitAssessment,
} from "../api/client";
import {
  CompletenessInfo,
  MissingSlot,
  ParsedSymptomsForm as ParsedSymptoms,
  SymptomItem,
  SYMPTOMS,
  SymptomSpec,
  countEdits,
  gradeOptions,
  makeEmptySymptom,
  recomputeCompleteness,
  symptomById,
} from "../lib/symptom_dict";

interface ConfirmState {
  extraction: ExtractResponse;
  raw_input_text: string;
  input_source: "free_text" | "checklist";
}

function isConfirmState(x: unknown): x is ConfirmState {
  if (!x || typeof x !== "object") return false;
  const s = x as Record<string, unknown>;
  return (
    typeof s.raw_input_text === "string" &&
    (s.input_source === "free_text" || s.input_source === "checklist") &&
    !!s.extraction &&
    typeof s.extraction === "object" &&
    "parsed_symptoms" in (s.extraction as object)
  );
}

export default function ConfirmExtractionPage() {
  const location = useLocation();
  // 直接访问 /confirm 没有 state → 回首页
  if (!isConfirmState(location.state)) return <Navigate to="/" replace />;
  return <ConfirmExtractionInner state={location.state} />;
}

function ConfirmExtractionInner({ state }: { state: ConfirmState }) {
  const { extraction, raw_input_text, input_source } = state;
  const navigate = useNavigate();

  const originalRef = useRef<ParsedSymptoms>(extraction.parsed_symptoms);
  const idempotencyKeyRef = useRef<string>(crypto.randomUUID());

  const [parsed, setParsed] = useState<ParsedSymptoms>(extraction.parsed_symptoms);
  const [submitting, setSubmitting] = useState(false);
  const [showAddPicker, setShowAddPicker] = useState(false);

  // 完整性：用户每次编辑后前端本地重算（不再调 API）
  const completeness: CompletenessInfo = useMemo(
    () => recomputeCompleteness(parsed),
    [parsed]
  );

  const selectedIds = useMemo(
    () => new Set(parsed.symptoms.map((s) => s.symptom_id)),
    [parsed.symptoms]
  );
  const addable = SYMPTOMS.filter((s) => !selectedIds.has(s.id));

  const missingById = useMemo(() => {
    const m = new Map<string, MissingSlot>();
    for (const slot of completeness.missing_slots) m.set(slot.symptom_id, slot);
    return m;
  }, [completeness.missing_slots]);

  const daysSinceChemo = readNumericContext(parsed.context, "days_since_chemo");

  useEffect(() => {
    analytics.emit("confirm_page_viewed", {
      input_source,
      symptom_count: extraction.parsed_symptoms.symptoms.length,
      initial_is_complete: extraction.completeness.is_complete,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function updateSymptom(idx: number, patch: Partial<SymptomItem>): void {
    setParsed((prev) => {
      const next = prev.symptoms.slice();
      next[idx] = { ...next[idx], ...patch };
      return { ...prev, symptoms: next };
    });
  }
  function removeSymptom(idx: number): void {
    setParsed((prev) => ({ ...prev, symptoms: prev.symptoms.filter((_, i) => i !== idx) }));
  }
  function addSymptom(spec: SymptomSpec): void {
    setParsed((prev) => ({ ...prev, symptoms: [...prev.symptoms, makeEmptySymptom(spec)] }));
    setShowAddPicker(false);
  }
  function updateDays(value: number | null): void {
    setParsed((prev) => ({ ...prev, context: { ...prev.context, days_since_chemo: value } }));
  }

  function handleBack(): void {
    // 把原文带回 InputPage 让它预填 textarea
    navigate("/", { state: { prefill_text: raw_input_text } });
  }

  async function handleConfirm(): Promise<void> {
    if (!completeness.is_complete || submitting) return;
    setSubmitting(true);
    analytics.emit("extraction_confirmed", {
      input_source,
      edited_count: countEdits(originalRef.current, parsed),
      symptom_count: parsed.symptoms.length,
    });
    try {
      const result = await submitAssessment({
        raw_input_text,
        parsed_symptoms: parsed,
        idempotency_key: idempotencyKeyRef.current,
        // 后端 enum: free_text | checklist_fallback
        input_source: input_source === "checklist" ? "checklist_fallback" : "free_text",
      });
      navigate(`/result/${result.assessment_id}`);
    } catch (err) {
      console.error(err);
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">确认信息</h1>

      <div className="bg-gray-100 rounded-md p-3 text-sm text-gray-700">
        <div className="text-xs text-gray-500 mb-1">您说：</div>
        <div className="whitespace-pre-line">{raw_input_text || "(无原文)"}</div>
      </div>

      {!completeness.is_complete && (
        <div role="alert" className="border border-yellow-300 bg-yellow-50 text-yellow-900 rounded-md p-3 text-sm">
          <div className="font-medium">
            ⚠️ 您的描述缺少 {completeness.missing_slots.length} 项关键信息
          </div>
          <div className="text-xs mt-1">请补充以便给出准确判断</div>
        </div>
      )}

      <div className="text-sm text-gray-600">我们这样理解您的描述：</div>

      <div className="text-sm bg-blue-50 border border-blue-100 rounded-md p-3">
        <span className="mr-1">📌</span>
        <span className="text-gray-700">距离上次化疗：</span>
        <input
          type="number"
          min={0}
          value={daysSinceChemo ?? ""}
          onChange={(e) => updateDays(e.target.value === "" ? null : Number(e.target.value))}
          placeholder="天数"
          className="mx-2 w-20 px-2 py-1 border border-gray-300 rounded"
        />
        <span className="text-gray-700">天</span>
        <span className="ml-2 text-xs text-gray-500">选填</span>
      </div>

      {parsed.symptoms.length === 0 && (
        <div className="text-sm text-gray-500 italic">
          没有抽到具体症状。请使用下方"补充其他症状"添加。
        </div>
      )}
      <div className="space-y-3">
        {parsed.symptoms.map((sym, idx) => (
          <SymptomCard
            key={`${sym.symptom_id}-${idx}`}
            item={sym}
            missing={missingById.get(sym.symptom_id)}
            onChange={(patch) => updateSymptom(idx, patch)}
            onRemove={() => removeSymptom(idx)}
          />
        ))}
      </div>

      <div className="border border-dashed border-gray-300 rounded-md p-3">
        {!showAddPicker ? (
          <button
            type="button"
            onClick={() => setShowAddPicker(true)}
            disabled={addable.length === 0}
            className="text-sm text-blue-600 disabled:text-gray-400"
          >
            + 补充其他症状
          </button>
        ) : (
          <div>
            <div className="text-xs text-gray-600 mb-2">您还有以下症状吗？</div>
            <div className="flex flex-wrap gap-2">
              {addable.map((spec) => (
                <button
                  key={spec.id}
                  type="button"
                  onClick={() => addSymptom(spec)}
                  className="px-3 py-1.5 text-sm border border-gray-300 rounded-full hover:bg-gray-50"
                >
                  {spec.emoji} {spec.display_name_zh}
                </button>
              ))}
              {addable.length === 0 && (
                <span className="text-xs text-gray-500">所有字典症状已添加</span>
              )}
            </div>
            <button
              type="button"
              onClick={() => setShowAddPicker(false)}
              className="mt-2 text-xs text-gray-500"
            >
              收起
            </button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 pt-2">
        <button
          type="button"
          onClick={handleBack}
          className="px-4 py-3 border border-gray-300 rounded-md text-sm"
        >
          ← 重新描述
        </button>
        <button
          type="button"
          onClick={handleConfirm}
          disabled={!completeness.is_complete || submitting}
          className="px-4 py-3 bg-blue-600 text-white rounded-md text-sm font-medium disabled:bg-gray-300"
        >
          {submitting ? "提交中..." : "确认 看结果 →"}
        </button>
      </div>
    </div>
  );
}

// ── 单条症状卡片 ──────────────────────────────────────────────
function SymptomCard({
  item,
  missing,
  onChange,
  onRemove,
}: {
  item: SymptomItem;
  missing: MissingSlot | undefined;
  onChange: (patch: Partial<SymptomItem>) => void;
  onRemove: () => void;
}) {
  const spec = symptomById(item.symptom_id);
  const missingFields = new Set(missing?.missing_fields ?? []);
  const hasIssue = missingFields.size > 0;

  if (!spec) {
    // 字典外症状 —— UI 不允许添加，仅作兜底显示
    return (
      <div className="border border-red-300 rounded-md p-3 bg-red-50 flex items-center justify-between text-sm">
        <span>未知症状: {item.symptom_id}</span>
        <button type="button" onClick={onRemove} aria-label="删除症状" className="text-gray-500">✕</button>
      </div>
    );
  }

  const numericMissing = missingFields.has("numeric_value");
  const categoricalMissing =
    missingFields.has("ctcae_grade") || missingFields.has("categorical_value");

  return (
    <div className={`border rounded-md p-3 ${hasIssue ? "border-red-300 bg-red-50" : "border-gray-200 bg-white"}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="font-medium text-sm">{spec.emoji} {spec.display_name_zh}</div>
        <button
          type="button"
          onClick={onRemove}
          aria-label="删除症状"
          className="text-gray-500 hover:text-gray-700 px-1"
        >
          ✕
        </button>
      </div>

      {spec.value_type === "numeric" && (
        <label className="block text-sm">
          <span className="text-gray-600">
            {spec.id === "fever" ? "体温" : "数值"}
            {spec.unit ? `（${spec.unit}）` : ""}
            {numericMissing && <span className="text-red-600 ml-1">*必填</span>}
          </span>
          <input
            type="number"
            step="0.1"
            value={item.numeric_value ?? ""}
            placeholder={spec.numeric_placeholder}
            onChange={(e) => {
              const raw = e.target.value;
              onChange({
                numeric_value: raw === "" ? null : Number(raw),
                numeric_unit: item.numeric_unit ?? spec.unit ?? null,
              });
            }}
            className={`mt-1 w-32 px-2 py-1 border rounded ${numericMissing ? "border-red-400" : "border-gray-300"}`}
          />
        </label>
      )}

      {spec.value_type === "categorical" && (
        <CategoricalField
          spec={spec}
          item={item}
          missing={categoricalMissing}
          onChange={onChange}
        />
      )}

      <div className="mt-3 space-y-2">
        <label className="block text-xs text-gray-600">
          持续时间（小时） <span className="text-gray-400">选填</span>
          <input
            type="number"
            step="0.5"
            min={0}
            value={item.duration_hours ?? ""}
            onChange={(e) =>
              onChange({ duration_hours: e.target.value === "" ? null : Number(e.target.value) })
            }
            className="ml-2 w-24 px-2 py-1 border border-gray-300 rounded text-sm"
          />
        </label>
        <label className="block text-xs text-gray-600">
          <input
            type="checkbox"
            checked={item.interferes_with_adl === true}
            onChange={(e) => onChange({ interferes_with_adl: e.target.checked })}
            className="mr-2"
          />
          影响进食/日常活动
        </label>
      </div>
    </div>
  );
}

function CategoricalField({
  spec,
  item,
  missing,
  onChange,
}: {
  spec: SymptomSpec;
  item: SymptomItem;
  missing: boolean;
  onChange: (patch: Partial<SymptomItem>) => void;
}) {
  const opts = gradeOptions(spec);

  function isSelected(opt: { value: number | string; field: string }): boolean {
    return opt.field === "ctcae_grade"
      ? item.ctcae_grade === opt.value
      : item.categorical_value === opt.value;
  }
  function pick(opt: { value: number | string; field: string }): void {
    if (opt.field === "ctcae_grade") {
      onChange({ ctcae_grade: opt.value as number, categorical_value: null });
    } else {
      onChange({ categorical_value: String(opt.value), ctcae_grade: null });
    }
  }

  return (
    <fieldset className="text-sm">
      <legend className="text-gray-600">
        严重程度{missing && <span className="text-red-600 ml-1">*必填</span>}
      </legend>
      <div className={`mt-1 flex flex-wrap gap-2 ${missing ? "p-2 border border-red-400 rounded" : ""}`}>
        {opts.map((opt) => {
          const selected = isSelected(opt);
          return (
            <button
              key={`${opt.field}-${opt.value}`}
              type="button"
              onClick={() => pick(opt)}
              aria-pressed={selected}
              className={`px-3 py-1 text-sm rounded-full border ${
                selected ? "bg-blue-600 text-white border-blue-600" : "bg-white text-gray-700 border-gray-300"
              }`}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

function readNumericContext(ctx: Record<string, unknown>, key: string): number | null {
  const v = ctx[key];
  if (typeof v === "number") return v;
  if (typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v))) return Number(v);
  return null;
}
