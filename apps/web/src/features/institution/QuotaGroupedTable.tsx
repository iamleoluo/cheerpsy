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
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="w-full text-left text-sm">
        <thead className="bg-gray-50 text-xs uppercase text-gray-500">
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
            <tr><td colSpan={COLS} className="px-4 py-8 text-center text-gray-400">載入中...</td></tr>
          ) : groups.length === 0 ? (
            <tr><td colSpan={COLS} className="px-4 py-8 text-center text-gray-400">尚無 Quota</td></tr>
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
                  className="cursor-pointer border-t border-gray-200 bg-white hover:bg-gray-50"
                  onClick={() => toggle(caseId)}
                >
                  <td className="px-3 py-3 font-semibold">
                    <span className="mr-2 text-gray-400">{isOpen ? "▼" : "▶"}</span>
                    {caseName}
                  </td>
                  <td className="px-3 py-3 text-right text-xs">
                    <span className="font-medium">{usedCount}</span>
                    <span className="text-gray-400"> / {totalCount}</span>
                  </td>
                  <td className="px-3 py-3 text-right font-medium">
                    <span className={remaining === 0 ? "text-gray-400" : "text-emerald-700"}>{remaining}</span>
                  </td>
                  <td className="px-3 py-3 text-xs text-gray-500">{quotas.length} 個機構</td>
                  <td className="px-3 py-3 text-xs">
                    {activeCount > 0 && <span className="mr-1 rounded-full bg-green-100 px-2 py-0.5 text-green-700">{activeCount} 有效</span>}
                    {expiredCount > 0 && <span className="rounded-full bg-gray-100 px-2 py-0.5 text-gray-500">{expiredCount} 過期/用罄</span>}
                  </td>
                  {canWrite && (
                    <td className="px-3 py-3">
                      <button
                        onClick={(e) => { e.stopPropagation(); onAdd(caseId); }}
                        className="rounded bg-primary-50 px-2 py-1 text-xs text-primary-600 hover:bg-primary-100"
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
                    <tr key={r.id} className="border-t border-gray-100 bg-gray-50/60">
                      <td className="py-2 pl-10 pr-3 text-gray-600">{r.institution_name ?? `#${r.institution_id}`}</td>
                      <td className="px-3 py-2 text-right text-xs">
                        <div className="font-medium">{r.used_count} / {r.total_count}</div>
                        {r.reserved_count > 0 && <div className="text-gray-400">預約中：{r.reserved_count}</div>}
                      </td>
                      <td className="px-3 py-2 text-right text-xs">
                        <span className={r.remaining === 0 ? "text-gray-400" : "text-emerald-700"}>{r.remaining}</span>
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-500">{r.valid_from ?? "—"} ~ {r.valid_until ?? "永久"}</td>
                      <td className="px-3 py-2">
                        {active && <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700">有效</span>}
                        {expired && <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">已過期</span>}
                        {!expired && exhausted && r.reserved_count > 0 && <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700">預約鎖定</span>}
                        {!expired && exhausted && !r.reserved_count && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">已用罄</span>}
                      </td>
                      {canWrite && (
                        <td className="px-3 py-2">
                          <div className="flex gap-2">
                            <button
                              onClick={() => onEdit(r)}
                              className="rounded bg-gray-100 px-2 py-1 text-xs text-gray-700 hover:bg-gray-200"
                            >
                              編輯
                            </button>
                            {r.used_count === 0 && (
                              <button
                                onClick={() => onDelete(r.id)}
                                className="rounded bg-red-50 px-2 py-1 text-xs text-red-600 hover:bg-red-100"
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

