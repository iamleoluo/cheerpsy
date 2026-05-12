"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

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
  locked_at: string | null;
}

const paymentLabels: Record<string, string> = {
  unpaid: "未收款",
  paid: "已收款",
  pending_claim: "待請款",
  claiming: "請款中",
  reconciled: "已核銷",
};

const paymentColors: Record<string, string> = {
  unpaid: "bg-red-100 text-red-700",
  paid: "bg-green-100 text-green-700",
  pending_claim: "bg-yellow-100 text-yellow-700",
  claiming: "bg-blue-100 text-blue-700",
  reconciled: "bg-green-100 text-green-700",
};

const sessionTypeLabels: Record<string, string> = {
  in_person: "現場",
  online: "線上",
  home_visit: "到宅",
};

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

  const handlePayment = async (id: number, newStatus: string) => {
    if (!token) return;
    try {
      await clientFetch(`/ledger/${id}/payment`, token, {
        method: "PUT",
        body: JSON.stringify({ payment_status: newStatus }),
      });
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
        {userRole === "admin" && (
          <div className="flex items-center gap-2">
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
          </div>
        )}
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
          {Object.entries(paymentLabels).map(([k, v]) => (
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
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-gray-400">
                  載入中...
                </td>
              </tr>
            ) : records.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-gray-400">
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
                      {paymentLabels[r.payment_status] ?? r.payment_status}
                    </span>
                    {r.locked_at && (
                      <span className="ml-1 text-xs text-gray-400">🔒</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {!r.locked_at && userRole !== "therapist" && (
                      <div className="flex gap-2">
                        {r.payment_status === "unpaid" && (
                          <button
                            onClick={() => handlePayment(r.id, "paid")}
                            className="text-xs text-green-600 hover:underline"
                          >
                            收款
                          </button>
                        )}
                        {r.payment_status === "pending_claim" && (
                          <button
                            onClick={() => handlePayment(r.id, "claiming")}
                            className="text-xs text-blue-600 hover:underline"
                          >
                            請款
                          </button>
                        )}
                        {r.payment_status === "claiming" && (
                          <button
                            onClick={() => handlePayment(r.id, "reconciled")}
                            className="text-xs text-green-600 hover:underline"
                          >
                            核銷
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
    </div>
  );
}
