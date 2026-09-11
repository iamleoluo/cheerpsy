"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { clientFetch } from "@/lib/client-api";
import type { CaseItem, InstitutionItem, QuotaRow, QuotaTemplate } from "@/features/shared/types";
import { caseDisplayId } from "@/features/shared/format";

import { QuotaGroupedTable } from "./QuotaGroupedTable";
import { QuotaFormModal } from "./QuotaFormModal";
import { TemplatesSection } from "./Templates";

/* @token-guard legacy — P3 從舊路由原樣搬入，尚未換語意 token（11 §2.2） */
/**
 * 機構額度管理 — 從 cases/page.tsx 搬出（V2升級計畫 11 §4.2）。
 *
 * 依 09 §2 的裁示，額度本來就該長在**合約專頁**裡，而不是個案路由底下：
 * 一個額度屬於「某機構方案配給某個案」，它的擁有者是合約，不是個案。
 * 這次先把程式碼搬到 features/institution，P4 建合約面板時直接接上去。
 *
 * ⚠️ 這一組走的是**舊的** case_institution_quotas 路徑，不是 07 的
 * inst_enrollments 三態模型。兩套並存，P4 要收斂（09 §1.4 同一類問題）。
 */

export function QuotasTab({ token, userRole }: { token: string; userRole: string }) {
  const [subTab, setSubTab] = useState<"quotas" | "templates">("quotas");
  const [rows, setRows] = useState<QuotaRow[]>([]);
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [institutions, setInstitutions] = useState<InstitutionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<"all" | "active" | "expired">("all");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<QuotaRow | null>(null);
  const [formDefaultCaseId, setFormDefaultCaseId] = useState<number | null>(null);
  const [error, setError] = useState("");

  const canWrite = ["admin", "staff"].includes(userRole);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [q, c, i] = await Promise.all([
        clientFetch("/quotas", token),
        clientFetch("/cases?limit=500", token),
        clientFetch("/institutions", token),
      ]);
      setRows(q);
      setCases(c);
      setInstitutions(i);
    } catch (e: any) {
      setError(e.message ?? "載入失敗");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const today = new Date().toISOString().slice(0, 10);
  const filtered = rows.filter((r) => {
    if (search) {
      const s = search.toLowerCase();
      if (
        !(r.case_name ?? "").toLowerCase().includes(s) &&
        !(r.institution_name ?? "").toLowerCase().includes(s)
      ) {
        return false;
      }
    }
    if (filterStatus === "active") {
      return (!r.valid_from || r.valid_from <= today)
        && (!r.valid_until || r.valid_until >= today)
        && r.remaining > 0;
    }
    if (filterStatus === "expired") {
      return (!!r.valid_until && r.valid_until < today) || r.remaining === 0;
    }
    return true;
  });

  const handleDelete = async (id: number) => {
    if (!confirm("確定刪除這筆 Quota？")) return;
    try {
      await clientFetch(`/quotas/${id}`, token, { method: "DELETE" });
      fetchAll();
    } catch (e: any) {
      alert(e.message);
    }
  };

  return (
    <div>
      {error && <div className="mb-3 rounded bg-st-danger-bg px-3 py-2 text-sm text-st-danger">{error}</div>}

      {/* Sub-tab navigation */}
      <div className="mb-4 flex gap-1 border-b border-line">
        {(["quotas", "templates"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setSubTab(t)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              subTab === t ? "border-b-2 border-accent text-accent" : "text-ink-3 hover:text-ink-2"
            }`}
          >
            {t === "quotas" ? "額度管理" : "方案範本"}
          </button>
        ))}
      </div>

      {subTab === "templates" ? (
        <TemplatesSection token={token} canWrite={canWrite} institutions={institutions} cases={cases} />
      ) : (
        <>
          <div className="mb-4 flex items-center justify-between gap-3">
            <div className="flex flex-1 gap-2">
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜尋個案 / 機構"
                className="w-64 rounded-lg border border-line-2 px-3 py-2 text-sm"
              />
              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value as any)}
                className="rounded-lg border border-line-2 px-3 py-2 text-sm"
              >
                <option value="all">全部</option>
                <option value="active">有效中</option>
                <option value="expired">已過期/用罄</option>
              </select>
            </div>
            {canWrite && (
              <button
                onClick={() => { setEditing(null); setFormDefaultCaseId(null); setShowForm(true); }}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-st-active"
              >
                ＋新增 Quota
              </button>
            )}
          </div>

          <QuotaGroupedTable
            rows={filtered}
            today={today}
            canWrite={canWrite}
            onEdit={(r) => { setEditing(r); setFormDefaultCaseId(null); setShowForm(true); }}
            onDelete={handleDelete}
            onAdd={(caseId) => { setEditing(null); setFormDefaultCaseId(caseId); setShowForm(true); }}
            loading={loading}
          />

          {showForm && (
            <QuotaFormModal
              token={token}
              cases={cases}
              institutions={institutions}
              editing={editing}
              defaultCaseId={formDefaultCaseId}
              onClose={() => { setShowForm(false); setFormDefaultCaseId(null); }}
              onSaved={() => { setShowForm(false); setFormDefaultCaseId(null); fetchAll(); }}
            />
          )}
        </>
      )}
    </div>
  );
}

