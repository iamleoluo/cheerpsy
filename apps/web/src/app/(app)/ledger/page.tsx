"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch, exportCsv } from "@/lib/client-api";
import HelpDrawer, { type HelpContent } from "@/components/HelpDrawer";

const helpContent: HelpContent = {
  title: "日結帳冊",
  overview: "由系統在 T+1 自動寫入的諮商財務台帳，無需手動輸入諮商記錄。行政需要做的是：確認收款狀態、填入收款資訊、最後鎖定。",
  sections: [
    {
      heading: "執行日結",
      type: "steps",
      items: [
        "每日進入日結帳冊，點「執行日結（每日查看請點擊確保資料更新）」",
        "系統自動將前一日未取消的預約寫入帳冊",
        "若需補跑歷史日期，可填入日期區間後執行",
        "確認新增筆數無誤",
      ],
    },
    {
      heading: "自費收款",
      type: "steps",
      items: [
        "找到待收款的自費紀錄",
        "點「收款」按鈕",
        "選付款方式：現金 / 匯款",
        "匯款需填入帳戶末 5 碼作為憑據",
        "確認後狀態變為「已收款」",
      ],
    },
    {
      heading: "機構請款",
      type: "steps",
      items: [
        "找到待請款的機構紀錄，點「請款」",
        "填入請款單號（請款單據上的編號）",
        "狀態變為「請款中」",
        "款項到帳後點「到款」，填入匯款單號或收據號",
        "狀態更新為「已核銷」",
      ],
    },
    {
      heading: "鎖定與解鎖",
      type: "steps",
      items: [
        "帳務確認無誤後點「鎖定」，進入唯讀狀態",
        "如需修正：點「解鎖」→ 填寫修改原因 → 修改後重新鎖定",
        "所有解鎖操作均記錄於稽核日誌，管理員可查",
      ],
    },
    {
      heading: "注意事項",
      type: "tips",
      items: [
        "諮商日期、金額等核心欄位鎖定後不可更改，需解鎖並填原因",
        "心理師只能看到自己的紀錄，行政與管理員可看全所",
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
  locked_at: string | null;
}

const selfPayLabels: Record<string, string> = {
  unpaid: "未收款",
  paid: "已收款",
};

const institutionLabels: Record<string, string> = {
  unpaid: "未請款",
  claiming: "請款中",
  claimed: "已請款",
};

const paymentColors: Record<string, string> = {
  unpaid: "bg-red-100 text-red-700",
  paid: "bg-green-100 text-green-700",
  claiming: "bg-blue-100 text-blue-700",
  claimed: "bg-green-100 text-green-700",
};

const allFilterLabels: Record<string, string> = {
  unpaid: "未收款/未請款",
  paid: "已收款",
  claiming: "請款中",
  claimed: "已請款",
};

const sessionTypeLabels: Record<string, string> = {
  in_person: "現場",
  online: "線上",
  home_visit: "到宅",
};

function getPaymentLabel(status: string, funding: string | null): string {
  if (funding === "institution") {
    return institutionLabels[status] ?? status;
  }
  return selfPayLabels[status] ?? status;
}

export default function LedgerPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const userRole = (session?.user as any)?.role;
  const [helpOpen, setHelpOpen] = useState(false);

  const now = new Date();
  const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;

  const [records, setRecords] = useState<SessionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [filterMonth, setFilterMonth] = useState(currentMonth);
  const [settling, setSettling] = useState(false);
  const [settleDateFrom, setSettleDateFrom] = useState("");
  const [settleDateTo, setSettleDateTo] = useState("");
  const [settleResult, setSettleResult] = useState("");

  const [inputModal, setInputModal] = useState<{
    recordId: number;
    type: "claiming" | "claimed";
  } | null>(null);
  const [inputValue, setInputValue] = useState("");
  const [collectModal, setCollectModal] = useState<number | null>(null);
  const [collectMethod, setCollectMethod] = useState<"cash" | "transfer">("cash");
  const [collectNote, setCollectNote] = useState("");
  const [unlockModal, setUnlockModal] = useState<number | null>(null);
  const [unlockReason, setUnlockReason] = useState("");

  const [editModal, setEditModal] = useState<SessionRecord | null>(null);
  const [editStatus, setEditStatus] = useState("");
  const [editMethod, setEditMethod] = useState<"cash" | "transfer" | "">("cash");
  const [editNote, setEditNote] = useState("");
  const [editClaim, setEditClaim] = useState("");
  const [editReceipt, setEditReceipt] = useState("");

  const fetchRecords = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filter) params.set("payment_status", filter);
      if (filterMonth) params.set("month", filterMonth);
      const qs = params.toString();
      const data = await clientFetch(`/ledger${qs ? `?${qs}` : ""}`, token);
      setRecords(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [token, filter, filterMonth]);

  useEffect(() => {
    fetchRecords();
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
      setSettleResult(
        `日結完成：${result.date}，執行 ${result.executed} 筆，跳過 ${result.skipped} 筆`,
      );
      fetchRecords();
    } catch (e: any) {
      setSettleResult(`錯誤：${e.message}`);
    } finally {
      setSettling(false);
    }
  };

  const handleSelfPayCollect = async () => {
    if (!collectModal || !token) return;
    if (collectMethod === "transfer" && !collectNote.trim()) {
      alert("匯款資訊為必填（如帳戶末五碼）");
      return;
    }
    try {
      await clientFetch(`/ledger/${collectModal}/payment`, token, {
        method: "PUT",
        body: JSON.stringify({
          payment_status: "paid",
          payment_method: collectMethod,
          payment_note: collectNote.trim() || null,
        }),
      });
      setCollectModal(null);
      setCollectMethod("cash");
      setCollectNote("");
      fetchRecords();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleInputSubmit = async () => {
    if (!inputModal || !token || !inputValue.trim()) return;
    const body: any = { payment_status: inputModal.type };
    if (inputModal.type === "claiming") {
      body.claim_number = inputValue.trim();
    } else {
      body.receipt_number = inputValue.trim();
    }
    try {
      await clientFetch(`/ledger/${inputModal.recordId}/payment`, token, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      setInputModal(null);
      setInputValue("");
      fetchRecords();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleLock = async (id: number) => {
    if (!token || !confirm("鎖定後無法修改，確定嗎？")) return;
    try {
      await clientFetch(`/ledger/${id}/lock`, token, { method: "PUT" });
      fetchRecords();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleUnlock = async () => {
    if (!unlockModal || !token || !unlockReason.trim()) return;
    try {
      await clientFetch(`/ledger/${unlockModal}/unlock`, token, {
        method: "PUT",
        body: JSON.stringify({ reason: unlockReason.trim() }),
      });
      setUnlockModal(null);
      setUnlockReason("");
      fetchRecords();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const openEditModal = (r: SessionRecord) => {
    setEditModal(r);
    setEditStatus(r.payment_status);
    setEditMethod((r.payment_method as any) || "cash");
    setEditNote(r.payment_note ?? "");
    setEditClaim(r.claim_number ?? "");
    setEditReceipt(r.receipt_number ?? "");
  };

  const handleDirectEdit = async () => {
    if (!editModal || !token) return;
    try {
      await clientFetch(`/ledger/${editModal.id}/edit`, token, {
        method: "PUT",
        body: JSON.stringify({
          payment_status: editStatus,
          payment_method: editMethod || null,
          payment_note: editNote.trim() || null,
          claim_number: editClaim.trim() || null,
          receipt_number: editReceipt.trim() || null,
        }),
      });
      setEditModal(null);
      fetchRecords();
    } catch (e: any) {
      alert(e.message);
    }
  };

  if (!token) return <p>Loading...</p>;

  const totalAmount = records.reduce((s, r) => s + r.amount, 0);
  const totalTherapist = records.reduce((s, r) => s + r.therapist_share, 0);
  const totalClinic = records.reduce((s, r) => s + r.clinic_share, 0);

  return (
    <div>
      <HelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} content={helpContent} />
      <div className="mb-6 flex items-center justify-between">
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
          {userRole === "admin" && (
            <>
              <div className="flex flex-col items-end gap-0.5">
                <div className="flex items-center gap-1">
                  <input
                    type="date"
                    value={settleDateFrom}
                    onChange={(e) => setSettleDateFrom(e.target.value)}
                    className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
                  />
                  <span className="text-xs text-gray-400">～</span>
                  <input
                    type="date"
                    value={settleDateTo}
                    onChange={(e) => setSettleDateTo(e.target.value)}
                    className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
                  />
                </div>
                <span className="text-xs text-gray-400">補跑日期區間，留空則結算昨日</span>
              </div>
              <button
                onClick={handleSettle}
                disabled={settling}
                className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
              >
                {settling ? "日結中..." : "執行日結（每日查看請點擊確保資料更新）"}
              </button>
            </>
          )}
        </div>
      </div>

      {settleResult && (
        <div className="mb-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-700">
          {settleResult}
        </div>
      )}

      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
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
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </div>
        <div className="flex gap-4 text-sm text-gray-500">
          <span>
            合計: <strong className="text-gray-900">${totalAmount.toLocaleString()}</strong>
          </span>
          <span>師: ${totalTherapist.toLocaleString()}</span>
          <span>所: ${totalClinic.toLocaleString()}</span>
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">日期</th>
              <th className="px-4 py-3">預約編號</th>
              <th className="px-4 py-3">個案</th>
              <th className="px-4 py-3">心理師</th>
              <th className="px-4 py-3">類型</th>
              <th className="px-4 py-3">金額</th>
              <th className="px-4 py-3">來源</th>
              <th className="px-4 py-3">收款狀態</th>
              <th className="px-4 py-3">收款/單號資訊</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={10} className="px-4 py-8 text-center text-gray-400">
                  載入中...
                </td>
              </tr>
            ) : records.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-4 py-8 text-center text-gray-400">
                  尚無流水帳資料（請先執行日結）
                </td>
              </tr>
            ) : (
              records.map((r) => (
                <tr key={r.id} className={`hover:bg-gray-50 ${r.locked_at ? "bg-gray-50/50" : ""}`}>
                  <td className="px-4 py-3">{r.session_date}</td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {r.appointment_number}
                  </td>
                  <td className="px-4 py-3">{r.case_name ?? "-"}</td>
                  <td className="px-4 py-3">{r.therapist_name ?? "-"}</td>
                  <td className="px-4 py-3">
                    {sessionTypeLabels[r.session_type] ?? r.session_type}
                  </td>
                  <td className="px-4 py-3">
                    ${r.amount.toLocaleString()}
                    <div className="text-xs text-gray-400">
                      師 ${r.therapist_share.toLocaleString()} / 所 $
                      {r.clinic_share.toLocaleString()}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {r.funding_source === "institution"
                      ? `機構${r.institution_name ? `(${r.institution_name})` : ""}`
                      : "自費"}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${paymentColors[r.payment_status] ?? "bg-gray-100"}`}
                    >
                      {getPaymentLabel(r.payment_status, r.funding_source)}
                    </span>
                    {r.locked_at && (
                      <span className="ml-1 text-xs text-gray-400">🔒</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {r.payment_method && (
                      <div>{r.payment_method === "cash" ? "現金" : "匯款"}{r.payment_note ? ` — ${r.payment_note}` : ""}</div>
                    )}
                    {r.claim_number && (
                      <div>請款: {r.claim_number}</div>
                    )}
                    {r.receipt_number && (
                      <div>收據: {r.receipt_number}</div>
                    )}
                    {!r.payment_method && !r.claim_number && !r.receipt_number && "-"}
                  </td>
                  <td className="px-4 py-3">
                    {!r.locked_at && userRole !== "therapist" && (
                      <div className="flex flex-wrap gap-2">
                        {r.funding_source !== "institution" &&
                          r.payment_status === "unpaid" && (
                            <button onClick={() => { setCollectModal(r.id); setCollectMethod("cash"); setCollectNote(""); }} className="text-xs text-green-600 hover:underline">收款</button>
                          )}
                        {r.funding_source === "institution" &&
                          r.payment_status === "unpaid" && (
                            <button onClick={() => { setInputModal({ recordId: r.id, type: "claiming" }); setInputValue(""); }} className="text-xs text-blue-600 hover:underline">請款</button>
                          )}
                        {r.funding_source === "institution" &&
                          r.payment_status === "claiming" && (
                            <button onClick={() => { setInputModal({ recordId: r.id, type: "claimed" }); setInputValue(""); }} className="text-xs text-green-600 hover:underline">到款</button>
                          )}
                        <button onClick={() => openEditModal(r)} className="text-xs text-gray-500 hover:underline">編輯</button>
                        <button onClick={() => handleLock(r.id)} className="text-xs text-gray-400 hover:underline">鎖定</button>
                      </div>
                    )}
                    {r.locked_at && userRole === "admin" && (
                      <button
                        onClick={() => { setUnlockModal(r.id); setUnlockReason(""); }}
                        className="text-xs text-amber-600 hover:underline"
                      >
                        解鎖
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {inputModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-96 rounded-xl bg-white p-6 shadow-xl">
            <h3 className="mb-4 text-lg font-semibold">
              {inputModal.type === "claiming" ? "輸入請款單號" : "輸入到款收據/單號"}
            </h3>
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={inputModal.type === "claiming" ? "請輸入請款單號..." : "請輸入到款收據或單號..."}
              className="mb-4 w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-primary-500 focus:outline-none"
              autoFocus
              onKeyDown={(e) => { if (e.key === "Enter") handleInputSubmit(); }}
            />
            <div className="flex justify-end gap-3">
              <button onClick={() => { setInputModal(null); setInputValue(""); }} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">取消</button>
              <button onClick={handleInputSubmit} disabled={!inputValue.trim()} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">確認</button>
            </div>
          </div>
        </div>
      )}

      {collectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-96 rounded-xl bg-white p-6 shadow-xl">
            <h3 className="mb-4 text-lg font-semibold">自費收款</h3>
            <div className="mb-4">
              <span className="mb-2 block text-sm font-medium text-gray-700">收款方式</span>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="collectMethod"
                    checked={collectMethod === "cash"}
                    onChange={() => setCollectMethod("cash")}
                    className="accent-primary-600"
                  />
                  現金
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="collectMethod"
                    checked={collectMethod === "transfer"}
                    onChange={() => setCollectMethod("transfer")}
                    className="accent-primary-600"
                  />
                  匯款
                </label>
              </div>
            </div>
            {collectMethod === "transfer" && (
              <div className="mb-4">
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">匯款資訊（如帳戶末五碼）*</span>
                  <input
                    type="text"
                    value={collectNote}
                    onChange={(e) => setCollectNote(e.target.value)}
                    placeholder="請輸入匯款資訊..."
                    className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-primary-500 focus:outline-none"
                    autoFocus
                  />
                </label>
              </div>
            )}
            {collectMethod === "cash" && (
              <div className="mb-4">
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">備註（選填）</span>
                  <input
                    type="text"
                    value={collectNote}
                    onChange={(e) => setCollectNote(e.target.value)}
                    placeholder="備註..."
                    className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-primary-500 focus:outline-none"
                  />
                </label>
              </div>
            )}
            <div className="flex justify-end gap-3">
              <button onClick={() => { setCollectModal(null); setCollectMethod("cash"); setCollectNote(""); }} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">取消</button>
              <button
                onClick={handleSelfPayCollect}
                disabled={collectMethod === "transfer" && !collectNote.trim()}
                className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
              >
                確認收款
              </button>
            </div>
          </div>
        </div>
      )}

      {unlockModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl">
            <h3 className="mb-4 text-lg font-semibold">解鎖帳務紀錄</h3>
            <p className="mb-3 text-sm text-gray-500">解鎖後可再次修改此筆帳務。此操作會記錄在稽核日誌中。</p>
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">解鎖原因 *</span>
              <textarea
                value={unlockReason}
                onChange={(e) => setUnlockReason(e.target.value)}
                rows={3}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                placeholder="請說明解鎖原因..."
                autoFocus
              />
            </label>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => { setUnlockModal(null); setUnlockReason(""); }} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">取消</button>
              <button onClick={handleUnlock} disabled={!unlockReason.trim()} className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50">確認解鎖</button>
            </div>
          </div>
        </div>
      )}
      {editModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <h3 className="mb-4 text-lg font-semibold">編輯收款資訊</h3>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500">收款狀態</label>
                <select
                  value={editStatus}
                  onChange={(e) => setEditStatus(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                >
                  <option value="unpaid">{editModal.funding_source === "institution" ? "待請款" : "未收款"}</option>
                  {editModal.funding_source !== "institution" && <option value="paid">已收款</option>}
                  {editModal.funding_source === "institution" && <option value="claiming">請款中</option>}
                  {editModal.funding_source === "institution" && <option value="claimed">已核銷</option>}
                </select>
              </div>
              {editModal.funding_source !== "institution" && (
                <>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-500">收款方式</label>
                    <div className="flex gap-4">
                      {(["cash", "transfer"] as const).map((m) => (
                        <label key={m} className="flex items-center gap-1.5 text-sm">
                          <input type="radio" checked={editMethod === m} onChange={() => setEditMethod(m)} />
                          {m === "cash" ? "現金" : "匯款"}
                        </label>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-500">收款備註</label>
                    <input type="text" value={editNote} onChange={(e) => setEditNote(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" placeholder="如帳戶末五碼..." />
                  </div>
                </>
              )}
              {editModal.funding_source === "institution" && (
                <>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-500">請款單號</label>
                    <input type="text" value={editClaim} onChange={(e) => setEditClaim(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" placeholder="請款單號..." />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-500">到款收據/單號</label>
                    <input type="text" value={editReceipt} onChange={(e) => setEditReceipt(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" placeholder="到款收據或單號..." />
                  </div>
                </>
              )}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setEditModal(null)} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">取消</button>
              <button onClick={handleDirectEdit} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700">儲存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
