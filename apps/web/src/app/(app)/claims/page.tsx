"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import HelpDrawer, { type HelpContent } from "@/components/HelpDrawer";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const helpContent: HelpContent = {
  title: "核銷案管理",
  overview: "將多筆諮商記錄打包成核銷批次，用於自費收款確認或機構統一請款。建立後可下載收據或請款單 PDF。",
  sections: [
    {
      heading: "建立自費核銷案",
      type: "steps",
      items: [
        "點「＋建立核銷案」，選「自費個案」",
        "搜尋並選擇個案",
        "勾選要納入的諮商記錄（系統列出未歸屬的記錄）",
        "設定期間（起訖日期），確認金額後建立",
        "狀態進入「收款中」",
        "點「付款」，選擇付款方式（現金/匯款）並填寫匯款資訊",
        "確認後批次自動結案，可下載收據 PDF 存檔",
      ],
    },
    {
      heading: "建立機構核銷案",
      type: "steps",
      items: [
        "點「＋建立核銷案」，選「機構」",
        "選擇機構名稱，勾選諮商記錄，設定期間後建立",
        "等待心理師在「確認文件」頁面逐筆標記文件備妥",
        "全部確認後批次自動升為「文件備妥」",
        "點「提交請款」，填入外部請款單號",
        "款項到帳後點「標記到款」→「結案」，下載請款單 PDF",
      ],
    },
    {
      heading: "狀態流程",
      type: "text",
      items: [
        "自費：收款中 → 付款（選現金/匯款）→ 結案 → 列印收據",
        "機構：收款中 → 文件備妥（自動）→ 已提交 → 款項到帳 → 結案",
      ],
    },
    {
      heading: "管理員提示",
      type: "notes",
      items: [
        "核銷案編號：自費 = S{週期}-{案號}-{YYYYMM}；機構 = I-{機構代碼}-{YYYYMM}",
        "同一筆諮商記錄不能同時屬於兩個核銷案",
        "PDF 收據含診所名稱、個案資訊、明細表、簽名欄",
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

interface CaseOption {
  id: number;
  name: string;
  case_number: string | null;
  billing_cycle: string;
  institution_id: number | null;
}

interface InstitutionOption {
  id: number;
  name: string;
  code: string | null;
}

/* ───── main page ───── */

export default function ClaimsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const userRole = (session?.user as any)?.role;
  const [tab, setTab] = useState<"batches" | "docs">("batches");
  const [helpOpen, setHelpOpen] = useState(false);

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <HelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} content={helpContent} />
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">核銷案管理</h1>
        <button onClick={() => setHelpOpen(true)} className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50 hover:text-gray-700">
          <span>ℹ️</span> 說明
        </button>
      </div>

      <div className="mb-4 flex gap-1 border-b border-gray-200">
        {(
          [
            ["batches", "核銷案列表"],
            ["docs", "文件確認"],
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

      {tab === "batches" && <BatchListTab token={token} userRole={userRole} />}
      {tab === "docs" && <DocConfirmTab token={token} userRole={userRole} />}
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
const TYPE_LABELS: Record<string, string> = { self_pay: "自費", institution: "機構" };

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
   Tab 1 — 核銷案列表
   ═══════════════════════════════════════════════ */

function BatchListTab({ token, userRole }: { token: string; userRole: string }) {
  const [batches, setBatches] = useState<ClaimBatch[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const fetchBatches = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      if (typeFilter) params.set("type", typeFilter);
      const qs = params.toString();
      const data = await clientFetch(`/claim-batches${qs ? `?${qs}` : ""}`, token);
      setBatches(data);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  }, [token, statusFilter, typeFilter]);

  useEffect(() => { fetchBatches(); }, [fetchBatches]);

  const canEdit = ["admin", "accountant", "staff"].includes(userRole);

  return (
    <div>
      {/* Filters + Create button */}
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
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="">全部類型</option>
          <option value="self_pay">自費</option>
          <option value="institution">機構</option>
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
        <div className="py-8 text-center text-gray-400">目前沒有核銷案</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50 text-left text-xs text-gray-500">
                <th className="px-3 py-2">編號</th>
                <th className="px-3 py-2">類型</th>
                <th className="px-3 py-2">個案/機構</th>
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

/* ── Batch row + expandable detail ── */

/* ── Payment Modal (self-pay only) ── */

function PaymentModal({
  batch,
  token,
  onClose,
  onDone,
}: {
  batch: ClaimBatch;
  token: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [method, setMethod] = useState<"cash" | "transfer">("cash");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    if (method === "transfer" && !note.trim()) {
      alert("請填寫匯款資訊");
      return;
    }
    setSaving(true);
    try {
      // 1. Save payment info
      await clientFetch(`/claim-batches/${batch.id}`, token, {
        method: "PUT",
        body: JSON.stringify({
          payment_method: method,
          payment_note: note.trim() || null,
        }),
      });
      // 2. Close the batch
      await clientFetch(`/claim-batches/${batch.id}/close`, token, { method: "PUT" });
      onDone();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-80 rounded-lg bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 text-base font-semibold">確認付款</h3>
        <p className="mb-3 text-sm text-gray-600">
          核銷案：<span className="font-mono">{batch.batch_number}</span><br />
          金額：<strong>${batch.total_amount.toLocaleString()}</strong>
        </p>

        <fieldset className="mb-3">
          <legend className="mb-1 text-xs font-medium text-gray-700">付款方式</legend>
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" value="cash" checked={method === "cash"} onChange={() => setMethod("cash")} />
            現金
          </label>
          <label className="flex items-center gap-2 text-sm mt-1">
            <input type="radio" value="transfer" checked={method === "transfer"} onChange={() => setMethod("transfer")} />
            匯款
          </label>
        </fieldset>

        <label className="block mb-4">
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

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100">
            取消
          </button>
          <button
            onClick={handleSubmit}
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
  const [showPayModal, setShowPayModal] = useState(false);

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
      {showPayModal && (
        <PaymentModal
          batch={b}
          token={token}
          onClose={() => setShowPayModal(false)}
          onDone={() => { setShowPayModal(false); onRefresh(); }}
        />
      )}
      <tr className="border-b hover:bg-gray-50 cursor-pointer" onClick={onToggle}>
        <td className="px-3 py-2 font-mono text-xs">{b.batch_number}</td>
        <td className="px-3 py-2">{TYPE_LABELS[b.type] ?? b.type}</td>
        <td className="px-3 py-2">{b.type === "self_pay" ? b.case_name : b.institution_name}</td>
        <td className="px-3 py-2 text-xs">
          {b.period_start ?? ""} ~ {b.period_end ?? ""}
        </td>
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
            {/* ── Self-pay flow ── */}
            {b.type === "self_pay" && canEdit && ["collecting", "ready"].includes(b.status) && (
              <button
                onClick={() => setShowPayModal(true)}
                className="rounded bg-green-600 px-2 py-0.5 text-xs text-white hover:bg-green-700"
              >
                付款
              </button>
            )}
            {b.type === "self_pay" && b.status === "closed" && (
              <button
                onClick={() => downloadPdf(`/claim-batches/${b.id}/receipt`, token, `receipt-${b.batch_number}.pdf`)}
                className="rounded border border-gray-300 px-2 py-0.5 text-xs hover:bg-gray-100"
              >
                列印收據
              </button>
            )}

            {/* ── Institution flow ── */}
            {b.type === "institution" && canEdit && (b.status === "collecting" || b.status === "ready") && (
              <button onClick={() => transition("submit")} className="rounded bg-blue-600 px-2 py-0.5 text-xs text-white hover:bg-blue-700">
                提交請款
              </button>
            )}
            {b.type === "institution" && canEdit && b.status === "submitted" && (
              <button onClick={() => transition("receive")} className="rounded bg-green-600 px-2 py-0.5 text-xs text-white hover:bg-green-700">
                確認收款
              </button>
            )}
            {b.type === "institution" && canEdit && ["submitted", "received"].includes(b.status) && (
              <button onClick={() => transition("close")} className="rounded bg-gray-600 px-2 py-0.5 text-xs text-white hover:bg-gray-700">
                結案
              </button>
            )}
            {b.type === "institution" && b.status === "closed" && (
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
          <td colSpan={8} className="border-b bg-gray-50 px-4 py-3">
            {/* Edit external_ref / payment info */}
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

            {/* Records detail */}
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
                    {b.type === "institution" && (
                      <th className="px-2 py-1">文件確認</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {records.map((r) => (
                    <tr key={r.id} className="border-t border-gray-200">
                      <td className="px-2 py-1">{r.session_date}</td>
                      <td className="px-2 py-1">{r.case_name}</td>
                      <td className="px-2 py-1">{r.therapist_name}</td>
                      <td className="px-2 py-1">{r.session_type}</td>
                      <td className="px-2 py-1 text-right">${r.amount.toLocaleString()}</td>
                      <td className="px-2 py-1">{r.payment_status}</td>
                      {b.type === "institution" && (
                        <td className="px-2 py-1">
                          {r.therapist_doc_submitted_at ? (
                            <span className="text-green-600">&#10003; 已確認</span>
                          ) : (
                            <span className="text-amber-600">待確認</span>
                          )}
                        </td>
                      )}
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

/* ── Create batch modal ── */

function CreateBatchModal({
  token,
  onClose,
  onCreated,
}: {
  token: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [batchType, setBatchType] = useState<"self_pay" | "institution">("self_pay");
  const [cases, setCases] = useState<CaseOption[]>([]);
  const [institutions, setInstitutions] = useState<InstitutionOption[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<number | "">("");
  const [selectedInstId, setSelectedInstId] = useState<number | "">("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [unassigned, setUnassigned] = useState<UnassignedRecord[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [step, setStep] = useState(1);

  useEffect(() => {
    clientFetch("/cases", token).then(setCases).catch(() => {});
    clientFetch("/institutions", token).then(setInstitutions).catch(() => {});
  }, [token]);

  const loadUnassigned = async () => {
    const params = new URLSearchParams();
    if (batchType === "self_pay" && selectedCaseId) params.set("case_id", String(selectedCaseId));
    if (batchType === "institution" && selectedInstId) params.set("institution_id", String(selectedInstId));
    const qs = params.toString();
    try {
      const data = await clientFetch(`/claim-batches/unassigned/records${qs ? `?${qs}` : ""}`, token);
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
    if (selectedIds.size === unassigned.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(unassigned.map((r) => r.id)));
    }
  };

  const handleCreate = async () => {
    if (selectedIds.size === 0) { alert("請至少勾選一筆紀錄"); return; }
    setSubmitting(true);
    try {
      const selectedCase = cases.find((c) => c.id === selectedCaseId);
      await clientFetch("/claim-batches", token, {
        method: "POST",
        body: JSON.stringify({
          type: batchType,
          case_id: batchType === "self_pay" ? selectedCaseId || null : null,
          institution_id: batchType === "institution" ? selectedInstId || null : null,
          billing_cycle: selectedCase?.billing_cycle ?? null,
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
          <h2 className="text-lg font-bold">建立核銷案</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
        </div>

        {step === 1 && (
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium">類型</label>
              <div className="flex gap-3">
                {(["self_pay", "institution"] as const).map((t) => (
                  <label key={t} className="flex items-center gap-1 text-sm">
                    <input type="radio" name="btype" checked={batchType === t} onChange={() => setBatchType(t)} />
                    {TYPE_LABELS[t]}
                  </label>
                ))}
              </div>
            </div>

            {batchType === "self_pay" && (
              <div>
                <label className="mb-1 block text-sm font-medium">個案</label>
                <select
                  value={selectedCaseId}
                  onChange={(e) => setSelectedCaseId(e.target.value ? Number(e.target.value) : "")}
                  className="w-full rounded border px-3 py-2 text-sm"
                >
                  <option value="">-- 選擇個案 --</option>
                  {cases.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.case_number ? `[${c.case_number}] ` : ""}{c.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {batchType === "institution" && (
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
            )}

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
                disabled={(batchType === "self_pay" && !selectedCaseId) || (batchType === "institution" && !selectedInstId)}
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
                        <td className="px-2 py-1">{r.session_type}</td>
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
   Tab 2 — 文件確認（心理師用）
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
                  <td className="px-3 py-2">{r.session_type}</td>
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
