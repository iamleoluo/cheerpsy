"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch, exportCsv } from "@/lib/client-api";
import HelpDrawer, { type HelpContent } from "@/components/HelpDrawer";
import ReceiptModal from "@/components/ReceiptModal";

const helpContent: HelpContent = {
  title: "帳冊流水帳",
  guideId: "ledger",
  overview: "預約結束時間一過即時進帳冊，列為應收未收。每筆都有收據編號可開立收據；行政可加優待，未執行的場次需於當日由心理師作廢（逾期由管理員處理）。",
  sections: [
    {
      heading: "頁面說明",
      type: "text",
      items: [
        "本月帳單：查看當月所有帳務紀錄（日期、個案、心理師、金額、核銷歸屬）",
        "待處理：尚未歸入核銷案的帳單，可勾選後批次建立核銷案",
        "歷史查詢：跨月份查詢，可依月份 / 心理師 / 狀態篩選",
      ],
    },
    {
      heading: "每日作業流程",
      type: "steps",
      items: [
        "進入日結帳冊，點「執行日結」確保昨日資料寫入",
        "切換到「待處理」分頁，確認未歸入核銷案的帳單",
        "勾選帳單 → 點「建立核銷案」，選擇自費或機構",
        "前往核銷案管理完成後續收款或請款流程",
      ],
    },
    {
      heading: "收款狀態說明",
      type: "text",
      items: [
        "自費：未收款 → 已收款（透過核銷案付款後自動更新）",
        "機構：未請款 → 請款中 → 已請款（隨核銷案狀態同步）",
      ],
    },
    {
      heading: "注意事項",
      type: "tips",
      items: [
        "日結帳冊為唯讀，收款狀態由核銷案流程自動更新",
        "心理師只能看到自己的帳務紀錄",
        "機構案心理師需在此頁面點「確認文件」，才能推進核銷案狀態",
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
  discount_amount: number;
  discount_note: string | null;
  effective_amount: number;
  receipt_no: string | null;
  is_void: boolean;
  void_reason: string | null;
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
  claim_batch_number: string | null;
  parent_record_id: number | null;
  therapist_doc_submitted_at: string | null;
  locked_at: string | null;
  commission_rate_used: number | null;
  billing_cycle: string | null;
  outcall_bonus: number;
}

const BILLING_CYCLE_LABEL: Record<string, string> = { monthly: "月結", once: "次結", multiple: "多次結" };
const selfPayLabels: Record<string, string> = { unpaid: "未收款", paid: "已收款" };
const institutionLabels: Record<string, string> = { unpaid: "未請款", claiming: "請款中", claimed: "已請款" };
const paymentColors: Record<string, string> = {
  unpaid: "bg-red-100 text-red-700",
  paid: "bg-green-100 text-green-700",
  claiming: "bg-blue-100 text-blue-700",
  claimed: "bg-green-100 text-green-700",
};
const allFilterLabels: Record<string, string> = { unpaid: "未收款/未請款", paid: "已收款", claiming: "請款中", claimed: "已請款" };
const sessionTypeLabels: Record<string, string> = { in_person: "現場", online: "線上", outdoor: "外出" };

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

  // Discount modal
  const [discountRec, setDiscountRec] = useState<SessionRecord | null>(null);
  const [discMode, setDiscMode] = useState<"amount" | "percent">("amount");
  const [discValue, setDiscValue] = useState("");
  const [discNote, setDiscNote] = useState("");

  const [splitRec, setSplitRec] = useState<SessionRecord | null>(null);
  const [splitAmount, setSplitAmount] = useState("");
  const [splitMethod, setSplitMethod] = useState<"cash" | "transfer">("cash");
  const [splitNote, setSplitNote] = useState("");
  const [splitFeeCategory, setSplitFeeCategory] = useState("行政規費");

  const [ledgerBatchId, setLedgerBatchId] = useState<number | null>(null);

  const [bonusRec, setBonusRec] = useState<SessionRecord | null>(null);
  const [bonusAmount, setBonusAmount] = useState("1000");
  const [bonusNote, setBonusNote] = useState("");

  const [receiptRecordId, setReceiptRecordId] = useState<number | null>(null);

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

  const openDiscount = (r: SessionRecord) => {
    setDiscountRec(r);
    setDiscMode("amount");
    setDiscValue(r.discount_amount ? String(r.discount_amount) : "");
    setDiscNote(r.discount_note ?? "");
  };

  const submitDiscount = async () => {
    if (!discountRec) return;
    const body: any = { discount_note: discNote || null };
    if (discMode === "percent") body.discount_percent = Number(discValue);
    else body.discount_amount = Number(discValue);
    try {
      await clientFetch(`/ledger/${discountRec.id}/discount`, token, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      setDiscountRec(null);
      fetchRecords();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const openSplit = (r: SessionRecord) => {
    setSplitRec(r);
    setSplitAmount("");
    setSplitMethod("cash");
    setSplitNote("");
    setSplitFeeCategory("行政規費");
  };

  const submitSplit = async () => {
    if (!splitRec) return;
    const amt = parseFloat(splitAmount);
    if (!amt || amt <= 0 || amt >= splitRec.amount) {
      alert("自費金額需 > 0 且 < 原金額");
      return;
    }
    try {
      await clientFetch(`/ledger/${splitRec.id}/split`, token, {
        method: "POST",
        body: JSON.stringify({
          self_pay_amount: amt,
          payment_method: splitMethod,
          payment_note: splitNote || null,
          fee_category: splitFeeCategory,
        }),
      });
      setSplitRec(null);
      fetchRecords();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const openBonus = (r: SessionRecord) => {
    setBonusRec(r);
    setBonusAmount(String((r as any).outcall_bonus ?? 1000));
    setBonusNote((r as any).outcall_note ?? "");
  };

  const submitBonus = async () => {
    if (!bonusRec) return;
    const amt = parseFloat(bonusAmount);
    if (isNaN(amt) || amt < 0) {
      alert("保底金額需 ≥ 0");
      return;
    }
    try {
      await clientFetch(`/ledger/${bonusRec.id}/outcall-bonus`, token, {
        method: "PUT",
        body: JSON.stringify({ amount: amt, note: bonusNote || null }),
      });
      setBonusRec(null);
      fetchRecords();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleVoid = async (r: SessionRecord) => {
    const reason = prompt("作廢原因（選填）：");
    if (reason === null) return;
    try {
      await clientFetch(`/ledger/${r.id}/void`, token, {
        method: "PUT",
        body: JSON.stringify({ reason: reason || null }),
      });
      fetchRecords();
    } catch (e: any) {
      alert(e.message);
    }
  };

  if (!token) return <p>Loading...</p>;

  // Filter pending: unpaid AND not in any claim batch
  const pendingRecords = tab === "pending"
    ? records.filter((r) => r.payment_status === "unpaid" && !r.claim_batch_id && !r.is_void)
    : records;

  const displayRecords = tab === "pending" ? pendingRecords : records;
  const totalAmount = displayRecords.filter((r) => !r.is_void).reduce((s, r) => s + r.effective_amount, 0);
  const totalTherapist = displayRecords.filter((r) => !r.is_void).reduce((s, r) => s + r.therapist_share, 0);
  const totalClinic = displayRecords.filter((r) => !r.is_void).reduce((s, r) => s + r.clinic_share, 0);

  const tabs: { key: Tab; label: string; badge?: number }[] = [
    { key: "month", label: "本月帳單" },
    { key: "pending", label: "待處理", badge: tab !== "pending" ? undefined : pendingRecords.length },
    { key: "history", label: "歷史查詢" },
  ];

  return (
    <div>
      <HelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} guideId="ledger" />
      {receiptRecordId !== null && (
        <ReceiptModal token={token} type="single_session" sourceId={receiptRecordId} onClose={() => setReceiptRecordId(null)} />
      )}
      {ledgerBatchId !== null && (
        <ReceiptModal token={token} type="self_pay_batch" sourceId={ledgerBatchId} onClose={() => setLedgerBatchId(null)} />
      )}

      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">帳冊流水帳</h1>
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
              <th className="px-4 py-3">收據編號</th>
              <th className="px-4 py-3">個案</th>
              <th className="px-4 py-3">心理師</th>
              <th className="px-4 py-3">類型</th>
              <th className="px-4 py-3">金額</th>
              <th className="px-4 py-3">來源</th>
              <th className="px-4 py-3">收款狀態</th>
              <th className="px-4 py-3">結帳批次</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={11} className="px-4 py-8 text-center text-gray-400">載入中...</td></tr>
            ) : displayRecords.length === 0 ? (
              <tr><td colSpan={11} className="px-4 py-8 text-center text-gray-400">
                {tab === "pending" ? "所有帳單皆已歸入核銷案 🎉" : "尚無流水帳資料"}
              </td></tr>
            ) : (
              displayRecords.map((r) => (
                <tr key={r.id} className={`hover:bg-gray-50 ${r.is_void ? "opacity-50 line-through" : ""}`}>
                  {tab === "pending" && userRole !== "therapist" && (
                    <td className="px-3 py-3">
                      <input type="checkbox" disabled={r.is_void} checked={selected.has(r.id)} onChange={() => toggleSelect(r.id)} className="accent-primary-600" />
                    </td>
                  )}
                  <td className="px-4 py-3 whitespace-nowrap">{r.session_date}</td>
                  <td className="px-4 py-3 font-mono text-xs">{r.receipt_no ?? "-"}</td>
                  <td className="px-4 py-3">{r.case_name ?? "-"}</td>
                  <td className="px-4 py-3">{r.therapist_name ?? "-"}</td>
                  <td className="px-4 py-3">{sessionTypeLabels[r.session_type] ?? r.session_type}</td>
                  <td className="px-4 py-3">
                    ${r.effective_amount.toLocaleString()}
                    {r.discount_amount > 0 && (
                      <span className="ml-1 text-xs text-amber-600">(原 ${r.amount.toLocaleString()} 優待 ${r.discount_amount.toLocaleString()})</span>
                    )}
                    <div className="text-xs text-gray-400">
                      師 ${r.therapist_share.toLocaleString()} / 所 ${r.clinic_share.toLocaleString()}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {r.funding_source === "institution"
                      ? `機構（${r.institution_name ?? ""}）`
                      : `自費（${BILLING_CYCLE_LABEL[r.billing_cycle ?? ""] ?? r.billing_cycle ?? ""}）`}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${paymentColors[r.payment_status] ?? "bg-gray-100"}`}>
                      {getPaymentLabel(r.payment_status, r.funding_source)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {r.claim_batch_id ? (
                      <a href={`/claims?batch=${r.claim_batch_id}`} className="font-mono text-primary-600 hover:underline">
                        {r.claim_batch_number ?? `#${r.claim_batch_id}`}
                      </a>
                    ) : (
                      <span className="text-gray-400">未歸入</span>
                    )}
                  </td>
                  <td className="px-4 py-3 no-underline">
                    {r.is_void ? (
                      <span className="text-xs text-red-500">已作廢</span>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        {["admin", "staff"].includes(userRole) && r.payment_status === "unpaid" && (
                          <button onClick={() => openDiscount(r)} className="text-xs text-amber-600 hover:underline">優待</button>
                        )}
                        {["admin", "staff"].includes(userRole) &&
                          r.funding_source === "institution" &&
                          !r.parent_record_id &&
                          !r.locked_at &&
                          r.payment_status !== "claimed" && (
                          <button onClick={() => openSplit(r)} className="text-xs text-indigo-600 hover:underline">拆帳</button>
                        )}
                        {["admin", "staff"].includes(userRole) &&
                          r.session_type === "outdoor" &&
                          r.payment_status === "unpaid" &&
                          !r.locked_at && (
                          <button onClick={() => openBonus(r)} className="text-xs text-emerald-600 hover:underline">
                            {r.outcall_bonus > 0 ? `保底 $${r.outcall_bonus}` : "外出保底"}
                          </button>
                        )}
                        {["admin", "staff"].includes(userRole) &&
                          r.funding_source === "institution" &&
                          r.claim_batch_id && (
                          <a href={`/claims?batch=${r.claim_batch_id}`} className="text-xs text-primary-600 hover:underline">核銷案收據</a>
                        )}
                        {["admin", "staff"].includes(userRole) &&
                          r.funding_source === "self_pay" &&
                          r.payment_status === "paid" &&
                          r.claim_batch_id && (
                          <button onClick={() => setLedgerBatchId(r.claim_batch_id!)} className="text-xs text-primary-600 hover:underline">整體收據</button>
                        )}
                        {["admin", "staff"].includes(userRole) &&
                          r.funding_source === "self_pay" &&
                          r.payment_status === "paid" &&
                          !r.claim_batch_id && (
                          <button onClick={() => setReceiptRecordId(r.id)} className="text-xs text-primary-600 hover:underline">開立收據</button>
                        )}
                        {(["admin", "staff"].includes(userRole) || userRole === "therapist") &&
                          !["paid", "claimed"].includes(r.payment_status) && (
                          <button onClick={() => handleVoid(r)} className="text-xs text-red-500 hover:underline">作廢</button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {discountRec && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setDiscountRec(null)}>
          <div className="w-80 rounded-lg bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-3 text-base font-semibold">設定優待</h3>
            <p className="mb-3 text-sm text-gray-600">
              原始金額：<strong>${discountRec.amount.toLocaleString()}</strong>
            </p>
            <fieldset className="mb-3">
              <legend className="mb-1 text-xs font-medium text-gray-700">優待方式</legend>
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" checked={discMode === "amount"} onChange={() => setDiscMode("amount")} />
                優待金額（直接扣除）
              </label>
              <label className="mt-1 flex items-center gap-2 text-sm">
                <input type="radio" checked={discMode === "percent"} onChange={() => setDiscMode("percent")} />
                打折（百分比）
              </label>
            </fieldset>
            <label className="mb-3 block">
              <span className="text-xs font-medium text-gray-700">
                {discMode === "amount" ? "優待金額" : "折扣 %（例：10 = 折抵 10%）"}
              </span>
              <input
                type="number"
                value={discValue}
                onChange={(e) => setDiscValue(e.target.value)}
                className="mt-1 block w-full rounded border px-2 py-1.5 text-sm"
              />
            </label>
            <label className="mb-4 block">
              <span className="text-xs font-medium text-gray-700">優待事由（選填）</span>
              <input
                type="text"
                value={discNote}
                onChange={(e) => setDiscNote(e.target.value)}
                className="mt-1 block w-full rounded border px-2 py-1.5 text-sm"
              />
            </label>
            <div className="flex justify-end gap-2">
              <button onClick={() => setDiscountRec(null)} className="rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100">取消</button>
              <button onClick={submitDiscount} className="rounded bg-amber-600 px-4 py-1.5 text-sm text-white hover:bg-amber-700">儲存</button>
            </div>
          </div>
        </div>
      )}

      {splitRec && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setSplitRec(null)}>
          <div className="w-96 rounded-lg bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-3 text-base font-semibold">拆帳</h3>
            <p className="mb-3 text-sm text-gray-600">
              原始金額：<strong>${splitRec.amount.toLocaleString()}</strong>（機構款）
            </p>
            <label className="mb-3 block">
              <span className="text-xs font-medium text-gray-700">自費金額（個案現場支付）</span>
              <input
                type="number"
                value={splitAmount}
                onChange={(e) => setSplitAmount(e.target.value)}
                placeholder="例如 400"
                className="mt-1 block w-full rounded border px-2 py-1.5 text-sm"
              />
              {splitAmount && parseFloat(splitAmount) > 0 && parseFloat(splitAmount) < splitRec.amount && (
                <p className="mt-1 text-xs text-gray-500">
                  拆完：機構 ${(splitRec.amount - parseFloat(splitAmount)).toLocaleString()}（-A） / 自費 ${parseFloat(splitAmount).toLocaleString()}（-B）
                </p>
              )}
            </label>
            <fieldset className="mb-3">
              <legend className="mb-1 text-xs font-medium text-gray-700">自費收款方式</legend>
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" checked={splitMethod === "cash"} onChange={() => setSplitMethod("cash")} /> 現金
              </label>
              <label className="mt-1 flex items-center gap-2 text-sm">
                <input type="radio" checked={splitMethod === "transfer"} onChange={() => setSplitMethod("transfer")} /> 匯款
              </label>
            </fieldset>
            <label className="mb-3 block">
              <span className="text-xs font-medium text-gray-700">費用名稱（收據顯示）</span>
              <input
                type="text"
                value={splitFeeCategory}
                onChange={(e) => setSplitFeeCategory(e.target.value)}
                placeholder="行政規費"
                className="mt-1 block w-full rounded border px-2 py-1.5 text-sm"
              />
            </label>
            <label className="mb-4 block">
              <span className="text-xs font-medium text-gray-700">備註（選填）</span>
              <input
                type="text"
                value={splitNote}
                onChange={(e) => setSplitNote(e.target.value)}
                className="mt-1 block w-full rounded border px-2 py-1.5 text-sm"
              />
            </label>
            <div className="flex justify-end gap-2">
              <button onClick={() => setSplitRec(null)} className="rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100">取消</button>
              <button onClick={submitSplit} className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-700">確認拆帳</button>
            </div>
          </div>
        </div>
      )}

      {bonusRec && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setBonusRec(null)}>
          <div className="w-80 rounded-lg bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-3 text-base font-semibold">心理師外出保底</h3>
            <p className="mb-3 text-xs text-gray-500">
              用於跨區家訪 / 外出諮商；金額會加入心理師月結酬勞。設 0 可取消。
            </p>
            <label className="mb-3 block">
              <span className="text-xs font-medium text-gray-700">保底金額</span>
              <input
                type="number"
                value={bonusAmount}
                onChange={(e) => setBonusAmount(e.target.value)}
                className="mt-1 block w-full rounded border px-2 py-1.5 text-sm"
              />
            </label>
            <label className="mb-4 block">
              <span className="text-xs font-medium text-gray-700">備註（選填）</span>
              <input
                type="text"
                value={bonusNote}
                onChange={(e) => setBonusNote(e.target.value)}
                placeholder="例：北區家訪"
                className="mt-1 block w-full rounded border px-2 py-1.5 text-sm"
              />
            </label>
            <div className="flex justify-end gap-2">
              <button onClick={() => setBonusRec(null)} className="rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100">取消</button>
              <button onClick={submitBonus} className="rounded bg-emerald-600 px-4 py-1.5 text-sm text-white hover:bg-emerald-700">儲存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
