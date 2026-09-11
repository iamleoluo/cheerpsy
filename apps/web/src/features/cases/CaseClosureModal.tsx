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

/**
 * 結案 — 從 cases/page.tsx 搬出（11 §4.2）。
 *
 * 結案會取消所有未來預約並釋出機構已預留／已預約額度（v7 個案管理定案）。
 */

export function CaseClosureModal({
  token, caseItem, mode, onClose, onDone,
}: {
  token: string;
  caseItem: CaseItem;
  mode: "close" | "reopen";
  onClose: () => void;
  onDone: () => void;
}) {
  const [password, setPassword] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const isClose = mode === "close";

  const submit = async () => {
    setError("");
    if (!password) { setError("請輸入密碼"); return; }
    setSubmitting(true);
    try {
      const endpoint = isClose ? "close" : "reopen";
      const body: any = { password };
      if (isClose && reason) body.reason = reason;
      await clientFetch(`/cases/${caseItem.id}/${endpoint}`, token, {
        method: "POST",
        body: JSON.stringify(body),
      });
      onDone();
    } catch (e: any) {
      setError(e.message ?? (isClose ? "結案失敗" : "復案失敗"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h3 className="mb-3 text-lg font-bold">
          {isClose ? `結案：${caseItem.name}` : `復案：${caseItem.name}`}
        </h3>

        {isClose ? (
          <div className="mb-4 rounded bg-st-danger-bg px-3 py-2 text-xs text-st-danger">
            <p className="mb-1 font-semibold">結案後將執行：</p>
            <ul className="list-disc pl-4 space-y-0.5">
              <li>個案標記為結案，從預約／個案名單預設隱藏</li>
              <li>取消所有未來預約</li>
              <li>機構額度歸零（保留歷史用量紀錄）</li>
            </ul>
            <p className="mt-2">所有過往資料完整保留，可隨時復案恢復。請重新輸入密碼確認。</p>
          </div>
        ) : (
          <div className="mb-4 rounded bg-st-done-bg px-3 py-2 text-xs text-st-done">
            <p>復案後個案恢復為「進行中」，可重新編輯與建立新預約。</p>
            <p className="mt-1">已取消的舊預約與已歸零的額度不會自動還原。請重新輸入密碼確認。</p>
          </div>
        )}

        {error && <div className="mb-3 rounded bg-st-danger-bg px-3 py-2 text-sm text-st-danger">{error}</div>}

        <div className="space-y-3 text-sm">
          <div>
            <label className="mb-1 block text-xs text-ink-3">您的登入密碼</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoFocus
              className="w-full rounded border border-line-2 px-3 py-2"
            />
          </div>
          {isClose && (
            <div>
              <label className="mb-1 block text-xs text-ink-3">結案原因（選填）</label>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={2}
                placeholder="例：流失、長期未派案"
                className="w-full rounded border border-line-2 px-3 py-2"
              />
            </div>
          )}
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
            className={
              "rounded px-4 py-2 text-sm text-white disabled:opacity-50 " +
              (isClose ? "bg-st-danger hover:bg-st-danger/90" : "bg-st-done hover:bg-st-done/90")
            }
          >
            {submitting ? "處理中..." : isClose ? "確認結案" : "確認復案"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   Case Detail Panel (展開面板)
   ═══════════════════════════════════════════════════ */

