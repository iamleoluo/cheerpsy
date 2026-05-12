"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

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

export default function RemindersPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;

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
    if (!token) return;
    setLoading(true);
    try {
      const data = await clientFetch(`/reminders/upcoming?days=${days}`, token);
      setAppointments(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [token, days]);

  useEffect(() => {
    fetchAppointments();
  }, [fetchAppointments]);

  const showLogs = async (appointmentId: number, appointmentNumber: string) => {
    if (!token) return;
    setLogModal({ appointmentId, appointmentNumber });
    try {
      const data = await clientFetch(`/reminders/logs/${appointmentId}`, token);
      setLogs(data);
    } catch {
      setLogs([]);
    }
  };

  const handleAddReminder = async () => {
    if (!addModal || !token) return;
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

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">預約提醒 / 電訪追蹤</h1>
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-500">未來</label>
          <select value={days} onChange={(e) => setDays(parseInt(e.target.value))} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
            <option value={1}>1 天</option>
            <option value={2}>2 天</option>
            <option value={3}>3 天</option>
            <option value={5}>5 天</option>
            <option value={7}>7 天</option>
            <option value={14}>14 天</option>
          </select>
          <span className="text-sm text-gray-500">的預約</span>
        </div>
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
              <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-400">載入中...</td></tr>
            ) : appointments.length === 0 ? (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-400">目前無需提醒的預約</td></tr>
            ) : (
              appointments.map((a) => (
                <tr key={a.appointment_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-xs">
                    {a.start_time ? new Date(a.start_time).toLocaleString("zh-TW", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "-"}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{a.appointment_number}</td>
                  <td className="px-4 py-3 font-medium">{a.case_name ?? "-"}</td>
                  <td className="px-4 py-3 text-xs">{a.case_phone ?? "-"}</td>
                  <td className="px-4 py-3">{a.therapist_name ?? "-"}</td>
                  <td className="px-4 py-3">{sessionTypeLabels[a.session_type] ?? a.session_type}</td>
                  <td className="px-4 py-3">
                    {a.last_contact_result ? (
                      <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${contactResultColors[a.last_contact_result] ?? "bg-gray-100"}`}>
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
                <select value={formResult} onChange={(e) => setFormResult(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
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
              <button onClick={() => { setAddModal(null); setFormNotes(""); }} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">取消</button>
              <button onClick={handleAddReminder} disabled={saving} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">
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
            <h2 className="mb-4 text-lg font-bold">聯繫歷史 — {logModal.appointmentNumber}</h2>
            {logs.length === 0 ? (
              <p className="text-sm text-gray-400">無聯繫紀錄</p>
            ) : (
              <div className="max-h-80 space-y-3 overflow-y-auto">
                {logs.map((l) => (
                  <div key={l.id} className="rounded-lg border border-gray-200 p-3">
                    <div className="flex items-center justify-between">
                      <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${contactResultColors[l.contact_result] ?? "bg-gray-100"}`}>
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
              <button onClick={() => setLogModal(null)} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">關閉</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
