"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch, exportCsv } from "@/lib/client-api";
import HelpDrawer from "@/components/HelpDrawer";
import type {
  Appointment,
  CaseItem,
  InstitutionItem,
  RoomOption,
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
import {
  CaseClosureModal,
  CaseDetailPanel,
  CaseForm,
  CoupleForm,
  helpContent,
} from "@/features/cases";
import { AppointmentEditModal, AppointmentForm, BatchForm } from "@/features/booking";
import { QuotasTab } from "@/features/institution";

/**
 * 個案管理 — V2升級計畫 11 §4.2 拆檔後的樣子。
 *
 * 拆之前這個檔案有 3,364 行、27 個元件，裡面包含整套預約表單、批次預約、
 * 收款視窗、機構額度管理與額度範本。它們會在這裡，只因為資料庫裡 appointments
 * 與 quotas 都掛在 case 底下——但櫃檯的心智不是這樣：**額度屬於合約、批次預約
 * 屬於排程**。
 *
 * 搬走的去處：
 *   預約四件   → features/booking（並與 /booking 共用，終結兩套表單並行）
 *   額度六件   → features/institution（依 09 §2，P4 併入合約專頁）
 *   個案五件   → features/cases（建檔／伴侶／結案／詳情／說明）
 *
 * 這個路由檔現在只負責「把三個分頁組起來」：個案列表、預約總覽、機構額度。
 */

export default function CasesPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const userRole = (session?.user as any)?.role;

  const [mainTab, setMainTab] = useState<"cases" | "appointments" | "quotas">("cases");
  const [helpOpen, setHelpOpen] = useState(false);

  if (!token) return <p className="p-6 text-ink-3">載入中...</p>;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">個案管理</h1>
        <button onClick={() => setHelpOpen(true)} className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm text-ink-3 hover:bg-surface-2 hover:text-ink-2">
          <span>ℹ️</span> 說明
        </button>
      </div>
      <HelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} guideId="cases" />

      <div className="mb-6 flex gap-1 border-b border-line">
        <button
          onClick={() => setMainTab("cases")}
          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
            mainTab === "cases" ? "border-b-2 border-accent text-accent" : "text-ink-3 hover:text-ink-2"
          }`}
        >
          個案列表
        </button>
        <button
          onClick={() => setMainTab("appointments")}
          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
            mainTab === "appointments" ? "border-b-2 border-accent text-accent" : "text-ink-3 hover:text-ink-2"
          }`}
        >
          預約總表
        </button>
        <button
          onClick={() => setMainTab("quotas")}
          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
            mainTab === "quotas" ? "border-b-2 border-accent text-accent" : "text-ink-3 hover:text-ink-2"
          }`}
        >
          機構額度
        </button>
      </div>

      {mainTab === "cases" && <CasesTab token={token} userRole={userRole} />}
      {mainTab === "appointments" && <AppointmentsTab token={token} userRole={userRole} />}
      {mainTab === "quotas" && <QuotasTab token={token} userRole={userRole} />}
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   Tab 1: 個案列表
   ═══════════════════════════════════════════════════ */

function CasesTab({ token, userRole }: { token: string; userRole: string }) {
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [therapists, setTherapists] = useState<Therapist[]>([]);
  const [institutions, setInstitutions] = useState<InstitutionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [therapistFilter, setTherapistFilter] = useState("");
  const [billingFilter, setBillingFilter] = useState("");
  const [error, setError] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [showCoupleForm, setShowCoupleForm] = useState(false);
  const [editingCase, setEditingCase] = useState<CaseItem | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const fetchCases = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set("q", search);
      if (statusFilter) params.set("status", statusFilter);
      if (therapistFilter) params.set("therapist_id", therapistFilter);
      if (billingFilter) params.set("billing_cycle", billingFilter);
      const qs = params.toString();
      setCases(await clientFetch(`/cases${qs ? `?${qs}` : ""}`, token));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, search, statusFilter, therapistFilter, billingFilter]);

  const fetchMeta = useCallback(async () => {
    const [t, i] = await Promise.all([
      clientFetch("/auth/therapists", token).catch(() => []),
      clientFetch("/institutions", token).catch(() => []),
    ]);
    setTherapists(t);
    setInstitutions(i);
  }, [token]);

  useEffect(() => { fetchCases(); fetchMeta(); }, [fetchCases, fetchMeta]);

  const handleActivate = async (c: CaseItem) => {
    if (!confirm(`確定將 ${caseDisplayId(c)} ${c.name} 轉為正式個案？\n正式編號產生後不可更改。`)) return;
    try {
      await clientFetch(`/cases/${c.id}/activate`, token, { method: "POST" });
      fetchCases();
    } catch (e: any) {
      alert(e.message);
    }
  };

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex flex-wrap gap-3">
          <input
            type="text"
            placeholder="搜尋個案姓名 / 案號 / 心理師..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="rounded-lg border border-line-2 px-3 py-2 text-sm focus:border-accent focus:outline-none"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-lg border border-line-2 px-3 py-2 text-sm"
          >
            <option value="">全部狀態</option>
            {Object.entries(statusLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select
            value={billingFilter}
            onChange={(e) => setBillingFilter(e.target.value)}
            className="rounded-lg border border-line-2 px-3 py-2 text-sm"
            title="結帳方式"
          >
            <option value="">全部結帳方式</option>
            <option value="once">次結</option>
            <option value="monthly">月結</option>
            <option value="multiple">多次結</option>
          </select>
          {userRole !== "therapist" && (
            <select
              value={therapistFilter}
              onChange={(e) => setTherapistFilter(e.target.value)}
              className="rounded-lg border border-line-2 px-3 py-2 text-sm"
              title="心理師"
            >
              <option value="">全部心理師</option>
              {therapists.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          )}
        </div>
        <div className="flex items-center gap-2">
          {userRole !== "therapist" && (
            <button onClick={() => exportCsv("/export/cases", token, "cases.csv")} className="rounded-lg border border-line-2 px-4 py-2 text-sm hover:bg-surface-2">匯出 CSV</button>
          )}
          {userRole !== "therapist" && (
            <button
              onClick={() => setShowCoupleForm(true)}
              className="rounded-lg border border-st-danger/30 px-4 py-2 text-sm font-medium text-st-danger hover:bg-st-danger-bg"
            >
              + 伴侶案
            </button>
          )}
          <button
            onClick={() => { setEditingCase(null); setShowForm(true); }}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-st-active"
          >
            + 新增個案
          </button>
        </div>
      </div>

      {error && <div className="mb-4 rounded-lg bg-st-danger-bg p-3 text-sm text-st-danger">{error}</div>}

      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-2 text-xs uppercase text-ink-3">
            <tr>
              <th className="px-4 py-3">編號</th>
              <th className="px-4 py-3">姓名</th>
              <th className="px-4 py-3">心理師</th>
              <th className="px-4 py-3">結帳方式</th>
              <th className="px-4 py-3">狀態</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {loading ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-ink-3">載入中...</td></tr>
            ) : cases.length === 0 ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-ink-3">尚無個案資料</td></tr>
            ) : cases.map((c) => (
              <React.Fragment key={c.id}>
                <tr
                  className={`hover:bg-surface-2 cursor-pointer ${expandedId === c.id ? "bg-accent-soft" : ""}`}
                  onClick={() => setExpandedId(expandedId === c.id ? null : c.id)}
                >
                  <td className="px-4 py-3">
                    <div className="font-mono text-xs">
                      {c.case_number ? (
                        <span className="font-medium text-ink">{c.case_number}</span>
                      ) : (
                        <span className="text-ink-3">#{String(c.temp_seq ?? 0).padStart(4, "0")}</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 font-medium">
                    {c.case_type === "couple" && (
                      <span className="mr-1.5 inline-block rounded-full bg-st-danger-bg px-2 py-0.5 text-xs font-medium text-st-danger">伴侶</span>
                    )}
                    {c.name}
                    {c.age && !c.birth_date && <span className="ml-1 text-xs text-ink-3">({c.age}歲)</span>}
                    {c.case_type === "couple" && c.members && c.members.length > 0 && (
                      <span className="ml-1.5 text-xs text-ink-3">🔗 {c.members.map((m) => m.name).join("、")}</span>
                    )}
                  </td>
                  <td className="px-4 py-3">{c.therapist_name ?? "—"}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs">{billingLabels[c.billing_cycle ?? "once"] ?? c.billing_cycle}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[c.status] ?? "bg-surface-3"}`}>
                      {statusLabels[c.status] ?? c.status}
                    </span>
                  </td>
                  <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center gap-2">
                      <button onClick={() => { setEditingCase(c); setShowForm(true); }} className="text-xs text-accent hover:underline">編輯</button>
                      {c.status === "initial" && (
                        <button onClick={() => handleActivate(c)} className="text-xs text-st-done hover:underline">轉正式</button>
                      )}
                    </div>
                  </td>
                </tr>
                {expandedId === c.id && (
                  <tr>
                    <td colSpan={7} className="p-0">
                      <CaseDetailPanel
                        token={token}
                        userRole={userRole}
                        caseItem={c}
                        onClose={() => setExpandedId(null)}
                        onCaseUpdated={fetchCases}
                      />
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {showForm && (
        <CaseForm
          token={token}
          therapists={therapists}
          institutions={institutions}
          editingCase={editingCase}
          userRole={userRole}
          onClose={() => { setShowForm(false); setEditingCase(null); }}
          onSaved={() => { setShowForm(false); setEditingCase(null); fetchCases(); }}
        />
      )}

      {showCoupleForm && (
        <CoupleForm
          token={token}
          therapists={therapists}
          institutions={institutions}
          cases={cases}
          onClose={() => setShowCoupleForm(false)}
          onSaved={() => { setShowCoupleForm(false); fetchCases(); }}
        />
      )}

    </>
  );
}

/* ═══════════════════════════════════════════════════
   伴侶案建立 Modal
   ═══════════════════════════════════════════════════ */

function AppointmentsTab({ token, userRole }: { token: string; userRole: string }) {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [showBatchForm, setShowBatchForm] = useState(false);
  const [editAppt, setEditAppt] = useState<Appointment | null>(null);

  const fetchAppointments = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      const qs = params.toString();
      const [appts, cs] = await Promise.all([
        clientFetch(`/appointments${qs ? `?${qs}` : ""}`, token),
        clientFetch("/cases", token).catch(() => []),
      ]);
      setAppointments(appts);
      setCases(cs);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, statusFilter]);

  useEffect(() => { fetchAppointments(); }, [fetchAppointments]);

  const handleCancel = async (id: number) => {
    if (!confirm("確定要取消此預約？")) return;
    try {
      await clientFetch(`/appointments/${id}/cancel`, token, { method: "PUT" });
      fetchAppointments();
    } catch (e: any) { alert(e.message); }
  };

  const casesMap = Object.fromEntries(cases.map((c) => [c.id, c]));
  const filtered = appointments.filter((a) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (a.case_name ?? "").toLowerCase().includes(q) || (a.therapist_name ?? "").toLowerCase().includes(q);
  });

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜尋個案或心理師…"
            className="rounded-lg border border-line-2 px-3 py-2 text-sm w-48"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-lg border border-line-2 px-3 py-2 text-sm"
          >
            <option value="">全部狀態</option>
            {Object.entries(apptStatusLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div className="flex gap-2">
          {userRole !== "therapist" && (
            <button onClick={() => exportCsv("/export/appointments", token, "appointments.csv")} className="rounded-lg border border-line-2 px-4 py-2 text-sm hover:bg-surface-2">匯出 CSV</button>
          )}
          <button onClick={() => setShowBatchForm(true)} className="rounded-lg border border-accent px-4 py-2 text-sm font-medium text-accent hover:bg-accent-soft">批次預約</button>
          <button onClick={() => setShowForm(true)} className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-st-active">+ 新增預約</button>
        </div>
      </div>

      {error && <div className="mb-4 rounded-lg bg-st-danger-bg p-3 text-sm text-st-danger">{error}</div>}

      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-2 text-xs uppercase text-ink-3">
            <tr>
              <th className="px-4 py-3">到訪序號</th>
              <th className="px-4 py-3">個案</th>
              <th className="px-4 py-3">心理師</th>
              <th className="px-4 py-3">日期 / 時間</th>
              <th className="px-4 py-3">類型</th>
              <th className="px-4 py-3">診間</th>
              <th className="px-4 py-3">金額</th>
              <th className="px-4 py-3">心理師酬勞</th>
              <th className="px-4 py-3">狀態</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {loading ? (
              <tr><td colSpan={10} className="px-4 py-8 text-center text-ink-3">載入中...</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={10} className="px-4 py-8 text-center text-ink-3">{search ? "找不到符合的預約" : "尚無預約資料"}</td></tr>
            ) : filtered.map((a) => {
              const c = casesMap[a.case_id];
              return (
                <tr key={a.id} className="hover:bg-surface-2">
                  <td className="px-4 py-3 font-mono text-xs text-ink-2">{visitId(c, a)}</td>
                  <td className="px-4 py-3">{a.case_name ?? "—"}</td>
                  <td className="px-4 py-3">{a.therapist_name ?? "—"}</td>
                  <td className="px-4 py-3 text-xs">
                    {fmtDate(a.start_time)} {fmtTime(a.start_time)}~{fmtTime(a.end_time)}
                  </td>
                  <td className="px-4 py-3 text-xs">{sessionTypeLabels[a.session_type] ?? a.session_type}</td>
                  <td className="px-4 py-3 text-xs">{a.room_name ?? "—"}</td>
                  <td className="px-4 py-3">${a.amount.toLocaleString()}</td>
                  <td className="px-4 py-3 text-xs text-ink-3">${a.therapist_share?.toLocaleString()}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${apptStatusColors[a.status] ?? "bg-surface-3"}`}>
                      {apptStatusLabels[a.status] ?? a.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {a.status === "booked" && (
                      <div className="flex gap-2">
                        <button onClick={() => setEditAppt(a)} className="text-xs text-accent hover:underline">編輯</button>
                        <button onClick={() => handleCancel(a.id)} className="text-xs text-st-danger hover:underline">取消</button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {showForm && (
        <AppointmentForm token={token} onClose={() => setShowForm(false)} onSaved={() => { setShowForm(false); fetchAppointments(); }} />
      )}
      {showBatchForm && (
        <BatchForm token={token} onClose={() => setShowBatchForm(false)} onSaved={() => { setShowBatchForm(false); fetchAppointments(); }} />
      )}
      {editAppt && (
        <AppointmentEditModal
          token={token}
          appt={editAppt}
          onClose={() => setEditAppt(null)}
          onDone={() => { setEditAppt(null); fetchAppointments(); }}
        />
      )}
    </>
  );
}

/* ═══════════════════════════════════════════════════
   Case Form (新增 / 編輯個案)
   ═══════════════════════════════════════════════════ */

