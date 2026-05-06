/**
 * Risk-level 展示工具：标签文案、dot 颜色、badge 样式。
 *
 * 集中放这里，HistoryPage / ResultPage 共用，避免硬编码 color class。
 */

export const RISK_LABEL: Record<string, string> = {
  high: "高风险",
  medium: "中风险",
  low: "低风险",
};

export function riskLabel(risk: string): string {
  return RISK_LABEL[risk] ?? risk;
}

/** 日历 cell 上的小圆点底色 */
export function dotColor(risk: string): string {
  switch (risk) {
    case "high":
      return "bg-red-500";
    case "medium":
      return "bg-amber-500";
    case "low":
      return "bg-green-500";
    default:
      return "bg-gray-400";
  }
}

/** 列表/详情页的 badge 样式 */
export function riskBadgeStyle(risk: string): string {
  switch (risk) {
    case "high":
      return "bg-red-100 text-red-700";
    case "medium":
      return "bg-amber-100 text-amber-800";
    case "low":
      return "bg-green-100 text-green-700";
    default:
      return "bg-gray-100 text-gray-700";
  }
}

/**
 * 已知 symptom_id → 中文标签的简单映射。
 * 与后端 dictionary_snapshot 中的 symptom_id 对应；未知值原样返回。
 */
const SYMPTOM_LABEL: Record<string, string> = {
  fever: "发热",
  diarrhea: "腹泻",
  vomiting: "呕吐",
  hand_foot_syndrome: "手足综合征",
  fatigue: "疲劳",
  nausea: "恶心",
  rash: "皮疹",
  pain: "疼痛",
  bleeding: "出血",
  dyspnea: "呼吸困难",
};

export function primarySymptomLabel(symptomId: string): string {
  return SYMPTOM_LABEL[symptomId] ?? symptomId;
}
