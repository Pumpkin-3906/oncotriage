import { describe, expect, it } from "vitest";

import type { SymptomItem, ParsedSymptomsForm } from "./symptom_dict";
import { countEdits, recomputeCompleteness } from "./symptom_dict";

function emptyItem(symptom_id: string): SymptomItem {
  return {
    symptom_id,
    numeric_value: null,
    numeric_unit: null,
    categorical_value: null,
    ctcae_grade: null,
    duration_hours: null,
    interferes_with_adl: null,
  };
}

function wrap(symptoms: SymptomItem[]): ParsedSymptomsForm {
  return { symptoms, context: {}, confidence: 0.9 };
}

describe("recomputeCompleteness", () => {
  it("空 symptoms 视为完整（兜底由 R999 处理）", () => {
    const r = recomputeCompleteness(wrap([]));
    expect(r.is_complete).toBe(true);
    expect(r.missing_slots).toEqual([]);
  });

  it("numeric 缺 numeric_value → 不完整", () => {
    const r = recomputeCompleteness(wrap([emptyItem("fever")]));
    expect(r.is_complete).toBe(false);
    expect(r.missing_slots).toEqual([
      { symptom_id: "fever", missing_fields: ["numeric_value"] },
    ]);
  });

  it("numeric 有 numeric_value → 完整", () => {
    const item = { ...emptyItem("fever"), numeric_value: 38.5 };
    expect(recomputeCompleteness(wrap([item])).is_complete).toBe(true);
  });

  it("categorical (ctcae_v5) 有 ctcae_grade → 完整", () => {
    const item = { ...emptyItem("nausea"), ctcae_grade: 1 };
    expect(recomputeCompleteness(wrap([item])).is_complete).toBe(true);
  });

  it("categorical (severity_3) 用 categorical_value → 完整", () => {
    const item = { ...emptyItem("hot_flashes"), categorical_value: "mild" };
    expect(recomputeCompleteness(wrap([item])).is_complete).toBe(true);
  });

  it("categorical 两个等级字段都缺 → 列出两候选", () => {
    const r = recomputeCompleteness(wrap([emptyItem("nausea")]));
    expect(r.is_complete).toBe(false);
    expect(r.missing_slots[0].symptom_id).toBe("nausea");
    expect(r.missing_slots[0].missing_fields).toEqual([
      "ctcae_grade",
      "categorical_value",
    ]);
  });

  it("字典外 symptom_id → 标记 unknown", () => {
    const r = recomputeCompleteness(wrap([emptyItem("not_a_real_symptom")]));
    expect(r.is_complete).toBe(false);
    expect(r.missing_slots[0].missing_fields).toEqual([
      "unknown_symptom_in_dictionary",
    ]);
  });

  it("混合：一个 OK 一个缺 → 不完整且只列出缺的", () => {
    const ok = { ...emptyItem("fever"), numeric_value: 38.0 };
    const missing = emptyItem("nausea");
    const r = recomputeCompleteness(wrap([ok, missing]));
    expect(r.is_complete).toBe(false);
    expect(r.missing_slots).toHaveLength(1);
    expect(r.missing_slots[0].symptom_id).toBe("nausea");
  });
});

describe("countEdits", () => {
  it("没改动 → 0", () => {
    const item = { ...emptyItem("fever"), numeric_value: 38.5 };
    const a = wrap([item]);
    const b = wrap([{ ...item }]);
    expect(countEdits(a, b)).toBe(0);
  });

  it("用户改了字段 → 1", () => {
    const a = wrap([{ ...emptyItem("fever"), numeric_value: 38.5 }]);
    const b = wrap([{ ...emptyItem("fever"), numeric_value: 39.0 }]);
    expect(countEdits(a, b)).toBe(1);
  });

  it("用户删除一个、新增一个 → 2", () => {
    const a = wrap([emptyItem("fever")]);
    const b = wrap([emptyItem("nausea")]);
    expect(countEdits(a, b)).toBe(2);
  });
});
