/** 日期／識別碼格式化 — V2升級計畫 11 §4.2。 */

import type { CaseItem, Appointment } from "./types";

export function fmtDate(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}`;
}
export function fmtTime(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function caseDisplayId(c: CaseItem) {
  if (c.case_number) return c.case_number;
  if (c.temp_seq) return `#${String(c.temp_seq).padStart(4, "0")}`;
  return "—";
}

export function visitId(c: CaseItem | null, appt: Appointment) {
  if (!c) return `—`;
  const prefix = c.case_number ?? `#${String(c.temp_seq ?? 0).padStart(4, "0")}`;
  return `${prefix}-${String(appt.visit_seq ?? 0).padStart(3, "0")}`;
}

/* ═══════════════════════════════════════════════════
   Main Page
   ═══════════════════════════════════════════════════ */

