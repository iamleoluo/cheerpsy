"use client";

import { useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

/**
 * 日報表 / 對帳（v1，已裁示先做「大概版」，見 V2升級計畫 09 §4.1）。
 *
 * 用既有 GET /ledger?month= 抓當月全部紀錄、前端篩今天——這支端點目前
 * 沒有單日篩選參數，先這樣接，不是效能最佳解但先求資料正確。
 *
 * 09 §1.4a 已裁示：這頁的「應收」清單必須不分 funding_source，機構案的
 * 個案自付額（case_payable）跟自費案一樣，是每天要看到的東西——不能只顯示
 * 純自費案。這裡就是那個統一查詢的第一版（前端先做，後端目前用 ledger 既有
 * 資料湊，還沒有專門的統一端點，見 09 §5 高優先項）。
 */

interface LedgerRow {
  id: number;
  session_date: string;
  case_name: string | null;
  therapist_name: string | null;
  session_type: string;
  amount: number;
  funding_source: string | null;
  plan_name: string | null;
  case_payable: number | null;
  institution_payable: number | null;
  payment_status: string;
  payment_method: string | null;
  copay_collected_at: string | null;
  copay_payment_method: string | null;
  receipt_no: string | null;
}

const sessionTypeLabel: Record<string, string> = { in_person: "現場", online: "視訊", outdoor: "外展" };

function todayStr(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function currentMonth(): string {
  return todayStr().slice(0, 7);
}

/** 這筆「個案自付款」是否已收：機構案看 copay_collected_at，純自費案看 payment_status。 */
function isCollected(r: LedgerRow): boolean {
  if (r.funding_source === "institution" || r.case_payable != null) {
    return r.copay_collected_at != null || (r.case_payable ?? r.amount) <= 0;
  }
  return r.payment_status === "paid" || r.payment_status === "claimed";
}

export default function DailyPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [date, setDate] = useState(todayStr());
  const [view, setView] = useState<"unpaid" | "paid">("unpaid");
  const [records, setRecords] = useState<LedgerRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    clientFetch(`/ledger?month=${date.slice(0, 7)}`, token)
      .then((rows: LedgerRow[]) => setRecords(rows.filter((r) => r.session_date === date)))
      .catch(() => setRecords([]))
      .finally(() => setLoading(false));
  }, [token, date]);

  const payable = (r: LedgerRow) => r.case_payable ?? r.amount;
  const collected = useMemo(() => records.filter(isCollected), [records]);
  const uncollected = useMemo(() => records.filter((r) => !isCollected(r)), [records]);

  const cashTotal = collected.filter((r) => (r.copay_payment_method ?? r.payment_method) === "cash").reduce((s, r) => s + payable(r), 0);
  const transferTotal = collected.filter((r) => (r.copay_payment_method ?? r.payment_method) === "transfer").reduce((s, r) => s + payable(r), 0);
  const unpaidTotal = uncollected.reduce((s, r) => s + payable(r), 0);
  const dueTotal = records.reduce((s, r) => s + payable(r), 0);

  const shown = view === "unpaid" ? uncollected : collected;

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">日報表 / 對帳</h1>

      <div className="mb-4 flex items-center gap-2">
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm" />
        {loading && <span className="text-xs text-gray-400">載入中...</span>}
      </div>

      <div className="mb-6 grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-xs text-gray-400">當日應收</div>
          <div className="mt-1 text-xl font-bold">${dueTotal.toLocaleString()}</div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-xs text-gray-400">已收 — 現金</div>
          <div className="mt-1 text-xl font-bold text-emerald-600">${cashTotal.toLocaleString()}</div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-xs text-gray-400">已收 — 匯款</div>
          <div className="mt-1 text-xl font-bold text-emerald-600">${transferTotal.toLocaleString()}</div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-xs text-gray-400">未收</div>
          <div className="mt-1 text-xl font-bold text-rose-600">${unpaidTotal.toLocaleString()}</div>
        </div>
      </div>

      <div className="mb-3 flex gap-1 border-b border-gray-200">
        {(["unpaid", "paid"] as const).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={`px-4 py-2 text-sm font-medium ${view === v ? "border-b-2 border-primary-600 text-primary-600" : "text-gray-500 hover:text-gray-700"}`}
          >
            {v === "unpaid" ? `未收（${uncollected.length}）` : `已收（${collected.length}）`}
          </button>
        ))}
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500">
            <tr>
              <th className="border-b border-gray-200 px-3 py-2 text-left">收據編號</th>
              <th className="border-b border-gray-200 px-3 py-2 text-left">姓名</th>
              <th className="border-b border-gray-200 px-3 py-2 text-left">心理師</th>
              <th className="border-b border-gray-200 px-3 py-2 text-left">類型</th>
              <th className="border-b border-gray-200 px-3 py-2 text-left">方案</th>
              <th className="border-b border-gray-200 px-3 py-2 text-right">個案自付額</th>
              <th className="border-b border-gray-200 px-3 py-2 text-right">機構請款額</th>
              <th className="border-b border-gray-200 px-3 py-2 text-left">結帳方式</th>
            </tr>
          </thead>
          <tbody>
            {shown.length === 0 && (
              <tr><td colSpan={8} className="px-3 py-10 text-center text-sm text-gray-400">沒有符合條件的紀錄</td></tr>
            )}
            {shown.map((r) => (
              <tr key={r.id} className="hover:bg-gray-50">
                <td className="border-b border-gray-100 px-3 py-2 font-mono text-xs">{r.receipt_no ?? "—"}</td>
                <td className="border-b border-gray-100 px-3 py-2 font-medium">{r.case_name ?? "—"}</td>
                <td className="border-b border-gray-100 px-3 py-2">{r.therapist_name}</td>
                <td className="border-b border-gray-100 px-3 py-2">{sessionTypeLabel[r.session_type] ?? r.session_type}</td>
                <td className="border-b border-gray-100 px-3 py-2">{r.plan_name ?? (r.funding_source === "institution" ? "機構" : "自費")}</td>
                <td className="border-b border-gray-100 px-3 py-2 text-right">${payable(r).toLocaleString()}</td>
                <td className="border-b border-gray-100 px-3 py-2 text-right text-gray-400">{r.institution_payable != null ? `$${r.institution_payable.toLocaleString()}` : "—"}</td>
                <td className="border-b border-gray-100 px-3 py-2">
                  {r.copay_payment_method === "cash" || r.payment_method === "cash" ? "現金" : (r.copay_payment_method === "transfer" || r.payment_method === "transfer") ? "匯款" : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
