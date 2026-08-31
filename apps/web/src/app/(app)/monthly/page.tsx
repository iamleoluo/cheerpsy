"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import { money } from "@/lib/format";

interface Day {
  day: string;
  closed: boolean;
  cash_total: number;
  transfer_total: number;
  unpaid_total: number;
  record_count: number;
}
interface Income {
  therapist_id: number;
  therapist_name: string | null;
  counseling_income: number;
  lecture_fee: number;
  supervision_income: number;
  venue_deduction: number;
  total: number;
}
interface Summary {
  month: string;
  status: string;
  closed_days: number;
  total_days: number;
  cash_total: number;
  transfer_total: number;
  unpaid_total: number;
  payout_date: string | null;
  days: Day[];
  therapist_income: Income[];
  pending_reviews: number;
}
interface Review {
  id: number;
  day: string;
  reason: string;
  unlocked_by: string | null;
  unlocked_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
}

function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function MonthlyPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [month, setMonth] = useState(thisMonth());
  const [data, setData] = useState<Summary | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [tab, setTab] = useState<"daily" | "income" | "reviews">("daily");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [s, r] = await Promise.all([
        clientFetch(`/finance/monthly?month=${month}`, token),
        clientFetch(`/finance/monthly/${month}/reviews`, token).catch(() => []),
      ]);
      setData(s);
      setReviews(r);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, month]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading || !data) return <p className="p-6 text-gray-400">載入中...</p>;

  const activeDays = data.days.filter((d) => d.record_count > 0 || d.closed);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">月報表</h1>
          <p className="mt-1 text-sm text-gray-500">
            資料來源只有一個：日報表按下「完成當日對帳」後寫入的每日紀錄。
          </p>
        </div>
        <input
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
        />
      </div>

      <div className="mb-4 rounded-lg border border-green-200 bg-green-50 px-4 py-2.5 text-sm text-green-900">
        📗 {data.month} 月報表 — 只收已完成對帳的每日紀錄 · 本月已對帳{" "}
        <b>{data.closed_days} / {data.total_days}</b> 日
        {data.closed_days < data.total_days && (
          <span className="ml-2 text-amber-700">
            （未對帳的日以「待對帳」標示，金額不計入合計，也不進心理師收入）
          </span>
        )}
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          ["現金合計", money(data.cash_total)],
          ["匯款合計", money(data.transfer_total)],
          ["當日應收未收", money(data.unpaid_total)],
          ["薪資發放日", data.payout_date ?? "—"],
        ].map(([l, v]) => (
          <div key={l} className="rounded-lg border border-gray-200 bg-white px-3 py-2">
            <div className="text-xs text-gray-500">{l}</div>
            <div className="text-lg font-semibold">{v}</div>
          </div>
        ))}
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      <div className="mb-4 flex gap-2 border-b border-gray-200">
        {([
          ["daily", "每日對帳彙總"],
          ["income", "心理師當月收入"],
          ["reviews", `主管覆核紀錄${data.pending_reviews ? ` (${data.pending_reviews})` : ""}`],
        ] as const).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`px-4 py-2 text-sm ${
              tab === k
                ? "border-b-2 border-primary-600 font-medium text-primary-700"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "daily" && (
        <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs text-gray-500">
              <tr>
                <th className="px-3 py-3">日期</th>
                <th className="px-3 py-3">狀態</th>
                <th className="px-3 py-3 text-right">筆數</th>
                <th className="px-3 py-3 text-right">現金</th>
                <th className="px-3 py-3 text-right">匯款</th>
                <th className="px-3 py-3 text-right">未收</th>
              </tr>
            </thead>
            <tbody>
              {activeDays.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-10 text-center text-gray-400">本月尚無紀錄</td></tr>
              )}
              {activeDays.map((d) => (
                <tr key={d.day} className={`border-b border-gray-100 last:border-0 ${d.closed ? "" : "bg-amber-50"}`}>
                  <td className="px-3 py-2.5">{d.day}</td>
                  <td className="px-3 py-2.5">
                    <span className={`rounded px-1.5 py-0.5 text-xs ${d.closed ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
                      {d.closed ? "已對帳" : "待對帳"}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{d.record_count}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{d.closed ? money(d.cash_total) : "—"}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{d.closed ? money(d.transfer_total) : "—"}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{d.closed ? money(d.unpaid_total) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "income" && (
        <>
          <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
            <table className="w-full text-sm">
              <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs text-gray-500">
                <tr>
                  <th className="px-3 py-3">心理師</th>
                  <th className="px-3 py-3 text-right">諮商收入認列</th>
                  <th className="px-3 py-3 text-right">講師費</th>
                  <th className="px-3 py-3 text-right">督導收入</th>
                  <th className="px-3 py-3 text-right">場地費扣項</th>
                  <th className="px-3 py-3 text-right">認列合計</th>
                </tr>
              </thead>
              <tbody>
                {data.therapist_income.length === 0 && (
                  <tr><td colSpan={6} className="px-4 py-10 text-center text-gray-400">
                    本月尚無已對帳的紀錄
                  </td></tr>
                )}
                {data.therapist_income.map((t) => (
                  <tr key={t.therapist_id} className="border-b border-gray-100 last:border-0">
                    <td className="px-3 py-2.5 font-medium">{t.therapist_name}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{money(t.counseling_income)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-gray-400">{money(t.lecture_fee)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-gray-400">{money(t.supervision_income)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-gray-400">−{money(t.venue_deduction)}</td>
                    <td className="px-3 py-2.5 text-right font-semibold tabular-nums">{money(t.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
            ⚠️ 講師費、督導收入、場地費扣項三欄目前固定為 0。這三項的認列規則
            （講師費是否入慈恩帳戶／是否收行政服務費、督導 A/B 模式與私人租借場地費的定義）
            在需求文件中尚未定義，見 open_questions.md Q16、Q17。
          </p>
        </>
      )}

      {tab === "reviews" && (
        <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs text-gray-500">
              <tr>
                <th className="px-3 py-3">對帳日</th>
                <th className="px-3 py-3">解鎖原因</th>
                <th className="px-3 py-3">解鎖者</th>
                <th className="px-3 py-3">解鎖時間</th>
                <th className="px-3 py-3">覆核狀態</th>
              </tr>
            </thead>
            <tbody>
              {reviews.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-10 text-center text-gray-400">
                  本月沒有解鎖修改的紀錄
                </td></tr>
              )}
              {reviews.map((r) => (
                <tr key={r.id} className="border-b border-gray-100 last:border-0">
                  <td className="px-3 py-2.5">{r.day}</td>
                  <td className="px-3 py-2.5">{r.reason}</td>
                  <td className="px-3 py-2.5">{r.unlocked_by ?? "—"}</td>
                  <td className="px-3 py-2.5 text-xs text-gray-500">{r.unlocked_at?.slice(0, 16).replace("T", " ")}</td>
                  <td className="px-3 py-2.5">
                    {r.reviewed_at ? (
                      <span className="text-xs text-green-700">已覆核 · {r.reviewed_by}</span>
                    ) : (
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">待覆核</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-4 text-xs text-gray-400">
        補收款會自動回寫月報表該日（該列標小字「MM/DD 補收 $X」），不視為修改、不需解鎖、不列入主管覆核。
      </p>
    </div>
  );
}
