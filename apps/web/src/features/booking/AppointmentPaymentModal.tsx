"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { clientFetch } from "@/lib/client-api";
import type { Appointment, CaseItem, QuotaRow, RoomOption, Therapist } from "@/features/shared/types";
import { sessionTypeLabels } from "@/features/shared/labels";
import { fmtDate, fmtTime } from "@/features/shared/format";

/** 預約收款視窗 — 從 cases/page.tsx 搬出（11 §4.2）。 */

export function AppointmentPaymentModal({
  token, appointment, onClose, onSaved,
}: {
  token: string;
  appointment: Appointment;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [fundingSource, setFundingSource] = useState<"self_pay" | "institution">(
    (appointment.funding_source as any) ?? "self_pay",
  );
  const [quotaId, setQuotaId] = useState<string>(
    appointment.quota_id ? String(appointment.quota_id) : "",
  );
  const [availableQuotas, setAvailableQuotas] = useState<QuotaRow[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const apptDate = appointment.start_time?.slice(0, 10) ?? "";

  useEffect(() => {
    if (fundingSource !== "institution" || !apptDate) {
      setAvailableQuotas([]);
      return;
    }
    clientFetch(
      `/cases/${appointment.case_id}/quotas/available?on_date=${apptDate}`,
      token,
    )
      .then((rows: QuotaRow[]) => {
        setAvailableQuotas(rows);
        setQuotaId((cur) => {
          if (cur && rows.some((r) => r.id === Number(cur))) return cur;
          return rows[0] ? String(rows[0].id) : "";
        });
      })
      .catch(() => setAvailableQuotas([]));
  }, [token, fundingSource, appointment.case_id, apptDate]);

  const submit = async () => {
    setError("");
    if (fundingSource === "institution" && !quotaId) {
      setError("請選擇 Quota，或改回自費");
      return;
    }
    setSubmitting(true);
    try {
      await clientFetch(`/appointments/${appointment.id}/payment`, token, {
        method: "PUT",
        body: JSON.stringify({
          funding_source: fundingSource,
          quota_id: fundingSource === "institution" && quotaId ? Number(quotaId) : null,
        }),
      });
      onSaved();
    } catch (e: any) {
      setError(e.message ?? "儲存失敗");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h3 className="mb-4 text-lg font-bold">編輯付款方式</h3>
        <p className="mb-3 text-xs text-ink-3">
          預約 {appointment.appointment_number} · {apptDate}
        </p>

        {error && <div className="mb-3 rounded bg-st-danger-bg px-3 py-2 text-sm text-st-danger">{error}</div>}

        <div className="space-y-3 text-sm">
          <div className="flex gap-3">
            <label className="inline-flex items-center gap-1">
              <input
                type="radio"
                checked={fundingSource === "self_pay"}
                onChange={() => { setFundingSource("self_pay"); setQuotaId(""); }}
              />
              自費
            </label>
            <label className="inline-flex items-center gap-1">
              <input
                type="radio"
                checked={fundingSource === "institution"}
                onChange={() => setFundingSource("institution")}
              />
              機構
            </label>
          </div>

          {fundingSource === "institution" && (
            <div>
              <label className="mb-1 block text-xs text-ink-3">機構 Quota</label>
              <select
                value={quotaId}
                onChange={(e) => setQuotaId(e.target.value)}
                className="w-full rounded border border-line-2 px-3 py-2"
              >
                <option value="">{availableQuotas.length === 0 ? "該日無可用 Quota" : "請選擇"}</option>
                {availableQuotas.map((q) => (
                  <option key={q.id} value={q.id}>
                    {q.institution_name}｜剩餘 {q.remaining}/{q.total_count}｜到期 {q.valid_until ?? "永久"}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded border border-line-2 px-4 py-2 text-sm text-ink-2 hover:bg-surface-2">取消</button>
          <button
            onClick={submit}
            disabled={submitting}
            className="rounded bg-accent px-4 py-2 text-sm text-white hover:bg-st-active disabled:opacity-50"
          >
            {submitting ? "儲存中..." : "儲存"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   Appointment Edit Modal
   ═══════════════════════════════════════════════════ */

