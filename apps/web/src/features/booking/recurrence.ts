/**
 * 批次預約的週期展開 — V2升級計畫 11 §4.2。
 *
 * 純函式，沒有 React 相依，所以獨立成一個檔案方便日後補測試（目前無測試覆蓋）。
 * 依 v7 預約作業定案 ②：批次遇國定假日**只標示提醒、不自動跳過**，由心理師
 * 與個案另行喬時間——所以這裡不做任何假日過濾。
 */

export const DOW_LABELS = ["日", "一", "二", "三", "四", "五", "六"];
export const WEEK_OF_MONTH_LABELS = ["第1個", "第2個", "第3個", "第4個", "最後一個"];

export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function formatPreviewDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return `${d.getMonth() + 1}/${d.getDate()} (${DOW_LABELS[d.getDay()]})`;
}

export function generateWeeklySlots(
  dowTarget: number,   // 0=Sun … 6=Sat
  startDate: string,  // YYYY-MM-DD — first possible date
  startTime: string,
  endTime: string,
  count: number,
): { date: string; start: string; end: string }[] {
  const results: { date: string; start: string; end: string }[] = [];
  const cur = new Date(startDate + "T00:00:00");
  // advance to first matching weekday
  while (cur.getDay() !== dowTarget) cur.setDate(cur.getDate() + 1);
  for (let i = 0; i < count; i++) {
    results.push({ date: isoDate(cur), start: startTime, end: endTime });
    cur.setDate(cur.getDate() + 7);
  }
  return results;
}

export function generateBiweeklySlots(
  dowTarget: number,
  startDate: string,
  startTime: string,
  endTime: string,
  count: number,
): { date: string; start: string; end: string }[] {
  const results: { date: string; start: string; end: string }[] = [];
  const cur = new Date(startDate + "T00:00:00");
  while (cur.getDay() !== dowTarget) cur.setDate(cur.getDate() + 1);
  for (let i = 0; i < count; i++) {
    results.push({ date: isoDate(cur), start: startTime, end: endTime });
    cur.setDate(cur.getDate() + 14);
  }
  return results;
}

export function nthWeekdayOfMonth(year: number, month: number, dow: number, n: number): Date | null {
  // n = 1..4 or -1 for last
  if (n === -1) {
    // last occurrence: start from last day, go back
    const d = new Date(year, month + 1, 0); // last day of month
    while (d.getDay() !== dow) d.setDate(d.getDate() - 1);
    return d;
  }
  // find nth occurrence (1-based)
  const d = new Date(year, month, 1);
  while (d.getDay() !== dow) d.setDate(d.getDate() + 1);
  d.setDate(d.getDate() + (n - 1) * 7);
  // ensure still in month
  if (d.getMonth() !== month) return null;
  return d;
}

export function generateMonthlySlots(
  dow: number,
  weekOfMonth: number,  // 1..4 or -1 for last
  startMonth: string,   // YYYY-MM
  startTime: string,
  endTime: string,
  count: number,
): { date: string; start: string; end: string }[] {
  const results: { date: string; start: string; end: string }[] = [];
  const [y, m] = startMonth.split("-").map(Number);
  let year = y;
  let month = m - 1; // JS month 0-based
  while (results.length < count) {
    const d = nthWeekdayOfMonth(year, month, dow, weekOfMonth);
    if (d) results.push({ date: isoDate(d), start: startTime, end: endTime });
    month++;
    if (month > 11) { month = 0; year++; }
    if (year > y + 10) break; // safety
  }
  return results;
}

