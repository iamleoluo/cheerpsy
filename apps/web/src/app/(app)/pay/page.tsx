"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

/**
 * 我的酬勞（v1）。GET /ledger?month= 與 GET /payouts 在 role=therapist 時
 * 後端已自動限定為本人資料。
 *
 * V2升級計畫 09 §4.3 已裁示這頁最終要依 compensation_mode（抽成/回饋/
 * 心理師定價）分區呈現，但 SessionRecordResponse 目前還沒把這幾個欄位
 * 攤平出來（models 上有，schema 沒露），且此頁本來就排在 09 §6 順序
 * 最後一項（要等優待與 compensation_mode 都定案）。這裡先做「大概版」：
 * 用既有欄位（therapist_share／commission_rate_used／outcall_bonus）
 * 呈現抽成制（目前絕大多數場次走這條），分區呈現留待欄位補齊後再做。
 */

interface LedgerRecord {
  id: number;
  session_date: string;
  case_name: string | null;
  session_type: string;
  amount: number;
  therapist_share: number;
  commission_rate_used: number | null;
  outcall_bonus: number;
  payment_status: string;
  institution_name: string | null;
}

interface Payout {
  id: number;
  payout_month: string;
  total_amount: number;
  session_count: number;
  status: string;
  paid_at: string | null;
}

const sessionTypeLabel: Record<string, string> = { in_person: "現場", online: "視訊", outdoor: "外展" };

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function PayPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [month, setMonth] = useState(currentMonth());
  const [records, setRecords] = useState<LedgerRecord[]>([]);
  const [payouts, setPayouts] = useState<Payout[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    Promise.all([
      clientFetch(`/ledger?month=${month}`, token).catch(() => []),
      clientFetch(`/payouts?payout_month=${month}`, token).catch(() => []),
    ])
      .then(([r, p]) => { setRecords(r); setPayouts(p); })
      .finally(() => setLoading(false));
  }, [token, month]);

  const totalSessions = records.length;
  const totalEarned = records.reduce((s, r) => s + r.therapist_share + r.outcall_bonus, 0);
  const currentPayout = payouts[0];

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">我的酬勞</h1>

      <div className="mb-6 grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-xs text-gray-400">本月場次</div>
          <div className="mt-1 text-xl font-bold">{totalSessions}</div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-xs text-gray-400">預估酬勞</div>
          <div className="mt-1 text-xl font-bold text-primary-600">${totalEarned.toLocaleString()}</div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-xs text-gray-400">結算狀態</div>
          <div className="mt-1 text-sm font-medium">
            {currentPayout ? (currentPayout.status === "paid" ? `✓ 已發放（${currentPayout.paid_at?.slice(0, 10)}）` : "待結算") : "尚未結算"}
          </div>
        </div>
      </div>

      <div className="mb-4 flex items-center gap-2">
        <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm" />
        {loading && <span className="text-xs text-gray-400">載入中...</span>}
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500">
            <tr>
              <th className="border-b border-gray-200 px-3 py-2 text-left">日期</th>
              <th className="border-b border-gray-200 px-3 py-2 text-left">個案</th>
              <th className="border-b border-gray-200 px-3 py-2 text-left">類型</th>
              <th className="border-b border-gray-200 px-3 py-2 text-right">場次金額</th>
              <th className="border-b border-gray-200 px-3 py-2 text-right">抽成率</th>
              <th className="border-b border-gray-200 px-3 py-2 text-right">外出加給</th>
              <th className="border-b border-gray-200 px-3 py-2 text-right">我的酬勞</th>
              <th className="border-b border-gray-200 px-3 py-2 text-left">狀態</th>
            </tr>
          </thead>
          <tbody>
            {records.length === 0 && (
              <tr><td colSpan={8} className="px-3 py-10 text-center text-sm text-gray-400">本月尚無紀錄</td></tr>
            )}
            {records.map((r) => (
              <tr key={r.id} className="hover:bg-gray-50">
                <td className="border-b border-gray-100 px-3 py-2">{r.session_date}</td>
                <td className="border-b border-gray-100 px-3 py-2">{r.case_name ?? "—"}</td>
                <td className="border-b border-gray-100 px-3 py-2">{sessionTypeLabel[r.session_type] ?? r.session_type}{r.institution_name ? ` · ${r.institution_name}` : ""}</td>
                <td className="border-b border-gray-100 px-3 py-2 text-right">${r.amount.toLocaleString()}</td>
                <td className="border-b border-gray-100 px-3 py-2 text-right">{r.commission_rate_used != null ? `${Math.round(r.commission_rate_used * 100)}%` : "—"}</td>
                <td className="border-b border-gray-100 px-3 py-2 text-right">{r.outcall_bonus > 0 ? `+$${r.outcall_bonus.toLocaleString()}` : "—"}</td>
                <td className="border-b border-gray-100 px-3 py-2 text-right font-medium">${(r.therapist_share + r.outcall_bonus).toLocaleString()}</td>
                <td className="border-b border-gray-100 px-3 py-2">
                  <span className={`rounded px-1.5 py-0.5 text-xs ${currentPayout?.status === "paid" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                    {currentPayout?.status === "paid" ? "已發放" : "待結算"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
