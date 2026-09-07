"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

/**
 * 應收帳冊（v1）。「未收」分頁接的是 GET /ledger/self-pay-unpaid——這支
 * 09 §1.4a 裁示後已改成統一查詢（不分 funding_source，只認自付額收了
 * 沒），機構案的個案自付額會跟自費案一起出現在這裡。
 *
 * 「機構應收」分頁依 09 §3.7 的裁示應該改成核銷案的唯讀檢視，但核銷案
 * 前端（合約面板）還沒建，這裡先留提示，等 09 §6 的機構那條線做完再補。
 */

interface Row {
  id: number;
  appointment_id: number | null;
  session_date: string;
  case_name: string | null;
  therapist_name: string | null;
  amount: number;
  case_payable: number | null;
  funding_source: string | null;
  plan_name: string | null;
  institution_name: string | null;
  billing_cycle: string | null;
}

function daysAgo(dateStr: string): number {
  const d = new Date(dateStr);
  const now = new Date();
  return Math.floor((now.getTime() - d.getTime()) / (1000 * 60 * 60 * 24));
}

export default function ARPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [tab, setTab] = useState<"unpaid" | "monthly" | "institution">("unpaid");
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    clientFetch("/ledger/self-pay-unpaid", token)
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [token]);

  const payable = (r: Row) => r.case_payable ?? r.amount;
  const unpaidGeneral = rows.filter((r) => r.billing_cycle !== "monthly");
  const unpaidMonthly = rows.filter((r) => r.billing_cycle === "monthly");
  const shown = tab === "unpaid" ? unpaidGeneral : unpaidMonthly;
  const total = shown.reduce((s, r) => s + payable(r), 0);

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">應收帳冊</h1>

      <div className="mb-4 flex gap-1 border-b border-gray-200">
        {([
          ["unpaid", "未收"],
          ["monthly", "月結"],
          ["institution", "機構應收"],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium ${tab === key ? "border-b-2 border-primary-600 text-primary-600" : "text-gray-500 hover:text-gray-700"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {loading && <p className="text-sm text-gray-400">載入中...</p>}

      {tab === "institution" ? (
        <div className="rounded-xl border border-dashed border-gray-200 py-12 text-center text-sm text-gray-400">
          機構應收將改為核銷案的唯讀檢視，待「機構合約」合約面板建置完成後接上（V2升級計畫 09 §3.7）。
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500">
                <tr>
                  <th className="border-b border-gray-200 px-3 py-2 text-left">預約日期</th>
                  <th className="border-b border-gray-200 px-3 py-2 text-left">姓名</th>
                  <th className="border-b border-gray-200 px-3 py-2 text-left">心理師</th>
                  <th className="border-b border-gray-200 px-3 py-2 text-left">方案</th>
                  <th className="border-b border-gray-200 px-3 py-2 text-right">應收金額</th>
                  <th className="border-b border-gray-200 px-3 py-2 text-left">逾期天數</th>
                </tr>
              </thead>
              <tbody>
                {shown.length === 0 && (
                  <tr><td colSpan={6} className="px-3 py-10 text-center text-sm text-gray-400">沒有符合條件的紀錄</td></tr>
                )}
                {shown.map((r) => {
                  const days = daysAgo(r.session_date);
                  return (
                    <tr key={r.id} className="hover:bg-gray-50">
                      <td className="border-b border-gray-100 px-3 py-2">{r.session_date}</td>
                      <td className="border-b border-gray-100 px-3 py-2 font-medium">{r.case_name ?? "—"}</td>
                      <td className="border-b border-gray-100 px-3 py-2">{r.therapist_name}</td>
                      <td className="border-b border-gray-100 px-3 py-2">{r.plan_name ?? (r.funding_source === "institution" ? r.institution_name ?? "機構" : "自費")}</td>
                      <td className="border-b border-gray-100 px-3 py-2 text-right font-medium">${payable(r).toLocaleString()}</td>
                      <td className="border-b border-gray-100 px-3 py-2">
                        <span className={`rounded px-1.5 py-0.5 text-xs ${days > 7 ? "bg-rose-100 text-rose-600" : days >= 1 ? "bg-amber-100 text-amber-700" : "bg-gray-100 text-gray-500"}`}>
                          {days > 0 ? `${days} 天` : "當日"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="mt-3 text-sm text-gray-500">合計未收 <b className="text-rose-600">${total.toLocaleString()}</b> ｜ {shown.length} 筆</div>
        </>
      )}
    </div>
  );
}
