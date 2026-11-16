"use client";

import { useState } from "react";
import { clientFetch } from "@/lib/client-api";
import { money } from "@/lib/format";

/**
 * 報到／收款明細：方案名稱、應收金額、自付額、交通費、收款方式。
 * 只記錄「已收／未收／免收」與收款方式、時間、經手人；不產生核銷、流水、對帳。
 * 行政可記錄；心理師只能唯讀自己個案的資訊。
 */
export type CollectAppt = {
  id: number;
  case_name: string | null;
  status: string;
  funding_source?: string | null;
  plan_name?: string | null;
  rate_item_label?: string | null;
  amount?: number;
  self_pay_amount?: number;
  transport_fee?: number;
  no_show_fee?: number;
  no_show_type?: string | null;
  payment_status?: string;
  payment_method?: string | null;
  paid_at?: string | null;
  paid_by_name?: string | null;
};

export const PAYMENT_STATUS_LABEL: Record<string, string> = { unpaid: "未收", paid: "已收", waived: "免收" };
export const PAYMENT_METHOD_LABEL: Record<string, string> = { cash: "現金", transfer: "轉帳", card: "刷卡", other: "其他" };

export function PaymentBadge({ a }: { a: CollectAppt }) {
  const s = a.payment_status ?? "unpaid";
  const cls = s === "paid" ? "bg-green-100 text-green-700" : s === "waived" ? "bg-gray-200 text-gray-600" : "bg-amber-100 text-amber-700";
  return (
    <span className={`rounded px-1 text-[9px] ${cls}`}>
      {PAYMENT_STATUS_LABEL[s] ?? s}
      {s === "paid" && a.payment_method ? `・${PAYMENT_METHOD_LABEL[a.payment_method] ?? a.payment_method}` : ""}
    </span>
  );
}

export function CollectionModal({
  token,
  appt,
  canRecord,
  onClose,
  onDone,
}: {
  token: string;
  appt: CollectAppt;
  canRecord: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const [status, setStatus] = useState(appt.payment_status ?? "unpaid");
  const [method, setMethod] = useState(appt.payment_method ?? "cash");
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const institution = appt.funding_source === "institution";
  const isNoShow = appt.status === "no_show";

  async function save() {
    setSaving(true);
    setErr(null);
    try {
      await clientFetch(`/appointments/${appt.id}/collection`, token, {
        method: "PUT",
        body: JSON.stringify({ payment_status: status, payment_method: status === "paid" ? method : null }),
      });
      onDone();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  const row = (k: string, v: React.ReactNode) => (
    <div className="flex justify-between gap-4 border-b border-gray-100 py-1.5 text-sm">
      <span className="text-gray-500">{k}</span>
      <span className="text-right font-medium">{v}</span>
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-3 text-lg font-bold">收款明細 — {appt.case_name}</h2>
        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}
        <div className="mb-4">
          {row("付款方式", institution ? "機構" : "自費")}
          {institution && row("方案", appt.plan_name ?? "—")}
          {institution && appt.rate_item_label && row("價目項目", appt.rate_item_label)}
          {row("應收金額", money(appt.amount ?? 0))}
          {row("個案自付額", money(appt.self_pay_amount ?? 0))}
          {institution && row("交通費", money(appt.transport_fee ?? 0))}
          {isNoShow && row("失約費（應收提示）", money(appt.no_show_fee ?? 0))}
          {row(
            "收款狀態",
            <>
              {PAYMENT_STATUS_LABEL[appt.payment_status ?? "unpaid"]}
              {appt.payment_method ? `（${PAYMENT_METHOD_LABEL[appt.payment_method] ?? appt.payment_method}）` : ""}
            </>,
          )}
          {appt.paid_at && row("收款時間／經手", `${appt.paid_at.slice(0, 16).replace("T", " ")}　${appt.paid_by_name ?? ""}`)}
        </div>

        {canRecord ? (
          <>
            <div className="mb-3 flex gap-4 text-sm">
              {(["unpaid", "paid", "waived"] as const).map((s) => (
                <label key={s} className="flex items-center gap-1.5">
                  <input type="radio" checked={status === s} onChange={() => setStatus(s)} />
                  {PAYMENT_STATUS_LABEL[s]}
                </label>
              ))}
            </div>
            {status === "paid" && (
              <label className="mb-3 block text-sm">
                <span className="mb-1 block text-xs font-medium text-gray-700">收款方式</span>
                <select value={method} onChange={(e) => setMethod(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                  {Object.entries(PAYMENT_METHOD_LABEL).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </label>
            )}
            <p className="mb-3 text-xs text-gray-400">只記錄收款狀態，不產生核銷、流水或對帳。</p>
          </>
        ) : (
          <p className="mb-3 text-xs text-gray-400">心理師唯讀；收款由行政人員記錄。</p>
        )}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">關閉</button>
          {canRecord && (
            <button onClick={save} disabled={saving} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
              {saving ? "儲存中..." : "儲存"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
