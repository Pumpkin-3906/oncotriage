import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { listAssessments, AssessmentSummary } from "../api/client";
import {
  buildMonthGrid,
  groupByDate,
  formatDate,
  formatTime,
  formatChineseDate,
  isSameDay,
  calculateWeeklyAverage,
} from "../lib/calendar";
import {
  dotColor,
  riskBadgeStyle,
  riskLabel,
  primarySymptomLabel,
} from "../lib/risk";

const DEMO_USER_ID_FALLBACK = "00000000-0000-0000-0000-000000000001";
const WEEK_HEADER = ["日", "一", "二", "三", "四", "五", "六"];

export default function HistoryPage() {
  const [items, setItems] = useState<AssessmentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentMonth, setCurrentMonth] = useState<Date>(() => {
    const d = new Date();
    d.setDate(1);
    d.setHours(0, 0, 0, 0);
    return d;
  });
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  useEffect(() => {
    const userId =
      localStorage.getItem("sz_demo_user_id") || DEMO_USER_ID_FALLBACK;
    listAssessments(userId)
      .then(setItems)
      .finally(() => setLoading(false));
  }, []);

  const stats = useMemo(
    () => ({
      total: items.length,
      high: items.filter((i) => i.risk_level === "high").length,
      medium: items.filter((i) => i.risk_level === "medium").length,
      low: items.filter((i) => i.risk_level === "low").length,
      weeklyAvg: calculateWeeklyAverage(items),
    }),
    [items],
  );

  const monthGrid = useMemo(() => buildMonthGrid(currentMonth), [currentMonth]);
  const itemsByDate = useMemo(() => groupByDate(items), [items]);

  if (loading) return <div>加载中...</div>;

  if (items.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        <div className="text-5xl mb-3">📋</div>
        <p>还没有评估记录</p>
        <Link
          to="/"
          className="inline-block mt-3 px-4 py-2 bg-blue-600 text-white rounded"
        >
          开始第一次评估
        </Link>
      </div>
    );
  }

  const today = new Date();
  const monthLabel = `${currentMonth.getFullYear()} 年 ${currentMonth.getMonth() + 1} 月`;
  const selectedItems = selectedDate ? (itemsByDate[selectedDate] ?? []) : [];

  function goPrevMonth() {
    setCurrentMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1));
  }
  function goNextMonth() {
    setCurrentMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1));
  }
  function goToday() {
    const d = new Date();
    d.setDate(1);
    d.setHours(0, 0, 0, 0);
    setCurrentMonth(d);
    setSelectedDate(formatDate(new Date()));
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">历史记录</h1>

      {/* 概览栏 */}
      <div className="p-3 bg-white border rounded-lg text-sm space-y-1">
        <div>
          共评估 <span className="font-medium">{stats.total}</span> 次 · 高风险{" "}
          <span className="text-red-600 font-medium">{stats.high}</span> · 中{" "}
          <span className="text-amber-600 font-medium">{stats.medium}</span> · 低{" "}
          <span className="text-green-600 font-medium">{stats.low}</span>
        </div>
        <div className="text-gray-500">
          最近一周：每天平均 {stats.weeklyAvg} 次
        </div>
      </div>

      {/* 月份导航 + 日历 */}
      <div className="p-3 bg-white border rounded-lg">
        <div className="flex items-center justify-between mb-3">
          <button
            type="button"
            onClick={goPrevMonth}
            className="px-2 py-1 rounded hover:bg-gray-100 text-gray-600"
            aria-label="上个月"
          >
            ‹
          </button>
          <div className="flex items-center gap-2">
            <span className="font-medium">{monthLabel}</span>
            <button
              type="button"
              onClick={goToday}
              className="text-xs px-2 py-0.5 border rounded text-gray-600 hover:bg-gray-100"
            >
              今天
            </button>
          </div>
          <button
            type="button"
            onClick={goNextMonth}
            className="px-2 py-1 rounded hover:bg-gray-100 text-gray-600"
            aria-label="下个月"
          >
            ›
          </button>
        </div>

        <div className="grid grid-cols-7 gap-1">
          {WEEK_HEADER.map((d) => (
            <div
              key={d}
              className="text-xs text-center text-gray-500 py-1 select-none"
            >
              {d}
            </div>
          ))}
          {monthGrid.map((day) => {
            const dateKey = formatDate(day);
            const dayItems = itemsByDate[dateKey] || [];
            const isToday = isSameDay(day, today);
            const isCurrentMonth = day.getMonth() === currentMonth.getMonth();
            const isSelected = dateKey === selectedDate;
            return (
              <button
                key={dateKey}
                type="button"
                onClick={() => setSelectedDate(dateKey)}
                className={[
                  "min-h-11 p-1 rounded-lg text-center",
                  isToday ? "ring-2 ring-blue-500" : "",
                  isSelected ? "bg-blue-50" : "",
                  isCurrentMonth ? "" : "text-gray-300",
                  dayItems.length > 0 ? "hover:bg-gray-100" : "hover:bg-gray-50",
                ]
                  .filter(Boolean)
                  .join(" ")}
                aria-label={`${dateKey}${dayItems.length ? `，${dayItems.length} 条评估` : ""}`}
              >
                <div className="text-sm">{day.getDate()}</div>
                <div className="flex justify-center items-center gap-0.5 mt-0.5 h-2">
                  {dayItems.slice(0, 3).map((item, i) => (
                    <span
                      key={i}
                      className={`w-1.5 h-1.5 rounded-full ${dotColor(item.risk_level)}`}
                    />
                  ))}
                  {dayItems.length > 3 && (
                    <span className="text-[10px] leading-none text-gray-500 ml-0.5">
                      +{dayItems.length - 3}
                    </span>
                  )}
                </div>
              </button>
            );
          })}
        </div>

        {/* 图例 */}
        <div className="flex items-center gap-3 mt-3 text-xs text-gray-500">
          <span className="flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full ${dotColor("high")}`} />
            高风险
          </span>
          <span className="flex items-center gap-1">
            <span
              className={`w-1.5 h-1.5 rounded-full ${dotColor("medium")}`}
            />
            中风险
          </span>
          <span className="flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full ${dotColor("low")}`} />
            低风险
          </span>
        </div>
      </div>

      {/* 选中日期展开列表 */}
      {selectedDate && (
        <div className="p-3 bg-white border rounded-lg">
          <h3 className="font-medium mb-2">{formatChineseDate(selectedDate)}</h3>
          {selectedItems.length === 0 ? (
            <p className="text-sm text-gray-500">这一天没有评估记录。</p>
          ) : (
            <ul>
              {selectedItems.map((item) => (
                <li
                  key={item.assessment_id}
                  className="border-b last:border-0"
                >
                  <Link
                    to={`/result/${item.assessment_id}`}
                    className="flex items-center py-2 text-sm hover:bg-gray-50 -mx-3 px-3"
                  >
                    <span className="text-gray-600 tabular-nums">
                      {formatTime(item.created_at)}
                    </span>
                    <span
                      className={`ml-2 px-2 py-0.5 rounded text-xs ${riskBadgeStyle(item.risk_level)}`}
                    >
                      {riskLabel(item.risk_level)}
                    </span>
                    {item.primary_symptom && (
                      <span className="ml-2 text-gray-600">
                        {primarySymptomLabel(item.primary_symptom)}
                      </span>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
