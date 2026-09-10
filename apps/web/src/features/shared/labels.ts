/**
 * 狀態顯示字串與對應的語意色 — V2升級計畫 11 §4.2。
 *
 * 這兩張 *Colors 表原本寫死色階（bg-blue-100 / bg-green-100 / …）。P3 搬檔時
 * 一併換成語意 token：它們本來就是「狀態 → 顏色」的對應，正是 11 §2.2 那條
 * 規則要處理的東西，而且只有兩行，不算混入視覺改動。
 *
 * 選 tone 的判準是**這件事現在怎麼了**，不是它原本長什麼顏色：
 *   pending 還沒發生 · active 正在進行 · done 成功結束
 *   warn 要注意但沒壞 · danger 壞掉了 · muted 今天不用再碰
 */

export const statusLabels: Record<string, string> = {
  initial: "已預約未初談",
  ongoing: "進行中",
  paused: "暫停",
  closed: "結案",
  lost: "流失",
};

export const statusColors: Record<string, string> = {
  initial: "bg-st-pending-bg text-st-pending", // 還沒初談，等於還沒真的開始
  ongoing: "bg-st-active-bg text-st-active",
  paused: "bg-st-warn-bg text-st-warn", // 要注意但沒壞
  closed: "bg-st-muted-bg text-st-muted", // 已結束，退到背景去
  lost: "bg-st-danger-bg text-st-danger",
};

export const apptStatusLabels: Record<string, string> = {
  booked: "已預約",
  executed: "已執行",
  cancelled: "已取消",
};

export const apptStatusColors: Record<string, string> = {
  booked: "bg-st-pending-bg text-st-pending",
  executed: "bg-st-done-bg text-st-done",
  cancelled: "bg-st-muted-bg text-st-muted",
};

export const billingLabels: Record<string, string> = {
  once: "次結",
  monthly: "月結",
  multiple: "多次結",
};

export const sessionTypeLabels: Record<string, string> = {
  in_person: "現場",
  online: "線上",
  outdoor: "外出",
};
