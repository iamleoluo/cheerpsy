"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

/**
 * 我的酬勞。GET /ledger?month= 與 GET /payouts 在 role=therapist 時後端已
 * 自動限定為本人資料。
 *
 * 依 09 §4.3 依 compensation_mode 分三區呈現：
 *   抽成（commission）  金額 × 抽成率 ＋ 外出保底
 *   回饋（kickback）    鐘點費由心理師自己向機構請領，診所抽的那份要**回繳**
 *                       ——所以這一區的金額是**負的**，是從當月酬勞扣掉的
 *   無勞務（none）      借場地那類，不計酬
 *
 * therapist_share 由後端的 payout_line_amount() 算好（帳冊、月結算、這頁
 * 共用同一支函式），所以這裡直接加總即可，不會出現「畫面算的跟實際發的
 * 不一樣」。
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
  compensation_mode: string | null;
  plan_name: string | null;
}

const MODE_META: Record<string, { label: string; hint: string; tone: string }> = {
  commission: { label: "抽成", hint: "場次金額 × 抽成率 ＋ 外出保底", tone: "text-primary-600" },
  kickback: { label: "回饋制", hint: "鐘點費由你直接向機構請領，此為應回繳診所的金額", tone: "text-rose-600" },
  none: { label: "無心理師勞務", hint: "借場地等，不計酬", tone: "text-gray-400" },
};

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
  // therapist_share 已由後端算好（含回饋制的負數與作廢排除），直接加總
  const totalEarned = records.reduce((s, r) => s + r.therapist_share, 0);
  const currentPayout = payouts[0];

  const byMode = records.reduce<Record<string, { count: number; sum: number }>>((acc, r) => {
    const key = r.compensation_mode ?? "commission";
    (acc[key] ??= { count: 0, sum: 0 });
    acc[key].count += 1;
    acc[key].sum += r.therapist_share;
    return acc;
  }, {});

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

      {Object.keys(byMode).length > 1 && (
        <div className="mb-6 space-y-2">
          <p className="text-xs text-gray-400">依薪酬模式分區（09 §4.3）</p>
          {Object.entries(byMode).map(([mode, v]) => {
            const meta = MODE_META[mode] ?? MODE_META.commission;
            return (
              <div key={mode} className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-2.5">
                <div>
                  <span className="text-sm font-medium">{meta.label}</span>
                  <span className="ml-2 text-xs text-gray-400">{v.count} 場 · {meta.hint}</span>
                </div>
                <div className={`text-sm font-bold ${v.sum < 0 ? "text-rose-600" : meta.tone}`}>
                  {v.sum < 0 ? "−" : ""}${Math.abs(v.sum).toLocaleString()}
                </div>
              </div>
            );
          })}
        </div>
      )}

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
              <th className="border-b border-gray-200 px-3 py-2 text-left">薪酬模式</th>
              <th className="border-b border-gray-200 px-3 py-2 text-right">場次金額</th>
              <th className="border-b border-gray-200 px-3 py-2 text-right">抽成率</th>
              <th className="border-b border-gray-200 px-3 py-2 text-right">外出加給</th>
              <th className="border-b border-gray-200 px-3 py-2 text-right">我的酬勞</th>
              <th className="border-b border-gray-200 px-3 py-2 text-left">狀態</th>
            </tr>
          </thead>
          <tbody>
            {records.length === 0 && (
              <tr><td colSpan={9} className="px-3 py-10 text-center text-sm text-gray-400">本月尚無紀錄</td></tr>
            )}
            {records.map((r) => (
              <tr key={r.id} className="hover:bg-gray-50">
                <td className="border-b border-gray-100 px-3 py-2">{r.session_date}</td>
                <td className="border-b border-gray-100 px-3 py-2">{r.case_name ?? "—"}</td>
                <td className="border-b border-gray-100 px-3 py-2">{sessionTypeLabel[r.session_type] ?? r.session_type}{r.institution_name ? ` · ${r.institution_name}` : ""}</td>
                <td className="border-b border-gray-100 px-3 py-2 text-xs text-gray-500">
                  {(MODE_META[r.compensation_mode ?? "commission"] ?? MODE_META.commission).label}
                  {r.plan_name ? <span className="ml-1 text-gray-400">{r.plan_name}</span> : null}
                </td>
                <td className="border-b border-gray-100 px-3 py-2 text-right">${r.amount.toLocaleString()}</td>
                <td className="border-b border-gray-100 px-3 py-2 text-right">{r.commission_rate_used != null ? `${Math.round(r.commission_rate_used * 100)}%` : "—"}</td>
                <td className="border-b border-gray-100 px-3 py-2 text-right">{r.outcall_bonus > 0 ? `+$${r.outcall_bonus.toLocaleString()}` : "—"}</td>
                <td className={`border-b border-gray-100 px-3 py-2 text-right font-medium ${r.therapist_share < 0 ? "text-rose-600" : ""}`}>
                  {r.therapist_share < 0 ? "−" : ""}${Math.abs(r.therapist_share).toLocaleString()}
                </td>
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
