"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import { AmountField, parseAmount, useCanEditAmount } from "@/components/amount-field";

/**
 * 預約的「金流資訊」欄位：付款方式（自費／機構）、機構額度、金額。
 *
 * 機構方案屬金流資訊（保留）；核銷、對帳、流水帳冊已移除，這裡只記錄資訊，不產生任何帳務紀錄。
 * 額度只顯示「總堂數、已用、剩餘」，不擋預約：額度不足時照常建立，伺服器回 warnings 由呼叫端顯示。
 */
export type BillingValue = {
  funding: "self_pay" | "institution";
  quotaId: string; // "" = 自動挑
  amount: string;
};

export const EMPTY_BILLING: BillingValue = { funding: "self_pay", quotaId: "", amount: "" };

type QuotaOption = {
  id: number;
  institution_name: string | null;
  plan_name: string | null;
  total_count: number;
  used_count: number;
  remaining: number;
  valid_until: string | null;
};

/** 行政與管理員：能改付款方式、額度（心理師只能改自己預約的金額）。 */
export function useIsStaff(): boolean {
  const { data } = useSession();
  const role = (data?.user as any)?.role;
  return role === "admin" || role === "staff";
}

/** 轉成送出的欄位：付款方式一定送，額度與金額有值才送。 */
export function billingBody(v: BillingValue, canAmount: boolean): Record<string, unknown> {
  const body: Record<string, unknown> = { funding_source: v.funding };
  if (v.funding === "institution" && v.quotaId) body.quota_id = Number(v.quotaId);
  const amt = canAmount ? parseAmount(v.amount) : undefined;
  if (amt !== undefined) body.amount = amt;
  return body;
}

/** 建立預約後伺服器回的提示（額度不足等）；沒有就回空字串。 */
export function warningsText(res: unknown): string {
  const rows = Array.isArray(res) ? res : [res];
  const all = new Set<string>();
  for (const r of rows) for (const w of ((r as { warnings?: string[] } | null)?.warnings ?? [])) all.add(w);
  return [...all].join("；");
}

export function BillingFields({
  token,
  caseId,
  caseFunding,
  date,
  value,
  onChange,
  className = "",
}: {
  token: string;
  caseId: number | 0;
  caseFunding?: string | null; // 選了個案後，付款方式預設跟著個案
  date: string; // YYYY-MM-DD，用來找當天有效的額度
  value: BillingValue;
  onChange: (v: BillingValue) => void;
  className?: string;
}) {
  const canAmount = useCanEditAmount();
  const [quotas, setQuotas] = useState<QuotaOption[]>([]);

  useEffect(() => {
    if (caseFunding === "institution" || caseFunding === "self_pay") {
      onChange({ ...value, funding: caseFunding, quotaId: "" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, caseFunding]);

  useEffect(() => {
    if (!caseId || value.funding !== "institution") {
      setQuotas([]);
      return;
    }
    clientFetch(`/cases/${caseId}/quotas/available?on_date=${date}`, token)
      .then((rows: QuotaOption[]) => setQuotas(rows))
      .catch(() => setQuotas([]));
  }, [token, caseId, date, value.funding]);

  const set = (patch: Partial<BillingValue>) => onChange({ ...value, ...patch });

  return (
    <div className={`space-y-3 ${className}`}>
      <div className="text-sm">
        <span className="mb-1 block text-xs font-medium text-gray-700">付款方式</span>
        <div className="flex gap-4">
          <label className="flex items-center gap-1.5">
            <input type="radio" checked={value.funding === "self_pay"} onChange={() => set({ funding: "self_pay", quotaId: "" })} />
            自費
          </label>
          <label className="flex items-center gap-1.5">
            <input type="radio" checked={value.funding === "institution"} onChange={() => set({ funding: "institution" })} />
            機構
          </label>
        </div>
      </div>

      {value.funding === "institution" && (
        <label className="block text-sm">
          <span className="mb-1 block text-xs font-medium text-gray-700">機構額度</span>
          <select
            value={value.quotaId}
            onChange={(e) => set({ quotaId: e.target.value })}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="">自動挑選（依到期日先到先用）</option>
            {quotas.map((q) => (
              <option key={q.id} value={q.id}>
                {(q.plan_name ?? q.institution_name ?? "機構")}：總 {q.total_count} 堂・已用 {q.used_count}・剩餘 {q.remaining}
                {q.valid_until ? `（至 ${q.valid_until}）` : ""}
              </option>
            ))}
          </select>
          {quotas.length === 0 && (
            <span className="mt-1 block text-xs text-amber-600">
              目前沒有可用額度。仍可建立預約（不佔額度），建立後會顯示提示。
            </span>
          )}
        </label>
      )}

      <AmountField value={value.amount} onChange={(v) => set({ amount: v })} />
    </div>
  );
}
