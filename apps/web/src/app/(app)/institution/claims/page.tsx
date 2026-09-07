"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { clientFetch } from "@/lib/client-api";

/**
 * 核銷案總表：跨機構的唯讀查詢（09 §3.7 已裁示）。回答「這個月所有待
 * 送出的有哪些」；建立／收納／送出／入帳／作廢等操作一律在合約專頁
 * （/institution/{id}）執行，這裡不做任何寫入，避免同一筆錢有兩個地方
 * 可以改、狀態打架。
 */

interface ClaimCaseRow {
  id: number; claim_no: string; claim_group_key: string; status: string;
  record_count: number; applied_amount: number | null; net_received: number | null;
}

const statusLabel: Record<string, string> = { collecting: "收集中", submitted: "已送出", closed: "已結案", void: "已作廢" };
const statusTagClass: Record<string, string> = {
  collecting: "bg-amber-100 text-amber-700", submitted: "bg-sky-100 text-sky-700",
  closed: "bg-emerald-100 text-emerald-700", void: "bg-gray-100 text-gray-400",
};

export default function ClaimCasesOverviewPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [rows, setRows] = useState<ClaimCaseRow[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    const qs = statusFilter ? `?status=${statusFilter}` : "";
    clientFetch(`/institution/claim-cases${qs}`, token)
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [token, statusFilter]);

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <h1 className="mb-1 text-2xl font-bold">核銷案總表</h1>
      <p className="mb-6 text-sm text-gray-400">唯讀查詢；建立／收納／送出／入帳／作廢請至各合約專頁的「核銷」分頁操作</p>

      <div className="mb-4 flex items-center gap-2">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm">
          <option value="">全部狀態</option>
          <option value="collecting">收集中</option>
          <option value="submitted">已送出</option>
          <option value="closed">已結案</option>
          <option value="void">已作廢</option>
        </select>
        {loading && <span className="text-xs text-gray-400">載入中...</span>}
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500">
            <tr>
              <th className="border-b border-gray-200 px-3 py-2 text-left">核銷案編號</th>
              <th className="border-b border-gray-200 px-3 py-2 text-left">核銷群組</th>
              <th className="border-b border-gray-200 px-3 py-2 text-right">場次</th>
              <th className="border-b border-gray-200 px-3 py-2 text-right">申請金額</th>
              <th className="border-b border-gray-200 px-3 py-2 text-right">實收金額</th>
              <th className="border-b border-gray-200 px-3 py-2 text-left">狀態</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-10 text-center text-sm text-gray-400">沒有符合條件的核銷案</td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="hover:bg-gray-50">
                <td className="border-b border-gray-100 px-3 py-2 font-mono">{r.claim_no}</td>
                <td className="border-b border-gray-100 px-3 py-2">{r.claim_group_key}</td>
                <td className="border-b border-gray-100 px-3 py-2 text-right">{r.record_count}</td>
                <td className="border-b border-gray-100 px-3 py-2 text-right">{r.applied_amount != null ? `$${r.applied_amount.toLocaleString()}` : "—"}</td>
                <td className="border-b border-gray-100 px-3 py-2 text-right">{r.net_received != null ? `$${r.net_received.toLocaleString()}` : "—"}</td>
                <td className="border-b border-gray-100 px-3 py-2"><span className={`rounded px-1.5 py-0.5 text-xs ${statusTagClass[r.status] ?? ""}`}>{statusLabel[r.status] ?? r.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-gray-400">
        要處理某一筆核銷案？至 <Link href="/institution" className="text-primary-500 hover:underline">機構合約</Link> 找到對應合約，在其專頁的「核銷」分頁操作。
      </p>
    </div>
  );
}
