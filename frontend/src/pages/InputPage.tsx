import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { analytics } from "../lib/analytics";
import {
  extractAssessment,
  ExtractFailedError,
  ExtractResponse,
} from "../api/client";
import {
  emptyParsedSymptoms,
  ParsedSymptomsForm,
} from "../lib/symptom_dict";
import ChecklistInput from "../components/ChecklistInput";

type Mode = "free_text" | "checklist";

export default function InputPage() {
  const [mode, setMode] = useState<Mode>("free_text");
  const [text, setText] = useState("");
  const [formData, setFormData] = useState<ParsedSymptomsForm>(
    emptyParsedSymptoms()
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  // 一次进入页面 = 一个 idempotency_key（最终提交时用）
  const idempotencyKeyRef = useRef<string>(crypto.randomUUID());

  useEffect(() => {
    analytics.emit("assessment_started");
  }, []);

  const canSubmit =
    !submitting &&
    (mode === "free_text"
      ? text.trim().length > 0
      : formData.symptoms.length > 0);

  async function handleSubmit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    analytics.emit("assessment_submitted", { mode });

    const payload =
      mode === "free_text"
        ? { input_source: "free_text" as const, raw_input_text: text }
        : { input_source: "checklist" as const, form_payload: formData };

    // 即使后端没起，至少能在 console 里验证 payload 形状
    if (import.meta.env.DEV) {
      console.log("[InputPage] submit payload", payload);
    }

    try {
      const extraction: ExtractResponse = await extractAssessment(payload);
      navigate("/confirm", {
        state: {
          extraction,
          raw_input_text: mode === "free_text" ? text : "",
          input_source: mode,
          idempotency_key: idempotencyKeyRef.current,
        },
      });
    } catch (err) {
      if (err instanceof ExtractFailedError) {
        setError(err.detail);
        if (err.reason === "extraction_failed" && mode === "free_text") {
          // LLM 失败 → 建议用户切清单
          setMode("checklist");
        }
      } else {
        console.error(err);
        setError("提交失败，请稍后重试");
      }
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">描述您的症状</h1>

      {/* mode toggle (segmented) */}
      <div className="inline-flex rounded-md border bg-white overflow-hidden text-sm">
        <button
          type="button"
          onClick={() => setMode("free_text")}
          className={
            "px-4 py-2 " +
            (mode === "free_text"
              ? "bg-blue-600 text-white"
              : "text-gray-700 hover:bg-gray-50")
          }
        >
          📝 自然语言
        </button>
        <button
          type="button"
          onClick={() => setMode("checklist")}
          className={
            "px-4 py-2 border-l " +
            (mode === "checklist"
              ? "bg-blue-600 text-white"
              : "text-gray-700 hover:bg-gray-50")
          }
        >
          ☑️ 清单
        </button>
      </div>

      {mode === "free_text" ? (
        <FreeTextMode text={text} setText={setText} />
      ) : (
        <ChecklistInput value={formData} onChange={setFormData} />
      )}

      {error && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md p-3">
          {error}
        </div>
      )}

      <div className="pt-2">
        <button
          onClick={handleSubmit}
          disabled={!canSubmit}
          className="px-4 py-2 bg-blue-600 text-white rounded-md disabled:bg-gray-300"
        >
          {submitting ? "分析中..." : "继续 →"}
        </button>
      </div>
    </div>
  );
}

function FreeTextMode({
  text,
  setText,
}: {
  text: string;
  setText: (v: string) => void;
}) {
  return (
    <div className="space-y-2">
      <p className="text-sm text-gray-600">描述您的不适：</p>
      <div className="relative">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={8}
          maxLength={4000}
          placeholder="例：今天发烧 38.5 度，浑身发冷..."
          className="w-full p-3 pr-12 border rounded-md text-sm"
        />
        <button
          type="button"
          disabled
          title="语音输入将在 v2 启用"
          className="absolute right-2 bottom-2 w-9 h-9 rounded-full border bg-gray-100 text-gray-400 cursor-not-allowed"
          aria-label="语音输入（v2 启用）"
        >
          🎤
        </button>
      </div>
      <div className="flex justify-between text-xs text-gray-500">
        <span>{text.length} / 4000 字</span>
      </div>
      <div className="bg-blue-50 border border-blue-200 rounded-md p-3 text-sm text-gray-700">
        <div className="font-medium mb-1">💡 描述时尽量包含：</div>
        <ul className="list-disc list-inside space-y-0.5">
          <li>症状是什么（发烧 / 恶心 / ...）</li>
          <li>严重程度（具体数字最好）</li>
          <li>距上次化疗多少天</li>
        </ul>
      </div>
    </div>
  );
}
