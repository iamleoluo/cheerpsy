/** Phase 3/4 前端共用的格式化工具。 */

export function money(n: number | null | undefined): string {
  return `$${Number(n ?? 0).toLocaleString()}`;
}

export function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
}

export function shiftDate(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
}

export function hhmm(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** 營業時段 08:00–22:00，30 分半格（原型 rooms 定案②） */
export const DAY_START_MIN = 8 * 60;
export const DAY_END_MIN = 22 * 60;
export const SLOT_MIN = 30;

export function minutesOfDay(iso: string): number {
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes();
}

export function slotLabels(): string[] {
  const out: string[] = [];
  for (let m = DAY_START_MIN; m < DAY_END_MIN; m += SLOT_MIN) {
    out.push(`${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`);
  }
  return out;
}

export const SESSION_TYPE: Record<string, string> = {
  in_person: "現場",
  online: "視訊",
  outdoor: "外展",
};

export const FEE_ITEMS: [string, string][] = [
  ["psychotherapy", "心理治療"],
  ["counseling", "心理諮商"],
  ["visitation", "會面交往"],
  ["summary_report", "摘要報告"],
  ["other", "其他"],
];

export const NO_SHOW_TYPES: [string, string, number][] = [
  ["advance_notice", "24 小時前請假", 0],
  ["late_cancel", "臨時取消", 200],
  ["no_notice", "無故未到", 500],
];

export const PAYMENT_TRACKS: [string, string][] = [
  ["immediate", "未收"],
  ["monthly", "月結"],
  ["institution", "機構應收"],
];
