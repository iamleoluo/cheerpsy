"use client";

import { useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import { parseAmount, useCanEditAmount } from "@/components/amount-field";
import { money } from "@/lib/format";

/**
 * 預約的「金流資訊」欄位：付款方式、機構額度、方案／價目項目／交通費、金額。
 *
 * 機構方案屬金流資訊（保留）；核銷、對帳、流水帳冊已移除，這裡只記錄資訊，不產生任何帳務紀錄。
 * - 自費：金額必填（個案要付的全額）。
 * - 機構：選方案、價目項目、交通費後，自動帶出應收與個案自付額；行政可手動調整應收（會留稽核）。
 * - 額度只顯示「總堂數、已用、剩餘」，不擋預約：額度不足時照常建立，伺服器回 warnings 由呼叫端顯示。
 */
export type BillingValue = {
  funding: "self_pay" | "institution";
  quotaId: string; // "" = 自動挑
  planId: string; // "" = 用額度所屬方案
  rateItemId: string; // "" = 自動挑
  transportId: string; // "" = 預設（現場無、外出用預設選項）
  amount: string; // 自費：全額（必填）；機構：手動調整應收（選填，空白＝依價目）
};

export const EMPTY_BILLING: BillingValue = {
  funding: "self_pay",
  quotaId: "",
  planId: "",
  rateItemId: "",
  transportId: "",
  amount: "",
};

type QuotaOption = {
  id: number;
  institution_name: string | null;
  plan_id: number | null;
  plan_name: string | null;
  total_count: number;
  used_count: number;
  remaining: number;
  valid_until: string | null;
};

type RateItem = {
  id: number;
  label: string;
  total_amount: number;
  self_pay_amount: number;
  duration_minutes: number | null;
};
type TransportOpt = { id: number; label: string; amount: number; is_default: boolean };
type PlanOpt = { id: number; name: string; quota_id: number | null; rate_items: RateItem[]; transport_fees: TransportOpt[] };

/** 轉成送出的欄位：付款方式一定送，其餘有值才送。 */
export function billingBody(v: BillingValue, canAmount: boolean): Record<string, unknown> {
  const body: Record<string, unknown> = { funding_source: v.funding };
  if (v.funding === "institution") {
    if (v.quotaId) body.quota_id = Number(v.quotaId);
    if (v.planId) body.plan_id = Number(v.planId);
    if (v.rateItemId) body.rate_item_id = Number(v.rateItemId);
    if (v.transportId) body.transport_fee_option_id = Number(v.transportId);
  }
  const amt = canAmount ? parseAmount(v.amount) : undefined;
  if (amt !== undefined) body.amount = amt;
  return body;
}

/** 自費預約必須填金額（機構案由方案帶出）。回傳錯誤訊息或空字串。 */
export function billingError(v: BillingValue): string {
  if (v.funding === "self_pay" && parseAmount(v.amount) === undefined) return "自費預約請填金額（免費請填 0）";
  return "";
}

/** 行政與管理員：能改付款方式、額度、方案（心理師只能改自己預約的金額）。 */
export function useIsStaff(): boolean {
  const { data } = useSession();
  const role = (data?.user as any)?.role;
  return role === "admin" || role === "staff";
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
  sessionType = "in_person",
  value,
  onChange,
  className = "",
}: {
  token: string;
  caseId: number | 0;
  caseFunding?: string | null; // 選了個案後，付款方式預設跟著個案
  date: string; // YYYY-MM-DD，用來找當天有效的額度
  sessionType?: string; // 外出才會自動帶預設交通費
  value: BillingValue;
  onChange: (v: BillingValue) => void;
  className?: string;
}) {
  const canAmount = useCanEditAmount();
  const [quotas, setQuotas] = useState<QuotaOption[]>([]);
  const [plans, setPlans] = useState<PlanOpt[]>([]);

  useEffect(() => {
    if (caseFunding === "institution" || caseFunding === "self_pay") {
      onChange({ ...EMPTY_BILLING, funding: caseFunding, amount: value.amount });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, caseFunding]);

  useEffect(() => {
    if (!caseId || value.funding !== "institution") {
      setQuotas([]);
      setPlans([]);
      return;
    }
    clientFetch(`/cases/${caseId}/quotas/available?on_date=${date}`, token)
      .then((rows: QuotaOption[]) => setQuotas(rows))
      .catch(() => setQuotas([]));
    clientFetch(`/cases/${caseId}/billing-options`, token)
      .then((o: { plans: PlanOpt[] }) => setPlans(o.plans))
      .catch(() => setPlans([]));
  }, [token, caseId, date, value.funding]);

  const set = (patch: Partial<BillingValue>) => onChange({ ...value, ...patch });

  // 實際使用的方案：手動選的 → 選到的額度所屬方案 → 只有一個方案就用它
  const effectivePlan = useMemo(() => {
    if (value.planId) return plans.find((p) => String(p.id) === value.planId);
    const q = quotas.find((x) => String(x.id) === value.quotaId) ?? (value.quotaId ? undefined : quotas[0]);
    if (q?.plan_id) return plans.find((p) => p.id === q.plan_id);
    return plans.length === 1 ? plans[0] : undefined;
  }, [plans, quotas, value.planId, value.quotaId]);

  const item = effectivePlan?.rate_items.find((r) => String(r.id) === value.rateItemId) ?? effectivePlan?.rate_items[0];
  const transport =
    effectivePlan?.transport_fees.find((t) => String(t.id) === value.transportId) ??
    (sessionType === "outdoor" ? effectivePlan?.transport_fees.find((t) => t.is_default) : undefined);

  const manual = parseAmount(value.amount);
  const shownTotal = manual ?? item?.total_amount;
  const shownSelfPay = item ? Math.min(item.self_pay_amount, shownTotal ?? item.total_amount) : undefined;

  return (
    <div className={`space-y-3 ${className}`}>
      <div className="text-sm">
        <span className="mb-1 block text-xs font-medium text-gray-700">付款方式</span>
        <div className="flex gap-4">
          <label className="flex items-center gap-1.5">
            <input type="radio" checked={value.funding === "self_pay"} onChange={() => onChange({ ...EMPTY_BILLING, amount: value.amount })} />
            自費
          </label>
          <label className="flex items-center gap-1.5">
            <input type="radio" checked={value.funding === "institution"} onChange={() => set({ funding: "institution", amount: "" })} />
            機構
          </label>
        </div>
      </div>

      {value.funding === "institution" && (
        <>
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

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <label className="block text-sm">
              <span className="mb-1 block text-xs font-medium text-gray-700">方案</span>
              <select
                value={value.planId}
                onChange={(e) => set({ planId: e.target.value, rateItemId: "", transportId: "" })}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              >
                <option value="">{effectivePlan ? `依額度（${effectivePlan.name}）` : "依額度所屬方案"}</option>
                {plans.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-xs font-medium text-gray-700">價目項目</span>
              <select
                value={value.rateItemId}
                onChange={(e) => set({ rateItemId: e.target.value })}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                disabled={!effectivePlan}
              >
                <option value="">自動挑選</option>
                {effectivePlan?.rate_items.map((r) => (
                  <option key={r.id} value={r.id}>{r.label}（{money(r.total_amount)}／自付 {money(r.self_pay_amount)}）</option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-xs font-medium text-gray-700">交通費</span>
              <select
                value={value.transportId}
                onChange={(e) => set({ transportId: e.target.value })}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                disabled={!effectivePlan}
              >
                <option value="">{sessionType === "outdoor" ? "預設選項" : "無（使用診間）"}</option>
                {effectivePlan?.transport_fees.map((t) => (
                  <option key={t.id} value={t.id}>{t.label}（{money(t.amount)}）</option>
                ))}
              </select>
            </label>
          </div>

          <div className="rounded-lg bg-violet-50 px-3 py-2 text-sm text-violet-900">
            {effectivePlan && item ? (
              <>
                應收 <b>{money(shownTotal ?? 0)}</b>・個案自付 <b>{money(shownSelfPay ?? 0)}</b>
                {transport ? <>・交通費 <b>{money(transport.amount)}</b></> : null}
                {manual !== undefined && manual !== item.total_amount ? <span className="ml-2 text-xs text-amber-700">（手動調整，會留稽核）</span> : null}
              </>
            ) : (
              <span className="text-xs text-amber-700">尚未選到方案，無法帶出應收與自付額；可在下方手動填金額。</span>
            )}
          </div>
        </>
      )}

      {canAmount && (
        <label className="block text-sm">
          <span className="mb-1 block text-xs font-medium text-gray-700">
            {value.funding === "self_pay" ? "金額（必填，個案要付的全額）" : "手動調整應收（選填）"}
          </span>
          <input
            type="number"
            inputMode="decimal"
            min={0}
            max={9999999}
            step="any"
            required={value.funding === "self_pay"}
            value={value.amount}
            onChange={(e) => set({ amount: e.target.value })}
            placeholder={value.funding === "self_pay" ? "例如 1500；免費請填 0" : "不填就依價目"}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
          <span className="mt-1 block text-xs text-gray-400">
            Google 日曆事件標題結尾會顯示個案這次要付的錢（機構案＝自付額；0 元不顯示）。
          </span>
        </label>
      )}
    </div>
  );
}
