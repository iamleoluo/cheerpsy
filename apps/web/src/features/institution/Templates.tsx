"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { clientFetch } from "@/lib/client-api";
import type { CaseItem, InstitutionItem, QuotaRow, QuotaTemplate } from "@/features/shared/types";
import { caseDisplayId } from "@/features/shared/format";

/* @token-guard legacy — P3 從舊路由原樣搬入，尚未換語意 token（11 §2.2） */
/**
 * 額度範本 — 從 cases/page.tsx 搬出（11 §4.2）。
 *
 * 三個元件互相只有這裡在用，所以合成一個檔案，不再各自一檔。
 */

export function TemplatesSection({
  token, canWrite, institutions, cases,
}: {
  token: string;
  canWrite: boolean;
  institutions: InstitutionItem[];
  cases: CaseItem[];
}) {
  const [templates, setTemplates] = useState<QuotaTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingTpl, setEditingTpl] = useState<QuotaTemplate | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [applyTarget, setApplyTarget] = useState<QuotaTemplate | null>(null);
  const [error, setError] = useState("");

  const fetchTemplates = useCallback(async () => {
    setLoading(true);
    try {
      const data = await clientFetch("/quota-templates/", token);
      setTemplates(data);
    } catch (e: any) {
      setError(e.message ?? "載入失敗");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchTemplates(); }, [fetchTemplates]);

  const handleDelete = async (id: number) => {
    if (!confirm("確定刪除此範本？")) return;
    try {
      await clientFetch(`/quota-templates/${id}`, token, { method: "DELETE" });
      fetchTemplates();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const grouped = templates.reduce<Record<string, QuotaTemplate[]>>((acc, t) => {
    const key = t.institution_name ?? `機構 ${t.institution_id}`;
    if (!acc[key]) acc[key] = [];
    acc[key].push(t);
    return acc;
  }, {});

  return (
    <div>
      {error && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-gray-500">定義常用方案（例如：青壯方案 8 次），一鍵套用至多個個案。</p>
        {canWrite && (
          <button
            onClick={() => { setEditingTpl(null); setShowForm(true); }}
            className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
          >
            ＋新增範本
          </button>
        )}
      </div>

      {loading ? (
        <div className="py-8 text-center text-sm text-gray-400">載入中…</div>
      ) : templates.length === 0 ? (
        <div className="py-12 text-center text-sm text-gray-400">尚無範本，點右上角新增。</div>
      ) : (
        <div className="space-y-6">
          {Object.entries(grouped).map(([instName, tpls]) => (
            <div key={instName}>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">{instName}</h4>
              <div className="overflow-hidden rounded-lg border border-gray-200">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-xs text-gray-500">
                    <tr>
                      <th className="px-4 py-2 text-left font-medium">方案名稱</th>
                      <th className="px-4 py-2 text-center font-medium">次數</th>
                      <th className="px-4 py-2 text-left font-medium">預設期間</th>
                      <th className="px-4 py-2 text-left font-medium">備註</th>
                      <th className="px-4 py-2 text-right font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {tpls.map((t) => (
                      <tr key={t.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-medium text-gray-800">{t.name}</td>
                        <td className="px-4 py-3 text-center text-gray-700">{t.total_count} 次</td>
                        <td className="px-4 py-3 text-xs text-gray-500">
                          {t.default_valid_from || t.default_valid_until
                            ? `${t.default_valid_from ?? "—"} ~ ${t.default_valid_until ?? "永久"}`
                            : "未設定"}
                        </td>
                        <td className="px-4 py-3 text-gray-500">{t.notes ?? "—"}</td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex justify-end gap-2">
                            {canWrite && (
                              <button onClick={() => setApplyTarget(t)} className="text-xs text-primary-600 hover:underline">
                                套用
                              </button>
                            )}
                            {canWrite && (
                              <button onClick={() => { setEditingTpl(t); setShowForm(true); }} className="text-xs text-gray-500 hover:underline">
                                編輯
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <TemplateFormModal
          token={token}
          institutions={institutions}
          editing={editingTpl}
          onClose={() => setShowForm(false)}
          onSaved={() => { setShowForm(false); fetchTemplates(); }}
          onDeleted={() => { setShowForm(false); fetchTemplates(); }}
        />
      )}

      {applyTarget && (
        <ApplyTemplateModal
          token={token}
          template={applyTarget}
          cases={cases}
          onClose={() => setApplyTarget(null)}
          onApplied={() => setApplyTarget(null)}
        />
      )}
    </div>
  );
}


export function TemplateFormModal({
  token, institutions, editing, onClose, onSaved, onDeleted,
}: {
  token: string;
  institutions: InstitutionItem[];
  editing: QuotaTemplate | null;
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const [institutionId, setInstitutionId] = useState<number | "">(editing?.institution_id ?? "");
  const [name, setName] = useState(editing?.name ?? "");
  const [totalCount, setTotalCount] = useState(editing?.total_count ?? 1);
  const [notes, setNotes] = useState(editing?.notes ?? "");
  const [defaultFrom, setDefaultFrom] = useState<string>(editing?.default_valid_from ?? "");
  const [defaultUntil, setDefaultUntil] = useState<string>(editing?.default_valid_until ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    setError("");
    if (!name.trim()) { setError("請填寫方案名稱"); return; }
    if (!institutionId) { setError("請選擇機構"); return; }
    if (totalCount <= 0) { setError("次數需大於 0"); return; }
    if (defaultFrom && defaultUntil && defaultFrom > defaultUntil) {
      setError("預設起日不可晚於預設迄日"); return;
    }

    setSubmitting(true);
    try {
      if (editing) {
        await clientFetch(`/quota-templates/${editing.id}`, token, {
          method: "PUT",
          body: JSON.stringify({
            name,
            total_count: totalCount,
            notes: notes || null,
            default_valid_from: defaultFrom || null,
            default_valid_until: defaultUntil || null,
            clear_default_valid_from: !defaultFrom,
            clear_default_valid_until: !defaultUntil,
          }),
        });
      } else {
        await clientFetch("/quota-templates/", token, {
          method: "POST",
          body: JSON.stringify({
            institution_id: institutionId,
            name,
            total_count: totalCount,
            notes: notes || null,
            default_valid_from: defaultFrom || null,
            default_valid_until: defaultUntil || null,
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
        <h3 className="mb-4 text-lg font-bold">{editing ? "編輯範本" : "新增方案範本"}</h3>

        {error && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

        <div className="space-y-3 text-sm">
          <div>
            <label className="mb-1 block text-xs text-gray-500">機構</label>
            <select
              value={institutionId}
              onChange={(e) => setInstitutionId(e.target.value ? Number(e.target.value) : "")}
              disabled={!!editing}
              className="w-full rounded border border-gray-300 px-3 py-2 disabled:bg-gray-100"
            >
              <option value="">— 選擇機構 —</option>
              {institutions.filter((i) => i.is_active).map((i) => (
                <option key={i.id} value={i.id}>{i.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-gray-500">方案名稱</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例：青壯方案"
              className="w-full rounded border border-gray-300 px-3 py-2"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-gray-500">次數</label>
            <input
              type="number"
              min={1}
              value={totalCount}
              onChange={(e) => setTotalCount(Number(e.target.value))}
              className="w-full rounded border border-gray-300 px-3 py-2"
            />
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="mb-1 block text-xs text-gray-500">預設起日（留空＝套用時不帶）</label>
              <input
                type="date"
                value={defaultFrom}
                onChange={(e) => setDefaultFrom(e.target.value)}
                className="w-full rounded border border-gray-300 px-3 py-2"
              />
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-xs text-gray-500">預設迄日（留空＝永久）</label>
              <input
                type="date"
                value={defaultUntil}
                onChange={(e) => setDefaultUntil(e.target.value)}
                className="w-full rounded border border-gray-300 px-3 py-2"
              />
            </div>
          </div>
          <div className="rounded bg-amber-50 px-3 py-2 text-xs text-amber-700">
            提示：填入日期後，套用範本時會自動帶入（仍可改）。例：2026 年方案，預設「2026-01-01 ~ 2026-12-31」即可，明年只需修改此處日期，不必每次套用都重選。
          </div>
          <div>
            <label className="mb-1 block text-xs text-gray-500">備註（選填）</label>
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="例：每月提供 8 次"
              className="w-full rounded border border-gray-300 px-3 py-2"
            />
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
            取消
          </button>
          <button
            onClick={submit}
            disabled={submitting}
            className="rounded bg-primary-600 px-4 py-2 text-sm text-white hover:bg-primary-700 disabled:opacity-50"
          >
            {submitting ? "儲存中..." : "儲存範本"}
          </button>
          {editing && (
            <button
              onClick={async () => {
                if (!confirm("確定刪除此範本？")) return;
                setSubmitting(true);
                try {
                  await clientFetch(`/quota-templates/${editing.id}`, token, { method: "DELETE" });
                  onDeleted();
                } catch (e: any) {
                  setError(e.message ?? "刪除失敗");
                } finally {
                  setSubmitting(false);
                }
              }}
              disabled={submitting}
              className="rounded border border-red-300 px-4 py-2 text-sm text-red-600 hover:bg-red-50 disabled:opacity-50"
            >
              刪除
            </button>
          )}
        </div>
      </div>
    </div>
  );
}


export function ApplyTemplateModal({
  token, template, cases, onClose, onApplied,
}: {
  token: string;
  template: QuotaTemplate;
  cases: CaseItem[];
  onClose: () => void;
  onApplied: () => void;
}) {
  // 套用日期預填優先序：範本的 default 值 > 不帶入（留空＝NULL/永久）
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [validFrom, setValidFrom] = useState<string>(template.default_valid_from ?? "");
  const [validUntil, setValidUntil] = useState<string>(template.default_valid_until ?? "");
  const [search, setSearch] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const filtered = cases.filter((c) => {
    if (!search) return true;
    return c.name.toLowerCase().includes(search.toLowerCase());
  });

  const toggle = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedIds.size === filtered.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filtered.map((c) => c.id)));
    }
  };

  const submit = async () => {
    setError("");
    if (selectedIds.size === 0) { setError("請至少選擇一個個案"); return; }
    if (validFrom && validUntil && validFrom > validUntil) { setError("起日不可晚於迄日"); return; }

    setSubmitting(true);
    try {
      await clientFetch(`/quota-templates/${template.id}/apply`, token, {
        method: "POST",
        body: JSON.stringify({
          case_ids: Array.from(selectedIds),
          valid_from: validFrom || null,
          valid_until: validUntil || null,
        }),
      });
      alert(`已成功為 ${selectedIds.size} 個個案套用「${template.name}」範本。`);
      onApplied();
    } catch (e: any) {
      setError(e.message ?? "套用失敗");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
        <h3 className="mb-1 text-lg font-bold">套用範本：{template.name}</h3>
        <p className="mb-4 text-sm text-gray-500">
          機構：{template.institution_name} ・ {template.total_count} 次
        </p>

        {error && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

        {(template.default_valid_from || template.default_valid_until) && (
          <div className="mb-2 rounded bg-blue-50 px-3 py-2 text-xs text-blue-700">
            已帶入範本預設期間：{template.default_valid_from ?? "—"} ~ {template.default_valid_until ?? "永久"}（可改）
          </div>
        )}
        <div className="mb-3 flex gap-3">
          <div className="flex-1">
            <label className="mb-1 block text-xs text-gray-500">有效起日（留空＝無下限）</label>
            <input type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm" />
          </div>
          <div className="flex-1">
            <label className="mb-1 block text-xs text-gray-500">有效迄日（留空＝永久）</label>
            <input type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm" />
          </div>
        </div>

        <div className="mb-2 flex items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜尋個案"
            className="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm"
          />
          <button onClick={toggleAll} className="whitespace-nowrap text-xs text-primary-600 hover:underline">
            {selectedIds.size === filtered.length ? "取消全選" : "全選"}
          </button>
        </div>

        <div className="mb-4 max-h-56 overflow-y-auto rounded border border-gray-200">
          {filtered.length === 0 ? (
            <div className="py-4 text-center text-sm text-gray-400">無符合個案</div>
          ) : (
            filtered.map((c) => (
              <label key={c.id} className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50">
                <input
                  type="checkbox"
                  checked={selectedIds.has(c.id)}
                  onChange={() => toggle(c.id)}
                  className="rounded border-gray-300"
                />
                <span>{caseDisplayId(c)} {c.name}</span>
              </label>
            ))
          )}
        </div>

        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">已選 {selectedIds.size} 個個案</span>
          <div className="flex gap-2">
            <button onClick={onClose} className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
              取消
            </button>
            <button
              onClick={submit}
              disabled={submitting}
              className="rounded bg-primary-600 px-4 py-2 text-sm text-white hover:bg-primary-700 disabled:opacity-50"
            >
              {submitting ? "套用中..." : "確認套用"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

