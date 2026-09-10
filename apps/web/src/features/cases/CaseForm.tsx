"use client";

import React, { useCallback, useEffect, useState } from "react";
import { clientFetch } from "@/lib/client-api";
import type {
  Appointment,
  CaseItem,
  InstitutionItem,
  RoomOption,
  SessionRecord,
  Therapist,
} from "@/features/shared/types";
import {
  apptStatusColors,
  apptStatusLabels,
  billingLabels,
  sessionTypeLabels,
  statusColors,
  statusLabels,
} from "@/features/shared/labels";
import { caseDisplayId, fmtDate, fmtTime, visitId } from "@/features/shared/format";

/* @token-guard legacy — P3 從舊路由原樣搬入，尚未換語意 token（11 §2.2） */
/** 個案建檔／編輯表單 — 從 cases/page.tsx 搬出（11 §4.2）。 */

export function CaseForm({
  token, therapists, institutions, editingCase, userRole, onClose, onSaved,
}: {
  token: string; therapists: Therapist[]; institutions: InstitutionItem[];
  editingCase: CaseItem | null; userRole: string; onClose: () => void; onSaved: () => void;
}) {
  const isEditing = !!editingCase;
  const [form, setForm] = useState({
    name: editingCase?.name ?? "",
    age: editingCase?.age?.toString() ?? "",
    gender: editingCase?.gender ?? "",
    phone: editingCase?.phone ?? "",
    phone_home: editingCase?.phone_home ?? "",
    address: editingCase?.address ?? "",
    emergency_contact: editingCase?.emergency_contact ?? "",
    emergency_phone: editingCase?.emergency_phone ?? "",
    emergency_phone2: editingCase?.emergency_phone2 ?? "",
    birth_date: editingCase?.birth_date ?? "",
    initial_visit_date: editingCase?.initial_visit_date ?? "",
    therapist_id: editingCase?.therapist_id?.toString() ?? "",
    billing_cycle: editingCase?.billing_cycle ?? "once",
    referral_source: editingCase?.referral_source ?? "",
    session_location: editingCase?.session_location ?? "",
    national_id: "",
    status: editingCase?.status ?? "initial",
    is_designated: editingCase?.is_designated ?? false,
    notes: editingCase?.notes ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [showClosure, setShowClosure] = useState(false);
  const [closurePassword, setClosurePassword] = useState("");
  const [closureReason, setClosureReason] = useState("");

  const isClosing = isEditing && showClosure && editingCase!.status !== "closed";
  const isReopening = isEditing && showClosure && editingCase!.status === "closed";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const body: any = {
        name: form.name,
        age: form.age ? parseInt(form.age) : null,
        gender: form.gender || null,
        phone: form.phone || null,
        phone_home: form.phone_home || null,
        address: form.address || null,
        emergency_contact: form.emergency_contact || null,
        emergency_phone: form.emergency_phone || null,
        emergency_phone2: form.emergency_phone2 || null,
        birth_date: form.birth_date || null,
        initial_visit_date: form.initial_visit_date || null,
        funding_source: "self_pay",
        institution_id: null,
        therapist_id: parseInt(form.therapist_id),
        billing_cycle: form.billing_cycle,
        referral_source: form.referral_source || null,
        session_location: form.session_location || null,
        is_designated: form.is_designated,
        notes: form.notes || null,
      };
      if (isEditing) {
        body.status = form.status;
        if (form.national_id) body.national_id = form.national_id;
        await clientFetch(`/cases/${editingCase!.id}`, token, { method: "PUT", body: JSON.stringify(body) });
      } else {
        if (form.national_id) body.national_id = form.national_id;
        await clientFetch("/cases", token, { method: "POST", body: JSON.stringify(body) });
      }
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleClosure = async () => {
    if (!showClosure) { setShowClosure(true); return; }
    if (!closurePassword) { setError("請輸入您的登入密碼"); return; }
    setSaving(true);
    setError("");
    try {
      if (isClosing) {
        const body: any = { password: closurePassword };
        if (closureReason) body.reason = closureReason;
        await clientFetch(`/cases/${editingCase!.id}/close`, token, { method: "POST", body: JSON.stringify(body) });
      } else {
        await clientFetch(`/cases/${editingCase!.id}/reopen`, token, { method: "POST", body: JSON.stringify({ password: closurePassword }) });
      }
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const sf = (key: string, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className={`w-full rounded-xl bg-white p-6 shadow-xl ${isEditing ? "max-w-2xl" : "max-w-lg"} max-h-[90vh] overflow-y-auto`}>
        <h2 className="mb-4 text-lg font-bold">{isEditing ? "編輯個案" : "新增個案（已預約未初談）"}</h2>
        {!isEditing && (
          <p className="mb-3 rounded-lg bg-blue-50 px-3 py-2 text-xs text-blue-700">
            Stage 1：僅需填寫基本資料。初診到場後再補填完整資料並轉為正式個案。
          </p>
        )}
        {error && <div className="mb-3 rounded-lg bg-red-50 p-2 text-sm text-red-600">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-3">
          {/* === 基本資料（新增＋編輯都顯示）=== */}
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">姓名 <span className="text-red-500">*</span></span>
              <input required value={form.name} onChange={(e) => sf("name", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">年齡</span>
              <input type="number" min="0" max="120" value={form.age} onChange={(e) => sf("age", e.target.value)} placeholder="初談前先記年紀" className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">電話<span className="text-red-500"> *</span><span className="text-gray-400">（轉正式必填）</span></span>
              <input value={form.phone} onChange={(e) => sf("phone", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">負責心理師 <span className="text-red-500">*</span></span>
              <select required value={form.therapist_id} onChange={(e) => sf("therapist_id", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                <option value="">請選擇</option>
                {therapists.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </label>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">結帳方式</span>
              <select value={form.billing_cycle} onChange={(e) => sf("billing_cycle", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                <option value="once">次結</option>
                <option value="monthly">月結</option>
                <option value="multiple">多次結</option>
              </select>
            </label>
            <div className="flex items-end pb-1">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.is_designated}
                  onChange={(e) => setForm((prev) => ({ ...prev, is_designated: e.target.checked }))}
                  className="h-4 w-4 rounded border-gray-300 text-primary-600"
                />
                <span className="text-sm text-gray-700">指定心理師</span>
              </label>
            </div>
          </div>

          {/* === 完整資料（編輯時顯示，用於轉正式前補填）=== */}
          {isEditing && (
            <>
              <hr className="my-2 border-gray-200" />
              <p className="text-xs font-medium text-gray-500">
                轉正式所需資料（初診後補填）
                <span className="ml-1 font-normal text-gray-400">— 僅需 身份證字號、出生日期、電話 三項</span>
              </p>
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">性別</span>
                  <select value={form.gender} onChange={(e) => sf("gender", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                    <option value="">未填寫</option>
                    <option value="male">男</option>
                    <option value="female">女</option>
                  </select>
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">出生日期<span className="text-red-500"> *</span></span>
                  <input type="date" value={form.birth_date} onChange={(e) => sf("birth_date", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                </label>
              </div>
              <label className="block">
                <span className="mb-1 block text-xs text-gray-500">
                  身份證字號（加密儲存）
                  {!editingCase?.has_national_id && <span className="text-red-500"> *</span>}
                </span>
                <input
                  required={!editingCase?.has_national_id}
                  value={form.national_id}
                  onChange={(e) => sf("national_id", e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  placeholder={editingCase?.has_national_id ? "已填寫（重新輸入將覆蓋）" : "必填，轉正式編號需要"}
                />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">市話</span>
                  <input value={form.phone_home} onChange={(e) => sf("phone_home", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">地址</span>
                  <input value={form.address} onChange={(e) => sf("address", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                </label>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">緊急聯絡人</span>
                  <input value={form.emergency_contact} onChange={(e) => sf("emergency_contact", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">聯絡電話1</span>
                  <input value={form.emergency_phone} onChange={(e) => sf("emergency_phone", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">聯絡電話2</span>
                  <input value={form.emergency_phone2} onChange={(e) => sf("emergency_phone2", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                </label>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">轉介來源</span>
                  <input value={form.referral_source} onChange={(e) => sf("referral_source", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">會談地點</span>
                  <input value={form.session_location} onChange={(e) => sf("session_location", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                </label>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">初談日期</span>
                  <input type="date" value={form.initial_visit_date} onChange={(e) => sf("initial_visit_date", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">狀態</span>
                  {editingCase!.status === "closed" ? (
                    <div className="flex items-center rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-400">已結案（可由右下「復案」變更）</div>
                  ) : (
                    <select value={form.status} onChange={(e) => sf("status", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                      {Object.entries(statusLabels).filter(([k]) => k !== "initial" && k !== "closed").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                  )}
                </label>
              </div>
            </>
          )}
          <label className="block">
            <span className="mb-1 block text-xs text-gray-500">備註</span>
            <textarea value={form.notes} onChange={(e) => sf("notes", e.target.value)} rows={2} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          </label>

          {/* === 結案操作區（選「結案」時出現）=== */}
          {isClosing && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 space-y-2">
              <p className="text-xs font-semibold text-red-700">⚠️ 結案後將執行：</p>
              <ul className="list-disc pl-4 text-xs text-red-600 space-y-0.5">
                <li>個案標記為結案，從預約／個案名單預設隱藏</li>
                <li>取消所有未來預約</li>
                <li>機構額度歸零（保留歷史用量紀錄）</li>
              </ul>
              <p className="text-xs text-red-600">所有過往資料完整保留，可隨時復案恢復。</p>
              <label className="block">
                <span className="mb-1 block text-xs text-gray-600">結案原因（選填）</span>
                <input
                  value={closureReason}
                  onChange={(e) => setClosureReason(e.target.value)}
                  placeholder="例：流失、長期未派案"
                  className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs text-gray-600">您的登入密碼 <span className="text-red-500">*</span></span>
                <input
                  type="password"
                  value={closurePassword}
                  onChange={(e) => setClosurePassword(e.target.value)}
                  className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
                />
              </label>
            </div>
          )}

          {/* === 復案操作區（已結案個案更改狀態時出現）=== */}
          {isReopening && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 space-y-2">
              <p className="text-xs font-semibold text-emerald-700">復案後個案恢復為「進行中」，可重新編輯與建立新預約。</p>
              <p className="text-xs text-emerald-600">已取消的舊預約與已歸零的額度不會自動還原。</p>
              <label className="block">
                <span className="mb-1 block text-xs text-gray-600">您的登入密碼 <span className="text-red-500">*</span></span>
                <input
                  type="password"
                  value={closurePassword}
                  onChange={(e) => setClosurePassword(e.target.value)}
                  className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
                />
              </label>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">取消</button>
            <button type="submit" disabled={saving} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">
              {saving && !showClosure ? "儲存中..." : "儲存"}
            </button>
            {isEditing && editingCase!.status !== "closed" && (
              <button
                type="button"
                disabled={saving}
                onClick={handleClosure}
                className={`rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-50 ${showClosure ? "bg-red-600 text-white hover:bg-red-700" : "border border-red-300 text-red-600 hover:bg-red-50"}`}
              >
                {saving && showClosure ? "處理中..." : showClosure ? "確認結案" : "結案"}
              </button>
            )}
            {isEditing && editingCase!.status === "closed" && (
              <button
                type="button"
                disabled={saving}
                onClick={handleClosure}
                className={`rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-50 ${showClosure ? "bg-emerald-600 text-white hover:bg-emerald-700" : "border border-emerald-300 text-emerald-600 hover:bg-emerald-50"}`}
              >
                {saving && showClosure ? "處理中..." : showClosure ? "確認復案" : "復案"}
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   Appointment Form (新增單筆預約)
   ═══════════════════════════════════════════════════ */


