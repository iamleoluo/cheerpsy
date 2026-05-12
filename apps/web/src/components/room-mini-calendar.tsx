"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { clientFetch } from "@/lib/client-api";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import type { EventInput, DatesSetArg } from "@fullcalendar/core";

interface Appointment {
  id: number;
  case_name: string | null;
  therapist_name: string | null;
  start_time: string | null;
  end_time: string | null;
  status: string;
}

const statusColors: Record<string, string> = {
  booked: "#3b82f6",
  executed: "#22c55e",
  cancelled: "#9ca3af",
};

export default function RoomMiniCalendar({
  token,
  roomId,
  roomName,
  focusDate,
}: {
  token: string;
  roomId: number;
  roomName: string;
  focusDate?: string;
}) {
  const [events, setEvents] = useState<EventInput[]>([]);
  const [loading, setLoading] = useState(false);
  const dateRangeRef = useRef<{ start: string; end: string } | null>(null);
  const calendarRef = useRef<FullCalendar>(null);

  const fetchAppointments = useCallback(
    async (start: string, end: string) => {
      setLoading(true);
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
        setEvents(
          data.map((a) => ({
            id: String(a.id),
            title: `${a.case_name ?? "未知"} — ${a.therapist_name ?? ""}`,
            start: a.start_time ?? undefined,
            end: a.end_time ?? undefined,
            backgroundColor: statusColors[a.status] ?? "#6b7280",
            borderColor: statusColors[a.status] ?? "#6b7280",
            extendedProps: {
              case_name: a.case_name,
              therapist_name: a.therapist_name,
              status: a.status,
            },
          })),
        );
      } catch {
        setEvents([]);
      } finally {
        setLoading(false);
      }
    },
    [token, roomId],
  );

  const handleDatesSet = useCallback(
    (arg: DatesSetArg) => {
      dateRangeRef.current = { start: arg.startStr, end: arg.endStr };
      fetchAppointments(arg.startStr, arg.endStr);
    },
    [fetchAppointments],
  );

  useEffect(() => {
    if (focusDate && calendarRef.current) {
      calendarRef.current.getApi().gotoDate(focusDate);
    }
  }, [focusDate]);

  useEffect(() => {
    if (dateRangeRef.current) {
      fetchAppointments(dateRangeRef.current.start, dateRangeRef.current.end);
    }
  }, [roomId, fetchAppointments]);

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">{roomName}</h3>
        {loading && <span className="text-xs text-gray-400">載入中...</span>}
      </div>
      <FullCalendar
        ref={calendarRef}
        plugins={[dayGridPlugin, timeGridPlugin]}
        initialView="timeGridWeek"
        locale="zh-tw"
        headerToolbar={{
          left: "prev,next",
          center: "title",
          right: "timeGridWeek,timeGridDay",
        }}
        buttonText={{ week: "週", day: "日" }}
        events={events}
        datesSet={handleDatesSet}
        height={420}
        eventTimeFormat={{
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        }}
        slotMinTime="08:00:00"
        slotMaxTime="22:00:00"
        allDaySlot={false}
        eventDisplay="block"
        titleFormat={{ month: "short", day: "numeric" }}
        dayHeaderFormat={{ weekday: "narrow", day: "numeric" }}
        slotLabelFormat={{
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        }}
        eventContent={(arg) => {
          const props = arg.event.extendedProps;
          return (
            <div className="overflow-hidden px-0.5 text-[10px] leading-tight">
              <div className="truncate font-medium">
                {props.case_name ?? "未知"}
              </div>
              <div className="truncate opacity-80">
                {props.therapist_name ?? ""}
              </div>
            </div>
          );
        }}
      />
    </div>
  );
}
