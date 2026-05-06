/**
 * Calendar utilities —— 自写月份网格 + 日期格式化
 *
 * 不依赖任何第三方日期库（date-fns / dayjs / etc）。
 * 仅使用原生 Date API + 简单工具函数。
 */

/**
 * 返回从「月初所在周的周日」到「月底所在周的周六」的连续日期数组。
 * 固定 6 行 × 7 列 = 42 天，避免不同月份 layout shift。
 *
 * 周起始：周日（与设计稿一致：日 一 二 三 四 五 六）
 */
export function buildMonthGrid(month: Date): Date[] {
  const year = month.getFullYear();
  const monthIdx = month.getMonth();

  // 月初
  const firstOfMonth = new Date(year, monthIdx, 1);
  // 起点：月初向前回退到周日
  const start = new Date(firstOfMonth);
  start.setDate(firstOfMonth.getDate() - firstOfMonth.getDay());

  const days: Date[] = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    days.push(d);
  }
  return days;
}

/**
 * 把 `created_at` 是 ISO 字符串的 items 按本地时区的 YYYY-MM-DD 分组。
 * 注意：使用本地时区，与日历显示一致；不要用 UTC。
 */
export function groupByDate<T extends { created_at: string }>(
  items: T[],
): Record<string, T[]> {
  const map: Record<string, T[]> = {};
  for (const item of items) {
    const d = new Date(item.created_at);
    const key = formatDate(d);
    if (!map[key]) map[key] = [];
    map[key].push(item);
  }
  // 同一天内按时间升序（早 → 晚），方便展开列表阅读
  for (const key of Object.keys(map)) {
    map[key].sort(
      (a, b) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    );
  }
  return map;
}

/** 本地时区下的 YYYY-MM-DD */
export function formatDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** ISO 字符串 → 本地 HH:mm */
export function formatTime(iso: string): string {
  const d = new Date(iso);
  const h = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${h}:${min}`;
}

const WEEKDAY_CN = ["日", "一", "二", "三", "四", "五", "六"];

/** YYYY-MM-DD → 「5 月 13 日，星期三」 */
export function formatChineseDate(isoDate: string): string {
  // 解析 YYYY-MM-DD 为本地日期（避开 new Date('YYYY-MM-DD') 的 UTC 解析陷阱）
  const [y, m, d] = isoDate.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return `${m} 月 ${d} 日，星期${WEEKDAY_CN[date.getDay()]}`;
}

/** 同一天（年月日） */
export function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/**
 * 最近 7 天（含今天）的日均评估次数。
 * 例：7 天里一共 10 条 → 1.43。
 */
export function calculateWeeklyAverage(
  items: Array<{ created_at: string }>,
): number {
  const now = new Date();
  const sevenDaysAgo = new Date(now);
  sevenDaysAgo.setDate(now.getDate() - 6); // 含今天共 7 天
  sevenDaysAgo.setHours(0, 0, 0, 0);
  const recent = items.filter(
    (i) => new Date(i.created_at).getTime() >= sevenDaysAgo.getTime(),
  );
  return Math.round((recent.length / 7) * 10) / 10;
}
