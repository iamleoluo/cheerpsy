"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { clientFetch } from "@/lib/client-api";
import type { Appointment, CaseItem, QuotaRow, RoomOption, Therapist } from "@/features/shared/types";
import { sessionTypeLabels } from "@/features/shared/labels";
import { fmtDate, fmtTime } from "@/features/shared/format";

/* @token-guard legacy — P3 從舊路由原樣搬入，尚未換語意 token（11 §2.2） */
/** 預約編輯視窗 — 從 cases/page.tsx 搬出（11 §4.2）。 */

export function AppointmentEditModal({
  token, appt, onClose, onDone,
}: {
  token: string; appt: Appointment; onClose: () => void; onDone: () => void;
}) {
  const [rooms, setRooms] = useState<RoomOption[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [sessionType, setSessionType] = useState(appt.session_type);
  const [roomId, setRoomId] = useState(appt.room_id ? String(appt.room_id) : "");
  const [startDate, setStartDate] = useState(appt.start_time?.slice(0, 10) ?? "");
  const [startTime, setStartTime] = useState(appt.start_time?.slice(11, 16) ?? "");
  const [endTime, setEndTime] = useState(appt.end_time?.slice(11, 16) ?? "");
  const [amount, setAmount] = useState(String(appt.amount));

  useEffect(() => {
    clientFetch("/rooms", token).then(setRooms).catch(() => {});
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const body: Record<string, unknown> = {
        session_type: sessionType,
        room_id: roomId ? parseInt(roomId) : null,
        amount: parseFloat(amount),
      };
      if (startDate && startTime) {
        body.start_time = `${startDate}T${startTime}:00+08:00`;
      }
      if (startDate && endTime) {
        body.end_time = `${startDate}T${endTime}:00+08:00`;
      }
      await clientFetch(`/appointments/${appt.id}`, token, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      onDone();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-[480px] rounded-lg bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 text-base font-semibold">編輯預約 #{appt.appointment_number}</h3>
        <p className="mb-4 text-xs text-gray-500">個案：{appt.case_name}　心理師：{appt.therapist_name}（唯讀）</p>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className={`grid gap-3 ${sessionType === "in_person" ? "grid-cols-2" : "grid-cols-1"}`}>
            <label className="block">
              <span className="text-xs font-medium text-gray-700">類型</span>
              <select value={sessionType} onChange={(e) => { setSessionType(e.target.value); if (e.target.value !== "in_person") setRoomId(""); }} className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                <option value="in_person">現場</option>
                <option value="online">線上</option>
                <option value="outdoor">外出</option>
              </select>
            </label>
            {sessionType === "in_person" && (
              <label className="block">
                <span className="text-xs font-medium text-gray-700">診間</span>
                <select value={roomId} onChange={(e) => setRoomId(e.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                  <option value="">— 不指定 —</option>
                  {rooms.map((r) => (
                    <option key={r.id} value={r.id}>{r.name}（{r.room_code}）</option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <label className="block">
            <span className="text-xs font-medium text-gray-700">日期</span>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-xs font-medium text-gray-700">開始時間</span>
              <input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-gray-700">結束時間</span>
              <input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            </label>
          </div>
          <label className="block">
            <span className="text-xs font-medium text-gray-700">費用</span>
            <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          </label>
          {error && <p className="text-xs text-red-600">{error}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">取消</button>
            <button type="submit" disabled={saving} className="rounded bg-primary-600 px-4 py-2 text-sm text-white hover:bg-primary-700 disabled:opacity-50">
              {saving ? "儲存中..." : "儲存"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   Tab 3: 機構額度（Quota）
   ═══════════════════════════════════════════════════ */

