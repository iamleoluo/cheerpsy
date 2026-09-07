"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

/**
 * 心理師端「我的今日」。GET /appointments 在 role=therapist 時後端已自動
 * 過濾成本人場次（見 routers/appointments.py list_appointments），這裡
 * 不用再帶 therapist_id。
 *
 * 權限矩陣（08 §5.3）：視訊／外展由心理師本人按已到；現場一律行政報到，
 * 這裡對現場場次只顯示狀態、不給按鈕。
 */

interface Appointment {
  id: number;
  appointment_number: string;
  case_name: string | null;
  is_couple?: boolean;
  couple_name?: string | null;
  room_name: string | null;
  session_type: string;
  start_time: string | null;
  end_time: string | null;
  status: string;
  check_in_status: "pending" | "arrived" | "no_show";
}

const sessionTypeLabel: Record<string, string> = { in_person: "現場", online: "視訊", outdoor: "外展" };

function toLocalDateString(d: Date): string {
  const y = d.getFullYear();
  const m = (d.getMonth() + 1).toString().padStart(2, "0");
  const day = d.getDate().toString().padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function TodayPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [appts, setAppts] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchToday = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const start = new Date();
      start.setHours(0, 0, 0, 0);
      const end = new Date(start);
      end.setDate(end.getDate() + 1);
      const data = await clientFetch(
        `/appointments?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`,
        token,
      );
      setAppts(data.sort((a: Appointment, b: Appointment) => (a.start_time ?? "").localeCompare(b.start_time ?? "")));
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchToday();
  }, [fetchToday]);

  async function checkIn(id: number, status: "arrived" | "no_show") {
    setBusyId(id);
    setError(null);
    try {
      await clientFetch(`/appointments/${id}/check-in`, token, {
        method: "PUT",
        body: JSON.stringify({ status }),
      });
      fetchToday();
    } catch (e: any) {
      setError(e.message ?? "操作失敗");
    } finally {
      setBusyId(null);
    }
  }

  if (!token) return <p>Loading...</p>;

  const todayLabel = new Date().toLocaleDateString("zh-TW", { year: "numeric", month: "long", day: "numeric", weekday: "short" });

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-1 text-2xl font-bold">我的今日</h1>
      <p className="mb-6 text-sm text-gray-400">{todayLabel}</p>

      {error && <div className="mb-4 rounded-lg bg-rose-50 px-4 py-2 text-sm text-rose-600">{error}</div>}

      {loading && appts.length === 0 && <p className="text-sm text-gray-400">載入中...</p>}
      {!loading && appts.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-200 py-12 text-center text-sm text-gray-400">今天沒有排定的場次</div>
      )}

      <div className="space-y-2">
        {appts.map((a) => {
          const selfCheckIn = a.session_type !== "in_person";
          return (
            <div key={a.id} className={`flex items-center justify-between rounded-xl border px-4 py-3 ${a.status === "cancelled" ? "border-gray-100 bg-gray-50 opacity-50" : "border-gray-200 bg-white"}`}>
              <div className="flex items-center gap-4">
                <div className="w-20 font-mono text-sm text-gray-600">{a.start_time?.slice(11, 16)}–{a.end_time?.slice(11, 16)}</div>
                <div>
                  <div className="text-sm font-medium">{a.is_couple ? `👫 ${a.couple_name}` : a.case_name}</div>
                  <div className="text-xs text-gray-400">{sessionTypeLabel[a.session_type] ?? a.session_type}{a.room_name ? ` · ${a.room_name}` : ""}</div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {a.check_in_status === "arrived" && <span className="rounded bg-emerald-100 px-2 py-1 text-xs text-emerald-700">✓ 已到</span>}
                {a.check_in_status === "no_show" && <span className="rounded bg-gray-100 px-2 py-1 text-xs text-gray-500">未到</span>}
                {a.check_in_status === "pending" && a.status !== "cancelled" && (
                  selfCheckIn ? (
                    <>
                      <button disabled={busyId === a.id} onClick={() => checkIn(a.id, "arrived")} className="rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-700 disabled:opacity-50">已到</button>
                      <button disabled={busyId === a.id} onClick={() => checkIn(a.id, "no_show")} className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50">未到</button>
                    </>
                  ) : (
                    <span className="rounded bg-gray-100 px-2 py-1 text-xs text-gray-400">待行政報到</span>
                  )
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
