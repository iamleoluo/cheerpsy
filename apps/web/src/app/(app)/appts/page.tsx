"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

interface Appointment {
  id: number;
  appointment_number: string;
  case_name: string | null;
  is_couple?: boolean;
  couple_name?: string | null;
  therapist_name: string | null;
  room_name: string | null;
  session_type: string;
  start_time: string | null;
  end_time: string | null;
  amount: number;
  funding_source: string;
  plan_name: string | null;
  status: string;
  check_in_status: "pending" | "arrived" | "no_show";
}

const sessionTypeLabel: Record<string, string> = { in_person: "現場", online: "視訊", outdoor: "外展" };
const statusLabel: Record<string, string> = { booked: "已預約", executed: "已執行", cancelled: "已取消" };
const checkInLabel: Record<string, { label: string; cls: string }> = {
  pending: { label: "待報到", cls: "bg-surface-3 text-ink-3" },
  arrived: { label: "已到", cls: "bg-st-done-bg text-st-done" },
  no_show: { label: "未到", cls: "bg-st-danger-bg text-st-danger" },
};

function toLocalDateString(d: Date): string {
  const y = d.getFullYear();
  const m = (d.getMonth() + 1).toString().padStart(2, "0");
  const day = d.getDate().toString().padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function AppointmentsListPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;

  const today = new Date();
  const weekAhead = new Date();
  weekAhead.setDate(weekAhead.getDate() + 7);

  const [dateFrom, setDateFrom] = useState(toLocalDateString(today));
  const [dateTo, setDateTo] = useState(toLocalDateString(weekAhead));
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [keyword, setKeyword] = useState("");
  const [appts, setAppts] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const fetchAppts = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const start = new Date(dateFrom + "T00:00:00");
      const end = new Date(dateTo + "T23:59:59");
      const qs = new URLSearchParams({ start: start.toISOString(), end: end.toISOString() });
      if (statusFilter) qs.set("status", statusFilter);
      const data = await clientFetch(`/appointments?${qs.toString()}`, token);
      setAppts(data);
      setPage(1);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token, dateFrom, dateTo, statusFilter]);

  useEffect(() => {
    fetchAppts();
  }, [fetchAppts]);

  const filtered = appts.filter((a) => {
    if (typeFilter && a.session_type !== typeFilter) return false;
    if (keyword) {
      const kw = keyword.toLowerCase();
      const name = (a.is_couple ? a.couple_name : a.case_name) ?? "";
      if (!name.toLowerCase().includes(kw) && !a.therapist_name?.toLowerCase().includes(kw)) return false;
    }
    return true;
  });

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paged = filtered.slice((page - 1) * pageSize, page * pageSize);

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">預約總表</h1>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="text-xs text-ink-3">區間</span>
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="rounded-lg border border-line px-2 py-1.5 text-sm" />
        <span className="text-xs text-ink-3">～</span>
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="rounded-lg border border-line px-2 py-1.5 text-sm" />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="rounded-lg border border-line px-2 py-1.5 text-sm">
          <option value="">全部狀態</option>
          <option value="booked">已預約</option>
          <option value="executed">已執行</option>
          <option value="cancelled">已取消</option>
        </select>
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="rounded-lg border border-line px-2 py-1.5 text-sm">
          <option value="">全部類型</option>
          <option value="in_person">現場</option>
          <option value="online">視訊</option>
          <option value="outdoor">外展</option>
        </select>
        <input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="搜尋個案／心理師" className="rounded-lg border border-line px-2 py-1.5 text-sm" />
        {loading && <span className="text-xs text-ink-3">載入中...</span>}
      </div>

      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-xs text-ink-3">
            <tr>
              <th className="border-b border-line px-3 py-2 text-left">編號</th>
              <th className="border-b border-line px-3 py-2 text-left">日期</th>
              <th className="border-b border-line px-3 py-2 text-left">時間</th>
              <th className="border-b border-line px-3 py-2 text-left">個案</th>
              <th className="border-b border-line px-3 py-2 text-left">心理師</th>
              <th className="border-b border-line px-3 py-2 text-left">診間</th>
              <th className="border-b border-line px-3 py-2 text-left">類型</th>
              <th className="border-b border-line px-3 py-2 text-left">方案</th>
              <th className="border-b border-line px-3 py-2 text-right">金額</th>
              <th className="border-b border-line px-3 py-2 text-left">狀態</th>
              <th className="border-b border-line px-3 py-2 text-left">報到</th>
            </tr>
          </thead>
          <tbody>
            {paged.length === 0 && (
              <tr><td colSpan={11} className="px-3 py-10 text-center text-sm text-ink-3">沒有符合條件的預約 · 調整日期區間或篩選條件</td></tr>
            )}
            {paged.map((a) => {
              const ci = checkInLabel[a.check_in_status];
              return (
                <tr key={a.id} className="hover:bg-surface-2">
                  <td className="border-b border-line px-3 py-2 font-mono text-xs">{a.appointment_number}</td>
                  <td className="border-b border-line px-3 py-2">{a.start_time?.slice(0, 10)}</td>
                  <td className="border-b border-line px-3 py-2">{a.start_time?.slice(11, 16)}–{a.end_time?.slice(11, 16)}</td>
                  <td className="border-b border-line px-3 py-2">{a.is_couple ? `👫 ${a.couple_name}` : a.case_name}</td>
                  <td className="border-b border-line px-3 py-2">{a.therapist_name}</td>
                  <td className="border-b border-line px-3 py-2">{a.room_name ?? "—"}</td>
                  <td className="border-b border-line px-3 py-2">{sessionTypeLabel[a.session_type] ?? a.session_type}</td>
                  <td className="border-b border-line px-3 py-2">{a.plan_name ?? (a.funding_source === "institution" ? "機構" : "自費")}</td>
                  <td className="border-b border-line px-3 py-2 text-right">${a.amount.toLocaleString()}</td>
                  <td className="border-b border-line px-3 py-2">{statusLabel[a.status] ?? a.status}</td>
                  <td className="border-b border-line px-3 py-2">
                    <span className={`rounded px-1.5 py-0.5 text-xs ${ci.cls}`}>{ci.label}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {pageCount > 1 && (
        <div className="mt-3 flex items-center justify-center gap-2 text-sm">
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg border border-line px-3 py-1 disabled:opacity-40">上一頁</button>
          <span className="text-ink-3">{page} / {pageCount}</span>
          <button disabled={page >= pageCount} onClick={() => setPage((p) => p + 1)} className="rounded-lg border border-line px-3 py-1 disabled:opacity-40">下一頁</button>
        </div>
      )}
    </div>
  );
}
