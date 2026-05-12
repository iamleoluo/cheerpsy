"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch, exportCsv } from "@/lib/client-api";

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

  const [records, setRecords] = useState<SessionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [settling, setSettling] = useState(false);
  const [settleDate, setSettleDate] = useState("");
  const [settleResult, setSettleResult] = useState("");

  const [inputModal, setInputModal] = useState<{
    recordId: number;
    type: "claiming" | "claimed";
  } | null>(null);
  const [inputValue, setInputValue] = useState("");

  const fetchRecords = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filter) params.set("payment_status", filter);
      const qs = params.toString();
      const data = await clientFetch(`/ledger${qs ? `?${qs}` : ""}`, token);
      setRecords(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [token, filter]);

  useEffect(() => {
    fetchRecords();
  }, [fetchRecords]);

  const handleSettle = async () => {
    if (!token) return;
    setSettling(true);
    setSettleResult("");
    try {
      const body: any = {};
      if (settleDate) body.target_date = settleDate;
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

  const handleSelfPayCollect = async (id: number) => {
    if (!token) return;
    try {
      await clientFetch(`/ledger/${id}/payment`, token, {
        method: "PUT",
        body: JSON.stringify({ payment_status: "paid" }),
      });
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

  if (!token) return <p>Loading...</p>;

  const totalAmount = records.reduce((s, r) => s + r.amount, 0);
  const totalTherapist = records.reduce((s, r) => s + r.therapist_share, 0);
  const totalClinic = records.reduce((s, r) => s + r.clinic_share, 0);

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">諮商流水帳</h1>
        <div className="flex items-center gap-2">
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
              <input
                type="date"
                value={settleDate}
                onChange={(e) => setSettleDate(e.target.value)}
                className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
                placeholder="日結日期"
              />
              <button
                onClick={handleSettle}
                disabled={settling}
                className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
              >
                {settling ? "日結中..." : "執行日結"}
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
              <th className="px-4 py-3">單號</th>
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
                    {r.funding_source === "institution" ? "機構" : "自費"}
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
                    {r.claim_number && (
                      <div>請款: {r.claim_number}</div>
                    )}
                    {r.receipt_number && (
                      <div>收據: {r.receipt_number}</div>
                    )}
                    {!r.claim_number && !r.receipt_number && "-"}
                  </td>
                  <td className="px-4 py-3">
                    {!r.locked_at && userRole !== "therapist" && (
                      <div className="flex gap-2">
                        {/* 自費: unpaid → paid */}
                        {r.funding_source !== "institution" &&
                          r.payment_status === "unpaid" && (
                            <button
                              onClick={() => handleSelfPayCollect(r.id)}
                              className="text-xs text-green-600 hover:underline"
                            >
                              收款
                            </button>
                          )}
                        {/* 機構: unpaid → claiming (輸入請款單號) */}
                        {r.funding_source === "institution" &&
                          r.payment_status === "unpaid" && (
                            <button
                              onClick={() => {
                                setInputModal({ recordId: r.id, type: "claiming" });
                                setInputValue("");
                              }}
                              className="text-xs text-blue-600 hover:underline"
                            >
                              請款
                            </button>
                          )}
                        {/* 機構: claiming → claimed (輸入到款收據) */}
                        {r.funding_source === "institution" &&
                          r.payment_status === "claiming" && (
                            <button
                              onClick={() => {
                                setInputModal({ recordId: r.id, type: "claimed" });
                                setInputValue("");
                              }}
                              className="text-xs text-green-600 hover:underline"
                            >
                              到款
                            </button>
                          )}
                        <button
                          onClick={() => handleLock(r.id)}
                          className="text-xs text-gray-500 hover:underline"
                        >
                          鎖定
                        </button>
                      </div>
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
              placeholder={
                inputModal.type === "claiming"
                  ? "請輸入請款單號..."
                  : "請輸入到款收據或單號..."
              }
              className="mb-4 w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-primary-500 focus:outline-none"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter") handleInputSubmit();
              }}
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setInputModal(null);
                  setInputValue("");
                }}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
              >
                取消
              </button>
              <button
                onClick={handleInputSubmit}
                disabled={!inputValue.trim()}
                className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
              >
                確認
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
