/** 前端預設值。只影響表單的預設，不影響既有預約，使用者仍可修改。 */

/** 新增預約時，結束時間預設為開始時間加這麼多分鐘。 */
export const DEFAULT_SESSION_MINUTES = 50;

/** "HH:MM" 加上分鐘數（跨午夜時回到 00:00 起算，不跨日）。 */
export function addMinutes(t: string, minutes: number): string {
  const [h, m] = t.split(":").map(Number);
  const total = Math.min(h * 60 + m + minutes, 23 * 60 + 59);
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}
