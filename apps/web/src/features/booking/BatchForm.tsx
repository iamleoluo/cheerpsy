"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { clientFetch } from "@/lib/client-api";
import RoomMiniCalendar from "@/components/room-mini-calendar";
import type { Appointment, CaseItem, QuotaRow, RoomOption, Therapist } from "@/features/shared/types";
import { sessionTypeLabels } from "@/features/shared/labels";
import { fmtDate, fmtTime } from "@/features/shared/format";

import {
  DOW_LABELS,
  WEEK_OF_MONTH_LABELS,
  formatPreviewDate,
  generateBiweeklySlots,
  generateMonthlySlots,
  generateWeeklySlots,
  isoDate,
} from "./recurrence";

/* @token-guard legacy — P3 從舊路由原樣搬入，尚未換語意 token（11 §2.2） */
/** 批次預約（週期性建約）— 從 cases/page.tsx 搬出（11 §4.2）。 */

export function BatchForm({
  token, fixedCaseId, fixedCaseName, onClose, onSaved,
}: {
  token: string; fixedCaseId?: number; fixedCaseName?: string; onClose: () => void; onSaved: () => void;
}) {
  const [cases, setCases] = useState<{ id: number; name: string; therapist_id: number; case_type?: string; members?: { case_id: number; name: string }[] | null }[]>([]);
  const [therapists, setTherapists] = useState<Therapist[]>([]);
  const [rooms, setRooms] = useState<RoomOption[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // base fields
  const [form, setForm] = useState({
    case_id: fixedCaseId?.toString() ?? "",
    room_id: "",
    session_type: "in_person",
    amount: "2000",
    funding_source: "self_pay",
    quota_id: "",
  });
  const [payerCaseId, setPayerCaseId] = useState("");
  const [allQuotas, setAllQuotas] = useState<QuotaRow[]>([]);

  // 合療付款方
  const selectedCase = cases.find((c) => String(c.id) === form.case_id);
  const isCouple = selectedCase?.case_type === "couple";
  const billingCaseId = isCouple ? (payerCaseId || (selectedCase ? String(selectedCase.id) : "")) : form.case_id;

  // recurrence settings
  const [recurrence, setRecurrence] = useState<"weekly" | "biweekly" | "monthly">("weekly");
  const [dow, setDow] = useState(3); // Wed
  const [weekOfMonth, setWeekOfMonth] = useState(1); // 1st
  const today = new Date();
  const [startDate, setStartDate] = useState(isoDate(today));
  const [startMonth, setStartMonth] = useState(
    `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`
  );
  const [startTime, setStartTime] = useState("10:00");
  const [endTime, setEndTime] = useState("11:00");
  const [count, setCount] = useState("8");

  // generated preview slots
  const [slots, setSlots] = useState<{ date: string; start: string; end: string }[] | null>(null);

  useEffect(() => {
    clientFetch("/auth/therapists", token).then(setTherapists).catch(() => {});
    clientFetch("/rooms", token).then(setRooms).catch(() => {});
    if (fixedCaseId) {
      clientFetch(`/cases/${fixedCaseId}`, token).then((c) => setCases([c])).catch(() => {});
    } else {
      clientFetch("/cases", token).then(setCases).catch(() => {});
    }
  }, [token, fixedCaseId]);

  const basePriceFor = (caseId: string) => {
    const c = cases.find((x) => String(x.id) === caseId);
    if (!c) return null;
    const t = therapists.find((x) => x.id === c.therapist_id);
    const bp = t?.base_price;
    return bp != null ? String(bp) : "2000";
  };

  useEffect(() => {
    if (!form.case_id || cases.length === 0 || therapists.length === 0) return;
    const bp = basePriceFor(form.case_id);
    if (bp != null) setForm((prev) => ({ ...prev, amount: bp }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.case_id, cases, therapists]);

  useEffect(() => {
    if (form.funding_source !== "institution" || !billingCaseId) {
      setAllQuotas([]);
      return;
    }
    clientFetch(`/cases/${billingCaseId}/quotas`, token)
      .then((rows: QuotaRow[]) => {
        const today = new Date().toISOString().slice(0, 10);
        const active = rows.filter(
          (r) => (!r.valid_until || r.valid_until >= today) && r.remaining > 0,
        );
        setAllQuotas(active);
        setForm((prev) => {
          if (prev.quota_id && active.some((r) => r.id === Number(prev.quota_id))) return prev;
          return { ...prev, quota_id: active[0] ? String(active[0].id) : "" };
        });
      })
      .catch(() => setAllQuotas([]));
  }, [token, form.funding_source, billingCaseId]);

  const sf = (key: string, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  const handleGenerate = () => {
    const n = Math.max(1, Math.min(52, parseInt(count) || 1));
    let generated: { date: string; start: string; end: string }[];
    if (recurrence === "weekly") {
      generated = generateWeeklySlots(dow, startDate, startTime, endTime, n);
    } else if (recurrence === "biweekly") {
      generated = generateBiweeklySlots(dow, startDate, startTime, endTime, n);
    } else {
      generated = generateMonthlySlots(dow, weekOfMonth, startMonth, startTime, endTime, n);
    }
    setSlots(generated);
    setError("");
  };

  const removeSlot = (i: number) => setSlots((prev) => prev ? prev.filter((_, idx) => idx !== i) : prev);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!slots || slots.length === 0) { setError("請先產生時段預覽"); return; }
    setSaving(true);
    setError("");
    try {
      if (form.funding_source === "institution" && !form.quota_id) {
        setError("請選擇機構 Quota，或改回自費");
        setSaving(false);
        return;
      }
      await clientFetch("/appointments/batch", token, {
        method: "POST",
        body: JSON.stringify({
          case_id: parseInt(billingCaseId),
          couple_case_id: isCouple && selectedCase ? selectedCase.id : null,
          room_id: form.room_id ? parseInt(form.room_id) : null,
          session_type: form.session_type,
          amount: parseFloat(form.amount),
          funding_source: form.funding_source,
          quota_id: form.funding_source === "institution" && form.quota_id
            ? Number(form.quota_id)
            : null,
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
  const showCalendar = form.session_type === "in_person" && selectedRoom && slots && slots.length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className={`flex max-h-[92vh] w-full rounded-xl bg-white shadow-xl ${showCalendar ? "max-w-5xl" : "max-w-lg"}`}>
        {/* left: settings + preview */}
        <div className={`flex flex-col overflow-hidden ${showCalendar ? "w-1/2 border-r border-gray-200" : "w-full"}`}>
          <div className="flex-1 overflow-y-auto p-6">
            <h2 className="mb-4 text-lg font-bold">批次預約{fixedCaseName ? ` — ${fixedCaseName}` : ""}</h2>
            {error && <div className="mb-3 rounded-lg bg-red-50 p-2 text-sm text-red-600">{error}</div>}

            <form id="batch-form" onSubmit={handleSubmit} className="space-y-4">
              {/* case */}
              {!fixedCaseId && (
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">個案 <span className="text-red-500">*</span></span>
                  <select required value={form.case_id} onChange={(e) => { sf("case_id", e.target.value); setPayerCaseId(""); }} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                    <option value="">請選擇</option>
                    {cases.map((c) => <option key={c.id} value={c.id}>{c.case_type === "couple" ? "👫 " : ""}{c.name}</option>)}
                  </select>
                </label>
              )}
              {isCouple && (
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">付款方（誰付款）<span className="text-red-500">*</span></span>
                  <select value={billingCaseId} onChange={(e) => setPayerCaseId(e.target.value)} className="w-full rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-sm">
                    <option value={selectedCase!.id}>伴侶案（自費合計）</option>
                    {(selectedCase!.members ?? []).map((m) => (
                      <option key={m.case_id} value={m.case_id}>{m.name}（機構請選此，扣其扣打）</option>
                    ))}
                  </select>
                </label>
              )}

              {/* session type + room */}
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">諮商類型</span>
                  <select value={form.session_type} onChange={(e) => { sf("session_type", e.target.value); setSlots(null); }} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                    <option value="in_person">現場</option>
                    <option value="online">線上</option>
                    <option value="outdoor">外出</option>
                  </select>
                </label>
                {form.session_type === "in_person" && (
                  <label className="block">
                    <span className="mb-1 block text-xs text-gray-500">診間</span>
                    <select value={form.room_id} onChange={(e) => sf("room_id", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                      <option value="">請選擇</option>
                      {rooms.map((r) => <option key={r.id} value={r.id}>{r.name} ({r.room_code})</option>)}
                    </select>
                  </label>
                )}
              </div>

              {/* amount */}
              <label className="block">
                <span className="mb-1 block text-xs text-gray-500">每次金額 <span className="text-red-500">*</span></span>
                <input required type="number" value={form.amount} onChange={(e) => sf("amount", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              </label>

              {/* funding source */}
              <div>
                <span className="mb-1 block text-xs text-gray-500">付款方式（套用全部時段）</span>
                <div className="flex gap-3 text-sm">
                  <label className="inline-flex items-center gap-1">
                    <input
                      type="radio"
                      checked={form.funding_source === "self_pay"}
                      onChange={() => setForm((p) => ({ ...p, funding_source: "self_pay", quota_id: "" }))}
                    />
                    自費
                  </label>
                  <label className="inline-flex items-center gap-1">
                    <input
                      type="radio"
                      checked={form.funding_source === "institution"}
                      onChange={() => setForm((p) => ({ ...p, funding_source: "institution" }))}
                    />
                    機構
                  </label>
                </div>
              </div>
              {form.funding_source === "institution" && (
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">機構 Quota <span className="text-red-500">*</span></span>
                  <select
                    required
                    value={form.quota_id}
                    onChange={(e) => sf("quota_id", e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  >
                    <option value="">{allQuotas.length === 0 ? "尚無有效 Quota" : "請選擇"}</option>
                    {allQuotas.map((q) => (
                      <option key={q.id} value={q.id}>
                        {q.institution_name}｜剩餘 {q.remaining}（預約 {q.reserved_count ?? 0}）/{q.total_count}｜到期 {q.valid_until ?? "永久"}
                      </option>
                    ))}
                  </select>
                  <p className="mt-1 text-xs text-amber-600">
                    注意：批次所有時段共用同一 Quota；若預約日超過該 Quota 期限或剩餘不足，後端會拒絕建立。
                  </p>
                </label>
              )}

              {/* recurrence panel */}
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 space-y-3">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">循環設定</p>

                {/* frequency toggle */}
                <div className="flex gap-1 rounded-lg border border-gray-200 bg-white p-1">
                  {(["weekly", "biweekly", "monthly"] as const).map((f) => (
                    <button
                      key={f}
                      type="button"
                      onClick={() => { setRecurrence(f); setSlots(null); }}
                      className={`flex-1 rounded-md py-1.5 text-sm font-medium transition-colors ${recurrence === f ? "bg-primary-600 text-white shadow-sm" : "text-gray-600 hover:bg-gray-100"}`}
                    >
                      {f === "weekly" ? "每週" : f === "biweekly" ? "每兩週" : "每月"}
                    </button>
                  ))}
                </div>

                {/* day of week picker — always shown */}
                <div>
                  <p className="mb-1.5 text-xs text-gray-500">
                    {recurrence === "monthly" ? "第幾個禮拜幾" : "星期幾"}
                  </p>
                  {recurrence === "monthly" && (
                    <div className="mb-2 flex flex-wrap gap-1">
                      {WEEK_OF_MONTH_LABELS.map((label, i) => {
                        const val = i === 4 ? -1 : i + 1;
                        return (
                          <button
                            key={i}
                            type="button"
                            onClick={() => { setWeekOfMonth(val); setSlots(null); }}
                            className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors ${weekOfMonth === val ? "border-primary-500 bg-primary-100 text-primary-700" : "border-gray-200 bg-white text-gray-600 hover:bg-gray-50"}`}
                          >
                            {label}
                          </button>
                        );
                      })}
                    </div>
                  )}
                  <div className="flex gap-1">
                    {DOW_LABELS.map((label, i) => (
                      <button
                        key={i}
                        type="button"
                        onClick={() => { setDow(i); setSlots(null); }}
                        className={`flex-1 rounded-lg border py-1.5 text-xs font-bold transition-colors ${dow === i ? "border-primary-500 bg-primary-500 text-white" : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50"}`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* time range */}
                <div className="flex items-center gap-2">
                  <div className="flex-1">
                    <p className="mb-1 text-xs text-gray-500">開始時間</p>
                    <input type="time" value={startTime} onChange={(e) => { setStartTime(e.target.value); setSlots(null); }} className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm" />
                  </div>
                  <span className="mt-4 text-gray-400">~</span>
                  <div className="flex-1">
                    <p className="mb-1 text-xs text-gray-500">結束時間</p>
                    <input type="time" value={endTime} onChange={(e) => { setEndTime(e.target.value); setSlots(null); }} className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm" />
                  </div>
                </div>

                {/* start + count */}
                <div className="flex items-end gap-3">
                  <div className="flex-1">
                    <p className="mb-1 text-xs text-gray-500">{recurrence === "monthly" ? "起始月份" : "起始日期"}</p>
                    {recurrence !== "monthly" ? (
                      <input type="date" value={startDate} onChange={(e) => { setStartDate(e.target.value); setSlots(null); }} className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm" />
                    ) : (
                      <input type="month" value={startMonth} onChange={(e) => { setStartMonth(e.target.value); setSlots(null); }} className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm" />
                    )}
                  </div>
                  <div className="w-24">
                    <p className="mb-1 text-xs text-gray-500">循環次數</p>
                    <div className="flex items-center gap-1">
                      <input
                        type="number"
                        min={1}
                        max={52}
                        value={count}
                        onChange={(e) => { setCount(e.target.value); setSlots(null); }}
                        className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm"
                      />
                      <span className="text-xs text-gray-400 whitespace-nowrap">次</span>
                    </div>
                  </div>
                </div>

                {/* generate button */}
                <button
                  type="button"
                  onClick={handleGenerate}
                  className="w-full rounded-lg bg-gray-800 py-2 text-sm font-medium text-white hover:bg-gray-700"
                >
                  產生時段預覽
                </button>
              </div>

              {/* slot preview */}
              {slots && (
                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs font-semibold text-gray-600">
                      預覽時段（共 {slots.length} 筆）
                    </span>
                    <span className="text-xs text-gray-400">點 ✕ 可移除個別時段</span>
                  </div>
                  {slots.length === 0 ? (
                    <p className="rounded-lg bg-yellow-50 px-3 py-2 text-xs text-yellow-700">所有時段已移除</p>
                  ) : (
                    <ul className="max-h-52 divide-y divide-gray-100 overflow-y-auto rounded-xl border border-gray-200 bg-white">
                      {slots.map((s, i) => (
                        <li key={i} className="flex items-center justify-between px-3 py-2">
                          <span className="text-sm text-gray-700">
                            <span className="font-medium">{formatPreviewDate(s.date)}</span>
                            <span className="ml-2 text-gray-400">{s.start} ~ {s.end}</span>
                          </span>
                          <button
                            type="button"
                            onClick={() => removeSlot(i)}
                            className="ml-2 text-xs text-gray-300 hover:text-red-500"
                          >
                            ✕
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </form>
          </div>

          {/* footer */}
          <div className="flex justify-end gap-2 border-t border-gray-200 px-6 py-4">
            <button type="button" onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">取消</button>
            <button
              form="batch-form"
              type="submit"
              disabled={saving || !slots || slots.length === 0}
              className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-40"
            >
              {saving ? "建立中..." : slots && slots.length > 0 ? `建立 ${slots.length} 筆預約` : "請先產生預覽"}
            </button>
          </div>
        </div>

        {/* right: room calendar */}
        {showCalendar && (
          <div className="w-1/2 overflow-y-auto p-4">
            <RoomMiniCalendar
              token={token}
              roomId={selectedRoom.id}
              roomName={selectedRoom.name}
              focusDate={slots[0]?.date || undefined}
            />
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   付款方式編輯 modal（既有預約改自費/機構）
   ═══════════════════════════════════════════════════ */

