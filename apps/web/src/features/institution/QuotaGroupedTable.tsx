"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { clientFetch } from "@/lib/client-api";
import type { CaseItem, InstitutionItem, QuotaRow, QuotaTemplate } from "@/features/shared/types";
import { caseDisplayId } from "@/features/shared/format";

/* @token-guard legacy — P3 從舊路由原樣搬入，尚未換語意 token（11 §2.2） */
/** 額度清單（依機構分組）— 從 cases/page.tsx 搬出（11 §4.2）。 */

export function QuotaGroupedTable({
  rows, today, canWrite, loading, onEdit, onDelete, onAdd,
}: {
  rows: QuotaRow[];
  today: string;
  canWrite: boolean;
  loading: boolean;
  onEdit: (r: QuotaRow) => void;
  onDelete: (id: number) => void;
  onAdd: (caseId: number) => void;
}) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const toggle = (caseId: number) =>
    setExpanded((prev) => { const n = new Set(prev); n.has(caseId) ? n.delete(caseId) : n.add(caseId); return n; });

  // Group by case_id, preserving first-seen order
  const groups: { caseId: number; caseName: string; quotas: QuotaRow[] }[] = [];
  const seen = new Map<number, number>();
  for (const r of rows) {
    if (!seen.has(r.case_id)) {
      seen.set(r.case_id, groups.length);
      groups.push({ caseId: r.case_id, caseName: r.case_name ?? `#${r.case_id}`, quotas: [] });
    }
    groups[seen.get(r.case_id)!].quotas.push(r);
  }

  const COLS = canWrite ? 6 : 5;

  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full text-left text-sm">
        <thead className="bg-surface-2 text-xs uppercase text-ink-3">
          <tr>
            <th className="px-3 py-3">個案</th>
            <th className="px-3 py-3 text-right">總已用 / 總額</th>
            <th className="px-3 py-3 text-right">剩餘</th>
            <th className="px-3 py-3">機構數</th>
            <th className="px-3 py-3">狀態概覽</th>
            {canWrite && <th className="px-3 py-3">操作</th>}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr><td colSpan={COLS} className="px-4 py-8 text-center text-ink-3">載入中...</td></tr>
          ) : groups.length === 0 ? (
            <tr><td colSpan={COLS} className="px-4 py-8 text-center text-ink-3">尚無 Quota</td></tr>
          ) : groups.map(({ caseId, caseName, quotas }) => {
            const isOpen = expanded.has(caseId);
            const totalCount = quotas.reduce((s, q) => s + q.total_count, 0);
            const usedCount = quotas.reduce((s, q) => s + q.used_count, 0);
            const remaining = quotas.reduce((s, q) => s + q.remaining, 0);
            const activeCount = quotas.filter(q =>
              (!q.valid_from || q.valid_from <= today) &&
              (!q.valid_until || q.valid_until >= today) &&
              q.remaining > 0
            ).length;
            const expiredCount = quotas.filter(q =>
              (!!q.valid_until && q.valid_until < today) || q.remaining === 0
            ).length;

            return (
              <>
                {/* summary row */}
                <tr
                  key={`g-${caseId}`}
                  className="cursor-pointer border-t border-line bg-white hover:bg-surface-2"
                  onClick={() => toggle(caseId)}
                >
                  <td className="px-3 py-3 font-semibold">
                    <span className="mr-2 text-ink-3">{isOpen ? "▼" : "▶"}</span>
                    {caseName}
                  </td>
                  <td className="px-3 py-3 text-right text-xs">
                    <span className="font-medium">{usedCount}</span>
                    <span className="text-ink-3"> / {totalCount}</span>
                  </td>
                  <td className="px-3 py-3 text-right font-medium">
                    <span className={remaining === 0 ? "text-ink-3" : "text-st-done"}>{remaining}</span>
                  </td>
                  <td className="px-3 py-3 text-xs text-ink-3">{quotas.length} 個機構</td>
                  <td className="px-3 py-3 text-xs">
                    {activeCount > 0 && <span className="mr-1 rounded-full bg-st-done-bg px-2 py-0.5 text-st-done">{activeCount} 有效</span>}
                    {expiredCount > 0 && <span className="rounded-full bg-surface-3 px-2 py-0.5 text-ink-3">{expiredCount} 過期/用罄</span>}
                  </td>
                  {canWrite && (
                    <td className="px-3 py-3">
                      <button
                        onClick={(e) => { e.stopPropagation(); onAdd(caseId); }}
                        className="rounded bg-accent-soft px-2 py-1 text-xs text-accent hover:bg-accent-soft"
                      >
                        ＋新增
                      </button>
                    </td>
                  )}
                </tr>

                {/* detail rows */}
                {isOpen && quotas.map((r) => {
                  const expired = !!r.valid_until && r.valid_until < today;
                  const exhausted = r.remaining === 0;
                  const active = !expired && !exhausted;
                  return (
                    <tr key={r.id} className="border-t border-line bg-surface-2/60">
                      <td className="py-2 pl-10 pr-3 text-ink-2">{r.institution_name ?? `#${r.institution_id}`}</td>
                      <td className="px-3 py-2 text-right text-xs">
                        <div className="font-medium">{r.used_count} / {r.total_count}</div>
                        {r.reserved_count > 0 && <div className="text-ink-3">預約中：{r.reserved_count}</div>}
                      </td>
                      <td className="px-3 py-2 text-right text-xs">
                        <span className={r.remaining === 0 ? "text-ink-3" : "text-st-done"}>{r.remaining}</span>
                      </td>
                      <td className="px-3 py-2 text-xs text-ink-3">{r.valid_from ?? "—"} ~ {r.valid_until ?? "永久"}</td>
                      <td className="px-3 py-2">
                        {active && <span className="rounded-full bg-st-done-bg px-2 py-0.5 text-xs text-st-done">有效</span>}
                        {expired && <span className="rounded-full bg-surface-3 px-2 py-0.5 text-xs text-ink-3">已過期</span>}
                        {!expired && exhausted && r.reserved_count > 0 && <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700">預約鎖定</span>}
                        {!expired && exhausted && !r.reserved_count && <span className="rounded-full bg-st-warn-bg px-2 py-0.5 text-xs text-st-warn">已用罄</span>}
                      </td>
                      {canWrite && (
                        <td className="px-3 py-2">
                          <div className="flex gap-2">
                            <button
                              onClick={() => onEdit(r)}
                              className="rounded bg-surface-3 px-2 py-1 text-xs text-ink-2 hover:bg-surface-3"
                            >
                              編輯
                            </button>
                            {r.used_count === 0 && (
                              <button
                                onClick={() => onDelete(r.id)}
                                className="rounded bg-st-danger-bg px-2 py-1 text-xs text-st-danger hover:bg-st-danger-bg"
                              >
                                刪除
                              </button>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

