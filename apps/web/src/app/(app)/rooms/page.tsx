"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import type { EventInput, DatesSetArg } from "@fullcalendar/core";

interface Room {
  id: number;
  name: string;
  floor: number;
  room_code: string;
  has_special_equipment: boolean;
  notes: string | null;
}

interface Appointment {
  id: number;
  appointment_number: string;
  case_name: string | null;
  therapist_name: string | null;
  start_time: string | null;
  end_time: string | null;
  status: string;
  session_type: string;
}

const statusColors: Record<string, string> = {
  booked: "#3b82f6",
  executed: "#22c55e",
  cancelled: "#9ca3af",
};

export default function RoomsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;

  const [rooms, setRooms] = useState<Room[]>([]);
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);
  const [events, setEvents] = useState<EventInput[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const dateRangeRef = useRef<{ start: string; end: string } | null>(null);
  const calendarRef = useRef<FullCalendar>(null);

  const fetchRooms = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await clientFetch("/rooms", token);
      setRooms(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchRooms();
  }, [fetchRooms]);

  const fetchAppointments = useCallback(
    async (roomId: number, start: string, end: string) => {
      if (!token) return;
      setLoadingEvents(true);
      try {
        const params = new URLSearchParams({
          room_id: roomId.toString(),
          start,
          end,
        });
        const data: Appointment[] = await clientFetch(
          `/appointments?${params}`,
          token,
        );
        const mapped: EventInput[] = data.map((a) => ({
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
        }));
        setEvents(mapped);
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
      const start = arg.startStr;
      const end = arg.endStr;
      dateRangeRef.current = { start, end };
      if (selectedRoom) {
        fetchAppointments(selectedRoom.id, start, end);
      }
    },
    [selectedRoom, fetchAppointments],
  );

  const handleSelectRoom = (room: Room) => {
    setSelectedRoom(room);
    setEvents([]);
    if (dateRangeRef.current) {
      fetchAppointments(
        room.id,
        dateRangeRef.current.start,
        dateRangeRef.current.end,
      );
    }
  };

  const handleBack = () => {
    setSelectedRoom(null);
    setEvents([]);
  };

  if (!token) return <p>Loading...</p>;

  if (selectedRoom) {
    return (
      <div>
        <div className="mb-4 flex items-center gap-3">
          <button
            onClick={handleBack}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
          >
            ← 返回空間列表
          </button>
          <h1 className="text-2xl font-bold">{selectedRoom.name}</h1>
          <span className="text-sm text-gray-400">
            {selectedRoom.floor}F · {selectedRoom.room_code}
            {selectedRoom.has_special_equipment && " · 特殊設備"}
          </span>
          {loadingEvents && (
            <span className="text-xs text-gray-400">載入中...</span>
          )}
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
            buttonText={{
              today: "今天",
              month: "月",
              week: "週",
              day: "日",
            }}
            events={events}
            datesSet={handleDatesSet}
            height="auto"
            eventTimeFormat={{
              hour: "2-digit",
              minute: "2-digit",
              hour12: false,
            }}
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

  const floors = [...new Set(rooms.map((r) => r.floor))].sort();

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">空間預約</h1>
      {loading ? (
        <p className="text-gray-400">載入中...</p>
      ) : (
        floors.map((floor) => (
          <div key={floor} className="mb-6">
            <h2 className="mb-3 text-sm font-medium text-gray-500">
              {floor} 樓
            </h2>
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
                    <div className="mt-1 text-xs text-gray-400">
                      {room.room_code}
                    </div>
                    {room.has_special_equipment && (
                      <span className="mt-2 inline-block rounded bg-purple-100 px-1.5 py-0.5 text-xs text-purple-600">
                        特殊設備
                      </span>
                    )}
                    {room.notes && (
                      <div className="mt-1 text-xs text-gray-400">
                        {room.notes}
                      </div>
                    )}
                  </button>
                ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
