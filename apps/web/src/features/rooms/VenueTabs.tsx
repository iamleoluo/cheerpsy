"use client";

import { useCallback, useEffect, useState } from "react";
import { clientFetch } from "@/lib/client-api";
import { Button } from "@/components/ui";
import type { Appointment, VenueRental, HallBooking, FeeItem, Room } from "./types";
import { NO_SHOW_REASONS, PAYER_LABEL, sessionTypeLabel, toLocalDateString } from "./types";

/**
 * 場地租借與 5F 雲燈教室分頁 — 從 rooms/page.tsx 搬出（11 §4.2）。
 *
 * 這兩者跟一般預約一樣會佔用空間，但走各自的資料表（venue_rentals /
 * hall_bookings），所以在診間日曆上是獨立分頁而不是混進同一張表。
 */

function StepDot({ done, active, label }: { done: boolean; active: boolean; label: string }) {
  return (
    <span className={`flex items-center gap-1 rounded px-1.5 py-0.5 ${done ? "bg-st-done-bg text-st-done" : active ? "bg-st-warn-bg text-st-warn" : "bg-surface-3 text-ink-3"}`}>
      {done ? "✓" : "·"} {label}
    </span>
  );
}

/* ═══════════════════════════════════════════════
   場地租借分頁（06 P6、v7 預約作業 b4）
   佔用實體診間，所以衝突檢查跟一般預約是同一套
   ═══════════════════════════════════════════════ */

export function RentalsTab({ token, date }: { token: string; date: Date }) {
  const [rows, setRows] = useState<VenueRental[]>([]);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    const start = new Date(date);
    const end = new Date(date);
    end.setDate(end.getDate() + 30);
    clientFetch(
      `/venues?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`,
      token,
    )
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [token, date, tick]);

  async function setAttendance(id: number, attendance: "arrived" | "no_show") {
    await clientFetch(`/venues/${id}/attendance`, token, {
      method: "PUT",
      body: JSON.stringify({ attendance }),
    });
    setTick((t) => t + 1);
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-xs text-ink-3">自 {toLocalDateString(date)} 起 30 天內的場地租借</p>
        <button onClick={() => setShowCreate(true)} className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-st-active">
          ＋ 新增場地租借
        </button>
      </div>

      {loading && <p className="text-sm text-ink-3">載入中…</p>}
      {!loading && rows.length === 0 && (
        <div className="rounded-xl border border-dashed border-line py-12 text-center text-sm text-ink-3">此期間沒有場地租借</div>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-xs">
            <thead className="bg-surface-2 text-left text-ink-3">
              <tr>
                <th className="px-3 py-2">單號</th>
                <th className="px-3 py-2">時間</th>
                <th className="px-3 py-2">診間</th>
                <th className="px-3 py-2">借用人／單位</th>
                <th className="px-3 py-2">用途</th>
                <th className="px-3 py-2">場地費</th>
                <th className="px-3 py-2">付款方</th>
                <th className="px-3 py-2">出席</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((v) => (
                <tr key={v.id} className={`border-t border-line ${v.status === "cancelled" ? "text-st-muted line-through" : ""}`}>
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-ink-3">{v.rental_no}</td>
                  <td className="whitespace-nowrap px-3 py-2">
                    {v.start_time?.slice(5, 10)} {v.start_time?.slice(11, 16)}–{v.end_time?.slice(11, 16)}
                  </td>
                  <td className="px-3 py-2">{v.room_name ?? "—"}</td>
                  <td className="px-3 py-2">
                    {v.renter_name}
                    {v.supervision_fee_mode && (
                      <span className="ml-1 rounded bg-surface-3 text-ink-2 px-1.5 py-0.5 text-[10px]">
                        督導模式 {v.supervision_fee_mode}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-ink-3">{v.purpose ?? "—"}</td>
                  <td className="whitespace-nowrap px-3 py-2">${v.amount.toLocaleString()}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-ink-3">{PAYER_LABEL[v.payer] ?? v.payer}</td>
                  <td className="whitespace-nowrap px-3 py-2">
                    {v.attendance === "pending" ? (
                      <span className="flex gap-1">
                        <button onClick={() => setAttendance(v.id, "arrived")} className="rounded border border-line px-1.5 py-0.5 hover:bg-surface-2">已到</button>
                        <button onClick={() => setAttendance(v.id, "no_show")} className="rounded border border-line px-1.5 py-0.5 hover:bg-surface-2">未到</button>
                      </span>
                    ) : v.attendance === "arrived" ? (
                      <span className="text-st-done">已到</span>
                    ) : (
                      <span className="text-st-danger">未到 · 改自付</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <CreateRentalModal token={token} date={date} onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); setTick((t) => t + 1); }} />
      )}
    </div>
  );
}

function CreateRentalModal({
  token, date, onClose, onCreated,
}: { token: string; date: Date; onClose: () => void; onCreated: () => void }) {
  const [rooms, setRooms] = useState<Room[]>([]);
  const [institutions, setInstitutions] = useState<{ id: number; name: string }[]>([]);
  const [therapists, setTherapists] = useState<{ id: number; name: string }[]>([]);
  const [roomId, setRoomId] = useState("");
  const [day, setDay] = useState(toLocalDateString(date));
  const [startH, setStartH] = useState("14:00");
  const [endH, setEndH] = useState("16:00");
  const [renterKind, setRenterKind] = useState("institution");
  const [institutionId, setInstitutionId] = useState("");
  const [therapistId, setTherapistId] = useState("");
  const [renterName, setRenterName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [mode, setMode] = useState("");
  const [amount, setAmount] = useState("1200");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    clientFetch("/rooms", token).then(setRooms).catch(() => {});
    clientFetch("/institutions", token).then(setInstitutions).catch(() => {});
    clientFetch("/auth/therapists", token).then(setTherapists).catch(() => {});
  }, [token]);

  // 督導模式 A：櫃台代收督導費並開收據，場地費自動 $0（不跟心理師收兩次）
  const feeDisabled = mode === "A";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await clientFetch("/venues", token, {
        method: "POST",
        body: JSON.stringify({
          room_id: Number(roomId),
          start_time: new Date(`${day}T${startH}:00`).toISOString(),
          end_time: new Date(`${day}T${endH}:00`).toISOString(),
          renter_kind: renterKind,
          renter_name: renterKind === "private"
            ? (therapists.find((t) => String(t.id) === therapistId)?.name ?? renterName)
            : (institutions.find((i) => String(i.id) === institutionId)?.name ?? renterName),
          institution_id: renterKind === "institution" ? Number(institutionId) : null,
          renter_therapist_id: renterKind === "private" ? Number(therapistId) : null,
          supervision_fee_mode: mode || null,
          purpose: purpose || null,
          amount: feeDisabled ? 0 : Number(amount),
        }),
      });
      onCreated();
    } catch (e: any) {
      setError(e.message ?? "建立失敗");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div className="max-h-[88vh] w-[460px] overflow-y-auto rounded-xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 font-semibold">新增場地租借</h3>
        {error && <div className="mb-3 rounded-lg bg-st-danger-bg px-3 py-2 text-xs text-st-danger">{error}</div>}
        <form onSubmit={submit} className="space-y-3 text-sm">
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">診間 <span className="text-st-danger">*</span></span>
            <select required value={roomId} onChange={(e) => setRoomId(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2">
              <option value="">請選擇</option>
              {rooms.map((r) => <option key={r.id} value={r.id}>{r.name}（{r.floor}F）</option>)}
            </select>
          </label>
          <div className="grid grid-cols-3 gap-2">
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">日期</span>
              <input type="date" value={day} onChange={(e) => setDay(e.target.value)} className="w-full rounded-lg border border-line-2 px-2 py-2" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">起</span>
              <input type="time" value={startH} onChange={(e) => setStartH(e.target.value)} className="w-full rounded-lg border border-line-2 px-2 py-2" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">迄</span>
              <input type="time" value={endH} onChange={(e) => setEndH(e.target.value)} className="w-full rounded-lg border border-line-2 px-2 py-2" />
            </label>
          </div>
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">借用類型</span>
            <select value={renterKind} onChange={(e) => setRenterKind(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2">
              <option value="institution">機構借用（場地費進機構應收）</option>
              <option value="private">心理師個人借用（從當月酬勞扣回）</option>
            </select>
          </label>
          {renterKind === "institution" ? (
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">借用單位 <span className="text-st-danger">*</span></span>
              <select required value={institutionId} onChange={(e) => setInstitutionId(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2">
                <option value="">請選擇</option>
                {institutions.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
              </select>
            </label>
          ) : (
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">借用心理師 <span className="text-st-danger">*</span></span>
              <select required value={therapistId} onChange={(e) => setTherapistId(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2">
                <option value="">請選擇</option>
                {therapists.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </label>
          )}
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">用途</span>
              <input value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="督導 / 團體 / 會議" className="w-full rounded-lg border border-line-2 px-3 py-2" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">督導收費模式</span>
              <select value={mode} onChange={(e) => setMode(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2">
                <option value="">非督導場次</option>
                <option value="A">A · 櫃台代收、開收據</option>
                <option value="B">B · 心理師自收、場地費回扣</option>
              </select>
            </label>
          </div>
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">場地費</span>
            <input
              type="number" value={feeDisabled ? "0" : amount} disabled={feeDisabled}
              onChange={(e) => setAmount(e.target.value)}
              className="w-full rounded-lg border border-line-2 px-3 py-2 disabled:bg-surface-3 disabled:text-ink-3"
            />
            {feeDisabled && (
              <span className="mt-1 block text-[11px] text-ink-3">
                模式 A 由櫃台代收督導費並開立收據，場地費自動為 $0（不重複收）
              </span>
            )}
          </label>
          <div className="flex gap-2 pt-1">
            <button type="submit" disabled={saving} className="flex-1 rounded-lg bg-accent py-2 font-medium text-white hover:bg-st-active disabled:opacity-50">
              {saving ? "建立中…" : "建立"}
            </button>
            <button type="button" onClick={onClose} className="rounded-lg border border-line px-4 py-2 text-ink-3 hover:bg-surface-2">取消</button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════
   5F 雲燈教室分頁（06 P6、v7 預約作業 n4）
   場佈時段與活動時段分開記；不掛在 rooms 底下
   ═══════════════════════════════════════════════ */

export function HallTab({ token, date }: { token: string; date: Date }) {
  const [rows, setRows] = useState<HallBooking[]>([]);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    const start = new Date(date);
    const end = new Date(date);
    end.setDate(end.getDate() + 60);
    clientFetch(
      `/venues/hall?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`,
      token,
    )
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [token, date, tick]);

  async function setStatus(id: number, status: string) {
    await clientFetch(`/venues/hall/${id}/status`, token, { method: "PUT", body: JSON.stringify({ status }) });
    setTick((t) => t + 1);
  }

  return (
    <div>
      <p className="mb-3 text-xs text-ink-3">自 {toLocalDateString(date)} 起 60 天內的雲燈教室借用</p>
      {loading && <p className="text-sm text-ink-3">載入中…</p>}
      {!loading && rows.length === 0 && (
        <div className="rounded-xl border border-dashed border-line py-12 text-center text-sm text-ink-3">此期間沒有借用紀錄</div>
      )}
      <div className="space-y-2">
        {rows.map((h) => (
          <div key={h.id} className={`rounded-lg border p-3 ${h.status === "cancelled" ? "border-line bg-surface-2 text-ink-3" : "border-line bg-white"}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-medium">{h.title}</span>
                <span className={`rounded px-1.5 py-0.5 text-[10px] ${
                  h.status === "executed" ? "bg-st-done-bg text-st-done"
                    : h.status === "cancelled" ? "bg-surface-3 text-ink-3"
                    : "bg-st-warn-bg text-st-warn"
                }`}>
                  {h.status === "executed" ? "已執行" : h.status === "cancelled" ? "已取消" : "已排定"}
                </span>
              </div>
              {h.status === "scheduled" && (
                <div className="flex gap-1 text-xs">
                  <button onClick={() => setStatus(h.id, "executed")} className="rounded border border-line px-2 py-0.5 hover:bg-surface-2">標記已執行</button>
                  <button onClick={() => setStatus(h.id, "cancelled")} className="rounded border border-line px-2 py-0.5 text-ink-3 hover:bg-surface-2">取消</button>
                </div>
              )}
            </div>
            <div className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs text-ink-3 md:grid-cols-4">
              <div>活動：{h.event_start?.slice(5, 10)} {h.event_start?.slice(11, 16)}–{h.event_end?.slice(11, 16)}</div>
              <div>場佈：{h.setup_start ? `${h.setup_start.slice(11, 16)}–${h.setup_end?.slice(11, 16)}` : "—"}</div>
              <div>
                講師：{h.lecturer_name ?? "—"}
                <span className="ml-1 text-ink-3">（{h.lecturer_kind === "internal" ? "所內" : "外聘"}）</span>
              </div>
              <div>借用：{h.borrower ?? "—"}{h.attendee_count ? ` · ${h.attendee_count} 人` : ""}</div>
              <div className="col-span-2">
                講師費：{h.lecturer_fee != null ? `$${h.lecturer_fee.toLocaleString()}` : "—"}
                <span className={`ml-1 rounded px-1.5 py-0.5 text-[10px] ${h.fee_to_clinic_account ? "bg-accent-soft text-accent" : "bg-surface-3 text-ink-3"}`}>
                  {h.fee_to_clinic_account ? "入慈恩帳戶" : "主辦方直付講師"}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

