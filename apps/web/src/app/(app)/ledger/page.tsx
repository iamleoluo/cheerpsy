"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch, exportCsv } from "@/lib/client-api";
import HelpDrawer, { type HelpContent } from "@/components/HelpDrawer";

const helpContent: HelpContent = {
  title: "日結帳冊",
  overview: "由系統在 T+1 自動產生的諮商財務帳冊。日結完成後的帳單會列在此處，待處理的帳單可直接建立核銷案。",
  sections: [
    {
      heading: "頁面說明",
      type: "text",
      items: [
        "本月帳單：查看當月所有帳務紀錄，含收款狀態與核銷歸屬",
        "待處理：列出尚未收款且未歸入核銷案的帳單，可從此處建立核銷案",
        "歷史查詢：跨月份查詢與搜尋歷史帳務",
      ],
    },
    {
      heading: "管理員操作",
      type: "steps",
      items: [
        "每日進入日結帳冊，點「執行日結」確保前日資料寫入",
        "檢查「待處理」分頁，確認未歸入核銷案的帳單",
        "勾選帳單 → 點「建立核銷案」開始收款流程",
        "核銷案建立後，帳單會從「待處理」移到對應的核銷案中管理",
      ],
    },
    {
      heading: "注意事項",
      type: "tips",
      items: [
        "心理師只能看到自己的帳務紀錄",
        "所有操作都會記錄在稽核日誌",
      ],
    },
  ],
};

interface SessionRecord {
  id: number;
  appointment_id: number;
  appointment_number: string | null;
  session_date: string;
  case_id: number;
  case_name: string | null;
  therapist_id: number;
  therapist_name: string | null;
  session_type: string;
  fee_category: string;
  amount: number;
  therapist_share: number;
  clinic_share: number;
  payment_status: string;
  funding_source: string | null;
  institution_name: string | null;
  payment_method: string | null;
  payment_note: string | null;
  claim_number: string | null;
  receipt_number: string | null;
  claim_batch_id: number | null;
  therapist_doc_submitted_at: string | null;
  locked_at: string | null;
  commission_rate_used: number | null;
}

const selfPayLabels: Record<string, string> = { unpaid: "未收款", paid: "已收款" };
const institutionLabels: Record<string, string> = { unpaid: "未請款", claiming: "請款中", claimed: "已請款" };
const paymentColors: Record<string, string> = {
  unpaid: "bg-red-100 text-red-700",
  paid: "bg-green-100 text-green-700",
  claiming: "bg-blue-100 text-blue-700",
  claimed: "bg-green-100 text-green-700",
};
const allFilterLabels: Record<string, string> = { unpaid: "未收款/未請款", paid: "已收款", claiming: "請款中", claimed: "已請款" };
const sessionTypeLabels: Record<string, string> = { in_person: "現場", online: "線上", home_visit: "到宅" };

function getPaymentLabel(status: string, funding: string | null): string {
  return (funding === "institution" ? institutionLabels : selfPayLabels)[status] ?? status;
}

type Tab = "month" | "pending" | "history";

export default function LedgerPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const userRole = (session?.user as any)?.role;
  const [helpOpen, setHelpOpen] = useState(false);

  const now = new Date();
  const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;

  const [tab, setTab] = useState<Tab>("month");
  const [records, setRecords] = useState<SessionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [filterMonth, setFilterMonth] = useState(currentMonth);

  // Settlement
  const [settling, setSettling] = useState(false);
  const [settleDateFrom, setSettleDateFrom] = useState("");
  const [settleDateTo, setSettleDateTo] = useState("");
  const [settleResult, setSettleResult] = useState("");


  // Batch select for creating claim
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const fetchRecords = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (tab === "pending") {
        params.set("payment_status", "unpaid");
      } else if (tab === "month") {
        if (filter) params.set("payment_status", filter);
        if (filterMonth) params.set("month", filterMonth);
      } else {
        // history: no month filter by default, user can set
        if (filter) params.set("payment_status", filter);
        if (filterMonth) params.set("month", filterMonth);
      }
      const qs = params.toString();
      const data = await clientFetch(`/ledger${qs ? `?${qs}` : ""}`, token);
      setRecords(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [token, filter, filterMonth, tab]);

  useEffect(() => {
    fetchRecords();
    setSelected(new Set());
  }, [fetchRecords]);

  const handleSettle = async () => {
    if (!token) return;
    setSettling(true);
    setSettleResult("");
    try {
      const body: any = {};
      if (settleDateFrom && settleDateTo) {
        body.date_from = settleDateFrom;
        body.date_to = settleDateTo;
      } else if (settleDateFrom) {
        body.target_date = settleDateFrom;
      }
      const result = await clientFetch("/ledger/settle", token, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setSettleResult(`日結完成：${result.date}，執行 ${result.executed} 筆，跳過 ${result.skipped} 筆`);
      fetchRecords();
    } catch (e: any) {
      setSettleResult(`錯誤：${e.message}`);
    } finally {
      setSettling(false);
    }
  };

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    const pending = pendingRecords;
    if (selected.size === pending.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(pending.map((r) => r.id)));
    }
  };

  if (!token) return <p>Loading...</p>;

  // Filter pending: unpaid AND not in any claim batch
  const pendingRecords = tab === "pending"
    ? records.filter((r) => r.payment_status === "unpaid" && !r.claim_batch_id)
    : records;

  const displayRecords = tab === "pending" ? pendingRecords : records;
  const totalAmount = displayRecords.reduce((s, r) => s + r.amount, 0);
  const totalTherapist = displayRecords.reduce((s, r) => s + r.therapist_share, 0);
  const totalClinic = displayRecords.reduce((s, r) => s + r.clinic_share, 0);

  const tabs: { key: Tab; label: string; badge?: number }[] = [
    { key: "month", label: "本月帳單" },
    { key: "pending", label: "待處理", badge: tab !== "pending" ? undefined : pendingRecords.length },
    { key: "history", label: "歷史查詢" },
  ];

  return (
    <div>
      <HelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} content={helpContent} />

      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">日結帳冊</h1>
        <div className="flex items-center gap-2">
          <button onClick={() => setHelpOpen(true)} className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50 hover:text-gray-700">
            <span>ℹ️</span> 說明
          </button>
          {userRole !== "therapist" && (
            <button
              onClick={() => exportCsv("/export/ledger", token, "ledger.csv")}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
            >
              匯出 CSV
            </button>
          )}
        </div>
      </div>

      {/* Settlement bar (admin only) */}
      {userRole === "admin" && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1">
              <input type="date" value={settleDateFrom} onChange={(e) => setSettleDateFrom(e.target.value)} className="rounded border border-gray-300 px-2 py-1 text-sm" />
              <span className="text-xs text-gray-400">～</span>
              <input type="date" value={settleDateTo} onChange={(e) => setSettleDateTo(e.target.value)} className="rounded border border-gray-300 px-2 py-1 text-sm" />
            </div>
            <button onClick={handleSettle} disabled={settling} className="rounded-lg bg-amber-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50">
              {settling ? "執行中..." : "執行日結"}
            </button>
            <span className="text-xs text-gray-500">留空則結算昨日</span>
          </div>
          {settleResult && <p className="mt-2 text-sm text-amber-700">{settleResult}</p>}
        </div>
      )}

      {/* Tabs */}
      <div className="mb-4 flex gap-1 border-b border-gray-200">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => { setTab(t.key); setFilter(""); }}
            className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${
              tab === t.key
                ? "border-b-2 border-primary-600 text-primary-700"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {t.label}
            {t.badge !== undefined && t.badge > 0 && (
              <span className="ml-1.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
                {t.badge}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {tab !== "pending" && (
            <>
              <input
                type="month"
                value={filterMonth}
                onChange={(e) => setFilterMonth(e.target.value)}
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
              <select
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
              >
                <option value="">全部狀態</option>
                {Object.entries(allFilterLabels).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </>
          )}
          {tab === "pending" && selected.size > 0 && userRole !== "therapist" && (
            <a
              href={`/claims?create=true&records=${Array.from(selected).join(",")}`}
              className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
            >
              建立核銷案（{selected.size} 筆）
            </a>
          )}
        </div>
        <div className="flex gap-4 text-sm text-gray-500">
          <span>合計: <strong className="text-gray-900">${totalAmount.toLocaleString()}</strong></span>
          <span>師: ${totalTherapist.toLocaleString()}</span>
          <span>所: ${totalClinic.toLocaleString()}</span>
          <span className="text-gray-400">共 {displayRecords.length} 筆</span>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              {tab === "pending" && userRole !== "therapist" && (
                <th className="px-3 py-3">
                  <input type="checkbox" checked={selected.size === pendingRecords.length && pendingRecords.length > 0} onChange={toggleSelectAll} className="accent-primary-600" />
                </th>
              )}
              <th className="px-4 py-3">日期</th>
              <th className="px-4 py-3">預約編號</th>
              <th className="px-4 py-3">個案</th>
              <th className="px-4 py-3">心理師</th>
              <th className="px-4 py-3">類型</th>
              <th className="px-4 py-3">金額</th>
              <th className="px-4 py-3">來源</th>
              <th className="px-4 py-3">收款狀態</th>
              <th className="px-4 py-3">核銷案</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={10} className="px-4 py-8 text-center text-gray-400">載入中...</td></tr>
            ) : displayRecords.length === 0 ? (
              <tr><td colSpan={10} className="px-4 py-8 text-center text-gray-400">
                {tab === "pending" ? "所有帳單皆已歸入核銷案 🎉" : "尚無流水帳資料"}
              </td></tr>
            ) : (
              displayRecords.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50">
                  {tab === "pending" && userRole !== "therapist" && (
                    <td className="px-3 py-3">
                      <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggleSelect(r.id)} className="accent-primary-600" />
                    </td>
                  )}
                  <td className="px-4 py-3 whitespace-nowrap">{r.session_date}</td>
                  <td className="px-4 py-3 font-mono text-xs">{r.appointment_number ?? "-"}</td>
                  <td className="px-4 py-3">{r.case_name ?? "-"}</td>
                  <td className="px-4 py-3">{r.therapist_name ?? "-"}</td>
                  <td className="px-4 py-3">{sessionTypeLabels[r.session_type] ?? r.session_type}</td>
                  <td className="px-4 py-3">
                    ${r.amount.toLocaleString()}
                    <div className="text-xs text-gray-400">
                      師 ${r.therapist_share.toLocaleString()} / 所 ${r.clinic_share.toLocaleString()}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {r.funding_source === "institution"
                      ? `機構${r.institution_name ? `(${r.institution_name})` : ""}`
                      : "自費"}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${paymentColors[r.payment_status] ?? "bg-gray-100"}`}>
                      {getPaymentLabel(r.payment_status, r.funding_source)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {r.claim_batch_id ? (
                      <a href={`/claims?batch=${r.claim_batch_id}`} className="text-primary-600 hover:underline">
                        核銷案 #{r.claim_batch_id}
                      </a>
                    ) : (
                      <span className="text-gray-400">未歸入</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

    </div>
  );
}
