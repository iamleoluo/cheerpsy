"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

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
}

function formatTime(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export default function RoomsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;

  const [rooms, setRooms] = useState<Room[]>([]);
  const [selectedRoom, setSelectedRoom] = useState<number | null>(null);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingAppts, setLoadingAppts] = useState(false);
  const [selectedDate, setSelectedDate] = useState(() => {
    const d = new Date();
    return d.toISOString().slice(0, 10);
  });

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

  const fetchRoomAppointments = useCallback(
    async (roomId: number) => {
      if (!token) return;
      setLoadingAppts(true);
      try {
        const start = `${selectedDate}T00:00:00+08:00`;
        const end = `${selectedDate}T23:59:59+08:00`;
        const params = new URLSearchParams({
          room_id: roomId.toString(),
          start,
          end,
          status: "booked",
        });
        const data = await clientFetch(`/appointments?${params}`, token);
        setAppointments(data);
      } catch {
        setAppointments([]);
      } finally {
        setLoadingAppts(false);
      }
    },
    [token, selectedDate],
  );

  useEffect(() => {
    fetchRooms();
  }, [fetchRooms]);

  useEffect(() => {
    if (selectedRoom) fetchRoomAppointments(selectedRoom);
  }, [selectedRoom, fetchRoomAppointments]);

  if (!token) return <p>Loading...</p>;

  const floors = [...new Set(rooms.map((r) => r.floor))].sort();

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">空間預約</h1>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {loading ? (
            <p className="text-gray-400">載入中...</p>
          ) : (
            floors.map((floor) => (
              <div key={floor} className="mb-6">
                <h2 className="mb-3 text-sm font-medium text-gray-500">
                  {floor} 樓
                </h2>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
                  {rooms
                    .filter((r) => r.floor === floor)
                    .map((room) => (
                      <button
                        key={room.id}
                        onClick={() => setSelectedRoom(room.id)}
                        className={`rounded-lg border p-3 text-left transition-colors ${
                          selectedRoom === room.id
                            ? "border-primary-500 bg-primary-50"
                            : "border-gray-200 hover:border-gray-300 hover:bg-gray-50"
                        }`}
                      >
                        <div className="text-sm font-medium">{room.name}</div>
                        <div className="text-xs text-gray-400">
                          {room.room_code}
                        </div>
                        {room.has_special_equipment && (
                          <span className="mt-1 inline-block rounded bg-purple-100 px-1.5 py-0.5 text-xs text-purple-600">
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

        <div>
          {selectedRoom ? (
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="font-medium">
                  {rooms.find((r) => r.id === selectedRoom)?.name} 預約
                </h3>
                <input
                  type="date"
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="rounded-lg border border-gray-300 px-2 py-1 text-sm"
                />
              </div>
              {loadingAppts ? (
                <p className="text-sm text-gray-400">載入中...</p>
              ) : appointments.length === 0 ? (
                <p className="text-sm text-gray-400">當日無預約</p>
              ) : (
                <div className="space-y-2">
                  {appointments.map((a) => (
                    <div
                      key={a.id}
                      className="rounded-lg bg-blue-50 px-3 py-2"
                    >
                      <div className="text-xs text-blue-600">
                        {formatTime(a.start_time)} ~ {formatTime(a.end_time)}
                      </div>
                      <div className="text-sm font-medium">
                        {a.case_name ?? "未知個案"}
                      </div>
                      <div className="text-xs text-gray-500">
                        {a.therapist_name}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-gray-300 p-8 text-center text-sm text-gray-400">
              點選左側空間查看預約
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
