"use client";

import { money } from "@/lib/format";

/**
 * 預約的金額與經費來源顯示（只讀）。本系統不負責收款與對帳，只清楚呈現：
 * 自費／機構、機構名、方案、價目項目、總額、自付額、機構補助（總額−自付額，算出來不存）、交通費、剩餘堂數。
 * 機構預約的自付額為 null 代表「未設定」（舊資料算不出來，不猜）。
 */
export type BillingAppt = {
  case_name?: string | null;
  funding_source?: string | null;
  institution_name?: string | null;
  plan_name?: string | null;
  rate_item_label?: string | null;
  amount?: number;
  self_pay_amount?: number | null;
  institution_subsidy?: number | null;
  transport_fee?: number;
  transport_fee_label?: string | null;
  quota_used?: number | null;
  quota_total?: number | null;
  quota_remaining?: number | null;
  quota_is_last_session?: boolean;
};

export const isInstitution = (a: BillingAppt) => a.funding_source === "institution";
export const selfPayText = (a: BillingAppt) => (a.self_pay_amount == null ? "未設定" : money(a.self_pay_amount));
export const subsidyText = (a: BillingAppt) => (a.institution_subsidy == null ? "未設定" : money(a.institution_subsidy));

/** 一行摘要（日曆格子、列表用）。 */
export function billingLine(a: BillingAppt): string {
  if (!isInstitution(a)) return `自費 ${money(a.amount)}`;
  const parts = [
    `機構${a.institution_name ? ` ${a.institution_name}` : ""}`,
    a.plan_name ?? null,
    `總額 ${money(a.amount)}`,
    `自付 ${selfPayText(a)}`,
    `補助 ${subsidyText(a)}`,
  ];
  if (a.transport_fee) parts.push(`車馬 ${money(a.transport_fee)}`);
  if (a.quota_total != null) parts.push(`剩 ${a.quota_remaining} 堂${a.quota_is_last_session ? "（最後一次）" : ""}`);
  return parts.filter(Boolean).join("・");
}

export function BillingLine({ a, className = "" }: { a: BillingAppt; className?: string }) {
  return (
    <div className={`${isInstitution(a) && a.quota_is_last_session ? "font-medium text-red-600" : "text-gray-600"} ${className}`}>
      {billingLine(a)}
    </div>
  );
}

export function BillingDetailModal({ appt, onClose }: { appt: BillingAppt; onClose: () => void }) {
  const inst = isInstitution(appt);
  const row = (k: string, v: React.ReactNode) => (
    <div className="flex justify-between gap-4 border-b border-gray-100 py-1.5 text-sm">
      <span className="text-gray-500">{k}</span>
      <span className="text-right font-medium">{v}</span>
    </div>
  );
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-3 text-lg font-bold">金額與經費來源{appt.case_name ? ` — ${appt.case_name}` : ""}</h2>
        {row("付款方式", inst ? "機構" : "自費")}
        {inst && row("機構", appt.institution_name ?? "—")}
        {inst && row("方案", appt.plan_name ?? "—")}
        {inst && appt.rate_item_label && row("價目項目", appt.rate_item_label)}
        {row("總額", money(appt.amount))}
        {row("自付額", inst ? selfPayText(appt) : money(appt.amount))}
        {inst && row("機構補助", subsidyText(appt))}
        {inst && row("交通費", appt.transport_fee ? `${money(appt.transport_fee)}${appt.transport_fee_label ? `（${appt.transport_fee_label}）` : ""}` : "無")}
        {inst && appt.quota_total != null && row("額度", `總 ${appt.quota_total} 堂・已用 ${appt.quota_used}・剩 ${appt.quota_remaining}`)}
        <p className="mt-3 text-xs text-gray-400">本系統只呈現金額與經費來源，不處理收款與對帳。</p>
        <div className="mt-4 flex justify-end">
          <button onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">關閉</button>
        </div>
      </div>
    </div>
  );
}
