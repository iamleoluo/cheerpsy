"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import { BillingDetailModal, BillingLine } from "@/components/billing-summary";
import {
  DAY_END_MIN,
  DAY_START_MIN,
  NO_SHOW_TYPES,
  SESSION_TYPE,
  SLOT_MIN,
  hhmm,
  minutesOfDay,
  shiftDate,
  slotLabels,
  todayISO,
} from "@/lib/format";

interface Room {
  id: number;
  name: string;
  room_code: string;
  room_type: string;
  is_active?: boolean;
}

interface OccSlot {
  room_id: number;
  start: string;
  end: string;
  occupied: true;
}

interface Appt {
  id: number;
  case_id: number;
  case_name: string | null;
  therapist_name: string | null;
  room_id: number | null;
  session_type: string;
  start_time: string | null;
  end_time: string | null;
  status: string;
  checkin_status: string;
  is_intake: boolean;
  funding_source?: string | null;
  quota_used?: number | null;
  quota_total?: number | null;
  quota_remaining?: number | null;
  quota_is_last_session?: boolean;
  plan_name?: string | null;
  rate_item_label?: string | null;
  amount?: number;
  self_pay_amount?: number | null;
  institution_name?: string | null;
  institution_subsidy?: number | null;
  transport_fee?: number;
  transport_fee_label?: string | null;
  no_show_type?: string | null;
}

const BADGE: Record<string, { label: string; cls: string }> = {
  pending: { label: "待報到", cls: "bg-gray-200 text-gray-600" },
  arrived: { label: "已到", cls: "bg-green-100 text-green-700" },
  absent: { label: "未到", cls: "bg-red-100 text-red-700" },
};

export default function CalendarPage() {
  const { data: session } = useSession();
  const router = useRouter();
  const token = (session?.user as any)?.accessToken;
  const canBook = (session?.user as any)?.role !== "therapist";
  const [day, setDay] = useState(todayISO());
  const [rooms, setRooms] = useState<Room[]>([]);
  const [appts, setAppts] = useState<Appt[]>([]);
  const [occ, setOcc] = useState<OccSlot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [absentFor, setAbsentFor] = useState<Appt | null>(null);
  const [detailFor, setDetailFor] = useState<Appt | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const range = `start=${day}T00:00:00%2B08:00&end=${shiftDate(day, 1)}T00:00:00%2B08:00`;
      const [rs, as, oc] = await Promise.all([
        clientFetch("/rooms?include_inactive=true", token),
        clientFetch(`/appointments?${range}`, token),
        // 所有角色都用這支畫「已佔用」：只有時段，沒有個人資料
        clientFetch(`/rooms/occupancy?${range}`, token),
      ]);
      setRooms(rs);
      setAppts(as);
      setOcc(oc);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, day]);

  useEffect(() => {
    load();
  }, [load]);

  // 只有 booked／executed 佔用診間；取消與未到已釋出，格子可再約
  const occupying = (a: Appt) => a.status === "booked" || a.status === "executed";
  const inRoom = useMemo(() => appts.filter((a) => a.room_id && occupying(a)), [appts]);
  const released = useMemo(() => appts.filter((a) => a.room_id && !occupying(a)), [appts]);
  const offsite = useMemo(() => appts.filter((a) => !a.room_id), [appts]);
  const labels = slotLabels();
  // 停用的診間：當天沒有任何預約或佔用就不畫欄位；有歷史資料才照常顯示
  const shownRooms = useMemo(
    () =>
      rooms.filter(
        (r) => r.is_active !== false || appts.some((a) => a.room_id === r.id) || occ.some((o) => o.room_id === r.id)
      ),
    [rooms, appts, occ]
  );

  const stats = useMemo(() => {
    const active = appts.filter((a) => a.status !== "cancelled");
    const arrived = active.filter((a) => a.checkin_status === "arrived");
    const absent = active.filter((a) => a.checkin_status === "absent");
    return {
      due: active.length,
      arrived: arrived.length,
      absent: absent.length,
      pending: active.length - arrived.length - absent.length,
    };
  }, [appts]);

  async function arrive(a: Appt) {
    try {
      await clientFetch(`/appointments/${a.id}/arrive`, token, { method: "PUT" });
      load();
    } catch (e: any) {
      alert(e.message);
    }
  }

  if (loading) return <p className="p-6 text-gray-400">載入中...</p>;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">診間日曆 — 櫃檯主控台</h1>
          <p className="mt-1 text-sm text-gray-500">報到、未到、初診與診間佔用一頁看完</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setDay(shiftDate(day, -1))} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">
            ◀ 前一天
          </button>
          <input
            type="date"
            value={day}
            onChange={(e) => setDay(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
          />
          <button onClick={() => setDay(shiftDate(day, 1))} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">
            後一天 ▶
          </button>
          <button onClick={() => setDay(todayISO())} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">
            今天
          </button>
        </div>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          ["應到", stats.due, ""],
          ["已報到", stats.arrived, "text-green-600"],
          ["未到", stats.absent, "text-red-600"],
          ["待報到", stats.pending, "text-amber-600"],
        ].map(([label, val, cls]) => (
          <div key={label as string} className="rounded-lg border border-gray-200 bg-white px-3 py-2">
            <div className="text-xs text-gray-500">{label}</div>
            <div className={`text-lg font-semibold ${cls}`}>{val}</div>
          </div>
        ))}
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="w-full border-collapse text-xs">
          <thead className="sticky top-0 bg-gray-50">
            <tr>
              <th className="w-14 border-b border-r border-gray-200 px-1 py-2 text-gray-500">時間</th>
              {shownRooms.map((r) => (
                <th key={r.id} className="border-b border-r border-gray-200 px-1 py-2 last:border-r-0">
                  <div className="font-medium">{r.room_code}{r.is_active === false ? "（停用）" : ""}</div>
                  <div className="text-[10px] font-normal text-gray-400">
                    {r.room_type === "play" ? "兒童遊戲室" : "晤談"}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {labels.map((label, i) => {
              const slotStart = DAY_START_MIN + i * SLOT_MIN;
              return (
                <tr key={label}>
                  <td className="border-b border-r border-gray-100 px-1 py-1 text-right align-top text-[10px] text-gray-400">
                    {slotStart % 60 === 0 ? label : ""}
                  </td>
                  {shownRooms.map((room) => {
                    const a = inRoom.find(
                      (x) =>
                        x.room_id === room.id &&
                        x.start_time &&
                        minutesOfDay(x.start_time) <= slotStart &&
                        (x.end_time ? minutesOfDay(x.end_time) : slotStart + SLOT_MIN) > slotStart
                    );
                    if (!a) {
                      // 別人的場次／活動：只顯示「已佔用」，不可點擊、不進詳情
                      const o = occ.find(
                        (x) =>
                          x.room_id === room.id &&
                          minutesOfDay(x.start) <= slotStart &&
                          minutesOfDay(x.end) > slotStart
                      );
                      if (o) {
                        return (
                          <td
                            key={room.id}
                            aria-disabled="true"
                            className="cursor-default select-none border-b border-r border-gray-100 bg-gray-100 px-1 text-center align-top text-[10px] text-gray-400 last:border-r-0"
                          >
                            {minutesOfDay(o.start) === slotStart ? "已佔用" : ""}
                          </td>
                        );
                      }
                      const hh = `${String(Math.floor(slotStart / 60)).padStart(2, "0")}:${String(slotStart % 60).padStart(2, "0")}`;
                      return (
                        <td
                          key={room.id}
                          title={canBook ? `預約 ${room.room_code} ${hh}` : undefined}
                          onClick={
                            canBook
                              ? () => router.push(`/booking?room=${room.id}&date=${day}&start=${hh}`)
                              : undefined
                          }
                          className={`h-8 border-b border-r border-gray-100 last:border-r-0 ${
                            canBook ? "cursor-pointer hover:bg-primary-50" : ""
                          }`}
                        />
                      );
                    }
                    const isStart = a.start_time && minutesOfDay(a.start_time) === slotStart;
                    if (!isStart) {
                      return (
                        <td
                          key={room.id}
                          className={`border-r border-gray-100 last:border-r-0 ${cellBg(a)}`}
                        />
                      );
                    }
                    return (
                      <td
                        key={room.id}
                        className={`border-b border-r border-gray-100 p-1 align-top last:border-r-0 ${cellBg(a)}`}
                      >
                        <ApptCell
                          a={a}
                          onArrive={() => arrive(a)}
                          onAbsent={() => setAbsentFor(a)}
                          onDetail={() => setDetailFor(a)}
                        />
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {released.length > 0 && (
        <div className="mt-4 rounded-xl border border-gray-200 bg-white p-4">
          <h2 className="mb-2 text-sm font-medium">已釋出的場次（取消／未到）</h2>
          <ul className="space-y-1 text-xs text-gray-500">
            {released.map((a) => (
              <li key={a.id}>
                {hhmm(a.start_time)}–{hhmm(a.end_time)} · {rooms.find((r) => r.id === a.room_id)?.room_code} · {a.case_name} ·{" "}
                {a.status === "cancelled" ? "已取消" : "未到"}，該時段可再約
              </li>
            ))}
          </ul>
        </div>
      )}

      {offsite.length > 0 && (
        <div className="mt-4 rounded-xl border border-gray-200 bg-white p-4">
          <h2 className="mb-2 text-sm font-medium">視訊 / 外展（不佔診間）</h2>
          <div className="grid gap-2 md:grid-cols-3">
            {offsite.map((a) => (
              <div key={a.id} className={`rounded-lg border p-2 ${cellBg(a)}`}>
                <ApptCell
                  a={a}
                  onArrive={() => arrive(a)}
                  onAbsent={() => setAbsentFor(a)}
                  onDetail={() => setDetailFor(a)}
                />
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-gray-400">
            這兩類個案不會到櫃檯報到，狀態不會自動變更；請在事後由行政標記已到或未到。
          </p>
        </div>
      )}

      {detailFor && <BillingDetailModal appt={detailFor} onClose={() => setDetailFor(null)} />}

      {absentFor && (
        <AbsentModal
          token={token}
          appt={absentFor}
          onClose={() => setAbsentFor(null)}
          onDone={() => {
            setAbsentFor(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function cellBg(a: Appt): string {
  if (a.status === "cancelled") return "bg-gray-100 opacity-50";
  if (a.checkin_status === "absent") return "bg-red-50";
  if (a.checkin_status === "arrived") return "bg-gray-100";
  if (a.quota_is_last_session) return "bg-violet-50 ring-1 ring-inset ring-red-400"; // 機構最後一次，下次轉自費
  if (a.is_intake) return "bg-amber-50 ring-1 ring-inset ring-amber-300";
  return a.funding_source === "institution" ? "bg-violet-50" : "bg-blue-50";
}

function ApptCell({
  a,
  onArrive,
  onAbsent,
  onDetail,
}: {
  a: Appt;
  onArrive: () => void;
  onAbsent: () => void;
  onDetail: () => void;
}) {
  const badge = BADGE[a.checkin_status] ?? BADGE.pending;
  const offsite = !a.room_id;
  return (
    <div>
      <div className="flex items-start justify-between gap-1">
        <span className="truncate font-medium">{a.case_name}</span>
        <span className={`shrink-0 rounded px-1 text-[9px] ${badge.cls}`}>{badge.label}</span>
      </div>
      <div className="truncate text-[10px] text-gray-500">
        {hhmm(a.start_time)}–{hhmm(a.end_time)} · {a.therapist_name}
      </div>
      <div className="truncate text-[10px] text-gray-500">
        {SESSION_TYPE[a.session_type]}
      </div>
      {a.is_intake && <div className="text-[10px] font-medium text-amber-700">⭐ 媒合初診</div>}
      {a.status !== "cancelled" && (
        <button type="button" onClick={onDetail} title="金額與經費來源" className="block w-full text-left text-[10px] hover:underline">
          <BillingLine a={a} className="line-clamp-2" />
        </button>
      )}

      {a.status !== "cancelled" && a.checkin_status === "pending" && !offsite && (
        <div className="mt-1 flex gap-1">
          <button onClick={onArrive} className="flex-1 rounded border border-gray-400 bg-white px-1 py-0.5 text-[10px] hover:bg-gray-50">
            {a.is_intake ? "初診有到" : "已到"}
          </button>
          <button onClick={onAbsent} className="flex-1 rounded border border-gray-400 bg-white px-1 py-0.5 text-[10px] hover:bg-gray-50">
            未到
          </button>
        </div>
      )}
      {a.checkin_status === "pending" && offsite && (
        <div className="mt-1 text-[10px] text-gray-400">心理師端確認</div>
      )}
    </div>
  );
}

function AbsentModal({
  token,
  appt,
  onClose,
  onDone,
}: {
  token: string;
  appt: Appt;
  onClose: () => void;
  onDone: () => void;
}) {
  const [type, setType] = useState("late_cancel");
  const [err, setErr] = useState<string | null>(null);
  async function go() {
    try {
      await clientFetch(`/appointments/${appt.id}/absent`, token, {
        method: "PUT",
        body: JSON.stringify({ no_show_type: type }),
      });
      onDone();
    } catch (e: any) {
      setErr(e.message);
    }
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-1 text-lg font-bold">未到原因 — {appt.case_name}</h2>
        <p className="mb-4 text-sm text-gray-500">
          只記錄未到類型；該診間時段會立即釋出，可再預約。
        </p>
        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}
        <div className="space-y-2">
          {NO_SHOW_TYPES.map(([k, label]) => (
            <label key={k} className="flex items-center gap-2 text-sm">
              <input type="radio" checked={type === k} onChange={() => setType(k)} />
              {label}
            </label>
          ))}
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">
            取消
          </button>
          <button onClick={go} className="rounded-lg bg-gray-700 px-4 py-2 text-sm font-medium text-white">
            確認未到
          </button>
        </div>
      </div>
    </div>
  );
}
