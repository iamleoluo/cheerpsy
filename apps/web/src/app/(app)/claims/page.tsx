"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import HelpDrawer, { type HelpContent } from "@/components/HelpDrawer";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const helpContent: HelpContent = {
  title: "帳冊管理",
  overview: "自費與機構帳務分流處理。自費不需建立核銷案，系統自動帶出個案所有未結清帳務，可逐筆或批次付款；機構維持核銷批次流程。",
  sections: [
    {
      heading: "自費付款",
      type: "steps",
      items: [
        "切到「自費」分頁，系統依個案列出所有未收款帳務（次結/月結同一個案彙整）",
        "逐筆點「付款」，或勾選多筆點「批次付款」",
        "選現金或匯款，匯款填末 5 碼",
        "付款後可下載收據；批次付款時可選擇合併單張或逐筆收據",
      ],
    },
    {
      heading: "機構核銷案",
      type: "steps",
      items: [
        "切到「機構」分頁，點「＋建立核銷案」",
        "選擇機構（僅列出有未歸入帳的機構），勾選紀錄，設定期間後建立",
        "心理師於「文件確認」逐筆確認，全部確認後自動升「待送出」",
        "點「提交請款」填外部單號 → 款項到帳「確認收款」→「結案」",
      ],
    },
    {
      heading: "狀態流程",
      type: "text",
      items: [
        "自費：未收款 → 付款（逐筆/批次）→ 可印收據",
        "機構：收集中 → 文件備妥（自動）→ 已送出 → 已收款 → 已結案",
      ],
    },
    {
      heading: "管理員提示",
      type: "notes",
      items: [
        "自費收據編號取自帳冊流水帳的收據編號；機構請款單號 = I-{機構代碼}-{YYYYMM}",
        "自費不需要心理師文件確認，機構案需要",
        "既有自費核銷案仍可於「歷史核銷案」檢視與重印收據",
      ],
    },
  ],
};

/* ───── types ───── */

interface ClaimBatch {
  id: number;
  batch_number: string;
  external_ref: string | null;
  type: string;
  billing_cycle: string | null;
  expected_sessions: number | null;
  institution_id: number | null;
  institution_name: string | null;
  case_id: number | null;
  case_name: string | null;
  period_start: string | null;
  period_end: string | null;
  total_amount: number;
  payment_method: string | null;
  payment_note: string | null;
  status: string;
  record_count: number;
  confirmed_count: number;
  created_at: string | null;
}

interface BatchRecord {
  id: number;
  session_date: string;
  case_name: string | null;
  therapist_name: string | null;
  session_type: string;
  amount: number;
  payment_status: string;
  therapist_doc_submitted_at: string | null;
}

interface UnassignedRecord {
  id: number;
  session_date: string;
  case_id: number;
  case_name: string | null;
  therapist_name: string | null;
  session_type: string;
  amount: number;
  payment_status: string;
  therapist_doc_submitted_at: string | null;
}

interface InstitutionOption {
  id: number;
  name: string;
  code: string | null;
}

interface LedgerRecord {
  id: number;
  session_date: string;
  case_id: number | null;
  case_name: string | null;
  therapist_name: string | null;
  session_type: string;
  amount: number;
  discount_amount: number;
  effective_amount: number;
  payment_status: string;
  receipt_no: string | null;
  is_void: boolean;
}

const SESSION_TYPE_LABELS: Record<string, string> = {
  in_person: "現場",
  online: "線上",
  home_visit: "到宅",
};

/* ───── main page ───── */

export default function ClaimsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const userRole = (session?.user as any)?.role;
  const [mode, setMode] = useState<"self_pay" | "institution">("self_pay");
  const [instTab, setInstTab] = useState<"batches" | "docs">("batches");
  const [helpOpen, setHelpOpen] = useState(false);

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <HelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} content={helpContent} />
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">帳冊管理</h1>
        <button onClick={() => setHelpOpen(true)} className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50 hover:text-gray-700">
          <span>ℹ️</span> 說明
        </button>
      </div>

      <div className="mb-4 flex gap-2">
        {(
          [
            ["self_pay", "自費"],
            ["institution", "機構"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setMode(key)}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              mode === key
                ? "bg-primary-600 text-white"
                : "border border-gray-300 text-gray-600 hover:bg-gray-50"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === "self_pay" && <SelfPayTab token={token} userRole={userRole} />}

      {mode === "institution" && (
        <div>
          <div className="mb-4 flex gap-1 border-b border-gray-200">
            {(
              [
                ["batches", "核銷案列表"],
                ["docs", "文件確認"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setInstTab(key)}
                className={`px-4 py-2 text-sm font-medium transition-colors ${
                  instTab === key
                    ? "border-b-2 border-primary-600 text-primary-600"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {instTab === "batches" && <BatchListTab token={token} userRole={userRole} />}
          {instTab === "docs" && <DocConfirmTab token={token} userRole={userRole} />}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════
   helpers
   ═══════════════════════════════════════════════ */

const STATUS_LABELS: Record<string, string> = {
  collecting: "收集中",
  ready: "待送出",
  submitted: "已送出",
  received: "已收款",
  closed: "已結案",
};
const STATUS_COLORS: Record<string, string> = {
  collecting: "bg-yellow-100 text-yellow-800",
  ready: "bg-blue-100 text-blue-800",
  submitted: "bg-purple-100 text-purple-800",
  received: "bg-green-100 text-green-800",
  closed: "bg-gray-100 text-gray-600",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[status] ?? "bg-gray-100 text-gray-600"}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

function downloadPdf(path: string, token: string, filename: string) {
  fetch(`${API_URL}${path}`, { headers: { Authorization: `Bearer ${token}` } })
    .then((res) => {
      if (!res.ok) throw new Error(`Download failed: ${res.status}`);
      return res.blob();
    })
    .then((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    });
}

/* ═══════════════════════════════════════════════
   自費 — per-record / batch payment (no claim batch)
   ═══════════════════════════════════════════════ */

function SelfPayPaymentModal({
  token,
  recordIds,
  total,
  onClose,
  onDone,
}: {
  token: string;
  recordIds: number[];
  total: number;
  onClose: () => void;
  onDone: (ids: number[], combine: boolean) => void;
}) {
  const [method, setMethod] = useState<"cash" | "transfer">("cash");
  const [note, setNote] = useState("");
  const [combine, setCombine] = useState(true);
  const [saving, setSaving] = useState(false);
  const isBatch = recordIds.length > 1;

  const submit = async () => {
    if (method === "transfer" && !note.trim()) {
      alert("請填寫匯款資訊");
      return;
    }
    setSaving(true);
    try {
      if (isBatch) {
        await clientFetch("/ledger/pay-batch", token, {
          method: "POST",
          body: JSON.stringify({
            record_ids: recordIds,
            payment_method: method,
            payment_note: note.trim() || null,
            combine_receipt: combine,
          }),
        });
      } else {
        await clientFetch(`/ledger/${recordIds[0]}/pay`, token, {
          method: "PUT",
          body: JSON.stringify({ payment_method: method, payment_note: note.trim() || null }),
        });
      }
      onDone(recordIds, isBatch ? combine : false);
    } catch (e: any) {
      alert(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-80 rounded-lg bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 text-base font-semibold">{isBatch ? `批次付款（${recordIds.length} 筆）` : "確認付款"}</h3>
        <p className="mb-3 text-sm text-gray-600">
          合計：<strong>${total.toLocaleString()}</strong>
        </p>

        <fieldset className="mb-3">
          <legend className="mb-1 text-xs font-medium text-gray-700">付款方式</legend>
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" checked={method === "cash"} onChange={() => setMethod("cash")} />
            現金
          </label>
          <label className="mt-1 flex items-center gap-2 text-sm">
            <input type="radio" checked={method === "transfer"} onChange={() => setMethod("transfer")} />
            匯款
          </label>
        </fieldset>

        <label className="mb-3 block">
          <span className="text-xs font-medium text-gray-700">
            匯款資訊{method === "cash" ? "（選填）" : "（必填）"}
          </span>
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={method === "transfer" ? "請輸入末5碼或匯款帳號" : ""}
            className="mt-1 block w-full rounded border px-2 py-1.5 text-sm"
          />
        </label>

        {isBatch && (
          <fieldset className="mb-4">
            <legend className="mb-1 text-xs font-medium text-gray-700">收據</legend>
            <label className="flex items-center gap-2 text-sm">
              <input type="radio" checked={combine} onChange={() => setCombine(true)} />
              合併一張收據
            </label>
            <label className="mt-1 flex items-center gap-2 text-sm">
              <input type="radio" checked={!combine} onChange={() => setCombine(false)} />
              逐筆各一張
            </label>
          </fieldset>
        )}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100">
            取消
          </button>
          <button
            onClick={submit}
            disabled={saving}
            className="rounded bg-green-600 px-4 py-1.5 text-sm text-white hover:bg-green-700 disabled:opacity-50"
          >
            {saving ? "處理中…" : "確認付款"}
          </button>
        </div>
      </div>
    </div>
  );
}

function SelfPayTab({ token, userRole }: { token: string; userRole: string }) {
  const [records, setRecords] = useState<LedgerRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [payIds, setPayIds] = useState<number[] | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<ClaimBatch[]>([]);
  const [expandedCaseId, setExpandedCaseId] = useState<number | string | null>(null);
  const [statusFilter, setStatusFilter] = useState<"all" | "unpaid" | "paid">("all");

  const canEdit = ["admin", "staff"].includes(userRole);

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const data = await clientFetch("/ledger/self-pay-all", token);
      setRecords(data);
      setSelected(new Set());
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchRecords(); }, [fetchRecords]);

  useEffect(() => {
    if (showHistory) {
      clientFetch("/claim-batches?type=self_pay", token).then(setHistory).catch(() => {});
    }
  }, [showHistory, token]);

  const isPaid = (r: LedgerRecord) => r.payment_status === "paid" || r.payment_status === "claimed";

  // Apply status filter
  const filtered = records.filter((r) => {
    if (statusFilter === "unpaid") return r.payment_status === "unpaid";
    if (statusFilter === "paid") return isPaid(r);
    return true;
  });

  // group by case_id (fall back to case_name if no id)
  const groups = filtered.reduce<Record<string | number, { name: string; records: LedgerRecord[] }>>(
    (acc, r) => {
      const key = r.case_id ?? (r.case_name ?? "?");
      if (!acc[key]) acc[key] = { name: r.case_name ?? `#${r.case_id}`, records: [] };
      acc[key].records.push(r);
      return acc;
    }, {}
  );

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleCase = (key: string | number) => {
    setExpandedCaseId((prev) => {
      if (prev === key) return null;
      // Clear selection when switching cases
      setSelected(new Set());
      return key;
    });
  };

  const afterPay = (ids: number[], combine: boolean) => {
    if (ids.length === 1) {
      downloadPdf(`/ledger/${ids[0]}/receipt`, token, `receipt-${ids[0]}.pdf`);
    } else if (combine) {
      downloadPdf(`/ledger/receipt?record_ids=${ids.join(",")}`, token, `receipt-combined.pdf`);
    } else {
      ids.forEach((id) => downloadPdf(`/ledger/${id}/receipt`, token, `receipt-${id}.pdf`));
    }
    setPayIds(null);
    fetchRecords();
  };

  return (
    <div>
      {payIds && (
        <SelfPayPaymentModal
          token={token}
          recordIds={payIds}
          total={records.filter((r) => payIds.includes(r.id)).reduce((s, r) => s + r.effective_amount, 0)}
          onClose={() => setPayIds(null)}
          onDone={afterPay}
        />
      )}

      <div className="mb-3 flex items-center gap-3">
        {!showHistory && (
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value as "all" | "unpaid" | "paid"); setExpandedCaseId(null); }}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option value="all">全部狀態</option>
            <option value="unpaid">待付款</option>
            <option value="paid">已付款</option>
          </select>
        )}
        <button
          onClick={() => setShowHistory((v) => !v)}
          className="ml-auto text-sm text-primary-600 hover:underline"
        >
          {showHistory ? "← 回帳冊" : "歷史核銷案"}
        </button>
      </div>

      {showHistory ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50 text-left text-xs text-gray-500">
                <th className="px-3 py-2">編號</th>
                <th className="px-3 py-2">個案</th>
                <th className="px-3 py-2">期間</th>
                <th className="px-3 py-2 text-right">金額</th>
                <th className="px-3 py-2">狀態</th>
                <th className="px-3 py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {history.length === 0 ? (
                <tr><td colSpan={6} className="py-6 text-center text-gray-400">無歷史核銷案</td></tr>
              ) : history.map((b) => (
                <tr key={b.id} className="border-b hover:bg-gray-50">
                  <td className="px-3 py-2 font-mono text-xs">{b.batch_number}</td>
                  <td className="px-3 py-2">{b.case_name}</td>
                  <td className="px-3 py-2 text-xs">{b.period_start ?? ""} ~ {b.period_end ?? ""}</td>
                  <td className="px-3 py-2 text-right">${b.total_amount.toLocaleString()}</td>
                  <td className="px-3 py-2"><StatusBadge status={b.status} /></td>
                  <td className="px-3 py-2">
                    <button
                      onClick={() => downloadPdf(`/claim-batches/${b.id}/receipt`, token, `receipt-${b.batch_number}.pdf`)}
                      className="rounded border border-gray-300 px-2 py-0.5 text-xs hover:bg-gray-100"
                    >
                      重印收據
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : loading ? (
        <div className="py-8 text-center text-gray-400">載入中...</div>
      ) : filtered.length === 0 ? (
        <div className="py-8 text-center text-gray-400">
          {statusFilter === "unpaid" ? "沒有待收款的自費帳務 🎉"
            : statusFilter === "paid" ? "尚無已付款的自費帳務"
            : "尚無自費帳務"}
        </div>
      ) : (
        <div className="space-y-2">
          {Object.entries(groups).map(([key, { name: caseName, records: rs }]) => {
            const caseKey = key;
            const isOpen = expandedCaseId === caseKey;
            const unpaidRs = rs.filter((r) => r.payment_status === "unpaid");
            const paidRs = rs.filter((r) => isPaid(r));
            const unpaidTotal = unpaidRs.reduce((s, r) => s + r.effective_amount, 0);
            const caseSelected = rs.filter((r) => selected.has(r.id));
            const caseSelectedTotal = caseSelected.reduce((s, r) => s + r.effective_amount, 0);

            return (
              <div key={caseKey} className="rounded-lg border border-gray-200 overflow-hidden">
                {/* Accordion header */}
                <button
                  onClick={() => toggleCase(caseKey)}
                  className="flex w-full items-center justify-between bg-gray-50 px-4 py-3 hover:bg-gray-100 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{caseName}</span>
                    {unpaidRs.length > 0 && (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
                        {unpaidRs.length} 筆待收
                      </span>
                    )}
                    {paidRs.length > 0 && (
                      <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700">
                        {paidRs.length} 筆已付
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    {unpaidTotal > 0
                      ? <span className="text-sm text-amber-600">待收 ${unpaidTotal.toLocaleString()}</span>
                      : <span className="text-sm text-green-600">全部結清 ✓</span>
                    }
                    <span className={`text-gray-400 transition-transform text-xs ${isOpen ? "rotate-180" : ""}`}>▼</span>
                  </div>
                </button>

                {/* Accordion body */}
                {isOpen && (
                  <>
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-t text-left text-xs text-gray-500 bg-white">
                          {canEdit && <th className="px-3 py-2 w-8"></th>}
                          <th className="px-3 py-2">收據編號</th>
                          <th className="px-3 py-2">日期</th>
                          <th className="px-3 py-2">心理師</th>
                          <th className="px-3 py-2">類型</th>
                          <th className="px-3 py-2 text-right">金額</th>
                          <th className="px-3 py-2">狀態</th>
                          <th className="px-3 py-2">操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rs.map((r) => {
                          const paid = isPaid(r);
                          return (
                          <tr key={r.id} className={`border-b hover:bg-gray-50 ${paid ? "bg-green-50/40" : ""}`}>
                            {canEdit && (
                              <td className="px-3 py-2">
                                {!paid && (
                                  <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} />
                                )}
                              </td>
                            )}
                            <td className="px-3 py-2 font-mono text-xs">{r.receipt_no ?? "-"}</td>
                            <td className="px-3 py-2">{r.session_date}</td>
                            <td className="px-3 py-2">{r.therapist_name}</td>
                            <td className="px-3 py-2">{SESSION_TYPE_LABELS[r.session_type] ?? r.session_type}</td>
                            <td className="px-3 py-2 text-right">
                              ${r.effective_amount.toLocaleString()}
                              {r.discount_amount > 0 && (
                                <span className="ml-1 text-xs text-amber-600">(優待 ${r.discount_amount.toLocaleString()})</span>
                              )}
                            </td>
                            <td className="px-3 py-2">
                              {paid
                                ? <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700">已付款</span>
                                : <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">待付款</span>
                              }
                            </td>
                            <td className="px-3 py-2">
                              {canEdit && !paid && (
                                <button
                                  onClick={() => setPayIds([r.id])}
                                  className="rounded bg-green-600 px-2 py-0.5 text-xs text-white hover:bg-green-700"
                                >
                                  付款
                                </button>
                              )}
                              {paid && (
                                <button
                                  onClick={() => downloadPdf(`/ledger/${r.id}/receipt`, token, `receipt-${r.id}.pdf`)}
                                  className="rounded border border-gray-300 px-2 py-0.5 text-xs hover:bg-gray-100"
                                >
                                  收據
                                </button>
                              )}
                            </td>
                          </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    {/* Per-case payment footer */}
                    {canEdit && caseSelected.length > 0 && (
                      <div className="flex items-center justify-end gap-2 border-t bg-gray-50 px-4 py-2">
                        <span className="text-xs text-gray-500">
                          已選 {caseSelected.length} 筆 · ${caseSelectedTotal.toLocaleString()}
                        </span>
                        <button
                          onClick={() => setPayIds(caseSelected.map((r) => r.id))}
                          className="rounded bg-green-600 px-3 py-1.5 text-xs text-white hover:bg-green-700"
                        >
                          批次付款
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════
   機構 — 核銷案列表 (institution only)
   ═══════════════════════════════════════════════ */

function BatchListTab({ token, userRole }: { token: string; userRole: string }) {
  const [batches, setBatches] = useState<ClaimBatch[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const fetchBatches = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ type: "institution" });
      if (statusFilter) params.set("status", statusFilter);
      const data = await clientFetch(`/claim-batches?${params.toString()}`, token);
      setBatches(data);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  }, [token, statusFilter]);

  useEffect(() => { fetchBatches(); }, [fetchBatches]);

  const canEdit = ["admin", "accountant", "staff"].includes(userRole);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="">全部狀態</option>
          {Object.entries(STATUS_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        {canEdit && (
          <button
            onClick={() => setShowCreate(true)}
            className="ml-auto rounded bg-primary-600 px-4 py-1.5 text-sm text-white hover:bg-primary-700"
          >
            + 建立核銷案
          </button>
        )}
      </div>

      {showCreate && (
        <CreateBatchModal
          token={token}
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); fetchBatches(); }}
        />
      )}

      {loading ? (
        <div className="py-8 text-center text-gray-400">載入中...</div>
      ) : batches.length === 0 ? (
        <div className="py-8 text-center text-gray-400">目前沒有機構核銷案</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50 text-left text-xs text-gray-500">
                <th className="px-3 py-2">編號</th>
                <th className="px-3 py-2">機構</th>
                <th className="px-3 py-2">期間</th>
                <th className="px-3 py-2 text-right">金額</th>
                <th className="px-3 py-2">紀錄</th>
                <th className="px-3 py-2">狀態</th>
                <th className="px-3 py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {batches.map((b) => (
                <BatchRow
                  key={b.id}
                  batch={b}
                  token={token}
                  canEdit={canEdit}
                  expanded={expandedId === b.id}
                  onToggle={() => setExpandedId(expandedId === b.id ? null : b.id)}
                  onRefresh={fetchBatches}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function BatchRow({
  batch: b,
  token,
  canEdit,
  expanded,
  onToggle,
  onRefresh,
}: {
  batch: ClaimBatch;
  token: string;
  canEdit: boolean;
  expanded: boolean;
  onToggle: () => void;
  onRefresh: () => void;
}) {
  const [records, setRecords] = useState<BatchRecord[]>([]);
  const [editRef, setEditRef] = useState(false);
  const [extRef, setExtRef] = useState(b.external_ref ?? "");
  const [payMethod, setPayMethod] = useState(b.payment_method ?? "");
  const [payNote, setPayNote] = useState(b.payment_note ?? "");

  useEffect(() => {
    if (expanded) {
      clientFetch(`/claim-batches/${b.id}/records`, token).then(setRecords).catch(() => {});
    }
  }, [expanded, b.id, token]);

  const transition = async (action: string) => {
    try {
      await clientFetch(`/claim-batches/${b.id}/${action}`, token, { method: "PUT" });
      onRefresh();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const saveInfo = async () => {
    try {
      await clientFetch(`/claim-batches/${b.id}`, token, {
        method: "PUT",
        body: JSON.stringify({ external_ref: extRef || null, payment_method: payMethod || null, payment_note: payNote || null }),
      });
      setEditRef(false);
      onRefresh();
    } catch (e: any) {
      alert(e.message);
    }
  };

  return (
    <>
      <tr className="border-b hover:bg-gray-50 cursor-pointer" onClick={onToggle}>
        <td className="px-3 py-2 font-mono text-xs">{b.batch_number}</td>
        <td className="px-3 py-2">{b.institution_name}</td>
        <td className="px-3 py-2 text-xs">{b.period_start ?? ""} ~ {b.period_end ?? ""}</td>
        <td className="px-3 py-2 text-right">${b.total_amount.toLocaleString()}</td>
        <td className="px-3 py-2 text-xs">
          {b.confirmed_count}/{b.record_count}
          {b.record_count > 0 && b.confirmed_count === b.record_count && (
            <span className="ml-1 text-green-600">&#10003;</span>
          )}
        </td>
        <td className="px-3 py-2"><StatusBadge status={b.status} /></td>
        <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
          <div className="flex flex-wrap gap-1">
            {canEdit && (b.status === "collecting" || b.status === "ready") && (
              <button onClick={() => transition("submit")} className="rounded bg-blue-600 px-2 py-0.5 text-xs text-white hover:bg-blue-700">
                提交請款
              </button>
            )}
            {canEdit && b.status === "submitted" && (
              <button onClick={() => transition("receive")} className="rounded bg-green-600 px-2 py-0.5 text-xs text-white hover:bg-green-700">
                確認收款
              </button>
            )}
            {canEdit && ["submitted", "received"].includes(b.status) && (
              <button onClick={() => transition("close")} className="rounded bg-gray-600 px-2 py-0.5 text-xs text-white hover:bg-gray-700">
                結案
              </button>
            )}
            {b.status === "closed" && (
              <button
                onClick={() => downloadPdf(`/claim-batches/${b.id}/claim-form`, token, `claim-${b.batch_number}.pdf`)}
                className="rounded border border-gray-300 px-2 py-0.5 text-xs hover:bg-gray-100"
              >
                請款單
              </button>
            )}
          </div>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={7} className="border-b bg-gray-50 px-4 py-3">
            {canEdit && (
              <div className="mb-3">
                {editRef ? (
                  <div className="flex flex-wrap items-end gap-2">
                    <label className="text-xs">
                      外部編號
                      <input value={extRef} onChange={(e) => setExtRef(e.target.value)} className="ml-1 rounded border px-2 py-1 text-xs" />
                    </label>
                    <label className="text-xs">
                      付款方式
                      <select value={payMethod} onChange={(e) => setPayMethod(e.target.value)} className="ml-1 rounded border px-2 py-1 text-xs">
                        <option value="">--</option>
                        <option value="cash">現金</option>
                        <option value="transfer">轉帳</option>
                      </select>
                    </label>
                    <label className="text-xs">
                      備註
                      <input value={payNote} onChange={(e) => setPayNote(e.target.value)} className="ml-1 rounded border px-2 py-1 text-xs" />
                    </label>
                    <button onClick={saveInfo} className="rounded bg-primary-600 px-3 py-1 text-xs text-white">儲存</button>
                    <button onClick={() => setEditRef(false)} className="text-xs text-gray-500">取消</button>
                  </div>
                ) : (
                  <button onClick={() => setEditRef(true)} className="text-xs text-primary-600 hover:underline">
                    編輯付款資訊 {b.external_ref ? `(${b.external_ref})` : ""}
                  </button>
                )}
              </div>
            )}

            {records.length === 0 ? (
              <p className="text-xs text-gray-400">無紀錄</p>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-gray-500">
                    <th className="px-2 py-1">日期</th>
                    <th className="px-2 py-1">個案</th>
                    <th className="px-2 py-1">心理師</th>
                    <th className="px-2 py-1">類型</th>
                    <th className="px-2 py-1 text-right">金額</th>
                    <th className="px-2 py-1">付款狀態</th>
                    <th className="px-2 py-1">文件確認</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((r) => (
                    <tr key={r.id} className="border-t border-gray-200">
                      <td className="px-2 py-1">{r.session_date}</td>
                      <td className="px-2 py-1">{r.case_name}</td>
                      <td className="px-2 py-1">{r.therapist_name}</td>
                      <td className="px-2 py-1">{SESSION_TYPE_LABELS[r.session_type] ?? r.session_type}</td>
                      <td className="px-2 py-1 text-right">${r.amount.toLocaleString()}</td>
                      <td className="px-2 py-1">{r.payment_status}</td>
                      <td className="px-2 py-1">
                        {r.therapist_doc_submitted_at ? (
                          <span className="text-green-600">&#10003; 已確認</span>
                        ) : (
                          <span className="text-amber-600">待確認</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

/* ── Create batch modal (institution only) ── */

function CreateBatchModal({
  token,
  onClose,
  onCreated,
}: {
  token: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [institutions, setInstitutions] = useState<InstitutionOption[]>([]);
  const [selectedInstId, setSelectedInstId] = useState<number | "">("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [unassigned, setUnassigned] = useState<UnassignedRecord[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [step, setStep] = useState(1);

  useEffect(() => {
    clientFetch("/claim-batches/eligible-institutions", token).then(setInstitutions).catch(() => {});
  }, [token]);

  const loadUnassigned = async () => {
    const params = new URLSearchParams();
    if (selectedInstId) params.set("institution_id", String(selectedInstId));
    try {
      const data = await clientFetch(`/claim-batches/unassigned/records?${params.toString()}`, token);
      setUnassigned(data);
      setSelectedIds(new Set(data.map((r: UnassignedRecord) => r.id)));
      setStep(2);
    } catch (e: any) {
      alert(e.message);
    }
  };

  const toggleId = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedIds.size === unassigned.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(unassigned.map((r) => r.id)));
  };

  const handleCreate = async () => {
    if (selectedIds.size === 0) { alert("請至少勾選一筆紀錄"); return; }
    setSubmitting(true);
    try {
      await clientFetch("/claim-batches", token, {
        method: "POST",
        body: JSON.stringify({
          type: "institution",
          case_id: null,
          institution_id: selectedInstId || null,
          billing_cycle: null,
          period_start: periodStart || null,
          period_end: periodEnd || null,
          session_record_ids: [...selectedIds],
        }),
      });
      onCreated();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const totalAmount = unassigned.filter((r) => selectedIds.has(r.id)).reduce((s, r) => s + r.amount, 0);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 pt-20" onClick={onClose}>
      <div className="w-full max-w-3xl rounded-lg bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold">建立機構核銷案</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
        </div>

        {step === 1 && (
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium">機構</label>
              <select
                value={selectedInstId}
                onChange={(e) => setSelectedInstId(e.target.value ? Number(e.target.value) : "")}
                className="w-full rounded border px-3 py-2 text-sm"
              >
                <option value="">-- 選擇機構 --</option>
                {institutions.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.code ? `[${i.code}] ` : ""}{i.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex gap-3">
              <div className="flex-1">
                <label className="mb-1 block text-sm font-medium">期間起</label>
                <input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} className="w-full rounded border px-3 py-2 text-sm" />
              </div>
              <div className="flex-1">
                <label className="mb-1 block text-sm font-medium">期間迄</label>
                <input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} className="w-full rounded border px-3 py-2 text-sm" />
              </div>
            </div>

            <div className="flex justify-end gap-2">
              <button onClick={onClose} className="rounded border px-4 py-2 text-sm">取消</button>
              <button
                onClick={loadUnassigned}
                disabled={!selectedInstId}
                className="rounded bg-primary-600 px-4 py-2 text-sm text-white hover:bg-primary-700 disabled:opacity-50"
              >
                下一步：選擇紀錄
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <p className="text-sm text-gray-500">
              找到 {unassigned.length} 筆未歸屬紀錄，已選 {selectedIds.size} 筆，合計 ${totalAmount.toLocaleString()}
            </p>

            {unassigned.length === 0 ? (
              <p className="py-4 text-center text-gray-400">沒有可用的未歸屬紀錄</p>
            ) : (
              <div className="max-h-64 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-gray-50 text-left text-xs text-gray-500">
                      <th className="px-2 py-1">
                        <input type="checkbox" checked={selectedIds.size === unassigned.length} onChange={toggleAll} />
                      </th>
                      <th className="px-2 py-1">日期</th>
                      <th className="px-2 py-1">個案</th>
                      <th className="px-2 py-1">心理師</th>
                      <th className="px-2 py-1">類型</th>
                      <th className="px-2 py-1 text-right">金額</th>
                      <th className="px-2 py-1">文件</th>
                    </tr>
                  </thead>
                  <tbody>
                    {unassigned.map((r) => (
                      <tr key={r.id} className="border-b hover:bg-gray-50">
                        <td className="px-2 py-1">
                          <input type="checkbox" checked={selectedIds.has(r.id)} onChange={() => toggleId(r.id)} />
                        </td>
                        <td className="px-2 py-1">{r.session_date}</td>
                        <td className="px-2 py-1">{r.case_name}</td>
                        <td className="px-2 py-1">{r.therapist_name}</td>
                        <td className="px-2 py-1">{SESSION_TYPE_LABELS[r.session_type] ?? r.session_type}</td>
                        <td className="px-2 py-1 text-right">${r.amount.toLocaleString()}</td>
                        <td className="px-2 py-1">
                          {r.therapist_doc_submitted_at ? (
                            <span className="text-green-600 text-xs">&#10003;</span>
                          ) : (
                            <span className="text-amber-500 text-xs">-</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button onClick={() => setStep(1)} className="rounded border px-4 py-2 text-sm">上一步</button>
              <button
                onClick={handleCreate}
                disabled={selectedIds.size === 0 || submitting}
                className="rounded bg-primary-600 px-4 py-2 text-sm text-white hover:bg-primary-700 disabled:opacity-50"
              >
                {submitting ? "建立中..." : `建立核銷案 (${selectedIds.size} 筆)`}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════
   文件確認（心理師用）
   ═══════════════════════════════════════════════ */

function DocConfirmTab({ token, userRole }: { token: string; userRole: string }) {
  const [records, setRecords] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchPending = useCallback(async () => {
    setLoading(true);
    try {
      const data = await clientFetch("/ledger", token);
      const pending = data.filter(
        (r: any) => r.claim_batch_id && !r.therapist_doc_submitted_at
      );
      setRecords(pending);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchPending(); }, [fetchPending]);

  const confirmDoc = async (recordId: number) => {
    try {
      await clientFetch(`/ledger/${recordId}/confirm-doc`, token, { method: "PUT" });
      fetchPending();
    } catch (e: any) {
      alert(e.message);
    }
  };

  return (
    <div>
      <p className="mb-4 text-sm text-gray-500">
        以下是您負責且屬於核銷案、尚未確認文件的諮商紀錄。確認後核銷案將自動檢查是否所有紀錄都已確認。
      </p>

      {loading ? (
        <div className="py-8 text-center text-gray-400">載入中...</div>
      ) : records.length === 0 ? (
        <div className="py-8 text-center text-gray-400">目前沒有待確認的紀錄</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50 text-left text-xs text-gray-500">
                <th className="px-3 py-2">日期</th>
                <th className="px-3 py-2">個案</th>
                <th className="px-3 py-2">類型</th>
                <th className="px-3 py-2 text-right">金額</th>
                <th className="px-3 py-2">核銷案</th>
                <th className="px-3 py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r: any) => (
                <tr key={r.id} className="border-b hover:bg-gray-50">
                  <td className="px-3 py-2">{r.session_date}</td>
                  <td className="px-3 py-2">{r.case_name}</td>
                  <td className="px-3 py-2">{SESSION_TYPE_LABELS[r.session_type] ?? r.session_type}</td>
                  <td className="px-3 py-2 text-right">${r.amount?.toLocaleString()}</td>
                  <td className="px-3 py-2 font-mono text-xs">{r.claim_batch_number ?? `#${r.claim_batch_id}`}</td>
                  <td className="px-3 py-2">
                    <button
                      onClick={() => confirmDoc(r.id)}
                      className="rounded bg-green-600 px-3 py-1 text-xs text-white hover:bg-green-700"
                    >
                      確認文件
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
