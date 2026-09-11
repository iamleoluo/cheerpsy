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
/**
 * 伴侶案建立 — 從 cases/page.tsx 搬出（11 §4.2）。
 *
 * 伴侶案本身是一筆 case_type='couple' 的個案，擁有合療的預約與帳；
 * 兩位真人仍是各自完整的 individual 個案，靠 couple_members 連起來。
 */

export function CoupleForm({
  token, therapists, institutions, cases, onClose, onSaved,
}: {
  token: string;
  therapists: Therapist[];
  institutions: InstitutionItem[];
  cases: CaseItem[];
  onClose: () => void;
  onSaved: () => void;
}) {
  // 只能挑「一般個案」（排除已是伴侶案的）
  const selectable = cases.filter((c) => c.case_type !== "couple");
  const [memberA, setMemberA] = useState("");
  const [memberB, setMemberB] = useState("");
  const [therapistId, setTherapistId] = useState("");
  const [fundingSource, setFundingSource] = useState("self_pay");
  const [institutionId, setInstitutionId] = useState("");
  const [billingCycle, setBillingCycle] = useState("once");
  const [displayName, setDisplayName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const nameOf = (id: string) => selectable.find((c) => String(c.id) === id)?.name ?? "";
  const autoName = memberA && memberB ? `${nameOf(memberA)}＆${nameOf(memberB)}（伴侶）` : "";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!memberA || !memberB) { setError("請選擇兩位個案"); return; }
    if (memberA === memberB) { setError("兩位個案不能相同"); return; }
    if (!therapistId) { setError("請選擇共同心理師"); return; }
    setSaving(true);
    try {
      const body = {
        member_case_ids: [parseInt(memberA), parseInt(memberB)],
        therapist_id: parseInt(therapistId),
        funding_source: fundingSource,
        institution_id: fundingSource === "institution" && institutionId ? parseInt(institutionId) : null,
        billing_cycle: billingCycle,
        display_name: displayName || null,
      };
      await clientFetch("/cases/couple", token, { method: "POST", body: JSON.stringify(body) });
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl max-h-[90vh] overflow-y-auto">
        <h2 className="mb-1 text-lg font-bold">建立伴侶案</h2>
        <p className="mb-4 rounded-lg bg-st-danger-bg px-3 py-2 text-xs text-st-danger">
          把兩個既有個案綁成一筆「伴侶案」，做為合療的預約與收費單位。費用記在伴侶案，計為一個案；兩人仍可各自單獨預約。
        </p>
        {error && <div className="mb-3 rounded-lg bg-st-danger-bg p-2 text-sm text-st-danger">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">個案一 <span className="text-st-danger">*</span></span>
              <select required value={memberA} onChange={(e) => setMemberA(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
                <option value="">請選擇</option>
                {selectable.map((c) => <option key={c.id} value={c.id} disabled={String(c.id) === memberB}>{c.name}{c.case_number ? `（${c.case_number}）` : ""}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">個案二 <span className="text-st-danger">*</span></span>
              <select required value={memberB} onChange={(e) => setMemberB(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
                <option value="">請選擇</option>
                {selectable.map((c) => <option key={c.id} value={c.id} disabled={String(c.id) === memberA}>{c.name}{c.case_number ? `（${c.case_number}）` : ""}</option>)}
              </select>
            </label>
          </div>
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">共同心理師 <span className="text-st-danger">*</span></span>
            <select required value={therapistId} onChange={(e) => setTherapistId(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
              <option value="">請選擇</option>
              {therapists.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">付費方式</span>
              <select value={fundingSource} onChange={(e) => setFundingSource(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
                <option value="self_pay">自費</option>
                <option value="institution">機構</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">結帳方式</span>
              <select value={billingCycle} onChange={(e) => setBillingCycle(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
                <option value="once">次結</option>
                <option value="monthly">月結</option>
                <option value="multiple">多次結</option>
              </select>
            </label>
          </div>
          {fundingSource === "institution" && (
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">機構</span>
              <select value={institutionId} onChange={(e) => setInstitutionId(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
                <option value="">請選擇機構</option>
                {institutions.filter((i) => i.is_active).map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
              </select>
            </label>
          )}
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">顯示名稱<span className="text-ink-3">（留空自動組合）</span></span>
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder={autoName || "例：陳○○＆林○○（伴侶）"} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="rounded-lg border border-line-2 px-4 py-2 text-sm hover:bg-surface-2">取消</button>
            <button type="submit" disabled={saving} className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-50">
              {saving ? "建立中..." : "建立伴侶案"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   結案／復案 Modal（密碼確認）
   ═══════════════════════════════════════════════════ */

