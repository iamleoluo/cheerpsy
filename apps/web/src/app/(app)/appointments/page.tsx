"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch, exportCsv } from "@/lib/client-api";
import RoomMiniCalendar from "@/components/room-mini-calendar";

interface Appointment {
  id: number;
  appointment_number: string;
  case_id: number;
  case_name: string | null;
  therapist_id: number;
  therapist_name: string | null;
  room_id: number | null;
  room_name: string | null;
  session_type: string;
  start_time: string | null;
  end_time: string | null;
  amount: number;
  therapist_share: number | null;
  clinic_share: number | null;
  status: string;
  batch_id: string | null;
  created_at: string | null;
}

interface CaseOption {
  id: number;
  name: string;
  therapist_id: number;
}

interface RoomOption {
  id: number;
  name: string;
  floor: number;
  room_code: string;
}

const statusLabels: Record<string, string> = {
  booked: "已預約",
  executed: "已執行",
  cancelled: "已取消",
};

const statusColors: Record<string, string> = {
  booked: "bg-blue-100 text-blue-700",
  executed: "bg-green-100 text-green-700",
  cancelled: "bg-gray-100 text-gray-500",
};

const sessionTypeLabels: Record<string, string> = {
  in_person: "現場",
  online: "線上",
  home_visit: "到宅",
};

function formatDateTime(iso: string | null) {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export default function AppointmentsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const userRole = (session?.user as any)?.role;

  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [showBatchForm, setShowBatchForm] = useState(false);
  const [error, setError] = useState("");

  const fetchAppointments = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      const qs = params.toString();
      const data = await clientFetch(
        `/appointments${qs ? `?${qs}` : ""}`,
        token,
      );
      setAppointments(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, statusFilter]);

  useEffect(() => {
    fetchAppointments();
  }, [fetchAppointments]);

  const handleCancel = async (id: number) => {
    if (!token || !confirm("確定要取消此預約？")) return;
    try {
      await clientFetch(`/appointments/${id}/cancel`, token, {
        method: "PUT",
      });
      fetchAppointments();
    } catch (e: any) {
      alert(e.message);
    }
  };

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">預約管理</h1>
        <div className="flex gap-2">
          {userRole !== "therapist" && (
            <button
              onClick={() => exportCsv("/export/appointments", token, "appointments.csv")}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
            >
              匯出 CSV
            </button>
          )}
          <button
            onClick={() => setShowBatchForm(true)}
            className="rounded-lg border border-primary-600 px-4 py-2 text-sm font-medium text-primary-600 hover:bg-primary-50"
          >
            批次預約
          </button>
          <button
            onClick={() => setShowForm(true)}
            className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
          >
            + 新增預約
          </button>
        </div>
      </div>

      <div className="mb-4 flex gap-3">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
        >
          <option value="">全部狀態</option>
          {Object.entries(statusLabels).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">
          {error}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">預約編號</th>
              <th className="px-4 py-3">個案</th>
              <th className="px-4 py-3">心理師</th>
              <th className="px-4 py-3">時間</th>
              <th className="px-4 py-3">類型</th>
              <th className="px-4 py-3">空間</th>
              <th className="px-4 py-3">金額</th>
              <th className="px-4 py-3">狀態</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-gray-400">
                  載入中...
                </td>
              </tr>
            ) : appointments.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-gray-400">
                  尚無預約資料
                </td>
              </tr>
            ) : (
              appointments.map((a) => (
                <tr key={a.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs">
                    {a.appointment_number}
                  </td>
                  <td className="px-4 py-3">{a.case_name ?? "-"}</td>
                  <td className="px-4 py-3">{a.therapist_name ?? "-"}</td>
                  <td className="px-4 py-3 text-xs">
                    {formatDateTime(a.start_time)}
                    {a.end_time && ` ~ ${formatDateTime(a.end_time)}`}
                  </td>
                  <td className="px-4 py-3">
                    {sessionTypeLabels[a.session_type] ?? a.session_type}
                  </td>
                  <td className="px-4 py-3">{a.room_name ?? "-"}</td>
                  <td className="px-4 py-3">
                    ${a.amount.toLocaleString()}
                    <div className="text-xs text-gray-400">
                      師 ${a.therapist_share?.toLocaleString()} / 所 $
                      {a.clinic_share?.toLocaleString()}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[a.status] ?? "bg-gray-100"}`}
                    >
                      {statusLabels[a.status] ?? a.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {a.status === "booked" && (
                      <button
                        onClick={() => handleCancel(a.id)}
                        className="text-red-600 hover:underline"
                      >
                        取消
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showForm && (
        <AppointmentForm
          token={token}
          onClose={() => setShowForm(false)}
          onSaved={() => {
            setShowForm(false);
            fetchAppointments();
          }}
        />
      )}
      {showBatchForm && (
        <BatchForm
          token={token}
          onClose={() => setShowBatchForm(false)}
          onSaved={() => {
            setShowBatchForm(false);
            fetchAppointments();
          }}
        />
      )}
    </div>
  );
}

function AppointmentForm({
  token,
  onClose,
  onSaved,
}: {
  token: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [cases, setCases] = useState<CaseOption[]>([]);
  const [rooms, setRooms] = useState<RoomOption[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [form, setForm] = useState({
    case_id: "",
    room_id: "",
    session_type: "in_person",
    start_date: "",
    start_time: "10:00",
    end_time: "11:00",
    amount: "2000",
  });

  useEffect(() => {
    clientFetch("/cases", token).then(setCases).catch(() => {});
    clientFetch("/rooms", token).then(setRooms).catch(() => {});
  }, [token]);

  const setField = (key: string, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const startISO = `${form.start_date}T${form.start_time}:00+08:00`;
      const endISO = `${form.start_date}T${form.end_time}:00+08:00`;
      await clientFetch("/appointments", token, {
        method: "POST",
        body: JSON.stringify({
          case_id: parseInt(form.case_id),
          room_id: form.room_id ? parseInt(form.room_id) : null,
          session_type: form.session_type,
          start_time: startISO,
          end_time: endISO,
          amount: parseFloat(form.amount),
        }),
      });
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const selectedRoom = rooms.find((r) => String(r.id) === form.room_id);
  const showCalendar = form.session_type === "in_person" && selectedRoom;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div
        className={`flex rounded-xl bg-white shadow-xl transition-all ${
          showCalendar ? "w-full max-w-4xl" : "w-full max-w-md"
        }`}
      >
        <div className={`p-6 ${showCalendar ? "w-1/2 border-r border-gray-200" : "w-full"}`}>
          <h2 className="mb-4 text-lg font-bold">新增預約</h2>

          {error && (
            <div className="mb-3 rounded-lg bg-red-50 p-2 text-sm text-red-600">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">
                個案 <span className="text-red-500">*</span>
              </span>
              <select
                required
                value={form.case_id}
                onChange={(e) => setField("case_id", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              >
                <option value="">請選擇</option>
                {cases.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">諮商類型</span>
              <select
                value={form.session_type}
                onChange={(e) => setField("session_type", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              >
                <option value="in_person">現場</option>
                <option value="online">線上</option>
                <option value="home_visit">到宅</option>
              </select>
            </label>

            {form.session_type === "in_person" && (
              <label className="block">
                <span className="mb-1 block text-xs text-gray-500">
                  空間 <span className="text-red-500">*</span>
                </span>
                <select
                  required={form.session_type === "in_person"}
                  value={form.room_id}
                  onChange={(e) => setField("room_id", e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                >
                  <option value="">請選擇</option>
                  {rooms.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name} ({r.room_code})
                    </option>
                  ))}
                </select>
              </label>
            )}

            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">
                日期 <span className="text-red-500">*</span>
              </span>
              <input
                required
                type="date"
                value={form.start_date}
                onChange={(e) => setField("start_date", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="mb-1 block text-xs text-gray-500">
                  開始時間
                </span>
                <input
                  required
                  type="time"
                  value={form.start_time}
                  onChange={(e) => setField("start_time", e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs text-gray-500">
                  結束時間
                </span>
                <input
                  required
                  type="time"
                  value={form.end_time}
                  onChange={(e) => setField("end_time", e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                />
              </label>
            </div>

            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">
                金額 <span className="text-red-500">*</span>
              </span>
              <input
                required
                type="number"
                value={form.amount}
                onChange={(e) => setField("amount", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </label>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
              >
                取消
              </button>
              <button
                type="submit"
                disabled={saving}
                className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
              >
                {saving ? "儲存中..." : "儲存"}
              </button>
            </div>
          </form>
        </div>

        {showCalendar && (
          <div className="w-1/2 p-4">
            <RoomMiniCalendar
              token={token}
              roomId={selectedRoom.id}
              roomName={selectedRoom.name}
              focusDate={form.start_date || undefined}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function BatchForm({
  token,
  onClose,
  onSaved,
}: {
  token: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [cases, setCases] = useState<CaseOption[]>([]);
  const [rooms, setRooms] = useState<RoomOption[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [form, setForm] = useState({
    case_id: "",
    room_id: "",
    session_type: "in_person",
    amount: "2000",
  });
  const [slots, setSlots] = useState([
    { date: "", start: "10:00", end: "11:00" },
  ]);

  useEffect(() => {
    clientFetch("/cases", token).then(setCases).catch(() => {});
    clientFetch("/rooms", token).then(setRooms).catch(() => {});
  }, [token]);

  const setField = (key: string, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const addSlot = () =>
    setSlots((prev) => [...prev, { date: "", start: "10:00", end: "11:00" }]);

  const removeSlot = (i: number) =>
    setSlots((prev) => prev.filter((_, idx) => idx !== i));

  const updateSlot = (i: number, key: string, value: string) =>
    setSlots((prev) =>
      prev.map((s, idx) => (idx === i ? { ...s, [key]: value } : s)),
    );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await clientFetch("/appointments/batch", token, {
        method: "POST",
        body: JSON.stringify({
          case_id: parseInt(form.case_id),
          room_id: form.room_id ? parseInt(form.room_id) : null,
          session_type: form.session_type,
          amount: parseFloat(form.amount),
          slots: slots.map((s) => ({
            start_time: `${s.date}T${s.start}:00+08:00`,
            end_time: `${s.date}T${s.end}:00+08:00`,
          })),
        }),
      });
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const selectedRoom = rooms.find((r) => String(r.id) === form.room_id);
  const showCalendar = form.session_type === "in_person" && selectedRoom;
  const firstSlotDate = slots.find((s) => s.date)?.date;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div
        className={`flex rounded-xl bg-white shadow-xl transition-all ${
          showCalendar ? "w-full max-w-5xl" : "w-full max-w-lg"
        }`}
      >
        <div className={`p-6 ${showCalendar ? "w-1/2 border-r border-gray-200" : "w-full"}`}>
          <h2 className="mb-4 text-lg font-bold">批次預約</h2>

          {error && (
            <div className="mb-3 rounded-lg bg-red-50 p-2 text-sm text-red-600">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">
                個案 <span className="text-red-500">*</span>
              </span>
              <select
                required
                value={form.case_id}
                onChange={(e) => setField("case_id", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              >
                <option value="">請選擇</option>
                {cases.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="mb-1 block text-xs text-gray-500">
                  諮商類型
                </span>
                <select
                  value={form.session_type}
                  onChange={(e) => setField("session_type", e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                >
                  <option value="in_person">現場</option>
                  <option value="online">線上</option>
                  <option value="home_visit">到宅</option>
                </select>
              </label>
              {form.session_type === "in_person" && (
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">空間</span>
                  <select
                    value={form.room_id}
                    onChange={(e) => setField("room_id", e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  >
                    <option value="">請選擇</option>
                    {rooms.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name} ({r.room_code})
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>

            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">
                預設金額 <span className="text-red-500">*</span>
              </span>
              <input
                required
                type="number"
                value={form.amount}
                onChange={(e) => setField("amount", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </label>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-medium text-gray-500">
                  時段 ({slots.length})
                </span>
                <button
                  type="button"
                  onClick={addSlot}
                  className="text-xs text-primary-600 hover:underline"
                >
                  + 新增時段
                </button>
              </div>
              <div className="max-h-48 space-y-2 overflow-y-auto">
                {slots.map((slot, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input
                      required
                      type="date"
                      value={slot.date}
                      onChange={(e) => updateSlot(i, "date", e.target.value)}
                      className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
                    />
                    <input
                      required
                      type="time"
                      value={slot.start}
                      onChange={(e) => updateSlot(i, "start", e.target.value)}
                      className="w-24 rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
                    />
                    <span className="text-gray-400">~</span>
                    <input
                      required
                      type="time"
                      value={slot.end}
                      onChange={(e) => updateSlot(i, "end", e.target.value)}
                      className="w-24 rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
                    />
                    {slots.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removeSlot(i)}
                        className="text-red-400 hover:text-red-600"
                      >
                        x
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
              >
                取消
              </button>
              <button
                type="submit"
                disabled={saving}
                className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
              >
                {saving ? "建立中..." : `建立 ${slots.length} 筆預約`}
              </button>
            </div>
          </form>
        </div>

        {showCalendar && (
          <div className="w-1/2 p-4">
            <RoomMiniCalendar
              token={token}
              roomId={selectedRoom.id}
              roomName={selectedRoom.name}
              focusDate={firstSlotDate || undefined}
            />
          </div>
        )}
      </div>
    </div>
  );
}
