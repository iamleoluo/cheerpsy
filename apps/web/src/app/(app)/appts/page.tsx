"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import { NO_SHOW_TYPES, SESSION_TYPE, hhmm, money, shiftDate, todayISO } from "@/lib/format";

interface Appt {
  id: number;
  case_id: number;
  case_name: string | null;
  therapist_name: string | null;
  room_name: string | null;
  room_id: number | null;
  session_type: string;
  start_time: string | null;
  end_time: string | null;
  amount: number;
  funding_source: string;
  status: string;
  checkin_status: string;
  no_show_fee: number;
  is_intake: boolean;
  quota_used: number | null;
  quota_total: number | null;
}

const STATUS: Record<string, { label: string; cls: string }> = {
  booked: { label: "已預約", cls: "bg-blue-100 text-blue-700" },
  executed: { label: "已執行", cls: "bg-green-100 text-green-700" },
  cancelled: { label: "已取消", cls: "bg-gray-200 text-gray-600" },
  no_show: { label: "未到", cls: "bg-red-100 text-red-700" },
};

export default function ApptsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [start, setStart] = useState(todayISO());
  const [end, setEnd] = useState(shiftDate(todayISO(), 3));
  const [rows, setRows] = useState<Appt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [fStatus, setFStatus] = useState("");
  const [fType, setFType] = useState("");
  const [absentFor, setAbsentFor] = useState<Appt | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      setRows(
        await clientFetch(
          `/appointments?start=${start}T00:00:00%2B08:00&end=${shiftDate(end, 1)}T00:00:00%2B08:00`,
          token
        )
      );
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, start, end]);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(
    () =>
      rows.filter((r) => {
        if (fStatus && r.status !== fStatus) return false;
        if (fType && r.session_type !== fType) return false;
        if (q) {
          const n = q.toLowerCase();
          if (
            !(r.case_name ?? "").toLowerCase().includes(n) &&
            !(r.therapist_name ?? "").toLowerCase().includes(n)
          )
            return false;
        }
        return true;
      }),
    [rows, q, fStatus, fType]
  );

  async function arrive(a: Appt) {
    try {
      await clientFetch(`/appointments/${a.id}/arrive`, token, { method: "PUT" });
      load();
    } catch (e: any) {
      alert(e.message);
    }
  }

  function exportCsv() {
    const head = ["心理師", "個案", "空間", "類型", "日期", "時段", "金額", "狀態", "報到"];
    const lines = filtered.map((r) => [
      r.therapist_name ?? "",
      r.case_name ?? "",
      r.room_name ?? "",
      SESSION_TYPE[r.session_type] ?? r.session_type,
      r.start_time?.slice(0, 10) ?? "",
      `${hhmm(r.start_time)}-${hhmm(r.end_time)}`,
      String(r.amount),
      STATUS[r.status]?.label ?? r.status,
      r.checkin_status,
    ]);
    const csv = [head, ...lines].map((c) => c.map((x) => `"${x}"`).join(",")).join("\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `預約總表_${start}_${end}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">預約總表</h1>
          <p className="mt-1 text-sm text-gray-500">
            跨日期區間的查詢與稽核總表。每日現場作業請用診間日曆——兩處是同一份資料。
          </p>
        </div>
        <button onClick={exportCsv} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">
          匯出 CSV
        </button>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="rounded-lg border border-gray-300 px-2 py-1.5" />
        <span className="text-gray-400">~</span>
        <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="rounded-lg border border-gray-300 px-2 py-1.5" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜尋 個案／心理師" className="w-52 rounded-lg border border-gray-300 px-3 py-1.5" />
        <select value={fStatus} onChange={(e) => setFStatus(e.target.value)} className="rounded-lg border border-gray-300 px-2 py-1.5">
          <option value="">全部狀態</option>
          {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <select value={fType} onChange={(e) => setFType(e.target.value)} className="rounded-lg border border-gray-300 px-2 py-1.5">
          <option value="">全部類型</option>
          {Object.entries(SESSION_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <span className="ml-auto text-gray-500">{filtered.length} 筆</span>
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
      {loading && <p className="text-gray-400">載入中...</p>}

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="w-full text-sm">
          <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs text-gray-500">
            <tr>
              <th className="px-3 py-3">預約日期</th>
              <th className="px-3 py-3">姓名</th>
              <th className="px-3 py-3">心理師</th>
              <th className="px-3 py-3">時間</th>
              <th className="px-3 py-3">類型</th>
              <th className="px-3 py-3">診間</th>
              <th className="px-3 py-3">方案</th>
              <th className="px-3 py-3 text-right">金額</th>
              <th className="px-3 py-3">狀態</th>
              <th className="px-3 py-3">行政確認</th>
            </tr>
          </thead>
          <tbody>
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={10} className="px-4 py-10 text-center text-gray-400">此區間沒有符合的預約</td></tr>
            )}
            {filtered.map((r) => {
              const st = STATUS[r.status] ?? { label: r.status, cls: "bg-gray-100" };
              const offsite = !r.room_id;
              return (
                <tr key={r.id} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                  <td className="px-3 py-2.5">{r.start_time?.slice(0, 10)}</td>
                  <td className="px-3 py-2.5 font-medium">
                    {r.is_intake && <span className="mr-1 text-amber-600" title="媒合初診">⭐</span>}
                    {r.case_name}
                  </td>
                  <td className="px-3 py-2.5">{r.therapist_name}</td>
                  <td className="px-3 py-2.5 tabular-nums">{hhmm(r.start_time)}–{hhmm(r.end_time)}</td>
                  <td className="px-3 py-2.5">{SESSION_TYPE[r.session_type] ?? r.session_type}</td>
                  <td className="px-3 py-2.5">{r.room_name ?? "—"}</td>
                  <td className="px-3 py-2.5 text-xs">
                    {r.funding_source === "institution"
                      ? `機構 ${r.quota_used ?? "?"}/${r.quota_total ?? "?"}`
                      : "自費"}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {money(r.amount)}
                    {r.no_show_fee > 0 && (
                      <span className="block text-[10px] text-red-600">失約費 {money(r.no_show_fee)}</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    <span className={`rounded px-1.5 py-0.5 text-xs ${st.cls}`}>{st.label}</span>
                  </td>
                  <td className="px-3 py-2.5">
                    {offsite ? (
                      <span className="text-xs text-gray-400">心理師端確認</span>
                    ) : r.checkin_status === "pending" && r.status === "booked" ? (
                      <div className="flex gap-2 text-xs">
                        <button onClick={() => arrive(r)} className="text-primary-600 hover:underline">
                          {r.is_intake ? "初診有到" : "已到"}
                        </button>
                        <button onClick={() => setAbsentFor(r)} className="text-red-500 hover:underline">未到</button>
                      </div>
                    ) : (
                      <span className="text-xs text-gray-500">
                        {r.checkin_status === "arrived" ? "已到" : r.checkin_status === "absent" ? "未到" : "—"}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {absentFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-bold">未到原因 — {absentFor.case_name}</h2>
            <div className="space-y-2">
              {NO_SHOW_TYPES.map(([k, label, fee]) => (
                <button
                  key={k}
                  onClick={async () => {
                    try {
                      await clientFetch(`/appointments/${absentFor.id}/absent`, token, {
                        method: "PUT",
                        body: JSON.stringify({ no_show_type: k }),
                      });
                      setAbsentFor(null);
                      load();
                    } catch (e: any) {
                      alert(e.message);
                    }
                  }}
                  className="flex w-full items-center justify-between rounded-lg border border-gray-300 px-3 py-2 text-sm hover:bg-gray-50"
                >
                  <span>{label}</span>
                  <span className="tabular-nums text-gray-500">失約費 {money(fee)}</span>
                </button>
              ))}
            </div>
            <div className="mt-6 flex justify-end">
              <button onClick={() => setAbsentFor(null)} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">取消</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
