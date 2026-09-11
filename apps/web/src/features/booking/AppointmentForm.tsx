"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { clientFetch } from "@/lib/client-api";
import RoomMiniCalendar from "@/components/room-mini-calendar";
import type { Appointment, CaseItem, QuotaRow, RoomOption, Therapist } from "@/features/shared/types";
import { sessionTypeLabels } from "@/features/shared/labels";
import { fmtDate, fmtTime } from "@/features/shared/format";

/* @token-guard legacy — P3 從舊路由原樣搬入，尚未換語意 token（11 §2.2） */
/**
 * 單筆預約表單 — 從 cases/page.tsx 搬出（V2升級計畫 11 §4.2）。
 *
 * 搬出來的理由：它原本擠在個案路由裡，只因為資料庫的 appointments 掛在 case
 * 底下。但預約屬於**排程**，不屬於個案管理；而且 /booking 另外還有一份 293 行
 * 的預約表單並行——那份的檔頭註解自己就寫著「沿用 /cases 頁既有的
 * AppointmentForm」。搬到這裡之後兩邊共用同一份。
 */

export function AppointmentForm({
  token, fixedCaseId, fixedCaseName, onClose, onSaved,
}: {
  token: string; fixedCaseId?: number; fixedCaseName?: string; onClose: () => void; onSaved: () => void;
}) {
  const [cases, setCases] = useState<{ id: number; name: string; therapist_id: number; case_type?: string; members?: { case_id: number; name: string }[] | null }[]>([]);
  const [therapists, setTherapists] = useState<Therapist[]>([]);
  const [rooms, setRooms] = useState<RoomOption[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    case_id: fixedCaseId?.toString() ?? "",
    room_id: "",
    session_type: "in_person",
    start_date: "",
    start_time: "10:00",
    end_time: "11:00",
    amount: "2000",
    funding_source: "self_pay",
    quota_id: "",
  });
  const [payerCaseId, setPayerCaseId] = useState("");
  const [availableQuotas, setAvailableQuotas] = useState<QuotaRow[]>([]);

  // 合療付款方：選到伴侶案時，billingCaseId 改為付款方（伴侶案本身或某成員）
  const selectedCase = cases.find((c) => String(c.id) === form.case_id);
  const isCouple = selectedCase?.case_type === "couple";
  const billingCaseId = isCouple ? (payerCaseId || (selectedCase ? String(selectedCase.id) : "")) : form.case_id;

  useEffect(() => {
    clientFetch("/auth/therapists", token).then(setTherapists).catch(() => {});
    clientFetch("/rooms", token).then(setRooms).catch(() => {});
    if (fixedCaseId) {
      clientFetch(`/cases/${fixedCaseId}`, token).then((c) => setCases([c])).catch(() => {});
    } else {
      clientFetch("/cases", token).then(setCases).catch(() => {});
    }
  }, [token, fixedCaseId]);

  useEffect(() => {
    if (form.funding_source !== "institution" || !billingCaseId || !form.start_date) {
      setAvailableQuotas([]);
      return;
    }
    clientFetch(
      `/cases/${billingCaseId}/quotas/available?on_date=${form.start_date}`,
      token,
    )
      .then((rows: QuotaRow[]) => {
        setAvailableQuotas(rows);
        setForm((prev) => {
          if (prev.quota_id && rows.some((r) => r.id === Number(prev.quota_id))) return prev;
          return { ...prev, quota_id: rows[0] ? String(rows[0].id) : "" };
        });
      })
      .catch(() => setAvailableQuotas([]));
  }, [token, form.funding_source, billingCaseId, form.start_date]);

  // Resolve a case's therapist base price (default 2000 if unset)
  const basePriceFor = (caseId: string) => {
    const c = cases.find((x) => String(x.id) === caseId);
    if (!c) return null;
    const t = therapists.find((x) => x.id === c.therapist_id);
    const bp = t?.base_price;
    return bp != null ? String(bp) : "2000";
  };

  // Auto-fill amount when the selected case (and therefore therapist) resolves
  useEffect(() => {
    if (!form.case_id || cases.length === 0 || therapists.length === 0) return;
    const bp = basePriceFor(form.case_id);
    if (bp != null) setForm((prev) => ({ ...prev, amount: bp }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.case_id, cases, therapists]);

  const sf = (key: string, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      if (form.funding_source === "institution" && !form.quota_id) {
        setError("請選擇機構 Quota，或改回自費");
        setSaving(false);
        return;
      }
      await clientFetch("/appointments", token, {
        method: "POST",
        body: JSON.stringify({
          case_id: parseInt(billingCaseId),
          couple_case_id: isCouple && selectedCase ? selectedCase.id : null,
          room_id: form.room_id ? parseInt(form.room_id) : null,
          session_type: form.session_type,
          start_time: `${form.start_date}T${form.start_time}:00+08:00`,
          end_time: `${form.start_date}T${form.end_time}:00+08:00`,
          amount: parseFloat(form.amount),
          funding_source: form.funding_source,
          quota_id: form.funding_source === "institution" && form.quota_id
            ? Number(form.quota_id)
            : null,
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
      <div className={`flex rounded-xl bg-white shadow-xl transition-all ${showCalendar ? "w-full max-w-4xl" : "w-full max-w-md"}`}>
        <div className={`p-6 ${showCalendar ? "w-1/2 border-r border-line" : "w-full"}`}>
          <h2 className="mb-4 text-lg font-bold">新增預約{fixedCaseName ? ` — ${fixedCaseName}` : ""}</h2>
          {error && <div className="mb-3 rounded-lg bg-st-danger-bg p-2 text-sm text-st-danger">{error}</div>}
          <form onSubmit={handleSubmit} className="space-y-3">
            {!fixedCaseId && (
              <label className="block">
                <span className="mb-1 block text-xs text-ink-3">個案 <span className="text-st-danger">*</span></span>
                <select required value={form.case_id} onChange={(e) => { sf("case_id", e.target.value); setPayerCaseId(""); }} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
                  <option value="">請選擇</option>
                  {cases.map((c) => <option key={c.id} value={c.id}>{c.case_type === "couple" ? "👫 " : ""}{c.name}</option>)}
                </select>
              </label>
            )}
            {isCouple && (
              <label className="block">
                <span className="mb-1 block text-xs text-ink-3">付款方（誰付款）<span className="text-st-danger">*</span></span>
                <select value={billingCaseId} onChange={(e) => setPayerCaseId(e.target.value)} className="w-full rounded-lg border border-st-danger/30 bg-st-danger-bg px-3 py-2 text-sm">
                  <option value={selectedCase!.id}>伴侶案（自費合計）</option>
                  {(selectedCase!.members ?? []).map((m) => (
                    <option key={m.case_id} value={m.case_id}>{m.name}（機構請選此，扣其扣打）</option>
                  ))}
                </select>
                <span className="mt-1 block text-xs text-ink-3">機構合療請選某位成員，費用記在他名下、扣他的機構扣打。</span>
              </label>
            )}
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">諮商類型</span>
              <select value={form.session_type} onChange={(e) => sf("session_type", e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
                <option value="in_person">現場</option>
                <option value="online">線上</option>
                <option value="outdoor">外出</option>
              </select>
            </label>
            {form.session_type === "in_person" && (
              <label className="block">
                <span className="mb-1 block text-xs text-ink-3">診間 <span className="text-st-danger">*</span></span>
                <select required={form.session_type === "in_person"} value={form.room_id} onChange={(e) => sf("room_id", e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
                  <option value="">請選擇</option>
                  {rooms.map((r) => <option key={r.id} value={r.id}>{r.name} ({r.room_code})</option>)}
                </select>
              </label>
            )}
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">日期 <span className="text-st-danger">*</span></span>
              <input required type="date" value={form.start_date} onChange={(e) => sf("start_date", e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="mb-1 block text-xs text-ink-3">開始時間</span>
                <input required type="time" value={form.start_time} onChange={(e) => sf("start_time", e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs text-ink-3">結束時間</span>
                <input required type="time" value={form.end_time} onChange={(e) => sf("end_time", e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
              </label>
            </div>
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">金額 <span className="text-st-danger">*</span></span>
              <input required type="number" value={form.amount} onChange={(e) => sf("amount", e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
            </label>
            <div>
              <span className="mb-1 block text-xs text-ink-3">付款方式</span>
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
                <span className="mb-1 block text-xs text-ink-3">機構 Quota <span className="text-st-danger">*</span></span>
                <select
                  required
                  value={form.quota_id}
                  onChange={(e) => sf("quota_id", e.target.value)}
                  className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm"
                >
                  <option value="">{availableQuotas.length === 0 ? "該日無可用 Quota" : "請選擇"}</option>
                  {availableQuotas.map((q) => (
                    <option key={q.id} value={q.id}>
                      {q.institution_name}｜剩餘 {q.remaining}（預約 {q.reserved_count ?? 0}）/{q.total_count}｜到期 {q.valid_until ?? "永久"}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={onClose} className="rounded-lg border border-line-2 px-4 py-2 text-sm hover:bg-surface-2">取消</button>
              <button type="submit" disabled={saving} className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-st-active disabled:opacity-50">{saving ? "儲存中..." : "儲存"}</button>
            </div>
          </form>
        </div>
        {showCalendar && (
          <div className="w-1/2 p-4">
            <RoomMiniCalendar token={token} roomId={selectedRoom.id} roomName={selectedRoom.name} focusDate={form.start_date || undefined} />
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   Batch Form (批次預約)
   ═══════════════════════════════════════════════════ */

