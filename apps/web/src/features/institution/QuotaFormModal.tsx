"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { clientFetch } from "@/lib/client-api";
import type { CaseItem, InstitutionItem, QuotaRow, QuotaTemplate } from "@/features/shared/types";
import { caseDisplayId } from "@/features/shared/format";

/* @token-guard legacy — P3 從舊路由原樣搬入，尚未換語意 token（11 §2.2） */
/** 新增／編輯額度 — 從 cases/page.tsx 搬出（11 §4.2）。 */

export function QuotaFormModal({
  token, cases, institutions, editing, defaultCaseId, onClose, onSaved,
}: {
  token: string;
  cases: CaseItem[];
  institutions: InstitutionItem[];
  editing: QuotaRow | null;
  defaultCaseId: number | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [caseId, setCaseId] = useState<number | "">(editing?.case_id ?? defaultCaseId ?? "");
  const [institutionId, setInstitutionId] = useState<number | "">(editing?.institution_id ?? "");
  const [totalCount, setTotalCount] = useState(editing?.total_count ?? 1);
  const [validFrom, setValidFrom] = useState<string>(editing?.valid_from ?? "");
  const [validUntil, setValidUntil] = useState<string>(editing?.valid_until ?? "");
  const [note, setNote] = useState(editing?.note ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const isEdit = !!editing;

  const submit = async () => {
    setError("");
    if (!caseId) { setError("請選擇個案"); return; }
    if (!institutionId) { setError("請選擇機構"); return; }
    if (totalCount <= 0) { setError("總次數需大於 0"); return; }
    if (validFrom && validUntil && validFrom > validUntil) { setError("起日不可晚於迄日"); return; }

    setSubmitting(true);
    try {
      if (isEdit) {
        await clientFetch(`/quotas/${editing!.id}`, token, {
          method: "PUT",
          body: JSON.stringify({
            total_count: totalCount,
            valid_from: validFrom || null,
            valid_until: validUntil || null,
            clear_valid_from: !validFrom,
            clear_valid_until: !validUntil,
            note: note || null,
          }),
        });
      } else {
        await clientFetch(`/cases/${caseId}/quotas`, token, {
          method: "POST",
          body: JSON.stringify({
            institution_id: institutionId,
            total_count: totalCount,
            valid_from: validFrom || null,
            valid_until: validUntil || null,
            note: note || null,
          }),
        });
      }
      onSaved();
    } catch (e: any) {
      setError(e.message ?? "儲存失敗");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h3 className="mb-4 text-lg font-bold">{isEdit ? "編輯 Quota" : "新增機構額度"}</h3>

        {error && <div className="mb-3 rounded bg-st-danger-bg px-3 py-2 text-sm text-st-danger">{error}</div>}

        <div className="space-y-3 text-sm">
          <div>
            <label className="mb-1 block text-xs text-ink-3">個案</label>
            <select
              value={caseId}
              onChange={(e) => setCaseId(e.target.value ? Number(e.target.value) : "")}
              disabled={isEdit}
              className="w-full rounded border border-line-2 px-3 py-2 disabled:bg-surface-3"
            >
              <option value="">— 選擇個案 —</option>
              {cases.map((c) => (
                <option key={c.id} value={c.id}>{c.case_type === "couple" ? "👫 " : ""}{caseDisplayId(c)} {c.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-ink-3">機構</label>
            <select
              value={institutionId}
              onChange={(e) => setInstitutionId(e.target.value ? Number(e.target.value) : "")}
              disabled={isEdit}
              className="w-full rounded border border-line-2 px-3 py-2 disabled:bg-surface-3"
            >
              <option value="">— 選擇機構 —</option>
              {institutions.filter((i) => i.is_active).map((i) => (
                <option key={i.id} value={i.id}>{i.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-ink-3">總次數</label>
            <input
              type="number"
              min={1}
              value={totalCount}
              onChange={(e) => setTotalCount(Number(e.target.value))}
              className="w-full rounded border border-line-2 px-3 py-2"
            />
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="mb-1 block text-xs text-ink-3">有效起日（留空＝無下限）</label>
              <input
                type="date"
                value={validFrom}
                onChange={(e) => setValidFrom(e.target.value)}
                className="w-full rounded border border-line-2 px-3 py-2"
              />
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-xs text-ink-3">有效迄日（留空＝永久）</label>
              <input
                type="date"
                value={validUntil}
                onChange={(e) => setValidUntil(e.target.value)}
                className="w-full rounded border border-line-2 px-3 py-2"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-ink-3">備註</label>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="選填"
              className="w-full rounded border border-line-2 px-3 py-2"
            />
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded border border-line-2 px-4 py-2 text-sm text-ink-2 hover:bg-surface-2"
          >
            取消
          </button>
          <button
            onClick={submit}
            disabled={submitting}
            className="rounded bg-accent px-4 py-2 text-sm text-white hover:bg-st-active disabled:opacity-50"
          >
            {submitting ? "儲存中..." : "儲存"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   方案範本 (TemplatesSection)
   ═══════════════════════════════════════════════════ */

