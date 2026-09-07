"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

/**
 * 心理師端「我的班表」：週為欄 × 半小時為列的個人行事曆（01 §13）。
 * GET /appointments 在 role=therapist 時已自動過濾為本人場次。
 */

interface Appointment {
  id: number;
  case_name: string | null;
  is_couple?: boolean;
  couple_name?: string | null;
  session_type: string;
  start_time: string | null;
  end_time: string | null;
  status: string;
  check_in_status: string;
}

const SLOT_HOURS = Array.from({ length: 28 }, (_, i) => {
  const totalMin = 8 * 60 + i * 30;
  const h = Math.floor(totalMin / 60).toString().padStart(2, "0");
  const m = (totalMin % 60).toString().padStart(2, "0");
  return `${h}:${m}`;
});
const DOW_ZH = ["日", "一", "二", "三", "四", "五", "六"];
const sessionTypeLabel: Record<string, string> = { in_person: "現場", online: "視訊", outdoor: "外展" };

function mondayOf(d: Date): Date {
  const n = new Date(d);
  const day = (n.getDay() + 6) % 7; // 0=一
  n.setDate(n.getDate() - day);
  n.setHours(0, 0, 0, 0);
  return n;
}

export default function SchedPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [weekStart, setWeekStart] = useState(() => mondayOf(new Date()));
  const [appts, setAppts] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(false);

  const weekDays = useMemo(
    () => Array.from({ length: 7 }, (_, i) => { const d = new Date(weekStart); d.setDate(d.getDate() + i); return d; }),
    [weekStart],
  );

  const fetchWeek = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const end = new Date(weekStart);
      end.setDate(end.getDate() + 7);
      const data = await clientFetch(
        `/appointments?start=${encodeURIComponent(weekStart.toISOString())}&end=${encodeURIComponent(end.toISOString())}`,
        token,
      );
      setAppts(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token, weekStart]);

  useEffect(() => {
    fetchWeek();
  }, [fetchWeek]);

  type Matrix = Record<string, (Appointment | undefined)[]>; // slot -> [7 days]
  const matrix: Matrix = useMemo(() => {
    const m: Matrix = {};
    for (const slot of SLOT_HOURS) m[slot] = Array(7).fill(undefined);
    for (const a of appts) {
      if (a.status === "cancelled" || !a.start_time || !a.end_time) continue;
      const start = new Date(a.start_time);
      const end = new Date(a.end_time);
      const dayIdx = weekDays.findIndex((d) => d.toDateString() === start.toDateString());
      if (dayIdx === -1) continue;
      const cur = new Date(start);
      while (cur < end) {
        const key = `${cur.getHours().toString().padStart(2, "0")}:${cur.getMinutes() < 30 ? "00" : "30"}`;
        if (m[key]) m[key][dayIdx] = a;
        cur.setMinutes(cur.getMinutes() + 30);
      }
    }
    return m;
  }, [appts, weekDays]);

  const prevWeek = () => setWeekStart((d) => { const n = new Date(d); n.setDate(n.getDate() - 7); return n; });
  const nextWeek = () => setWeekStart((d) => { const n = new Date(d); n.setDate(n.getDate() + 7); return n; });
  const goThisWeek = () => setWeekStart(mondayOf(new Date()));

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">我的班表</h1>

      <div className="mb-4 flex items-center gap-2">
        <button onClick={prevWeek} className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm hover:bg-gray-50">← 上週</button>
        <button onClick={goThisWeek} className="rounded-lg border border-primary-300 px-3 py-1.5 text-sm text-primary-600 hover:bg-primary-50">本週</button>
        <button onClick={nextWeek} className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm hover:bg-gray-50">下週 →</button>
        <span className="text-sm font-medium text-gray-700">
          {weekDays[0].toLocaleDateString("zh-TW", { month: "short", day: "numeric" })} – {weekDays[6].toLocaleDateString("zh-TW", { month: "short", day: "numeric" })}
        </span>
        {loading && <span className="text-xs text-gray-400">載入中...</span>}
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="bg-gray-50">
              <th className="w-14 border-b border-r border-gray-200 px-2 py-2 text-left text-gray-500">時段</th>
              {weekDays.map((d, i) => {
                const isToday = d.toDateString() === new Date().toDateString();
                return (
                  <th key={i} className={`min-w-[100px] border-b border-r border-gray-200 px-2 py-2 text-center font-medium ${isToday ? "bg-primary-50" : ""}`}>
                    <div>週{DOW_ZH[d.getDay()]}</div>
                    <div className="text-[10px] font-normal text-gray-400">{d.getMonth() + 1}/{d.getDate()}</div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {SLOT_HOURS.map((slot) => {
              const rowHasAny = matrix[slot]?.some(Boolean);
              return (
                <tr key={slot} className={rowHasAny ? "bg-white" : "bg-gray-50/30"}>
                  <td className="whitespace-nowrap border-b border-r border-gray-200 px-2 py-1 font-mono text-gray-400">{slot}</td>
                  {matrix[slot].map((a, i) => (
                    <td key={i} className={`border-b border-r border-gray-200 px-1 py-1 align-middle ${a ? (a.check_in_status === "arrived" ? "bg-emerald-50 text-emerald-800" : a.check_in_status === "no_show" ? "bg-gray-100 text-gray-400 line-through" : "bg-primary-50 text-primary-700") : ""}`}>
                      {a && (
                        <div className="truncate leading-tight" title={`${sessionTypeLabel[a.session_type]} ${a.start_time?.slice(11, 16)}~${a.end_time?.slice(11, 16)}`}>
                          {a.is_couple ? `👫${a.couple_name?.slice(0, 4)}` : a.case_name?.slice(0, 5) ?? "—"}
                        </div>
                      )}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
