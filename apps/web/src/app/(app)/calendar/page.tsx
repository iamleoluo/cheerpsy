"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import HelpDrawer, { type HelpContent } from "@/components/HelpDrawer";
import FullCalendar from "@fullcalendar/react";

const helpContent: HelpContent = {
  title: "預約日曆",
  overview: "排程中心，所有諮商都從建立預約開始。新增預約後，系統在 T+1（隔日）自動執行日結，將已執行預約寫入流水帳，無需手動操作。",
  sections: [
    {
      heading: "新增單次預約",
      type: "steps",
      items: [
        "點「＋新增預約」（或點月曆空格）",
        "選個案（可輸入姓名搜尋）",
        "選心理師、諮商類型（現場／線上／家訪）、診間",
        "選日期與起始時間，填入諮商費用",
        "系統自動計算心理師份額與診所份額，儲存",
      ],
    },
    {
      heading: "批次預約（定期諮商）",
      type: "steps",
      items: [
        "點「批次預約」",
        "選個案、心理師、類型、診間",
        "設定起始日期、頻率（每週／隔週）與總次數",
        "確認預覽清單後一次建立所有預約",
      ],
    },
    {
      heading: "取消預約",
      type: "steps",
      items: [
        "找到該筆預約，點「取消」並確認",
        "當日取消不計費",
        "過隔日日結後自動視為已執行，帳務已產生",
      ],
    },
    {
      heading: "T+1 日結規則",
      type: "tips",
      items: [
        "當日 23:59 前未取消的預約，隔日日結自動標記為「已執行」並寫入流水帳",
        "個案未到請務必在當日結束前取消，否則帳務自動產生無法撤回",
        "管理員可在日結帳冊手動補跑指定日期區間的結算",
      ],
    },
    {
      heading: "管理員提示",
      type: "notes",
      items: [
        "診間衝突由系統自動阻擋，同診間同時段只能一個預約",
        "預約建立後若需修改費用，至日結帳冊解鎖後調整",
      ],
    },
  ],
};
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import type { EventInput, DatesSetArg } from "@fullcalendar/core";

/* ───── types ───── */

interface Room {
  id: number;
  name: string;
  floor: number;
  room_code: string;
  has_special_equipment: boolean;
  notes: string | null;
}

interface CalendarAppointment {
  id: number;
  appointment_number: string;
  case_name: string | null;
  therapist_name: string | null;
  start_time: string | null;
  end_time: string | null;
  status: string;
  session_type: string;
}

interface UpcomingAppointment {
  appointment_id: number;
  appointment_number: string;
  case_id: number;
  case_name: string | null;
  case_phone: string | null;
  therapist_name: string | null;
  session_type: string;
  start_time: string | null;
  status: string;
  reminder_count: number;
  last_contact_result: string | null;
}

interface ReminderLog {
  id: number;
  contact_result: string;
  notes: string | null;
  contacted_by_name: string | null;
  contacted_at: string | null;
}

/* ───── constants ───── */

const statusColors: Record<string, string> = {
  booked: "#3b82f6",
  executed: "#22c55e",
  cancelled: "#9ca3af",
};

const sessionTypeLabels: Record<string, string> = {
  in_person: "現場",
  online: "線上",
  home_visit: "到宅",
};

const contactResultLabels: Record<string, string> = {
  confirmed: "已確認",
  wants_cancel: "欲取消",
  no_answer: "未接聽",
};

const contactResultColors: Record<string, string> = {
  confirmed: "bg-green-100 text-green-700",
  wants_cancel: "bg-red-100 text-red-700",
  no_answer: "bg-yellow-100 text-yellow-700",
};

/* ───── main page ───── */

export default function CalendarPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [tab, setTab] = useState<"calendar" | "reminders">("calendar");
  const [helpOpen, setHelpOpen] = useState(false);

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">預約日曆</h1>
        <button onClick={() => setHelpOpen(true)} className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50 hover:text-gray-700">
          <span>ℹ️</span> 說明
        </button>
      </div>
      <HelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} content={helpContent} />

      <div className="mb-4 flex gap-1 border-b border-gray-200">
        {(
          [
            ["calendar", "診間日曆"],
            ["reminders", "預約提醒"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              tab === key
                ? "border-b-2 border-primary-600 text-primary-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "calendar" ? (
        <RoomCalendarTab token={token} />
      ) : (
        <RemindersTab token={token} />
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════
   Tab 1 — 診間日曆
   ═══════════════════════════════════════════════ */

function RoomCalendarTab({ token }: { token: string }) {
  const [rooms, setRooms] = useState<Room[]>([]);
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);
  const [events, setEvents] = useState<EventInput[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const dateRangeRef = useRef<{ start: string; end: string } | null>(null);
  const calendarRef = useRef<FullCalendar>(null);

  const fetchRooms = useCallback(async () => {
    setLoading(true);
    try {
      const data = await clientFetch("/rooms", token);
      setRooms(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchRooms();
  }, [fetchRooms]);

  const fetchAppointments = useCallback(
    async (roomId: number, start: string, end: string) => {
      setLoadingEvents(true);
      try {
        const params = new URLSearchParams({ room_id: roomId.toString(), start, end });
        const data: CalendarAppointment[] = await clientFetch(`/appointments?${params}`, token);
        setEvents(
          data.map((a) => ({
            id: String(a.id),
            title: `${a.case_name ?? "未知"} — ${a.therapist_name ?? ""}`,
            start: a.start_time ?? undefined,
            end: a.end_time ?? undefined,
            backgroundColor: statusColors[a.status] ?? "#6b7280",
            borderColor: statusColors[a.status] ?? "#6b7280",
            extendedProps: {
              appointment_number: a.appointment_number,
              case_name: a.case_name,
              therapist_name: a.therapist_name,
              status: a.status,
              session_type: a.session_type,
            },
          })),
        );
      } catch {
        setEvents([]);
      } finally {
        setLoadingEvents(false);
      }
    },
    [token],
  );

  const handleDatesSet = useCallback(
    (arg: DatesSetArg) => {
      dateRangeRef.current = { start: arg.startStr, end: arg.endStr };
      if (selectedRoom) {
        fetchAppointments(selectedRoom.id, arg.startStr, arg.endStr);
      }
    },
    [selectedRoom, fetchAppointments],
  );

  const handleSelectRoom = (room: Room) => {
    setSelectedRoom(room);
    setEvents([]);
    if (dateRangeRef.current) {
      fetchAppointments(room.id, dateRangeRef.current.start, dateRangeRef.current.end);
    }
  };

  const handleBack = () => {
    setSelectedRoom(null);
    setEvents([]);
  };

  /* ── per-room calendar view ── */
  if (selectedRoom) {
    return (
      <div>
        <div className="mb-4 flex items-center gap-3">
          <button
            onClick={handleBack}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
          >
            ← 返回診間列表
          </button>
          <h2 className="text-xl font-bold">{selectedRoom.name}</h2>
          <span className="text-sm text-gray-400">
            {selectedRoom.floor}F · {selectedRoom.room_code}
            {selectedRoom.has_special_equipment && " · 特殊設備"}
          </span>
          {loadingEvents && <span className="text-xs text-gray-400">載入中...</span>}
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <FullCalendar
            ref={calendarRef}
            plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
            initialView="dayGridMonth"
            locale="zh-tw"
            headerToolbar={{
              left: "prev,next today",
              center: "title",
              right: "dayGridMonth,timeGridWeek,timeGridDay",
            }}
            buttonText={{ today: "今天", month: "月", week: "週", day: "日" }}
            events={events}
            datesSet={handleDatesSet}
            height="auto"
            eventTimeFormat={{ hour: "2-digit", minute: "2-digit", hour12: false }}
            slotMinTime="08:00:00"
            slotMaxTime="22:00:00"
            allDaySlot={false}
            eventDisplay="block"
            dayMaxEvents={4}
            eventContent={(arg) => {
              const props = arg.event.extendedProps;
              return (
                <div className="overflow-hidden px-1 py-0.5 text-xs leading-tight">
                  <div className="font-medium">{arg.timeText}</div>
                  <div className="truncate">
                    {props.case_name ?? "未知"} — {props.therapist_name ?? ""}
                  </div>
                </div>
              );
            }}
          />
        </div>
      </div>
    );
  }

  /* ── room grid ── */
  const floors = [...new Set(rooms.map((r) => r.floor))].sort();

  if (loading) return <p className="text-gray-400">載入中...</p>;

  return (
    <div>
      {floors.map((floor) => (
        <div key={floor} className="mb-6">
          <h2 className="mb-3 text-sm font-medium text-gray-500">{floor} 樓</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
            {rooms
              .filter((r) => r.floor === floor)
              .map((room) => (
                <button
                  key={room.id}
                  onClick={() => handleSelectRoom(room)}
                  className="rounded-lg border border-gray-200 p-4 text-left transition-all hover:border-primary-400 hover:shadow-md"
                >
                  <div className="text-base font-medium">{room.name}</div>
                  <div className="mt-1 text-xs text-gray-400">{room.room_code}</div>
                  {room.has_special_equipment && (
                    <span className="mt-2 inline-block rounded bg-purple-100 px-1.5 py-0.5 text-xs text-purple-600">
                      特殊設備
                    </span>
                  )}
                  {room.notes && <div className="mt-1 text-xs text-gray-400">{room.notes}</div>}
                </button>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ═══════════════════════════════════════════════
   Tab 2 — 預約提醒 / 電訪追蹤
   ═══════════════════════════════════════════════ */

function RemindersTab({ token }: { token: string }) {
  const [days, setDays] = useState(3);
  const [appointments, setAppointments] = useState<UpcomingAppointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [logModal, setLogModal] = useState<{ appointmentId: number; appointmentNumber: string } | null>(null);
  const [logs, setLogs] = useState<ReminderLog[]>([]);
  const [addModal, setAddModal] = useState<{ appointmentId: number } | null>(null);
  const [formResult, setFormResult] = useState("confirmed");
  const [formNotes, setFormNotes] = useState("");
  const [saving, setSaving] = useState(false);

  const fetchAppointments = useCallback(async () => {
    setLoading(true);
    try {
      const data = await clientFetch(`/reminders/upcoming?days=${days}`, token);
      setAppointments(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token, days]);

  useEffect(() => {
    fetchAppointments();
  }, [fetchAppointments]);

  const showLogs = async (appointmentId: number, appointmentNumber: string) => {
    setLogModal({ appointmentId, appointmentNumber });
    try {
      const data = await clientFetch(`/reminders/logs/${appointmentId}`, token);
      setLogs(data);
    } catch {
      setLogs([]);
    }
  };

  const handleAddReminder = async () => {
    if (!addModal) return;
    setSaving(true);
    try {
      await clientFetch("/reminders", token, {
        method: "POST",
        body: JSON.stringify({
          appointment_id: addModal.appointmentId,
          contact_result: formResult,
          notes: formNotes || null,
        }),
      });
      setAddModal(null);
      setFormResult("confirmed");
      setFormNotes("");
      fetchAppointments();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <label className="text-sm text-gray-500">顯示未來</label>
        <select
          value={days}
          onChange={(e) => setDays(parseInt(e.target.value))}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
        >
          <option value={1}>1 天</option>
          <option value={2}>2 天</option>
          <option value={3}>3 天</option>
          <option value={5}>5 天</option>
          <option value={7}>7 天</option>
          <option value={14}>14 天</option>
        </select>
        <span className="text-sm text-gray-500">的預約</span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">時間</th>
              <th className="px-4 py-3">預約編號</th>
              <th className="px-4 py-3">個案</th>
              <th className="px-4 py-3">電話</th>
              <th className="px-4 py-3">心理師</th>
              <th className="px-4 py-3">類型</th>
              <th className="px-4 py-3">聯繫狀態</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-400">
                  載入中...
                </td>
              </tr>
            ) : appointments.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-400">
                  目前無需提醒的預約
                </td>
              </tr>
            ) : (
              appointments.map((a) => (
                <tr key={a.appointment_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-xs">
                    {a.start_time
                      ? new Date(a.start_time).toLocaleString("zh-TW", {
                          month: "numeric",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : "-"}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{a.appointment_number}</td>
                  <td className="px-4 py-3 font-medium">{a.case_name ?? "-"}</td>
                  <td className="px-4 py-3 text-xs">{a.case_phone ?? "-"}</td>
                  <td className="px-4 py-3">{a.therapist_name ?? "-"}</td>
                  <td className="px-4 py-3">{sessionTypeLabels[a.session_type] ?? a.session_type}</td>
                  <td className="px-4 py-3">
                    {a.last_contact_result ? (
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${contactResultColors[a.last_contact_result] ?? "bg-gray-100"}`}
                      >
                        {contactResultLabels[a.last_contact_result] ?? a.last_contact_result}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-400">未聯繫</span>
                    )}
                    {a.reminder_count > 0 && (
                      <span className="ml-1 text-xs text-gray-400">({a.reminder_count}次)</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button
                        onClick={() => setAddModal({ appointmentId: a.appointment_id })}
                        className="text-xs text-primary-600 hover:underline"
                      >
                        記錄聯繫
                      </button>
                      {a.reminder_count > 0 && (
                        <button
                          onClick={() => showLogs(a.appointment_id, a.appointment_number)}
                          className="text-xs text-gray-500 hover:underline"
                        >
                          歷史
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Add reminder modal */}
      {addModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-bold">記錄聯繫結果</h2>
            <div className="space-y-3">
              <label className="block">
                <span className="mb-1 block text-xs text-gray-500">聯繫結果 *</span>
                <select
                  value={formResult}
                  onChange={(e) => setFormResult(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                >
                  <option value="confirmed">已確認出席</option>
                  <option value="wants_cancel">欲取消預約</option>
                  <option value="no_answer">未接聽</option>
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block text-xs text-gray-500">備註</span>
                <textarea
                  value={formNotes}
                  onChange={(e) => setFormNotes(e.target.value)}
                  rows={3}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  placeholder="補充說明..."
                />
              </label>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => {
                  setAddModal(null);
                  setFormNotes("");
                }}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
              >
                取消
              </button>
              <button
                onClick={handleAddReminder}
                disabled={saving}
                className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
              >
                {saving ? "儲存中..." : "儲存"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Logs modal */}
      {logModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-bold">
              聯繫歷史 — {logModal.appointmentNumber}
            </h2>
            {logs.length === 0 ? (
              <p className="text-sm text-gray-400">無聯繫紀錄</p>
            ) : (
              <div className="max-h-80 space-y-3 overflow-y-auto">
                {logs.map((l) => (
                  <div key={l.id} className="rounded-lg border border-gray-200 p-3">
                    <div className="flex items-center justify-between">
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${contactResultColors[l.contact_result] ?? "bg-gray-100"}`}
                      >
                        {contactResultLabels[l.contact_result] ?? l.contact_result}
                      </span>
                      <span className="text-xs text-gray-400">
                        {l.contacted_at ? new Date(l.contacted_at).toLocaleString("zh-TW") : ""}
                        {l.contacted_by_name && ` · ${l.contacted_by_name}`}
                      </span>
                    </div>
                    {l.notes && <p className="mt-2 text-sm text-gray-600">{l.notes}</p>}
                  </div>
                ))}
              </div>
            )}
            <div className="mt-4 flex justify-end">
              <button
                onClick={() => setLogModal(null)}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
              >
                關閉
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
