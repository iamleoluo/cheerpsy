"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

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

const statusLabels: Record<string, string> = { pending: "待發放", paid: "已發放" };
const statusColors: Record<string, string> = {
  pending: "bg-amber-100 text-amber-700",
  paid: "bg-green-100 text-green-700",
};
const sessionTypeLabels: Record<string, string> = { in_person: "現場", online: "線上", home_visit: "到宅" };

export default function PayoutsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const userRole = (session?.user as any)?.role;

  const now = new Date();
  const [filterMonth, setFilterMonth] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`);
  const [payouts, setPayouts] = useState<Payout[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [genMonth, setGenMonth] = useState(filterMonth);
  const [detailModal, setDetailModal] = useState<{ payoutId: number; name: string } | null>(null);
  const [details, setDetails] = useState<PayoutSession[]>([]);

  const fetchPayouts = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const params = filterMonth ? `?payout_month=${filterMonth}` : "";
      const data = await clientFetch(`/payouts${params}`, token);
      setPayouts(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [token, filterMonth]);

  useEffect(() => {
    fetchPayouts();
  }, [fetchPayouts]);

  const handleGenerate = async () => {
    if (!token || !genMonth) return;
    setGenerating(true);
    try {
      const result = await clientFetch("/payouts/generate", token, {
        method: "POST",
        body: JSON.stringify({ payout_month: genMonth }),
      });
      alert(`${result.month} 酬勞已產生，共 ${result.payouts_created} 位心理師`);
      setFilterMonth(genMonth);
      fetchPayouts();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setGenerating(false);
    }
  };

  const handlePay = async (id: number) => {
    if (!token || !confirm("確認已發放此酬勞？")) return;
    try {
      await clientFetch(`/payouts/${id}/pay`, token, { method: "PUT" });
      fetchPayouts();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const showDetails = async (payoutId: number, name: string) => {
    if (!token) return;
    setDetailModal({ payoutId, name });
    try {
      const data = await clientFetch(`/payouts/${payoutId}/details`, token);
      setDetails(data.sessions);
    } catch {
      setDetails([]);
    }
  };

  if (!token) return <p>Loading...</p>;

  const totalAmount = payouts.reduce((s, p) => s + p.total_amount, 0);
  const pendingCount = payouts.filter((p) => p.status === "pending").length;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">心理師酬勞月結</h1>
          {payouts.length > 0 && (
            <p className="mt-1 text-sm text-gray-500">
              合計 ${totalAmount.toLocaleString()} · {pendingCount > 0 ? `${pendingCount} 筆待發放` : "全部已發放"}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <input
            type="month"
            value={filterMonth}
            onChange={(e) => setFilterMonth(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
          {userRole === "admin" && (
            <>
              <input
                type="month"
                value={genMonth}
                onChange={(e) => setGenMonth(e.target.value)}
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
              <button
                onClick={handleGenerate}
                disabled={generating}
                className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
              >
                {generating ? "產生中..." : "產生酬勞"}
              </button>
            </>
          )}
        </div>
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
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-400">載入中...</td></tr>
            ) : payouts.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-400">尚無酬勞資料（管理員可產生月結酬勞）</td></tr>
            ) : (
              payouts.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">{p.payout_month}</td>
                  <td className="px-4 py-3 font-medium">{p.therapist_name ?? "-"}</td>
                  <td className="px-4 py-3 text-right">{p.session_count}</td>
                  <td className="px-4 py-3 text-right font-medium">${p.total_amount.toLocaleString()}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[p.status] ?? "bg-gray-100"}`}>
                      {statusLabels[p.status] ?? p.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {p.paid_at ? new Date(p.paid_at).toLocaleDateString("zh-TW") : "-"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button onClick={() => showDetails(p.id, p.therapist_name ?? "")} className="text-xs text-primary-600 hover:underline">
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
              <button onClick={() => setDetailModal(null)} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">關閉</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
