"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import {
  RateItemsEditor,
  RateSummary,
  emptyRateItem,
  type RateItem,
} from "@/components/rate-items-editor";

interface TransportFee {
  id?: number;
  label: string;
  amount: number;
  is_default: boolean;
}

interface Plan {
  id: number;
  contract_id: number;
  contract_name: string | null;
  institution_id: number | null;
  institution_name: string | null;
  name: string;
  claim_unit: string | null;
  claim_contact: string | null;
  claim_phone: string | null;
  quota_unit: "count" | "amount";
  per_person_count: number | null;
  annual_total_count: number | null;
  per_person_amount: number | null;
  annual_total_amount: number | null;
  per_person_monthly_limit: number | null;
  extension_sessions: number | null;
  claim_threshold_sessions: number | null;
  pricing_mode: "contract_fixed" | "therapist_rate";
  rate_items: RateItem[];
  settlement_direction: string;
  rebate_rate: number | null;
  valid_from: string | null;
  valid_until: string | null;
  notes: string | null;
  status: "active" | "exhausted" | "expired";
  hourly_rate: number | null;
  self_pay_amount: number | null;
  transport_fees: TransportFee[];
  annual_used: number;
  annual_booked: number;
  annual_reserved: number;
  case_count: number;
}

interface Contract {
  id: number;
  name: string;
  institution_name: string | null;
  valid_from: string | null;
  valid_until: string | null;
}

interface Quota {
  quota_id: number;
  case_id: number;
  case_name: string;
  total_count: number;
  used_count: number;
  booked_count: number;
  reserved_count: number;
  valid_from: string | null;
  valid_until: string | null;
  status: string;
  note: string | null;
  is_last_session: boolean;
}

const STATUS_STYLE: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  exhausted: "bg-red-100 text-red-700",
  expired: "bg-gray-100 text-gray-500",
};
const STATUS_LABEL: Record<string, string> = {
  active: "使用中",
  exhausted: "已用罄",
  expired: "已過期",
};

/** 額度三態長條：已使用（藍）／已預約（琥珀）／已預留（灰） */
function TriStateBar({ used, booked, reserved }: { used: number; booked: number; reserved: number }) {
  const total = used + booked + reserved;
  if (total === 0) return <span className="text-xs text-gray-400">—</span>;
  const pct = (n: number) => `${(n / total) * 100}%`;
  return (
    <div>
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-gray-100">
        <div style={{ width: pct(used) }} className="bg-primary-500" title={`已使用 ${used}`} />
        <div style={{ width: pct(booked) }} className="bg-amber-400" title={`已預約 ${booked}`} />
        <div style={{ width: pct(reserved) }} className="bg-gray-300" title={`已預留 ${reserved}`} />
      </div>
      <div className="mt-1 flex gap-3 text-[11px] text-gray-500">
        <span className="text-primary-600">已使用 {used}</span>
        <span className="text-amber-600">已預約 {booked}</span>
        <span>已預留 {reserved}</span>
        <span className="ml-auto tabular-nums">共 {total}</span>
      </div>
    </div>
  );
}

export default function PlansPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [plans, setPlans] = useState<Plan[]>([]);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [quotas, setQuotas] = useState<Record<number, Quota[]>>({});
  const [editing, setEditing] = useState<Plan | "new" | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [ps, cs] = await Promise.all([
        clientFetch("/institution-plans", token),
        clientFetch("/institution-contracts", token),
      ]);
      setPlans(ps);
      setContracts(cs);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function toggle(planId: number) {
    if (expanded === planId) {
      setExpanded(null);
      return;
    }
    setExpanded(planId);
    if (!quotas[planId]) {
      try {
        const rows = await clientFetch(`/institution-plans/${planId}/quotas`, token);
        setQuotas((q) => ({ ...q, [planId]: rows }));
      } catch (e: any) {
        setError(e.message);
      }
    }
  }

  async function setStatus(plan: Plan, value: string) {
    try {
      await clientFetch(`/institution-plans/${plan.id}/status?value=${value}`, token, {
        method: "PUT",
      });
      load();
    } catch (e: any) {
      alert(e.message);
    }
  }

  if (loading) return <p className="p-6 text-gray-400">載入中...</p>;

  return (
    <div>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">機構方案清冊</h1>
          <p className="mt-1 text-sm text-gray-500">
            由合約開出的年度方案。點方案列可展開個案清冊，看每個人的額度三態。
          </p>
        </div>
        <button
          onClick={() => setEditing("new")}
          disabled={contracts.length === 0}
          className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
          title={contracts.length === 0 ? "請先在「機構合約清冊」建立合約" : undefined}
        >
          ＋新增方案
        </button>
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      {contracts.length === 0 && (
        <div className="mb-4 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800">
          尚無機構合約。方案必須掛在合約底下，請先到「機構合約清冊」建立。
        </div>
      )}

      <div className="space-y-3">
        {plans.length === 0 && (
          <div className="rounded-xl border border-gray-200 bg-white px-4 py-10 text-center text-gray-400">
            尚無方案
          </div>
        )}

        {plans.map((p) => {
          const isOpen = expanded === p.id;
          const annualTotal = p.annual_total_count;
          const annualUsedPct =
            annualTotal && annualTotal > 0
              ? Math.min(100, (p.annual_used / annualTotal) * 100)
              : null;

          return (
            <div key={p.id} className="overflow-hidden rounded-xl border border-gray-200 bg-white">
              <button
                onClick={() => toggle(p.id)}
                className="flex w-full items-start gap-4 px-4 py-4 text-left hover:bg-gray-50"
              >
                <span className="mt-1 text-gray-400">{isOpen ? "▾" : "▸"}</span>

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">{p.name}</span>
                    <span className={`rounded px-1.5 py-0.5 text-xs ${STATUS_STYLE[p.status]}`}>
                      {STATUS_LABEL[p.status]}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-gray-500">
                    {p.institution_name} · {p.contract_name}
                  </div>
                  <div className="mt-1 text-xs text-gray-600">
                    <RateSummary items={p.rate_items ?? []} />
                  </div>
                  <div className="mt-1 text-xs text-gray-400">
                    有效 {p.valid_from || "—"} ~ {p.valid_until || "—"}
                    {p.quota_unit === "amount" ? (
                      <>
                        {" · "}額度以金額計 · 每人{" "}
                        {p.per_person_amount != null ? `$${p.per_person_amount.toLocaleString()}` : "不限"}
                        {" · 年度 "}
                        {p.annual_total_amount != null ? `$${p.annual_total_amount.toLocaleString()}` : "不限"}
                      </>
                    ) : (
                      <>
                        {" · 每人 "}{p.per_person_count ?? "不限"} 次
                        {p.extension_sessions ? `（可延長 ${p.extension_sessions} 次）` : ""}
                        {" · 年度 "}{p.annual_total_count ?? "不限"} 次
                      </>
                    )}
                    {p.per_person_monthly_limit ? ` · 每月上限 ${p.per_person_monthly_limit} 次` : ""}
                    {p.transport_fees.length > 0 && (
                      <> · 交通費 {p.transport_fees.map((t) => `${t.label} $${t.amount}`).join("／")}</>
                    )}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {p.claim_threshold_sessions ? (
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] text-amber-700">
                        達 {p.claim_threshold_sessions} 次才可核銷
                      </span>
                    ) : null}
                    {p.pricing_mode === "therapist_rate" && (
                      <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[11px] text-blue-700">
                        依心理師鐘點費
                      </span>
                    )}
                    {p.settlement_direction === "to_therapist" && (
                      <span className="rounded bg-violet-100 px-1.5 py-0.5 text-[11px] text-violet-700">
                        回扣型 · 機構直接匯給心理師
                        {p.rebate_rate != null ? `（回繳 ${Math.round(p.rebate_rate * 100)}%）` : ""}
                      </span>
                    )}
                  </div>
                </div>

                <div className="w-56 shrink-0">
                  <div className="mb-1 text-[11px] text-gray-500">
                    年度使用（{p.case_count} 位個案）
                  </div>
                  {annualUsedPct != null ? (
                    <>
                      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
                        <div
                          style={{ width: `${annualUsedPct}%` }}
                          className={annualUsedPct >= 100 ? "h-full bg-red-500" : "h-full bg-primary-500"}
                        />
                      </div>
                      <div className="mt-1 text-[11px] tabular-nums text-gray-500">
                        {p.annual_used} / {annualTotal} 次
                      </div>
                    </>
                  ) : (
                    <div className="text-[11px] text-gray-400">年度不限</div>
                  )}
                </div>
              </button>

              {isOpen && (
                <div className="border-t border-gray-100 bg-gray-50 px-4 py-4">
                  <div className="mb-3 flex items-center gap-2">
                    <span className="text-sm font-medium">個案清冊</span>
                    <div className="ml-auto flex gap-2 text-xs">
                      <button
                        onClick={() => setEditing(p)}
                        className="rounded border border-gray-300 bg-white px-2 py-1 hover:bg-gray-50"
                      >
                        編輯方案
                      </button>
                      {(["active", "exhausted", "expired"] as const)
                        .filter((s) => s !== p.status)
                        .map((s) => (
                          <button
                            key={s}
                            onClick={() => setStatus(p, s)}
                            className="rounded border border-gray-300 bg-white px-2 py-1 hover:bg-gray-50"
                          >
                            設為{STATUS_LABEL[s]}
                          </button>
                        ))}
                    </div>
                  </div>

                  {!quotas[p.id] ? (
                    <p className="text-sm text-gray-400">載入中...</p>
                  ) : quotas[p.id].length === 0 ? (
                    <p className="text-sm text-gray-400">
                      尚無個案掛在此方案。個案額度目前仍由「個案管理 → 機構額度」建立，Phase 3
                      會把加入方案的動作移到這裡。
                    </p>
                  ) : (
                    <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
                      <table className="w-full text-sm">
                        <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs text-gray-500">
                          <tr>
                            <th className="px-3 py-2">姓名</th>
                            <th className="w-64 px-3 py-2">額度三態</th>
                            <th className="px-3 py-2">有效期間</th>
                            <th className="px-3 py-2">狀態</th>
                            <th className="px-3 py-2">備註</th>
                          </tr>
                        </thead>
                        <tbody>
                          {quotas[p.id].map((q) => (
                            <tr
                              key={q.quota_id}
                              className={`border-b border-gray-100 last:border-0 ${
                                q.is_last_session ? "bg-amber-50" : ""
                              }`}
                            >
                              <td className="px-3 py-2 font-medium">
                                {q.case_name}
                                {q.is_last_session && (
                                  <span className="ml-2 rounded bg-red-100 px-1.5 py-0.5 text-[11px] text-red-700">
                                    最後一次
                                  </span>
                                )}
                              </td>
                              <td className="px-3 py-2">
                                <TriStateBar
                                  used={q.used_count}
                                  booked={q.booked_count}
                                  reserved={q.reserved_count}
                                />
                              </td>
                              <td className="px-3 py-2 text-xs text-gray-500">
                                {q.valid_from || "—"} ~ {q.valid_until || "—"}
                              </td>
                              <td className="px-3 py-2 text-xs">{q.status}</td>
                              <td className="px-3 py-2 text-xs text-gray-500">{q.note || "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <p className="mt-4 text-xs text-gray-400">
        額度三態恆等式：已使用 ＋ 已預約 ＋ 已預留 ＝ 個人上限。由資料庫 CHECK 約束強制。
        目前額度流轉（報到轉已使用、取消退回已預留）尚未接上，排在 Phase 3。
      </p>

      {editing && (
        <PlanForm
          token={token}
          contracts={contracts}
          plan={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setQuotas({});
            load();
          }}
        />
      )}
    </div>
  );
}

function PlanForm({
  token,
  contracts,
  plan,
  onClose,
  onSaved,
}: {
  token: string;
  contracts: Contract[];
  plan: Plan | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [contractId, setContractId] = useState(plan?.contract_id ?? contracts[0]?.id ?? 0);
  const [name, setName] = useState(plan?.name ?? "");
  const [claimUnit, setClaimUnit] = useState(plan?.claim_unit ?? "");
  const [claimContact, setClaimContact] = useState(plan?.claim_contact ?? "");
  const [claimPhone, setClaimPhone] = useState(plan?.claim_phone ?? "");
  const [quotaUnit, setQuotaUnit] = useState<"count" | "amount">(plan?.quota_unit ?? "count");
  const [perPerson, setPerPerson] = useState(
    plan?.per_person_count != null ? String(plan.per_person_count) : ""
  );
  const [annual, setAnnual] = useState(
    plan?.annual_total_count != null ? String(plan.annual_total_count) : ""
  );
  const [perPersonAmt, setPerPersonAmt] = useState(
    plan?.per_person_amount != null ? String(plan.per_person_amount) : ""
  );
  const [annualAmt, setAnnualAmt] = useState(
    plan?.annual_total_amount != null ? String(plan.annual_total_amount) : ""
  );
  const [monthlyLimit, setMonthlyLimit] = useState(
    plan?.per_person_monthly_limit != null ? String(plan.per_person_monthly_limit) : ""
  );
  const [extension, setExtension] = useState(
    plan?.extension_sessions != null ? String(plan.extension_sessions) : ""
  );
  const [threshold, setThreshold] = useState(
    plan?.claim_threshold_sessions != null ? String(plan.claim_threshold_sessions) : ""
  );
  const [pricingMode, setPricingMode] = useState<"contract_fixed" | "therapist_rate">(
    plan?.pricing_mode ?? "contract_fixed"
  );
  const [rateItems, setRateItems] = useState<RateItem[]>(
    plan?.rate_items?.length ? plan.rate_items : [{ ...emptyRateItem(), label: "個別諮商" }]
  );
  const [from, setFrom] = useState(plan?.valid_from ?? "");
  const [until, setUntil] = useState(plan?.valid_until ?? "");
  const [notes, setNotes] = useState(plan?.notes ?? "");
  const [fees, setFees] = useState<TransportFee[]>(plan?.transport_fees ?? []);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const contract = contracts.find((c) => c.id === contractId);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    const payload: any = {
      name,
      claim_unit: claimUnit || null,
      claim_contact: claimContact || null,
      claim_phone: claimPhone || null,
      quota_unit: quotaUnit,
      per_person_count: quotaUnit === "count" && perPerson !== "" ? Number(perPerson) : null,
      annual_total_count: quotaUnit === "count" && annual !== "" ? Number(annual) : null,
      per_person_amount: quotaUnit === "amount" && perPersonAmt !== "" ? Number(perPersonAmt) : null,
      annual_total_amount: quotaUnit === "amount" && annualAmt !== "" ? Number(annualAmt) : null,
      per_person_monthly_limit: monthlyLimit === "" ? null : Number(monthlyLimit),
      extension_sessions: extension === "" ? null : Number(extension),
      claim_threshold_sessions: threshold === "" ? null : Number(threshold),
      pricing_mode: pricingMode,
      rate_items: pricingMode === "contract_fixed" ? rateItems : [],
      valid_from: from || null,
      valid_until: until || null,
      notes: notes || null,
      transport_fees: fees.map((f) => ({
        label: f.label,
        amount: Number(f.amount) || 0,
        is_default: f.is_default,
      })),
    };
    try {
      if (plan) {
        await clientFetch(`/institution-plans/${plan.id}`, token, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      } else {
        await clientFetch("/institution-plans", token, {
          method: "POST",
          body: JSON.stringify({ ...payload, contract_id: contractId }),
        });
      }
      onSaved();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <form
        onSubmit={submit}
        className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl bg-white p-6 shadow-xl"
      >
        <h2 className="mb-4 text-lg font-bold">{plan ? "編輯機構方案" : "新增機構方案"}</h2>

        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}

        <div className="grid grid-cols-2 gap-4">
          <label className="col-span-2 text-sm">
            <span className="mb-1 block text-gray-600">所屬合約 *</span>
            <select
              value={contractId}
              onChange={(e) => setContractId(Number(e.target.value))}
              disabled={!!plan}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 disabled:bg-gray-100"
            >
              {contracts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.institution_name} — {c.name}
                </option>
              ))}
            </select>
          </label>

          <label className="col-span-2 text-sm">
            <span className="mb-1 block text-gray-600">方案名稱 *</span>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如：2026年度 15-45青壯"
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>

          <label className="text-sm">
            <span className="mb-1 block text-gray-600">核銷單位</span>
            <input
              value={claimUnit}
              onChange={(e) => setClaimUnit(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">核銷窗口</span>
            <input
              value={claimContact}
              onChange={(e) => setClaimContact(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">核銷電話</span>
            <input
              value={claimPhone}
              onChange={(e) => setClaimPhone(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>

          <div />

          <div className="col-span-2 rounded-lg border border-gray-200 p-3">
            <div className="mb-2 flex items-center gap-3">
              <span className="text-sm text-gray-600">額度單位</span>
              {([["count", "以次數計"], ["amount", "以金額計"]] as const).map(([k, label]) => (
                <label key={k} className="flex items-center gap-1.5 text-sm">
                  <input
                    type="radio"
                    checked={quotaUnit === k}
                    onChange={() => setQuotaUnit(k)}
                  />
                  {label}
                </label>
              ))}
              <span className="text-xs text-gray-400">如國軍是整個機構一年 $149,000</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {quotaUnit === "count" ? (
                <>
                  <label className="text-sm">
                    <span className="mb-1 block text-gray-600">每人次數（留空＝不限）</span>
                    <input type="number" min="1" value={perPerson} onChange={(e) => setPerPerson(e.target.value)} placeholder="不限" className="w-full rounded-lg border border-gray-300 px-3 py-2 tabular-nums" />
                  </label>
                  <label className="text-sm">
                    <span className="mb-1 block text-gray-600">年度總次數（留空＝不限）</span>
                    <input type="number" min="1" value={annual} onChange={(e) => setAnnual(e.target.value)} placeholder="不限" className="w-full rounded-lg border border-gray-300 px-3 py-2 tabular-nums" />
                  </label>
                </>
              ) : (
                <>
                  <label className="text-sm">
                    <span className="mb-1 block text-gray-600">每人金額上限</span>
                    <input type="number" min="0" value={perPersonAmt} onChange={(e) => setPerPersonAmt(e.target.value)} placeholder="不限" className="w-full rounded-lg border border-gray-300 px-3 py-2 tabular-nums" />
                  </label>
                  <label className="text-sm">
                    <span className="mb-1 block text-gray-600">年度總金額上限</span>
                    <input type="number" min="0" value={annualAmt} onChange={(e) => setAnnualAmt(e.target.value)} placeholder="不限" className="w-full rounded-lg border border-gray-300 px-3 py-2 tabular-nums" />
                  </label>
                </>
              )}
              <label className="text-sm">
                <span className="mb-1 block text-gray-600">每人每月上限</span>
                <input type="number" min="1" value={monthlyLimit} onChange={(e) => setMonthlyLimit(e.target.value)} placeholder="無" className="w-full rounded-lg border border-gray-300 px-3 py-2 tabular-nums" />
                <span className="mt-0.5 block text-xs text-gray-400">如容愛協會每月 4 次、總 24 次</span>
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-gray-600">可延長次數</span>
                <input type="number" min="1" value={extension} onChange={(e) => setExtension(e.target.value)} placeholder="不可延長" className="w-full rounded-lg border border-gray-300 px-3 py-2 tabular-nums" />
                <span className="mt-0.5 block text-xs text-gray-400">如警局、奇美家照 6 次可再延長 3 次</span>
              </label>
            </div>
          </div>

          <label className="text-sm">
            <span className="mb-1 block text-gray-600">核銷門檻次數</span>
            <input type="number" min="1" value={threshold} onChange={(e) => setThreshold(e.target.value)} placeholder="無門檻" className="w-full rounded-lg border border-gray-300 px-3 py-2 tabular-nums" />
            <span className="mt-0.5 block text-xs text-gray-400">
              個案需累積達此次數才可送核銷（人事處系列 4 次、脆弱家庭 8 次）
            </span>
          </label>

          <label className="text-sm">
            <span className="mb-1 block text-gray-600">價格來源</span>
            <select value={pricingMode} onChange={(e) => setPricingMode(e.target.value as any)} className="w-full rounded-lg border border-gray-300 px-3 py-2">
              <option value="contract_fixed">合約談定固定價</option>
              <option value="therapist_rate">依心理師鐘點費</option>
            </select>
            <span className="mt-0.5 block text-xs text-gray-400">
              聊心茶室、遠距抱抱等機構案價格跟著心理師鐘點費走
            </span>
          </label>

          <label className="text-sm">
            <span className="mb-1 block text-gray-600">有效起日</span>
            <input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">有效迄日</span>
            <input
              type="date"
              value={until}
              onChange={(e) => setUntil(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>

          {!plan && contract && (
            <p className="col-span-2 -mt-2 text-xs text-gray-500">
              留空會自動帶入合約的有效期間（{contract.valid_from || "—"} ~ {contract.valid_until || "—"}）。
            </p>
          )}

          <label className="col-span-2 text-sm">
            <span className="mb-1 block text-gray-600">備註</span>
            <textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="如：每年每人都有 8 次額度"
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>

          <div className="col-span-2 rounded-lg border border-gray-200 p-3">
            {pricingMode === "contract_fixed" ? (
              <RateItemsEditor items={rateItems} onChange={setRateItems} />
            ) : (
              <p className="rounded bg-blue-50 px-3 py-2 text-sm text-blue-800">
                此方案的價格<b>依心理師鐘點費</b>決定，不需設定方案價目。
                心理師預約時會帶入自己的鐘點費。
              </p>
            )}
          </div>

          <div className="col-span-2">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm text-gray-600">交通費選項</span>
              <button
                type="button"
                onClick={() => setFees([...fees, { label: "", amount: 0, is_default: fees.length === 0 }])}
                className="text-xs text-primary-600 hover:underline"
              >
                ＋新增選項
              </button>
            </div>
            {fees.length === 0 && (
              <p className="text-xs text-gray-400">
                未設定。使用診間的預約不收交通費；外展／到宅可在此設定供心理師選擇。
              </p>
            )}
            {fees.map((f, i) => (
              <div key={i} className="mb-2 flex items-center gap-2">
                <input
                  placeholder="名稱（如：市區）"
                  value={f.label}
                  onChange={(e) => {
                    const n = [...fees];
                    n[i] = { ...n[i], label: e.target.value };
                    setFees(n);
                  }}
                  className="flex-1 rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
                />
                <input
                  type="number"
                  min="0"
                  value={f.amount}
                  onChange={(e) => {
                    const n = [...fees];
                    n[i] = { ...n[i], amount: Number(e.target.value) };
                    setFees(n);
                  }}
                  className="w-28 rounded-lg border border-gray-300 px-2 py-1.5 text-sm tabular-nums"
                />
                <label className="flex items-center gap-1 text-xs text-gray-600">
                  <input
                    type="radio"
                    name="tf-default"
                    checked={f.is_default}
                    onChange={() => setFees(fees.map((x, j) => ({ ...x, is_default: i === j })))}
                  />
                  預設
                </label>
                <button
                  type="button"
                  onClick={() => setFees(fees.filter((_, j) => j !== i))}
                  className="text-xs text-red-500 hover:underline"
                >
                  移除
                </button>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
          >
            {saving ? "儲存中..." : "儲存"}
          </button>
        </div>
      </form>
    </div>
  );
}
