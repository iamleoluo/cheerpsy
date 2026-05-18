"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch, exportCsv } from "@/lib/client-api";
import HelpDrawer, { type HelpContent } from "@/components/HelpDrawer";

const helpContent: HelpContent = {
  title: "財務管理",
  overview: "三個子模組：款項追蹤（核銷案進度對帳）、心理師酬勞月結（依各人抽成比例自動計算）、零用金管理（診所日常支出記帳）。",
  sections: [
    {
      heading: "款項追蹤",
      type: "steps",
      items: [
        "點「款項追蹤」頁籤",
        "以進度條查看每筆核銷案的狀態（建立 → 提交 → 到款 → 結案）",
        "右側選擇日期，查看當天結案或到款的核銷案清單",
        "直接與銀行明細或現金對帳，確認金額與付款方式",
      ],
    },
    {
      heading: "心理師酬勞月結",
      type: "steps",
      items: [
        "點「心理師酬勞」頁籤，選擇年月",
        "點「產生月結」，系統依各心理師抽成比例計算應付金額",
        "可重複產生（更新計算）；已標記「已付款」的不會被覆蓋",
        "確認金額後完成匯款，點「標記已付款」",
        "可匯出明細 CSV 作為薪資憑證",
      ],
    },
    {
      heading: "零用金管理",
      type: "steps",
      items: [
        "點「零用金」頁籤",
        "每筆支出點「＋新增支出」，填入日期、金額、品項",
        "系統即時更新零用金餘額",
        "補款時記錄補款金額，水位恢復",
      ],
    },
    {
      heading: "管理員提示",
      type: "notes",
      items: [
        "各心理師抽成比例在「帳號管理」設定，預設 70%",
        "月結使用諮商發生當下的比例快照（commission_rate_used），事後改比例不影響歷史",
        "款項追蹤的日期對帳欄以 closed_at（自費）或 received_at（機構）為準",
      ],
    },
  ],
};

/* ───── main page ───── */

export default function FinancePage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const userRole = (session?.user as any)?.role;
  const [tab, setTab] = useState<"tracking" | "payouts" | "petty">("tracking");
  const [helpOpen, setHelpOpen] = useState(false);

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <HelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} content={helpContent} />
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">財務管理</h1>
        <button onClick={() => setHelpOpen(true)} className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50 hover:text-gray-700">
          <span>ℹ️</span> 說明
        </button>
      </div>

      <div className="mb-4 flex gap-1 border-b border-gray-200">
        {(
          [
            ["tracking", "款項追蹤"],
            ["payouts", "心理師酬勞"],
            ["petty", "零用金"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              tab === key
                ? "border-b-2 border-primary-600 text-primary-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "tracking" && <PaymentTrackingTab token={token} />}
      {tab === "payouts" && <PayoutsTab token={token} userRole={userRole} />}
      {tab === "petty" && <PettyCashTab token={token} userRole={userRole} />}
    </div>
  );
}

/* ═══════════════════════════════════════════════
   Tab 1 — 款項追蹤
   ═══════════════════════════════════════════════ */

interface TrackingBatch {
  id: number;
  batch_number: string;
  type: string;
  case_name: string | null;
  institution_name: string | null;
  total_amount: number;
  payment_method: string | null;
  payment_note: string | null;
  status: string;
  record_count: number;
  created_at: string | null;
  submitted_at: string | null;
  received_at: string | null;
  closed_at: string | null;
}

interface SelfPayCaseStat {
  case_id: number;
  case_name: string;
  therapist_name: string | null;
  paid_count: number;
  unpaid_count: number;
  paid_amount: number;
  unpaid_amount: number;
  total_count: number;
  all_paid: boolean;
}

const TRACK_TYPE_LABELS: Record<string, string> = { self_pay: "自費", institution: "機構" };
const TRACK_STATUS_LABELS: Record<string, string> = {
  collecting: "收集中",
  ready: "文件備妥",
  submitted: "已提交",
  received: "款項到帳",
  closed: "已結案",
};
const TRACK_STATUS_COLORS: Record<string, string> = {
  collecting: "bg-blue-100 text-blue-700",
  ready: "bg-cyan-100 text-cyan-700",
  submitted: "bg-amber-100 text-amber-700",
  received: "bg-green-100 text-green-700",
  closed: "bg-gray-100 text-gray-600",
};

function fmtTs(iso: string | null) {
  if (!iso) return null;
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function fmtDateOnly(iso: string | null) {
  if (!iso) return null;
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

/** Self-pay progress steps */
const SELF_PAY_STEPS = ["建立", "付款結案"] as const;
/** Institution progress steps */
const INST_STEPS = ["建立", "提交", "到帳", "結案"] as const;

function ProgressBar({ steps, timestamps }: { steps: readonly string[]; timestamps: (string | null)[] }) {
  const completed = timestamps.filter(Boolean).length;
  const total = steps.length;

  return (
    <div className="flex items-center gap-0">
      {steps.map((label, i) => {
        const ts = timestamps[i];
        const done = !!ts;
        const isLast = i === total - 1;
        return (
          <div key={label} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
                  done ? "bg-green-500 text-white" : "bg-gray-200 text-gray-400"
                }`}
              >
                {done ? "✓" : i + 1}
              </div>
              <span className={`mt-0.5 text-[10px] leading-tight ${done ? "text-green-700 font-medium" : "text-gray-400"}`}>
                {label}
              </span>
              {ts && (
                <span className="text-[9px] text-gray-400">{fmtDateOnly(ts)}</span>
              )}
            </div>
            {!isLast && (
              <div className={`mx-0.5 h-0.5 w-6 ${done && timestamps[i + 1] ? "bg-green-400" : "bg-gray-200"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Self-pay steps: simple 2-step progress */
const SELF_PAY_RECORD_STEPS = ["建立", "付款"] as const;

/* ── Institution batch table (sub-component, no recon panel) ── */
function InstitutionTrackingContent({ token, reconDate }: { token: string; reconDate: string }) {
  const [batches, setBatches] = useState<TrackingBatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");

  const fetchBatches = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("type", "institution");
      if (statusFilter) params.set("status", statusFilter);
      const data = await clientFetch(`/claim-batches?${params.toString()}`, token);
      setBatches(data);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  }, [token, statusFilter]);

  useEffect(() => { fetchBatches(); }, [fetchBatches]);

  const totalAmount = batches.reduce((s, b) => s + b.total_amount, 0);
  const openCount = batches.filter((b) => b.status !== "closed").length;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex gap-3">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="">全部狀態</option>
            {Object.entries(TRACK_STATUS_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-4 text-sm text-gray-500">
          <span>共 {batches.length} 筆</span>
          <span>合計 <strong className="text-gray-800">${totalAmount.toLocaleString()}</strong></span>
          {openCount > 0 && <span className="text-amber-600">{openCount} 筆進行中</span>}
        </div>
      </div>
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-3 py-3">案號</th>
              <th className="px-3 py-3">機構</th>
              <th className="px-3 py-3">筆數</th>
              <th className="px-3 py-3 text-right">金額</th>
              <th className="px-3 py-3">付款方式</th>
              <th className="px-3 py-3">狀態</th>
              <th className="px-3 py-3">進度</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-400">載入中...</td></tr>
            ) : batches.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-400">尚無機構核銷案</td></tr>
            ) : batches.map((b) => {
              const timestamps = [b.created_at, b.submitted_at, b.received_at, b.closed_at];
              const highlighted = b.closed_at?.slice(0, 10) === reconDate || b.received_at?.slice(0, 10) === reconDate;
              return (
                <tr key={b.id} className={`hover:bg-gray-50 ${highlighted ? "bg-green-50" : ""}`}>
                  <td className="px-3 py-3 font-mono text-xs">{b.batch_number}</td>
                  <td className="px-3 py-3 text-xs">{b.institution_name}</td>
                  <td className="px-3 py-3 text-xs">{b.record_count}</td>
                  <td className="px-3 py-3 text-right font-medium">${b.total_amount.toLocaleString()}</td>
                  <td className="px-3 py-3 text-xs">
                    {b.payment_method === "cash" ? "現金" : b.payment_method === "transfer" ? "匯款" : "—"}
                    {b.payment_note && <span className="ml-1 text-gray-400">({b.payment_note})</span>}
                  </td>
                  <td className="px-3 py-3">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${TRACK_STATUS_COLORS[b.status] ?? "bg-gray-100"}`}>
                      {TRACK_STATUS_LABELS[b.status] ?? b.status}
                    </span>
                  </td>
                  <td className="px-3 py-3">
                    <ProgressBar steps={INST_STEPS} timestamps={timestamps} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Self-pay records with progress bars ── */
interface SelfPayRecord {
  id: number;
  session_date: string;
  case_id: number | null;
  case_name: string | null;
  therapist_name: string | null;
  effective_amount: number;
  payment_status: string;
  payment_method: string | null;
  payment_note: string | null;
}

function SelfPayTrackingContent({ records, loading, reconDate }: { records: SelfPayRecord[]; loading: boolean; reconDate: string }) {
  if (loading) return <div className="py-12 text-center text-gray-400">載入中...</div>;

  if (records.length === 0) {
    return (
      <div className="rounded-lg border border-green-200 bg-green-50 py-12 text-center">
        <p className="text-lg font-medium text-green-700">目前尚無自費記錄</p>
      </div>
    );
  }

  // Group by case_id (fallback to case_name)
  const caseMap = new Map<string | number, { caseName: string; therapistName: string | null; recs: SelfPayRecord[] }>();
  for (const r of records) {
    const key = r.case_id ?? (r.case_name ?? "?");
    if (!caseMap.has(key)) caseMap.set(key, { caseName: r.case_name ?? `#${r.case_id}`, therapistName: r.therapist_name, recs: [] });
    caseMap.get(key)!.recs.push(r);
  }

  // Sort: cases with unpaid first, then by case name
  const groups = [...caseMap.entries()].map(([key, g]) => {
    const sorted = [...g.recs].sort((a, b) => a.session_date.localeCompare(b.session_date));
    const paidCount = sorted.filter(r => r.payment_status === "paid" || r.payment_status === "claimed").length;
    const unpaidAmount = sorted.filter(r => r.payment_status === "unpaid").reduce((s, r) => s + r.effective_amount, 0);
    const allPaid = paidCount === sorted.length;
    return { key, caseName: g.caseName, therapistName: g.therapistName, recs: sorted, paidCount, unpaidAmount, allPaid };
  }).sort((a, b) => (a.allPaid ? 1 : 0) - (b.allPaid ? 1 : 0) || a.caseName.localeCompare(b.caseName));

  const unpaidTotal = groups.reduce((s, g) => s + g.unpaidAmount, 0);

  return (
    <div>
      {unpaidTotal > 0 && (
        <div className="mb-3 flex items-center gap-2 text-sm">
          <span className="rounded-full bg-amber-100 px-3 py-1 font-medium text-amber-700">
            待收合計 ${unpaidTotal.toLocaleString()}
          </span>
        </div>
      )}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">個案</th>
              <th className="px-4 py-3">治療師</th>
              <th className="px-4 py-3">療程付款進度</th>
              <th className="px-4 py-3 text-right">待收金額</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {groups.map(({ key, caseName, therapistName, recs, paidCount, unpaidAmount, allPaid }) => (
              <tr key={String(key)} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-900">{caseName}</td>
                <td className="px-4 py-3">
                  {therapistName
                    ? <span className="inline-block rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-700">{therapistName}</span>
                    : <span className="text-xs text-gray-400">—</span>
                  }
                </td>
                <td className="px-4 py-3">
                  {/* Dot per session: green = paid, gray = unpaid */}
                  <div className="flex flex-wrap items-center gap-1">
                    {recs.map((r) => {
                      const isPaid = r.payment_status === "paid" || r.payment_status === "claimed";
                      const isToday = r.session_date === reconDate && isPaid;
                      return (
                        <div
                          key={r.id}
                          title={`${r.session_date} ${isPaid ? "已付款" : "待付款"} $${r.effective_amount.toLocaleString()}`}
                          className={`h-3 w-3 rounded-full border ${
                            isToday
                              ? "bg-blue-400 border-blue-500"
                              : isPaid
                                ? "bg-green-500 border-green-600"
                                : "bg-gray-200 border-gray-300"
                          }`}
                        />
                      );
                    })}
                    <span className="ml-1 text-xs text-gray-400">
                      {paidCount}/{recs.length} 筆
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3 text-right font-medium">
                  {allPaid
                    ? <span className="text-green-600 text-xs font-medium">全部結清 ✓</span>
                    : <span className="text-amber-700">${unpaidAmount.toLocaleString()}</span>
                  }
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Main PaymentTrackingTab — sub-tabs + shared 每日對帳 panel ── */
function PaymentTrackingTab({ token }: { token: string }) {
  const [trackingSubTab, setTrackingSubTab] = useState<"institution" | "self_pay">("institution");

  // Self-pay records fetched at top level (needed for recon panel regardless of sub-tab)
  const [selfPayRecords, setSelfPayRecords] = useState<SelfPayRecord[]>([]);
  const [spLoading, setSpLoading] = useState(true);

  // Institution batches fetched at top level for recon panel (unfiltered)
  const [instBatches, setInstBatches] = useState<TrackingBatch[]>([]);

  const [reconDate, setReconDate] = useState(new Date().toISOString().slice(0, 10));

  useEffect(() => {
    clientFetch("/ledger/self-pay-all", token)
      .then(setSelfPayRecords)
      .catch(() => {})
      .finally(() => setSpLoading(false));
    clientFetch("/claim-batches?type=institution", token)
      .then(setInstBatches)
      .catch(() => {});
  }, [token]);

  // Recon: institution batches closed/received on date
  const reconInstItems = instBatches.filter((b) =>
    b.closed_at?.slice(0, 10) === reconDate || b.received_at?.slice(0, 10) === reconDate
  );
  // Recon: self-pay records paid on session_date (used as proxy for payment date)
  const reconSpItems = selfPayRecords.filter((r) =>
    r.session_date === reconDate && (r.payment_status === "paid" || r.payment_status === "claimed")
  );

  const reconInstTotal = reconInstItems.reduce((s, b) => s + b.total_amount, 0);
  const reconSpTotal = reconSpItems.reduce((s, r) => s + r.effective_amount, 0);
  const reconTotal = reconInstTotal + reconSpTotal;
  const reconCash = [
    ...reconInstItems.filter((b) => b.payment_method === "cash").map((b) => b.total_amount),
    ...reconSpItems.filter((r) => r.payment_method === "cash").map((r) => r.effective_amount),
  ].reduce((s, v) => s + v, 0);
  const reconTransfer = [
    ...reconInstItems.filter((b) => b.payment_method === "transfer").map((b) => b.total_amount),
    ...reconSpItems.filter((r) => r.payment_method === "transfer").map((r) => r.effective_amount),
  ].reduce((s, v) => s + v, 0);
  const reconOther = reconTotal - reconCash - reconTransfer;
  const hasRecon = reconInstItems.length > 0 || reconSpItems.length > 0;

  return (
    <div className="flex gap-4">
      {/* ── Left: sub-tabs + content ── */}
      <div className="min-w-0 flex-1">
        {/* Sub-tab switcher */}
        <div className="mb-4 flex gap-2">
          {(["institution", "self_pay"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTrackingSubTab(t)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                trackingSubTab === t
                  ? "bg-primary-600 text-white shadow-sm"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {t === "institution" ? "機構" : "自費"}
            </button>
          ))}
        </div>

        {trackingSubTab === "institution" ? (
          <InstitutionTrackingContent token={token} reconDate={reconDate} />
        ) : (
          <SelfPayTrackingContent records={selfPayRecords} loading={spLoading} reconDate={reconDate} />
        )}
      </div>

      {/* ── Right: 每日對帳 (機構 + 自費 合計) ── */}
      <div className="w-72 shrink-0">
        <div className="sticky top-4 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h3 className="mb-3 text-sm font-bold text-gray-700">每日對帳</h3>
          <input
            type="date"
            value={reconDate}
            onChange={(e) => setReconDate(e.target.value)}
            className="mb-3 w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
          />

          {!hasRecon ? (
            <p className="py-4 text-center text-xs text-gray-400">該日無到帳/結案項目</p>
          ) : (
            <>
              {/* Summary */}
              <div className="mb-3 space-y-1 rounded bg-gray-50 p-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-gray-500">筆數</span>
                  <span className="font-medium">{reconInstItems.length + reconSpItems.length} 筆</span>
                </div>
                <div className="flex justify-between border-t border-gray-200 pt-1">
                  <span className="text-gray-500">合計</span>
                  <span className="font-bold text-gray-800">${reconTotal.toLocaleString()}</span>
                </div>
                {reconCash > 0 && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">現金</span>
                    <span>${reconCash.toLocaleString()}</span>
                  </div>
                )}
                {reconTransfer > 0 && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">匯款</span>
                    <span>${reconTransfer.toLocaleString()}</span>
                  </div>
                )}
                {reconOther > 0 && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">其他</span>
                    <span>${reconOther.toLocaleString()}</span>
                  </div>
                )}
              </div>

              {/* Institution items */}
              {reconInstItems.length > 0 && (
                <div className="mb-2">
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-indigo-500">機構</p>
                  <div className="space-y-1.5">
                    {reconInstItems.map((b) => (
                      <div key={b.id} className="rounded border border-gray-100 bg-gray-50 px-3 py-2">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-xs font-medium">{b.batch_number}</span>
                        </div>
                        <div className="mt-0.5 text-xs text-gray-500">{b.institution_name}</div>
                        <div className="mt-1 flex items-center justify-between">
                          <span className="text-xs text-gray-400">
                            {b.payment_method === "cash" ? "現金" : b.payment_method === "transfer" ? "匯款" : "—"}
                          </span>
                          <span className="text-sm font-bold">${b.total_amount.toLocaleString()}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Self-pay items */}
              {reconSpItems.length > 0 && (
                <div>
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-purple-500">自費</p>
                  <div className="space-y-1.5">
                    {reconSpItems.map((r) => (
                      <div key={r.id} className="rounded border border-gray-100 bg-gray-50 px-3 py-2">
                        <div className="text-xs font-medium text-gray-800">{r.case_name ?? "—"}</div>
                        <div className="mt-1 flex items-center justify-between">
                          <span className="text-xs text-gray-400">
                            {r.payment_method === "cash" ? "現金" : r.payment_method === "transfer" ? "匯款" : "—"}
                            {r.payment_note && <span className="ml-1">({r.payment_note})</span>}
                          </span>
                          <span className="text-sm font-bold">${r.effective_amount.toLocaleString()}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════
   Tab 2 — 心理師酬勞月結
   ═══════════════════════════════════════════════ */

interface Payout {
  id: number;
  therapist_id: number;
  therapist_name: string | null;
  payout_month: string;
  total_amount: number;
  session_count: number;
  status: string;
  paid_at: string | null;
}

interface PayoutSession {
  session_id: number;
  session_date: string;
  amount: number;
  therapist_share: number;
  fee_category: string;
  session_type: string;
}

const payoutStatusLabels: Record<string, string> = { pending: "待發放", paid: "已發放" };
const payoutStatusColors: Record<string, string> = {
  pending: "bg-amber-100 text-amber-700",
  paid: "bg-green-100 text-green-700",
};
const sessionTypeLabels: Record<string, string> = { in_person: "現場", online: "線上", home_visit: "到宅" };

function PayoutsTab({ token, userRole }: { token: string; userRole: string }) {
  const now = new Date();
  const [filterMonth, setFilterMonth] = useState(
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`,
  );
  const [payouts, setPayouts] = useState<Payout[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [detailModal, setDetailModal] = useState<{ payoutId: number; name: string } | null>(null);
  const [details, setDetails] = useState<PayoutSession[]>([]);

  const fetchPayouts = useCallback(async () => {
    setLoading(true);
    try {
      const params = filterMonth ? `?payout_month=${filterMonth}` : "";
      const data = await clientFetch(`/payouts${params}`, token);
      setPayouts(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token, filterMonth]);

  useEffect(() => {
    fetchPayouts();
  }, [fetchPayouts]);

  const handleGenerate = async () => {
    if (!filterMonth) return;
    setGenerating(true);
    try {
      const result = await clientFetch("/payouts/generate", token, {
        method: "POST",
        body: JSON.stringify({ payout_month: filterMonth }),
      });
      const parts = [];
      if (result.payouts_created > 0) parts.push(`新增 ${result.payouts_created} 位`);
      if (result.payouts_updated > 0) parts.push(`更新 ${result.payouts_updated} 位`);
      alert(`${result.month} 酬勞已更新：${parts.join("、") || "無異動"}（已付款者不重算）`);
      fetchPayouts();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setGenerating(false);
    }
  };

  const handlePay = async (id: number) => {
    if (!confirm("確認已發放此酬勞？")) return;
    try {
      await clientFetch(`/payouts/${id}/pay`, token, { method: "PUT" });
      fetchPayouts();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const showDetails = async (payoutId: number, name: string) => {
    setDetailModal({ payoutId, name });
    try {
      const data = await clientFetch(`/payouts/${payoutId}/details`, token);
      setDetails(data.sessions);
    } catch {
      setDetails([]);
    }
  };

  const totalAmount = payouts.reduce((s, p) => s + p.total_amount, 0);
  const pendingCount = payouts.filter((p) => p.status === "pending").length;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <input
            type="month"
            value={filterMonth}
            onChange={(e) => setFilterMonth(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
          {payouts.length > 0 && (
            <span className="text-sm text-gray-500">
              合計 ${totalAmount.toLocaleString()} · {pendingCount > 0 ? `${pendingCount} 筆待發放` : "全部已發放"}
            </span>
          )}
        </div>
        {userRole === "admin" && (
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
          >
            {generating ? "產生中..." : "產生酬勞"}
          </button>
        )}
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">月份</th>
              <th className="px-4 py-3">心理師</th>
              <th className="px-4 py-3 text-right">場次</th>
              <th className="px-4 py-3 text-right">酬勞金額</th>
              <th className="px-4 py-3">狀態</th>
              <th className="px-4 py-3">發放日期</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-400">載入中...</td>
              </tr>
            ) : payouts.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                  尚無酬勞資料（管理員可產生月結酬勞）
                </td>
              </tr>
            ) : (
              payouts.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">{p.payout_month}</td>
                  <td className="px-4 py-3 font-medium">{p.therapist_name ?? "-"}</td>
                  <td className="px-4 py-3 text-right">{p.session_count}</td>
                  <td className="px-4 py-3 text-right font-medium">${p.total_amount.toLocaleString()}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${payoutStatusColors[p.status] ?? "bg-gray-100"}`}
                    >
                      {payoutStatusLabels[p.status] ?? p.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {p.paid_at ? new Date(p.paid_at).toLocaleDateString("zh-TW") : "-"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button
                        onClick={() => showDetails(p.id, p.therapist_name ?? "")}
                        className="text-xs text-primary-600 hover:underline"
                      >
                        明細
                      </button>
                      {userRole === "admin" && p.status === "pending" && (
                        <button onClick={() => handlePay(p.id)} className="text-xs text-green-600 hover:underline">
                          確認發放
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {detailModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-bold">{detailModal.name} — 酬勞明細</h2>
            {details.length === 0 ? (
              <p className="text-sm text-gray-400">無明細資料</p>
            ) : (
              <div className="max-h-96 overflow-y-auto">
                <table className="w-full text-left text-sm">
                  <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                    <tr>
                      <th className="px-4 py-2">日期</th>
                      <th className="px-4 py-2">類型</th>
                      <th className="px-4 py-2">費目</th>
                      <th className="px-4 py-2 text-right">金額</th>
                      <th className="px-4 py-2 text-right">師酬</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {details.map((d) => (
                      <tr key={d.session_id}>
                        <td className="px-4 py-2">{d.session_date}</td>
                        <td className="px-4 py-2">{sessionTypeLabels[d.session_type] ?? d.session_type}</td>
                        <td className="px-4 py-2">{d.fee_category}</td>
                        <td className="px-4 py-2 text-right">${d.amount.toLocaleString()}</td>
                        <td className="px-4 py-2 text-right font-medium">${d.therapist_share.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="mt-4 flex justify-end">
              <button
                onClick={() => setDetailModal(null)}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
              >
                關閉
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════
   Tab 3 — 零用金
   ═══════════════════════════════════════════════ */

interface PettyCashItem {
  id: number;
  date: string;
  amount: number;
  category: string;
  description: string | null;
  receipt_note: string | null;
  balance_after: number;
}

const categoryLabels: Record<string, string> = {
  cleaning: "清潔費",
  supplies: "文具耗材",
  electricity: "電費",
  water: "水費",
  other: "其他",
};

function PettyCashTab({ token, userRole }: { token: string; userRole: string }) {
  const [records, setRecords] = useState<PettyCashItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const data = await clientFetch("/petty-cash", token);
      setRecords(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchRecords();
  }, [fetchRecords]);

  const currentBalance = records.length > 0 ? records[0].balance_after : 0;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-gray-500">
          目前餘額：
          <span className={`font-bold ${currentBalance >= 0 ? "text-green-600" : "text-red-600"}`}>
            ${currentBalance.toLocaleString()}
          </span>
        </p>
        <div className="flex items-center gap-2">
          {userRole !== "therapist" && (
            <button
              onClick={() => exportCsv("/export/petty-cash", token, "petty_cash.csv")}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
            >
              匯出 CSV
            </button>
          )}
          {userRole !== "therapist" && (
            <button
              onClick={() => setShowForm(true)}
              className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
            >
              + 新增紀錄
            </button>
          )}
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">日期</th>
              <th className="px-4 py-3">類別</th>
              <th className="px-4 py-3">說明</th>
              <th className="px-4 py-3 text-right">金額</th>
              <th className="px-4 py-3 text-right">餘額</th>
              <th className="px-4 py-3">收據備註</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">載入中...</td>
              </tr>
            ) : records.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">尚無零用金紀錄</td>
              </tr>
            ) : (
              records.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">{r.date}</td>
                  <td className="px-4 py-3">{categoryLabels[r.category] ?? r.category}</td>
                  <td className="px-4 py-3">{r.description ?? "-"}</td>
                  <td
                    className={`px-4 py-3 text-right font-medium ${r.amount >= 0 ? "text-green-600" : "text-red-600"}`}
                  >
                    {r.amount >= 0 ? "+" : ""}${r.amount.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right">${r.balance_after.toLocaleString()}</td>
                  <td className="px-4 py-3 text-xs text-gray-400">{r.receipt_note ?? "-"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showForm && (
        <PettyCashForm
          token={token}
          onClose={() => setShowForm(false)}
          onSaved={() => {
            setShowForm(false);
            fetchRecords();
          }}
        />
      )}
    </div>
  );
}

function PettyCashForm({
  token,
  onClose,
  onSaved,
}: {
  token: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    type: "expense",
    amount: "",
    category: "other",
    description: "",
    receipt_note: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const setField = (key: string, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const amt = parseFloat(form.amount);
      await clientFetch("/petty-cash", token, {
        method: "POST",
        body: JSON.stringify({
          date: form.date,
          amount: form.type === "expense" ? -Math.abs(amt) : Math.abs(amt),
          category: form.category,
          description: form.description || null,
          receipt_note: form.receipt_note || null,
        }),
      });
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-bold">新增零用金紀錄</h2>
        {error && <div className="mb-3 rounded-lg bg-red-50 p-2 text-sm text-red-600">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">日期 *</span>
              <input
                required
                type="date"
                value={form.date}
                onChange={(e) => setField("date", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">類型</span>
              <select
                value={form.type}
                onChange={(e) => setField("type", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              >
                <option value="expense">支出</option>
                <option value="income">補充</option>
              </select>
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">金額 *</span>
              <input
                required
                type="number"
                min="0"
                step="1"
                value={form.amount}
                onChange={(e) => setField("amount", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">類別</span>
              <select
                value={form.category}
                onChange={(e) => setField("category", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              >
                <option value="cleaning">清潔費</option>
                <option value="supplies">文具耗材</option>
                <option value="electricity">電費</option>
                <option value="water">水費</option>
                <option value="other">其他</option>
              </select>
            </label>
          </div>

          <label className="block">
            <span className="mb-1 block text-xs text-gray-500">說明</span>
            <input
              value={form.description}
              onChange={(e) => setField("description", e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs text-gray-500">收據備註</span>
            <input
              value={form.receipt_note}
              onChange={(e) => setField("receipt_note", e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              placeholder="收據編號或備註"
            />
          </label>

          <div className="flex justify-end gap-2 pt-2">
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
    </div>
  );
}
