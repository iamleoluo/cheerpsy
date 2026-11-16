"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import { useCanEditAmount } from "@/components/amount-field";
import { BillingFields, EMPTY_BILLING, billingBody, billingError, warningsText, type BillingValue } from "@/components/billing-fields";
import { EventsTab } from "@/components/events-tab";
import { SESSION_TYPE, hhmm, shiftDate, todayISO } from "@/lib/format";

interface Case {
  id: number;
  name: string;
  case_number: string | null;
  therapist_id: number;
  funding_source?: string;
}
interface Room {
  id: number;
  name: string;
  room_code: string;
  room_type: string;
}
interface Therapist {
  id: number;
  name: string;
}
interface Appt {
  id: number;
  case_name: string | null;
  therapist_name: string | null;
  room_id: number | null;
  start_time: string | null;
  end_time: string | null;
  status: string;
}
interface OccSlot {
  room_id: number;
  start: string;
  end: string;
  occupied: true;
}

const MINUTES = ["00", "15", "30", "45"];

function addHour(t: string): string {
  const [h, m] = t.split(":").map(Number);
  return `${String((h + 1) % 24).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export default function BookingPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const role = (session?.user as any)?.role;
  const isTherapist = role === "therapist";

  const [tab, setTab] = useState<"single" | "batch" | "week" | "events">("single");
  const [cases, setCases] = useState<Case[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [therapists, setTherapists] = useState<Therapist[]>([]);
  const [weekStart, setWeekStart] = useState(todayISO());
  const [weekAppts, setWeekAppts] = useState<Appt[]>([]);
  const [weekOcc, setWeekOcc] = useState<OccSlot[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  // 單筆表單
  const [caseId, setCaseId] = useState<number | 0>(0);
  const [therapistId, setTherapistId] = useState<number | 0>(0);
  const [roomId, setRoomId] = useState<number | 0>(0);
  const [sessionType, setSessionType] = useState("in_person");
  const [date, setDate] = useState(todayISO());
  const [startTime, setStartTime] = useState("14:00");
  const [endTime, setEndTime] = useState("15:00");
  const [videoLink, setVideoLink] = useState("");
  const [billing, setBilling] = useState<BillingValue>(EMPTY_BILLING);
  const canAmount = useCanEditAmount();
  const [notifyAdmin, setNotifyAdmin] = useState(false);
  const [outreach, setOutreach] = useState("");
  const [saving, setSaving] = useState(false);
  // 此時段空著的診間（伺服器算：沒有 booked／executed 預約，也沒有活動）
  const [freeRooms, setFreeRooms] = useState<Room[] | null>(null);

  // 批次
  const [freq, setFreq] = useState<"weekly" | "biweekly" | "monthly">("weekly");
  const [count, setCount] = useState("4");

  // 從診間日曆空白格點進來：?room=&date=&start=
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const r = Number(p.get("room"));
    const d = p.get("date");
    const s = p.get("start");
    if (r) setRoomId(r);
    if (d && /^\d{4}-\d{2}-\d{2}$/.test(d)) setDate(d);
    if (s && /^\d{2}:\d{2}$/.test(s)) {
      setStartTime(s);
      setEndTime(addHour(s));
    }
  }, []);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const [cs, rs, ts] = await Promise.all([
        clientFetch("/cases", token),
        clientFetch("/rooms", token),
        clientFetch("/auth/therapists", token).catch(() => []),
      ]);
      setCases(cs);
      setRooms(rs);
      setTherapists(ts);
    } catch (e: any) {
      setError(e.message);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const loadWeek = useCallback(async () => {
    if (!token) return;
    try {
      const range = `start=${weekStart}T00:00:00%2B08:00&end=${shiftDate(weekStart, 7)}T00:00:00%2B08:00`;
      // 自己可見的完整場次 + 所有人的「已佔用」時段（含他人與活動，只有時段，沒有個人資料）
      const [ap, oc] = await Promise.all([
        clientFetch(`/appointments?${range}`, token),
        clientFetch(`/rooms/occupancy?${range}`, token),
      ]);
      setWeekAppts(ap);
      setWeekOcc(oc);
    } catch { /* 週檢視載入失敗不擋表單 */ }
  }, [token, weekStart]);

  useEffect(() => {
    loadWeek();
  }, [loadWeek]);

  // 選了個案自動帶心理師
  useEffect(() => {
    const c = cases.find((x) => x.id === caseId);
    if (c) setTherapistId(c.therapist_id);
  }, [caseId, cases]);

  const offsite = sessionType !== "in_person";

  useEffect(() => {
    if (!token || offsite || !date || startTime >= endTime) {
      setFreeRooms(null);
      return;
    }
    let stale = false;
    const q = `start=${encodeURIComponent(`${date}T${startTime}:00+08:00`)}&end=${encodeURIComponent(`${date}T${endTime}:00+08:00`)}`;
    clientFetch(`/rooms/availability?${q}`, token)
      .then((r) => { if (!stale) setFreeRooms(r); })
      .catch(() => { if (!stale) setFreeRooms(null); });
    return () => { stale = true; };
  }, [token, offsite, date, startTime, endTime]);

  const weekDays = useMemo(
    () => Array.from({ length: 7 }, (_, i) => shiftDate(weekStart, i)),
    [weekStart]
  );

  const conflicts = useMemo(() => {
    if (offsite || !roomId) return [];
    return weekOcc.filter(
      (o) =>
        o.room_id === roomId &&
        o.start.slice(0, 10) === date &&
        hhmm(o.start) < endTime &&
        hhmm(o.end) > startTime
    );
  }, [weekOcc, roomId, date, startTime, endTime, offsite]);

  // 週檢視：自己可見的場次顯示完整內容；其餘佔用（他人、活動）只顯示「已佔用」
  const weekItems = useMemo(() => {
    const mine = weekAppts
      .filter((a) => a.status === "booked" || a.status === "executed")
      .map((a) => ({ key: `a${a.id}`, room_id: a.room_id, start: a.start_time, end: a.end_time, appt: a as Appt | null }));
    const covered = new Set(mine.map((m) => `${m.room_id}|${m.start && new Date(m.start).getTime()}|${m.end && new Date(m.end).getTime()}`));
    const masked = weekOcc
      .filter((o) => !covered.has(`${o.room_id}|${new Date(o.start).getTime()}|${new Date(o.end).getTime()}`))
      .map((o, i) => ({ key: `o${i}`, room_id: o.room_id as number | null, start: o.start as string | null, end: o.end as string | null, appt: null as Appt | null }));
    return [...mine, ...masked].sort((x, y) => (x.start ?? "").localeCompare(y.start ?? ""));
  }, [weekAppts, weekOcc]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const billErr = billingError(billing);
    if (billErr) { setError(billErr); return; }
    setSaving(true);
    setError(null);
    setOk(null);
    const body: any = {
      case_id: caseId,
      therapist_id: therapistId,
      room_id: offsite ? null : roomId || null,
      session_type: sessionType,
      start_time: `${date}T${startTime}:00+08:00`,
      end_time: `${date}T${endTime}:00+08:00`,
    };
    Object.assign(body, billingBody(billing, canAmount)); // 付款方式、額度、金額（批次時整批共用）
    try {
      if (tab === "batch") {
        const slots: any[] = [];
        const step = freq === "weekly" ? 7 : freq === "biweekly" ? 14 : 28;
        for (let i = 0; i < Number(count); i++) {
          const d = shiftDate(date, i * step);
          slots.push({
            start_time: `${d}T${startTime}:00+08:00`,
            end_time: `${d}T${endTime}:00+08:00`,
          });
        }
        const res = await clientFetch("/appointments/batch", token, {
          method: "POST",
          body: JSON.stringify({ ...body, slots }),
        });
        const warn = warningsText(res);
        setOk(`已建立 ${slots.length} 筆預約` + (warn ? `　⚠ ${warn}` : ""));
      } else {
        const res = await clientFetch("/appointments", token, { method: "POST", body: JSON.stringify(body) });
        const warn = warningsText(res);
        setOk("預約已建立" + (warn ? `　⚠ ${warn}` : ""));
      }
      loadWeek();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold">預約作業</h1>
      <p className="mt-1 text-sm text-gray-500">
        邊訂邊看空間：左邊填資料，右邊同步顯示該診間的週檢視。
        {isTherapist && " 查空間時他人時段只顯示心理師姓名，不顯示個案資訊。"}
      </p>

      <div className="mb-4 mt-4 flex gap-2 border-b border-gray-200">
        {([["single", "新增預約（單筆）"], ["batch", "批次預約"], ["week", "診間空間週檢視"], ["events", "🏛️ 5F雲燈教室（活動借用）"]] as const).map(
          ([k, label]) => (
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
          )
        )}
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
      {ok && <div className="mb-4 rounded-lg bg-green-50 px-4 py-3 text-sm text-green-700">{ok}</div>}

      {tab === "events" && <EventsTab token={token} rooms={rooms} people={therapists} />}

      {tab !== "events" && (
      <div className={tab === "week" ? "" : "grid gap-4 lg:grid-cols-2"}>
        {tab !== "week" && (
          <form onSubmit={submit} className="rounded-xl border border-gray-200 bg-white p-4">
            <div className="grid grid-cols-2 gap-3">
              <label className="col-span-2 text-sm">
                <span className="mb-1 block text-gray-600">個案 *</span>
                <select required value={caseId} onChange={(e) => setCaseId(Number(e.target.value))} className="w-full rounded-lg border border-gray-300 px-3 py-2">
                  <option value={0}>請選擇</option>
                  {cases.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}{c.case_number ? ` (${c.case_number})` : ""}</option>
                  ))}
                </select>
              </label>

              <label className="text-sm">
                <span className="mb-1 block text-gray-600">心理師 *</span>
                <select required value={therapistId} disabled={isTherapist} onChange={(e) => setTherapistId(Number(e.target.value))} className="w-full rounded-lg border border-gray-300 px-3 py-2 disabled:bg-gray-100">
                  <option value={0}>請選擇</option>
                  {therapists.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </label>

              <label className="text-sm">
                <span className="mb-1 block text-gray-600">類型</span>
                <select value={sessionType} onChange={(e) => setSessionType(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2">
                  {Object.entries(SESSION_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>

              {!offsite && (
                <label className="col-span-2 text-sm">
                  <span className="mb-1 block text-gray-600">診間 *</span>
                  <select required value={roomId} onChange={(e) => setRoomId(Number(e.target.value))} className="w-full rounded-lg border border-gray-300 px-3 py-2">
                    <option value={0}>請選擇</option>
                    {rooms.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.room_code} {r.room_type === "play" ? "兒童遊戲室" : "晤談室"}
                      </option>
                    ))}
                  </select>
                  {freeRooms && (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
                      <span className="text-gray-500">此時段空房：</span>
                      {freeRooms.length === 0 ? (
                        <span className="text-red-600">沒有空房</span>
                      ) : (
                        freeRooms.map((r) => (
                          <button
                            key={r.id}
                            type="button"
                            onClick={() => setRoomId(r.id)}
                            className={`rounded-full border px-2 py-0.5 ${
                              roomId === r.id
                                ? "border-primary-500 bg-primary-50 text-primary-700"
                                : "border-gray-300 text-gray-600 hover:bg-gray-50"
                            }`}
                          >
                            {r.room_code}{r.room_type === "play" ? "（遊戲室）" : ""}
                          </button>
                        ))
                      )}
                    </div>
                  )}
                </label>
              )}

              <BillingFields
                token={token}
                caseId={caseId}
                caseFunding={cases.find((x) => x.id === caseId)?.funding_source}
                date={date}
                sessionType={sessionType}
                value={billing}
                onChange={setBilling}
                className="col-span-2"
              />

              {sessionType === "online" && (
                <>
                  <label className="col-span-2 text-sm">
                    <span className="mb-1 block text-gray-600">視訊連結</span>
                    <input value={videoLink} onChange={(e) => setVideoLink(e.target.value)} placeholder="https://..." className="w-full rounded-lg border border-gray-300 px-3 py-2" />
                  </label>
                  <label className="col-span-2 flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={notifyAdmin} onChange={(e) => setNotifyAdmin(e.target.checked)} />
                    請通知行政傳視訊連結給個案
                  </label>
                </>
              )}
              {sessionType === "outdoor" && (
                <label className="col-span-2 text-sm">
                  <span className="mb-1 block text-gray-600">外展地點</span>
                  <input value={outreach} onChange={(e) => setOutreach(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2" />
                </label>
              )}

              <label className="text-sm">
                <span className="mb-1 block text-gray-600">日期 *</span>
                <input required type="date" value={date} onChange={(e) => setDate(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2" />
              </label>

              <div className="text-sm">
                <span className="mb-1 block text-gray-600">時段 *</span>
                <div className="flex items-center gap-1">
                  <TimeSelect value={startTime} onChange={(v) => { setStartTime(v); setEndTime(addHour(v)); }} />
                  <span className="text-gray-400">–</span>
                  <TimeSelect value={endTime} onChange={setEndTime} />
                </div>
              </div>

              {tab === "batch" && (
                <>
                  <label className="text-sm">
                    <span className="mb-1 block text-gray-600">循環模式</span>
                    <select value={freq} onChange={(e) => setFreq(e.target.value as any)} className="w-full rounded-lg border border-gray-300 px-3 py-2">
                      <option value="weekly">每週</option>
                      <option value="biweekly">每兩週</option>
                      <option value="monthly">每月</option>
                    </select>
                  </label>
                  <label className="text-sm">
                    <span className="mb-1 block text-gray-600">次數</span>
                    <input type="number" min="1" max="52" value={count} onChange={(e) => setCount(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 tabular-nums" />
                  </label>
                  <p className="col-span-2 rounded bg-amber-50 px-3 py-2 text-xs text-amber-800">
                    批次遇國定假日會標示提醒但<b>不自動跳過</b>，請與個案另行喬時間。
                    診間時段衝突時整批不會建立。
                  </p>
                </>
              )}
            </div>

            {conflicts.length > 0 && (
              <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                ⚠️ 該診間此時段已被使用（已佔用）
              </div>
            )}

            <div className="mt-4 flex justify-end">
              <button type="submit" disabled={saving || conflicts.length > 0} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                {saving ? "建立中..." : tab === "batch" ? "建立批次預約" : "建立預約"}
              </button>
            </div>
          </form>
        )}

        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-medium">
              診間週檢視{!offsite && roomId ? ` — ${rooms.find((r) => r.id === roomId)?.room_code}` : ""}
            </h2>
            <div className="flex items-center gap-1">
              <button onClick={() => setWeekStart(shiftDate(weekStart, -7))} className="rounded border border-gray-300 px-2 py-1 text-xs">◀</button>
              <span className="text-xs text-gray-500">{weekStart} 起</span>
              <button onClick={() => setWeekStart(shiftDate(weekStart, 7))} className="rounded border border-gray-300 px-2 py-1 text-xs">▶</button>
            </div>
          </div>
          {offsite ? (
            <p className="py-8 text-center text-sm text-gray-400">線上／外展不佔用診間，不需檢查空間衝突。</p>
          ) : (
            <div className="space-y-2">
              {weekDays.map((d) => {
                const list = weekItems.filter(
                  (a) => a.start?.slice(0, 10) === d && a.room_id && (!roomId || a.room_id === roomId)
                );
                return (
                  <div key={d} className={`rounded-lg border px-3 py-2 ${d === date ? "border-primary-400 bg-primary-50" : "border-gray-200"}`}>
                    <div className="mb-1 text-xs font-medium text-gray-600">{d}</div>
                    {list.length === 0 ? (
                      <div className="text-xs text-gray-400">空</div>
                    ) : (
                      list.map((it) => (
                        <div key={it.key} className={`text-xs text-gray-700 ${it.appt ? "" : "cursor-default select-none"}`} aria-disabled={it.appt ? undefined : true}>
                          {hhmm(it.start)}–{hhmm(it.end)}{" "}
                          {!it.appt ? (
                            <span className="text-gray-400">已佔用</span>
                          ) : isTherapist ? (
                            <span className="text-gray-700">{it.appt.case_name}</span>
                          ) : (
                            <>{it.appt.case_name} · {it.appt.therapist_name}</>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
      )}
    </div>
  );
}

function TimeSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [h, m] = value.split(":");
  const hours = Array.from({ length: 15 }, (_, i) => String(i + 8).padStart(2, "0"));
  return (
    <div className="flex items-center gap-0.5">
      <select value={h} onChange={(e) => onChange(`${e.target.value}:${m}`)} className="rounded-lg border border-gray-300 px-1.5 py-2 text-sm">
        {hours.map((x) => <option key={x} value={x}>{x}</option>)}
      </select>
      <span>:</span>
      <select value={m} onChange={(e) => onChange(`${h}:${e.target.value}`)} className="rounded-lg border border-gray-300 px-1.5 py-2 text-sm">
        {MINUTES.map((x) => <option key={x} value={x}>{x}</option>)}
      </select>
    </div>
  );
}
