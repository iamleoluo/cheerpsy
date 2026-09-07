"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

/**
 * 合約專頁（09 §3.5 四分頁骨架）。這是分層架構裡「讀專屬、寫共用」的
 * 前端半邊：整頁只有一個讀取來源（GET /institution/contracts/{id}/panel），
 * 形狀由後端的 Layer 3 模組決定；畫面是這份 read model 的通用渲染器，
 * 不需要理解任何機構規則——換一份合約，區塊自動跟著換，不用改這支檔案。
 *
 * 寫入動作全部呼叫共用的 write API（09 §3.2），這裡沒有任何機構專屬邏輯。
 */

interface QuotaPoolInfo {
  id: number; name: string; unit: string;
  total_limit: number | null; consumed_total: number; remaining: number | null;
}
interface EnrollmentRow {
  enrollment_id: number; case_id: number | null; case_name: string | null;
  external_case_code: string | null; quota_unit: string; quota_limit: number | null;
  used: number; booked: number; reserved: number; extended_count: number;
  assessment_status: string; status: string;
}
interface ClaimUncollectedRow { id: number; session_date: string; case_id: number; amount: number }
interface ClaimCandidateRow { case_id: number; session_record_ids: number[]; count: number; ready: boolean; total_amount: number }
interface RateRuleRow { id: number; sort_order: number; when_json: string; unit_price: number; case_payable: number; label: string | null }
interface PlanPanel {
  plan: {
    id: number; name: string; quota_unit: string; default_quota_limit_numeric: number | null;
    period_limit: number | null; period_unit: string | null; compensation_mode: string;
    claim_group_key: string; claim_grouping_mode: string; claim_capacity: number | null;
    claim_timing: string; requires_external_code: boolean; counts_toward_quota: boolean; is_active: boolean;
  };
  blocks: string[];
  enrollments: EnrollmentRow[];
  quota_pool: QuotaPoolInfo | null;
  claim_uncollected: ClaimUncollectedRow[];
  claim_candidates: ClaimCandidateRow[] | null;
  admin_checklist: string[];
  therapist_checklist: string[];
  rate_rules: RateRuleRow[];
}
interface ClaimCaseRow {
  id: number; claim_no: string; claim_group_key: string; status: string;
  record_count: number; applied_amount: number | null; net_received: number | null;
}
interface Panel {
  contract: {
    id: number; name: string; institution_name: string | null; contact_name: string | null;
    contact_phone: string | null; eligibility_note: string | null;
    valid_from: string | null; valid_until: string | null; is_active: boolean;
  };
  module: string;
  plans: PlanPanel[];
  claim_cases: ClaimCaseRow[];
}
interface DocRow {
  id: number; appointment_id: number | null; session_date: string; case_name: string | null;
  therapist_name: string | null;
}

const compensationLabel: Record<string, string> = { commission: "抽成", kickback: "回饋", none: "無心理師勞務" };
const statusLabel: Record<string, string> = { collecting: "收集中", submitted: "已送出", closed: "已結案", void: "已作廢" };
const statusTagClass: Record<string, string> = {
  collecting: "bg-amber-100 text-amber-700", submitted: "bg-sky-100 text-sky-700",
  closed: "bg-emerald-100 text-emerald-700", void: "bg-gray-100 text-gray-400",
};

export default function ContractPanelPage() {
  const params = useParams();
  const contractId = params?.id as string;
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;

  const [panel, setPanel] = useState<Panel | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"quota" | "claims" | "docs" | "settings">("quota");
  const [busy, setBusy] = useState(false);

  const fetchPanel = useCallback(async () => {
    if (!token || !contractId) return;
    setLoading(true);
    try {
      const data = await clientFetch(`/institution/contracts/${contractId}/panel`, token);
      setPanel(data);
    } catch (e: any) {
      setError(e.message ?? "載入失敗");
    } finally {
      setLoading(false);
    }
  }, [token, contractId]);

  useEffect(() => {
    fetchPanel();
  }, [fetchPanel]);

  async function openAndSubmitClaim(claimGroupKey: string, groupingMode: string, sessionRecordIds: number[]) {
    if (sessionRecordIds.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const cc = await clientFetch("/institution/claim-cases", token, {
        method: "POST",
        body: JSON.stringify({ claim_group_key: claimGroupKey, grouping_mode: groupingMode }),
      });
      await clientFetch(`/institution/claim-cases/${cc.id}/records`, token, {
        method: "POST",
        body: JSON.stringify({ session_record_ids: sessionRecordIds }),
      });
      await clientFetch(`/institution/claim-cases/${cc.id}/submit`, token, { method: "PUT" });
      await fetchPanel();
    } catch (e: any) {
      setError(e.message ?? "開核銷案失敗");
    } finally {
      setBusy(false);
    }
  }

  async function voidClaimCase(id: number) {
    const reason = window.prompt("作廢原因（選填）") ?? "";
    setBusy(true);
    try {
      await clientFetch(`/institution/claim-cases/${id}/void`, token, {
        method: "PUT",
        body: JSON.stringify({ reason: reason || null }),
      });
      await fetchPanel();
    } catch (e: any) {
      setError(e.message ?? "作廢失敗");
    } finally {
      setBusy(false);
    }
  }

  if (!token) return <p>Loading...</p>;
  if (loading && !panel) return <p className="text-sm text-gray-400">載入中...</p>;
  if (!panel) return <p className="text-sm text-rose-500">{error ?? "找不到合約"}</p>;

  const { contract } = panel;

  return (
    <div>
      <div className="mb-1 flex items-center gap-2">
        <h1 className="text-2xl font-bold">{contract.name}</h1>
        {!contract.is_active && <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-400">已停用</span>}
      </div>
      <p className="mb-6 text-sm text-gray-400">
        {contract.institution_name}
        {contract.valid_from && contract.valid_until ? ` · ${contract.valid_from} ~ ${contract.valid_until}` : ""}
        {contract.contact_name ? ` · 承辦 ${contract.contact_name}${contract.contact_phone ? ` (${contract.contact_phone})` : ""}` : ""}
      </p>

      {error && <div className="mb-4 rounded-lg bg-rose-50 px-4 py-2 text-sm text-rose-600">{error}</div>}

      <div className="mb-4 flex gap-1 border-b border-gray-200">
        {([
          ["quota", "個案與額度"],
          ["claims", "核銷"],
          ["docs", "文件"],
          ["settings", "設定"],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium ${tab === key ? "border-b-2 border-primary-600 text-primary-600" : "text-gray-500 hover:text-gray-700"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "quota" && (
        <div className="space-y-6">
          {panel.plans.map((p) => (
            <div key={p.plan.id} className="rounded-xl border border-gray-200 bg-white p-4">
              <div className="mb-3 flex items-center gap-2">
                <h3 className="font-semibold">{p.plan.name}</h3>
                <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">{compensationLabel[p.plan.compensation_mode] ?? p.plan.compensation_mode}</span>
                {p.blocks.includes("period_sublimit") && (
                  <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">
                    {p.plan.period_unit === "week" ? "每週" : "每月"}上限 {p.plan.period_limit} 次
                  </span>
                )}
              </div>

              {p.blocks.includes("quota_pool") && p.quota_pool && (
                <div className="mb-3 rounded-lg bg-gray-50 p-3 text-xs">
                  <div className="mb-1 flex justify-between text-gray-600">
                    <span>{p.quota_pool.name}（合約層級總額度）</span>
                    <span>{p.quota_pool.unit === "amount" ? "$" : ""}{p.quota_pool.consumed_total.toLocaleString()} / {p.quota_pool.total_limit != null ? (p.quota_pool.unit === "amount" ? "$" : "") + p.quota_pool.total_limit.toLocaleString() : "不限"}</span>
                  </div>
                  {p.quota_pool.total_limit != null && (
                    <div className="h-2 overflow-hidden rounded-full bg-gray-200">
                      <div
                        className={`h-full ${(p.quota_pool.remaining ?? 0) <= 0 ? "bg-rose-500" : "bg-primary-500"}`}
                        style={{ width: `${Math.min(100, (p.quota_pool.consumed_total / p.quota_pool.total_limit) * 100)}%` }}
                      />
                    </div>
                  )}
                  {p.quota_pool.remaining != null && <div className="mt-1 text-gray-400">剩餘 {p.quota_pool.unit === "amount" ? "$" : ""}{p.quota_pool.remaining.toLocaleString()}</div>}
                </div>
              )}

              {p.enrollments.length === 0 ? (
                <p className="text-xs text-gray-400">尚無個案加入此方案</p>
              ) : (
                <div className="overflow-hidden rounded-lg border border-gray-100">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50 text-gray-500">
                      <tr>
                        <th className="px-2 py-1.5 text-left">個案</th>
                        <th className="px-2 py-1.5 text-left">代號</th>
                        {p.blocks.includes("quota_per_case") && <th className="px-2 py-1.5 text-left">額度使用情形</th>}
                        <th className="px-2 py-1.5 text-right">已使用/已預約/已預留</th>
                        <th className="px-2 py-1.5 text-left">狀態</th>
                      </tr>
                    </thead>
                    <tbody>
                      {p.enrollments.map((e) => {
                        const limit = e.quota_limit ?? 0;
                        const total = limit + e.extended_count || 1;
                        return (
                          <tr key={e.enrollment_id} className="border-t border-gray-100">
                            <td className="px-2 py-1.5 font-medium">{e.case_name ?? "—"}</td>
                            <td className="px-2 py-1.5 font-mono">{e.external_case_code ?? "—"}</td>
                            {p.blocks.includes("quota_per_case") && (
                              <td className="px-2 py-1.5">
                                <div className="flex h-2 w-24 overflow-hidden rounded-full bg-gray-100">
                                  <div className="bg-rose-400" style={{ width: `${(e.used / total) * 100}%` }} />
                                  <div className="bg-amber-400" style={{ width: `${(e.booked / total) * 100}%` }} />
                                  <div className="bg-sky-300" style={{ width: `${(e.reserved / total) * 100}%` }} />
                                </div>
                              </td>
                            )}
                            <td className="px-2 py-1.5 text-right font-mono">{e.used} / {e.booked} / {e.reserved}</td>
                            <td className="px-2 py-1.5">{e.status === "active" ? "使用中" : e.status === "exhausted" ? "已用罄" : "已結案"}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === "claims" && (
        <div className="space-y-6">
          {panel.plans.map((p) => (
            <div key={p.plan.id} className="rounded-xl border border-gray-200 bg-white p-4">
              <h3 className="mb-3 font-semibold">{p.plan.name}</h3>

              {p.blocks.includes("claim_by_period") && (
                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs text-gray-500">待核銷（{p.claim_uncollected.length} 筆）</span>
                    <button
                      disabled={busy || p.claim_uncollected.length === 0}
                      onClick={() => openAndSubmitClaim(p.plan.claim_group_key, "period", p.claim_uncollected.map((r) => r.id))}
                      className="rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-700 disabled:opacity-40"
                    >
                      開核銷案並送出
                    </button>
                  </div>
                  {p.claim_uncollected.length > 0 && (
                    <ul className="space-y-1 text-xs text-gray-500">
                      {p.claim_uncollected.slice(0, 8).map((r) => (
                        <li key={r.id} className="flex justify-between border-b border-gray-50 py-1">
                          <span>{r.session_date} · 個案 #{r.case_id}</span>
                          <span>${r.amount.toLocaleString()}</span>
                        </li>
                      ))}
                      {p.claim_uncollected.length > 8 && <li className="text-gray-400">…還有 {p.claim_uncollected.length - 8} 筆</li>}
                    </ul>
                  )}
                </div>
              )}

              {p.blocks.includes("claim_by_count") && p.claim_candidates && (
                <div className="space-y-2">
                  {p.claim_candidates.length === 0 && <p className="text-xs text-gray-400">目前沒有累積中的紀錄</p>}
                  {p.claim_candidates.map((c) => (
                    <div key={c.case_id} className={`flex items-center justify-between rounded-lg p-2 text-xs ${c.ready ? "bg-amber-50" : "bg-gray-50"}`}>
                      <span>個案 #{c.case_id} · 已達 {c.count} / {p.plan.claim_capacity} 次{c.ready && <b className="ml-1 text-amber-700">可核銷</b>}</span>
                      <button
                        disabled={busy}
                        onClick={() => openAndSubmitClaim(p.plan.claim_group_key, "per_case_count", c.session_record_ids)}
                        className="rounded-lg border border-primary-300 px-2 py-1 text-primary-600 hover:bg-primary-50 disabled:opacity-40"
                      >
                        開核銷案
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}

          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <h3 className="mb-3 font-semibold">本合約核銷案清單</h3>
            {panel.claim_cases.length === 0 ? (
              <p className="text-xs text-gray-400">尚無核銷案</p>
            ) : (
              <table className="w-full text-xs">
                <thead className="bg-gray-50 text-gray-500">
                  <tr>
                    <th className="px-2 py-1.5 text-left">核銷案編號</th>
                    <th className="px-2 py-1.5 text-right">場次</th>
                    <th className="px-2 py-1.5 text-right">金額</th>
                    <th className="px-2 py-1.5 text-left">狀態</th>
                    <th className="px-2 py-1.5 text-left">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {panel.claim_cases.map((c) => (
                    <tr key={c.id} className="border-t border-gray-100">
                      <td className="px-2 py-1.5 font-mono">{c.claim_no}</td>
                      <td className="px-2 py-1.5 text-right">{c.record_count}</td>
                      <td className="px-2 py-1.5 text-right">{c.applied_amount != null ? `$${c.applied_amount.toLocaleString()}` : "—"}</td>
                      <td className="px-2 py-1.5"><span className={`rounded px-1.5 py-0.5 ${statusTagClass[c.status] ?? ""}`}>{statusLabel[c.status] ?? c.status}</span></td>
                      <td className="px-2 py-1.5">
                        {c.status !== "void" && c.status !== "closed" && (
                          <button disabled={busy} onClick={() => voidClaimCase(c.id)} className="text-rose-500 hover:underline disabled:opacity-40">作廢</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {tab === "docs" && (
        <div className="space-y-6">
          {panel.plans.filter((p) => p.blocks.includes("doc_gate")).length === 0 && (
            <p className="text-sm text-gray-400">此合約底下的方案都不需要文件確認</p>
          )}
          {panel.plans.filter((p) => p.blocks.includes("doc_gate")).map((p) => (
            <DocGateSection key={p.plan.id} claimGroupKey={p.plan.claim_group_key} planName={p.plan.name} token={token} onChanged={fetchPanel} />
          ))}
        </div>
      )}

      {tab === "settings" && (
        <div className="space-y-6">
          {panel.plans.map((p) => (
            <div key={p.plan.id} className="rounded-xl border border-gray-200 bg-white p-4">
              <h3 className="mb-3 font-semibold">{p.plan.name}</h3>
              <dl className="mb-4 grid grid-cols-2 gap-2 text-xs text-gray-500 md:grid-cols-3">
                <div><dt className="text-gray-400">額度單位</dt><dd>{p.plan.quota_unit === "amount" ? "金額" : "次數"}</dd></div>
                <div><dt className="text-gray-400">個人上限</dt><dd>{p.plan.default_quota_limit_numeric ?? "不限"}</dd></div>
                <div><dt className="text-gray-400">核銷方式</dt><dd>{p.plan.claim_grouping_mode === "per_case_count" ? `每滿 ${p.plan.claim_capacity} 次` : "期間制"}</dd></div>
                <div><dt className="text-gray-400">核銷頻率</dt><dd>{p.plan.claim_timing}</dd></div>
                <div><dt className="text-gray-400">酬勞模式</dt><dd>{compensationLabel[p.plan.compensation_mode] ?? p.plan.compensation_mode}</dd></div>
                <div><dt className="text-gray-400">外部代號</dt><dd>{p.plan.requires_external_code ? "需要" : "不需要"}</dd></div>
              </dl>

              <h4 className="mb-2 text-xs font-medium text-gray-500">費率規則（依序先匹配先贏）</h4>
              <table className="w-full text-xs">
                <thead className="bg-gray-50 text-gray-500">
                  <tr>
                    <th className="px-2 py-1.5 text-left">#</th>
                    <th className="px-2 py-1.5 text-left">條件</th>
                    <th className="px-2 py-1.5 text-right">單價</th>
                    <th className="px-2 py-1.5 text-right">個案自付</th>
                    <th className="px-2 py-1.5 text-left">標籤</th>
                  </tr>
                </thead>
                <tbody>
                  {p.rate_rules.map((rr) => (
                    <tr key={rr.id} className="border-t border-gray-100">
                      <td className="px-2 py-1.5">{rr.sort_order}</td>
                      <td className="px-2 py-1.5 font-mono">{rr.when_json === "{}" ? "（無條件・保底）" : rr.when_json}</td>
                      <td className="px-2 py-1.5 text-right">${rr.unit_price.toLocaleString()}</td>
                      <td className="px-2 py-1.5 text-right">${rr.case_payable.toLocaleString()}</td>
                      <td className="px-2 py-1.5">{rr.label ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-xs text-gray-400">費率規則編輯功能尚未上線，目前僅供檢視。</p>

              {(p.admin_checklist.length > 0 || p.therapist_checklist.length > 0) && (
                <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
                  {p.admin_checklist.length > 0 && (
                    <div><dt className="mb-1 text-gray-400">行政流程提醒</dt><ul className="list-disc pl-4 text-gray-600">{p.admin_checklist.map((i) => <li key={i}>{i}</li>)}</ul></div>
                  )}
                  {p.therapist_checklist.length > 0 && (
                    <div><dt className="mb-1 text-gray-400">心理師端提醒</dt><ul className="list-disc pl-4 text-gray-600">{p.therapist_checklist.map((i) => <li key={i}>{i}</li>)}</ul></div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DocGateSection({
  claimGroupKey, planName, token, onChanged,
}: { claimGroupKey: string; planName: string; token: string; onChanged: () => void }) {
  const [pending, setPending] = useState<DocRow[]>([]);
  const [confirmed, setConfirmed] = useState<DocRow[]>([]);
  const [busy, setBusy] = useState(false);

  const fetchDocs = useCallback(() => {
    clientFetch(`/institution/claim-groups/${encodeURIComponent(claimGroupKey)}/pending-docs`, token).then(setPending).catch(() => {});
    clientFetch(`/institution/claim-groups/${encodeURIComponent(claimGroupKey)}/confirmed-docs`, token).then(setConfirmed).catch(() => {});
  }, [claimGroupKey, token]);

  useEffect(() => { fetchDocs(); }, [fetchDocs]);

  async function verify(recordId: number) {
    setBusy(true);
    try {
      await clientFetch(`/ledger/${recordId}/admin-verify`, token, { method: "PUT" });
      fetchDocs();
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4">
      <h3 className="mb-3 font-semibold">{planName}</h3>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <h4 className="mb-2 text-xs font-medium text-amber-600">待心理師提交（{pending.length}）</h4>
          <ul className="space-y-1 text-xs text-gray-500">
            {pending.map((r) => <li key={r.id} className="border-b border-gray-50 py-1">{r.session_date} · {r.case_name} · {r.therapist_name}</li>)}
            {pending.length === 0 && <li className="text-gray-300">無</li>}
          </ul>
        </div>
        <div>
          <h4 className="mb-2 text-xs font-medium text-sky-600">待行政核對（{confirmed.length}）</h4>
          <ul className="space-y-1 text-xs text-gray-500">
            {confirmed.map((r) => (
              <li key={r.id} className="flex items-center justify-between border-b border-gray-50 py-1">
                <span>{r.session_date} · {r.case_name} · {r.therapist_name}</span>
                <button disabled={busy} onClick={() => verify(r.id)} className="text-primary-600 hover:underline disabled:opacity-40">核對</button>
              </li>
            ))}
            {confirmed.length === 0 && <li className="text-gray-300">無</li>}
          </ul>
        </div>
      </div>
    </div>
  );
}
