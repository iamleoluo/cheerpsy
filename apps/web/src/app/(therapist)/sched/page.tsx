"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import { SESSION_TYPE, hhmm, money, shiftDate, todayISO } from "@/lib/format";

interface Appt {
  id: number;
  case_name: string | null;
  room_name: string | null;
  room_id: number | null;
  session_type: string;
  start_time: string | null;
  end_time: string | null;
  amount: number;
  funding_source: string;
  status: string;
  checkin_status: string;
  quota_is_last_session: boolean;
  quota_used: number | null;
  quota_total: number | null;
}

const WEEKDAYS = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"];

function mondayOf(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  const dow = (d.getDay() + 6) % 7; // 週一 = 0
  return shiftDate(iso, -dow);
}

export default function SchedPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [weekStart, setWeekStart] = useState(mondayOf(todayISO()));
  const [appts, setAppts] = useState<Appt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cancelFor, setCancelFor] = useState<Appt | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      setAppts(
        await clientFetch(
          `/appointments?start=${weekStart}T00:00:00%2B08:00&end=${shiftDate(weekStart, 7)}T00:00:00%2B08:00`,
          token
        )
      );
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, weekStart]);

  useEffect(() => {
    load();
  }, [load]);

  const days = useMemo(
    () => Array.from({ length: 7 }, (_, i) => shiftDate(weekStart, i)),
    [weekStart]
  );

  const next = useMemo(() => {
    const now = Date.now();
    return appts
      .filter((a) => a.status === "booked" && a.start_time && new Date(a.start_time).getTime() > now)
      .sort((a, b) => (a.start_time! < b.start_time! ? -1 : 1))[0];
  }, [appts]);

  const stats = useMemo(() => {
    const active = appts.filter((a) => a.status !== "cancelled");
    return {
      total: active.length,
      inPerson: active.filter((a) => a.session_type === "in_person").length,
      offsite: active.filter((a) => a.session_type !== "in_person").length,
      done: active.filter((a) => a.status === "executed").length,
    };
  }, [appts]);

  if (loading) return <p className="p-6 text-gray-400">載入中...</p>;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">我的班表</h1>
          <p className="mt-1 text-sm text-gray-500">
            個人週行事曆 —— 我什麼時候要看誰。空間調度是行政的事，查空間請到「預約作業」。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setWeekStart(shiftDate(weekStart, -7))} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">◀ 上週</button>
          <button onClick={() => setWeekStart(mondayOf(todayISO()))} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">本週</button>
          <button onClick={() => setWeekStart(shiftDate(weekStart, 7))} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">下週 ▶</button>
        </div>
      </div>

      {next && (
        <div className="mb-4 rounded-lg border border-primary-200 bg-primary-50 px-4 py-3 text-sm">
          <span className="text-primary-700">下一場 </span>
          <b>{next.case_name}</b>
          <span className="ml-2 text-gray-600">
            {next.start_time?.slice(5, 10)} {hhmm(next.start_time)}–{hhmm(next.end_time)} ·{" "}
            {next.room_name ?? SESSION_TYPE[next.session_type]}
          </span>
        </div>
      )}

      {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      <div className="grid gap-2 md:grid-cols-7">
        {days.map((d, i) => {
          const list = appts
            .filter((a) => a.start_time?.slice(0, 10) === d && a.status !== "cancelled")
            .sort((a, b) => (a.start_time! < b.start_time! ? -1 : 1));
          const isToday = d === todayISO();
          return (
            <div key={d} className={`rounded-xl border bg-white p-2 ${isToday ? "border-primary-400" : "border-gray-200"}`}>
              <div className="mb-2 text-center">
                <div className="text-xs font-medium text-gray-600">{WEEKDAYS[i]}</div>
                <div className={`text-xs ${isToday ? "font-semibold text-primary-700" : "text-gray-400"}`}>
                  {d.slice(5)}
                </div>
              </div>
              {list.length === 0 && <div className="py-4 text-center text-[11px] text-gray-300">—</div>}
              <div className="space-y-1.5">
                {list.map((a) => {
                  const offsite = !a.room_id;
                  const done = a.status === "executed";
                  return (
                    <div
                      key={a.id}
                      className={`rounded-lg p-1.5 text-[11px] ${
                        done ? "bg-green-50" : offsite ? "bg-violet-50" : "bg-blue-50"
                      } ${a.quota_is_last_session ? "ring-1 ring-red-400" : ""}`}
                    >
                      <div className="font-medium">{hhmm(a.start_time)}–{hhmm(a.end_time)}</div>
                      <div className="truncate">{a.case_name}</div>
                      <div className="truncate text-gray-500">
                        {a.room_name ?? SESSION_TYPE[a.session_type]}
                      </div>
                      <div className="truncate text-gray-500">
                        {a.funding_source === "institution"
                          ? `機構 ${a.quota_used ?? "?"}/${a.quota_total ?? "?"}`
                          : "自費"}
                      </div>
                      {a.quota_is_last_session && (
                        <div className="text-red-600">最後一次 · 下次轉自費</div>
                      )}
                      {done && <div className="text-green-700">已完成</div>}
                      {!done && offsite && (
                        <button
                          onClick={() => setCancelFor(a)}
                          className="mt-1 w-full rounded border border-gray-300 bg-white px-1 py-0.5 text-[10px] hover:bg-gray-50"
                        >
                          為此次預約請假
                        </button>
                      )}
                      {!done && !offsite && (
                        <div className="mt-1 text-[10px] text-gray-400">櫃檯報到</div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 flex flex-wrap gap-4 rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm">
        <span>本週場次 <b>{stats.total}</b></span>
        <span className="text-gray-500">現場 {stats.inPerson}</span>
        <span className="text-gray-500">視訊／外展 {stats.offsite}</span>
        <span className="text-green-700">已完成 {stats.done}</span>
      </div>

      <p className="mt-3 text-xs text-gray-400">
        視訊／外展的個案不會到櫃檯報到，超過起始時間後系統自動視為已到；個案沒來時才需要按「請假」。
        現場個案由櫃檯報到，此處不顯示操作按鈕。
      </p>

      {cancelFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <h2 className="mb-2 text-lg font-bold">為此次預約請假</h2>
            <p className="mb-4 text-sm text-gray-500">
              {cancelFor.case_name} · {cancelFor.start_time?.slice(5, 10)}{" "}
              {hhmm(cancelFor.start_time)}–{hhmm(cancelFor.end_time)}
              <br />
              取消後不產生應收，機構額度會釋回為可用。
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setCancelFor(null)} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">返回</button>
              <button
                onClick={async () => {
                  try {
                    await clientFetch(`/appointments/${cancelFor.id}/cancel`, token, { method: "PUT" });
                    setCancelFor(null);
                    load();
                  } catch (e: any) {
                    alert(e.message);
                  }
                }}
                className="rounded-lg bg-gray-700 px-4 py-2 text-sm font-medium text-white"
              >
                確認請假
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
