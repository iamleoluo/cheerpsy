"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch, exportCsv } from "@/lib/client-api";
import RoomMiniCalendar from "@/components/room-mini-calendar";
import HelpDrawer, { type HelpContent } from "@/components/HelpDrawer";

const helpContent: HelpContent = {
  title: "個案管理",
  overview: "個案管理採兩階段設計：預約時快速建檔（Stage 1），初診到場後補填完整資料並「轉正式」產生永久案號（Stage 2）。",
  sections: [
    {
      heading: "Stage 1：新增預約個案",
      type: "steps",
      items: [
        "點「＋新增個案」",
        "填入姓名、電話、年齡（初診前估算用）",
        "指定負責心理師，選付費方式與結帳週期",
        "儲存後狀態為「已預約未初談」，自動分配流水序號 #000X",
      ],
    },
    {
      heading: "Stage 2：初診後轉為正式個案",
      type: "steps",
      items: [
        "個案初診到場後，點列表的「編輯」",
        "補填身份證字號（必填，加密儲存）、出生日期、性別",
        "補填緊急聯絡人姓名與電話",
        "儲存後點「轉正式」按鈕",
        "系統自動產生正式案號（例：26000145），狀態變為「進行中」",
      ],
    },
    {
      heading: "狀態流程",
      type: "text",
      items: [
        "已預約未初談 → 轉正式 → 進行中",
        "進行中 → 暫停 / 結案 / 流失",
        "編輯時狀態下拉不含「已預約未初談」",
      ],
    },
    {
      heading: "注意事項",
      type: "tips",
      items: [
        "身份證字號加密儲存，任何人無法查看原始值，轉正後案號不可修改",
        "機構個案請務必選對機構，影響後續核銷案編號與請款流程",
      ],
    },
  ],
};

/* ───── types ───── */

interface CaseItem {
  id: number;
  temp_seq: number | null;
  case_number: string | null;
  name: string;
  age: number | null;
  birth_date: string | null;
  gender: string | null;
  phone: string | null;
  phone_home: string | null;
  address: string | null;
  emergency_contact: string | null;
  emergency_phone: string | null;
  emergency_phone2: string | null;
  referral_source: string | null;
  session_location: string | null;
  has_national_id: boolean;
  initial_visit_date: string | null;
  funding_source: string;
  institution_id: number | null;
  institution_name: string | null;
  therapist_id: number;
  therapist_name: string | null;
  status: string;
  billing_cycle: string | null;
  notes: string | null;
}

interface Appointment {
  id: number;
  appointment_number: string;
  case_id: number;
  case_name: string | null;
  therapist_id: number;
  therapist_name: string | null;
  room_id: number | null;
  room_name: string | null;
  session_type: string;
  start_time: string | null;
  end_time: string | null;
  amount: number;
  therapist_share: number | null;
  clinic_share: number | null;
  visit_seq: number | null;
  status: string;
  batch_id: string | null;
  created_at: string | null;
}

interface SessionRecord {
  id: number;
  session_date: string;
  appointment_number: string;
  case_name: string;
  therapist_name: string;
  amount: number;
  therapist_share: number;
  clinic_share: number;
  commission_rate_used: number | null;
  payment_status: string;
  claim_batch_id: number | null;
  therapist_doc_submitted_at: string | null;
}

interface Therapist { id: number; name: string; email: string; role: string; }
interface InstitutionItem { id: number; name: string; is_active: boolean; }
interface RoomOption { id: number; name: string; floor: number; room_code: string; }

/* ───── constants ───── */

const statusLabels: Record<string, string> = { initial: "已預約未初談", ongoing: "進行中", paused: "暫停", closed: "結案", lost: "流失" };
const statusColors: Record<string, string> = { initial: "bg-blue-100 text-blue-700", ongoing: "bg-green-100 text-green-700", paused: "bg-yellow-100 text-yellow-700", closed: "bg-gray-100 text-gray-600", lost: "bg-red-100 text-red-700" };
const apptStatusLabels: Record<string, string> = { booked: "已預約", executed: "已執行", cancelled: "已取消" };
const apptStatusColors: Record<string, string> = { booked: "bg-blue-100 text-blue-700", executed: "bg-green-100 text-green-700", cancelled: "bg-gray-100 text-gray-500" };
const billingLabels: Record<string, string> = { once: "次結", monthly: "月結", multiple: "多次結" };
const sessionTypeLabels: Record<string, string> = { in_person: "現場", online: "線上", home_visit: "到宅" };

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}`;
}
function fmtTime(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function caseDisplayId(c: CaseItem) {
  if (c.case_number) return c.case_number;
  if (c.temp_seq) return `#${String(c.temp_seq).padStart(4, "0")}`;
  return "—";
}

function visitId(c: CaseItem | null, appt: Appointment) {
  if (!c) return `—`;
  const prefix = c.case_number ?? `#${String(c.temp_seq ?? 0).padStart(4, "0")}`;
  return `${prefix}-${String(appt.visit_seq ?? 0).padStart(3, "0")}`;
}

/* ═══════════════════════════════════════════════════
   Main Page
   ═══════════════════════════════════════════════════ */

export default function CasesPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const userRole = (session?.user as any)?.role;

  const [mainTab, setMainTab] = useState<"cases" | "appointments">("cases");
  const [helpOpen, setHelpOpen] = useState(false);

  if (!token) return <p className="p-6 text-gray-400">載入中...</p>;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">個案管理</h1>
        <button onClick={() => setHelpOpen(true)} className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50 hover:text-gray-700">
          <span>ℹ️</span> 說明
        </button>
      </div>
      <HelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} content={helpContent} />

      <div className="mb-6 flex gap-1 border-b border-gray-200">
        <button
          onClick={() => setMainTab("cases")}
          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
            mainTab === "cases" ? "border-b-2 border-primary-600 text-primary-700" : "text-gray-500 hover:text-gray-700"
          }`}
        >
          個案列表
        </button>
        <button
          onClick={() => setMainTab("appointments")}
          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
            mainTab === "appointments" ? "border-b-2 border-primary-600 text-primary-700" : "text-gray-500 hover:text-gray-700"
          }`}
        >
          預約總表
        </button>
      </div>

      {mainTab === "cases" ? (
        <CasesTab token={token} userRole={userRole} />
      ) : (
        <AppointmentsTab token={token} userRole={userRole} />
      )}
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
  const [error, setError] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [editingCase, setEditingCase] = useState<CaseItem | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const fetchCases = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set("q", search);
      if (statusFilter) params.set("status", statusFilter);
      const qs = params.toString();
      setCases(await clientFetch(`/cases${qs ? `?${qs}` : ""}`, token));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, search, statusFilter]);

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
        <div className="flex gap-3">
          <input
            type="text"
            placeholder="搜尋個案姓名..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="">全部狀態</option>
            {Object.entries(statusLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div className="flex items-center gap-2">
          {userRole !== "therapist" && (
            <button onClick={() => exportCsv("/export/cases", token, "cases.csv")} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">匯出 CSV</button>
          )}
          <button
            onClick={() => { setEditingCase(null); setShowForm(true); }}
            className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
          >
            + 新增個案
          </button>
        </div>
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">{error}</div>}

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">編號</th>
              <th className="px-4 py-3">姓名</th>
              <th className="px-4 py-3">心理師</th>
              <th className="px-4 py-3">付費 / 機構</th>
              <th className="px-4 py-3">結帳週期</th>
              <th className="px-4 py-3">狀態</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-400">載入中...</td></tr>
            ) : cases.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-400">尚無個案資料</td></tr>
            ) : cases.map((c) => (
              <React.Fragment key={c.id}>
                <tr
                  className={`hover:bg-gray-50 cursor-pointer ${expandedId === c.id ? "bg-primary-50" : ""}`}
                  onClick={() => setExpandedId(expandedId === c.id ? null : c.id)}
                >
                  <td className="px-4 py-3">
                    <div className="font-mono text-xs">
                      {c.case_number ? (
                        <span className="font-medium text-gray-800">{c.case_number}</span>
                      ) : (
                        <span className="text-gray-400">#{String(c.temp_seq ?? 0).padStart(4, "0")}</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 font-medium">
                    {c.name}
                    {c.age && !c.birth_date && <span className="ml-1 text-xs text-gray-400">({c.age}歲)</span>}
                  </td>
                  <td className="px-4 py-3">{c.therapist_name ?? "—"}</td>
                  <td className="px-4 py-3">
                    {c.funding_source === "institution" ? c.institution_name ?? "機構" : "自費"}
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs">{billingLabels[c.billing_cycle ?? "once"] ?? c.billing_cycle}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[c.status] ?? "bg-gray-100"}`}>
                      {statusLabels[c.status] ?? c.status}
                    </span>
                  </td>
                  <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center gap-2">
                      <button onClick={() => { setEditingCase(c); setShowForm(true); }} className="text-xs text-blue-600 hover:underline">編輯</button>
                      {c.status === "initial" && (
                        <button onClick={() => handleActivate(c)} className="text-xs text-green-600 hover:underline">轉正式</button>
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
    </>
  );
}

/* ═══════════════════════════════════════════════════
   Case Detail Panel (展開面板)
   ═══════════════════════════════════════════════════ */

function CaseDetailPanel({
  token, userRole, caseItem, onClose, onCaseUpdated,
}: {
  token: string; userRole: string; caseItem: CaseItem; onClose: () => void; onCaseUpdated: () => void;
}) {
  const [subTab, setSubTab] = useState<"appointments" | "ledger">("appointments");
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [records, setRecords] = useState<SessionRecord[]>([]);
  const [loadingAppts, setLoadingAppts] = useState(true);
  const [loadingRecords, setLoadingRecords] = useState(false);
  const [showApptForm, setShowApptForm] = useState(false);
  const [showBatchForm, setShowBatchForm] = useState(false);

  const fetchAppts = useCallback(async () => {
    setLoadingAppts(true);
    try {
      setAppointments(await clientFetch(`/appointments?case_id=${caseItem.id}`, token));
    } catch { /* ignore */ } finally { setLoadingAppts(false); }
  }, [token, caseItem.id]);

  const fetchRecords = useCallback(async () => {
    setLoadingRecords(true);
    try {
      const all = await clientFetch("/ledger", token);
      setRecords(all.filter((r: any) => r.case_name === caseItem.name));
    } catch { /* ignore */ } finally { setLoadingRecords(false); }
  }, [token, caseItem.name]);

  useEffect(() => { fetchAppts(); }, [fetchAppts]);
  useEffect(() => { if (subTab === "ledger") fetchRecords(); }, [subTab, fetchRecords]);

  const handleCancelAppt = async (id: number) => {
    if (!confirm("確定要取消此預約？")) return;
    try {
      await clientFetch(`/appointments/${id}/cancel`, token, { method: "PUT" });
      fetchAppts();
    } catch (e: any) { alert(e.message); }
  };

  const c = caseItem;
  const displayId = caseDisplayId(c);

  return (
    <div className="mt-4 rounded-lg border border-primary-200 bg-white p-5 shadow-sm">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-bold">
            {c.name}
            <span className="ml-2 font-mono text-sm font-normal text-gray-500">{displayId}</span>
          </h3>
          <p className="mt-1 text-sm text-gray-500">
            心理師：{c.therapist_name} ・
            {c.funding_source === "institution" ? c.institution_name : "自費"} ・
            {billingLabels[c.billing_cycle ?? "once"]} ・
            <span className={`${statusColors[c.status]} rounded-full px-1.5 py-0.5 text-xs`}>
              {statusLabels[c.status]}
            </span>
          </p>
        </div>
        <button onClick={onClose} className="rounded px-2 py-1 text-sm text-gray-400 hover:bg-gray-100 hover:text-gray-600">✕ 收合</button>
      </div>

      {/* Sub-tabs */}
      <div className="mb-4 flex gap-1 border-b border-gray-200">
        <button
          onClick={() => setSubTab("appointments")}
          className={`px-3 py-2 text-sm font-medium ${subTab === "appointments" ? "border-b-2 border-primary-600 text-primary-700" : "text-gray-500 hover:text-gray-700"}`}
        >
          預約紀錄 ({appointments.length})
        </button>
        <button
          onClick={() => setSubTab("ledger")}
          className={`px-3 py-2 text-sm font-medium ${subTab === "ledger" ? "border-b-2 border-primary-600 text-primary-700" : "text-gray-500 hover:text-gray-700"}`}
        >
          帳冊紀錄 ({records.length})
        </button>
      </div>

      {/* Sub-tab content */}
      {subTab === "appointments" && (
        <>
          <div className="mb-3 flex justify-end gap-2">
            <button onClick={() => setShowBatchForm(true)} className="rounded-lg border border-primary-600 px-3 py-1.5 text-xs font-medium text-primary-600 hover:bg-primary-50">批次預約</button>
            <button onClick={() => setShowApptForm(true)} className="rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-700">+ 新增預約</button>
          </div>
          {loadingAppts ? (
            <p className="py-4 text-center text-sm text-gray-400">載入中...</p>
          ) : appointments.length === 0 ? (
            <p className="py-4 text-center text-sm text-gray-400">尚無預約</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                  <tr>
                    <th className="px-3 py-2">到訪序號</th>
                    <th className="px-3 py-2">日期</th>
                    <th className="px-3 py-2">時間</th>
                    <th className="px-3 py-2">診間</th>
                    <th className="px-3 py-2">金額</th>
                    <th className="px-3 py-2">酬勞</th>
                    <th className="px-3 py-2">狀態</th>
                    <th className="px-3 py-2">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {appointments.map((a) => (
                    <tr key={a.id} className="hover:bg-gray-50">
                      <td className="px-3 py-2 font-mono text-xs text-gray-600">
                        {visitId(c, a)}
                      </td>
                      <td className="px-3 py-2 text-xs">{fmtDate(a.start_time)}</td>
                      <td className="px-3 py-2 text-xs">{fmtTime(a.start_time)}~{fmtTime(a.end_time)}</td>
                      <td className="px-3 py-2 text-xs">{a.room_name ?? "—"}</td>
                      <td className="px-3 py-2">${a.amount.toLocaleString()}</td>
                      <td className="px-3 py-2 text-xs text-gray-500">
                        ${a.therapist_share?.toLocaleString()}
                      </td>
                      <td className="px-3 py-2">
                        <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${apptStatusColors[a.status] ?? "bg-gray-100"}`}>
                          {apptStatusLabels[a.status] ?? a.status}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        {a.status === "booked" && (
                          <button onClick={() => handleCancelAppt(a.id)} className="text-xs text-red-500 hover:underline">取消</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {subTab === "ledger" && (
        <>
          {loadingRecords ? (
            <p className="py-4 text-center text-sm text-gray-400">載入中...</p>
          ) : records.length === 0 ? (
            <p className="py-4 text-center text-sm text-gray-400">尚無帳冊紀錄（需先日結）</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                  <tr>
                    <th className="px-3 py-2">日期</th>
                    <th className="px-3 py-2">金額</th>
                    <th className="px-3 py-2">抽成</th>
                    <th className="px-3 py-2">收款狀態</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {records.map((r) => (
                    <tr key={r.id} className="hover:bg-gray-50">
                      <td className="px-3 py-2 text-xs">{r.session_date}</td>
                      <td className="px-3 py-2">${r.amount.toLocaleString()}</td>
                      <td className="px-3 py-2 text-xs text-gray-500">
                        {r.commission_rate_used ? `${Math.round(r.commission_rate_used * 100)}%` : "—"}
                      </td>
                      <td className="px-3 py-2">
                        <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${
                          r.payment_status === "paid" ? "bg-green-100 text-green-700" : "bg-yellow-100 text-yellow-700"
                        }`}>
                          {r.payment_status === "paid" ? "已收" : "未收"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Appointment forms */}
      {showApptForm && (
        <AppointmentForm
          token={token}
          fixedCaseId={caseItem.id}
          fixedCaseName={caseItem.name}
          onClose={() => setShowApptForm(false)}
          onSaved={() => { setShowApptForm(false); fetchAppts(); }}
        />
      )}
      {showBatchForm && (
        <BatchForm
          token={token}
          fixedCaseId={caseItem.id}
          fixedCaseName={caseItem.name}
          onClose={() => setShowBatchForm(false)}
          onSaved={() => { setShowBatchForm(false); fetchAppts(); }}
        />
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   Tab 2: 預約總表
   ═══════════════════════════════════════════════════ */

function AppointmentsTab({ token, userRole }: { token: string; userRole: string }) {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [showBatchForm, setShowBatchForm] = useState(false);

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

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex gap-3">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="">全部狀態</option>
            {Object.entries(apptStatusLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div className="flex gap-2">
          {userRole !== "therapist" && (
            <button onClick={() => exportCsv("/export/appointments", token, "appointments.csv")} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">匯出 CSV</button>
          )}
          <button onClick={() => setShowBatchForm(true)} className="rounded-lg border border-primary-600 px-4 py-2 text-sm font-medium text-primary-600 hover:bg-primary-50">批次預約</button>
          <button onClick={() => setShowForm(true)} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700">+ 新增預約</button>
        </div>
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">{error}</div>}

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
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
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={10} className="px-4 py-8 text-center text-gray-400">載入中...</td></tr>
            ) : appointments.length === 0 ? (
              <tr><td colSpan={10} className="px-4 py-8 text-center text-gray-400">尚無預約資料</td></tr>
            ) : appointments.map((a) => {
              const c = casesMap[a.case_id];
              return (
                <tr key={a.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-600">{visitId(c, a)}</td>
                  <td className="px-4 py-3">{a.case_name ?? "—"}</td>
                  <td className="px-4 py-3">{a.therapist_name ?? "—"}</td>
                  <td className="px-4 py-3 text-xs">
                    {fmtDate(a.start_time)} {fmtTime(a.start_time)}~{fmtTime(a.end_time)}
                  </td>
                  <td className="px-4 py-3 text-xs">{sessionTypeLabels[a.session_type] ?? a.session_type}</td>
                  <td className="px-4 py-3 text-xs">{a.room_name ?? "—"}</td>
                  <td className="px-4 py-3">${a.amount.toLocaleString()}</td>
                  <td className="px-4 py-3 text-xs text-gray-500">${a.therapist_share?.toLocaleString()}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${apptStatusColors[a.status] ?? "bg-gray-100"}`}>
                      {apptStatusLabels[a.status] ?? a.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {a.status === "booked" && (
                      <button onClick={() => handleCancel(a.id)} className="text-xs text-red-500 hover:underline">取消</button>
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
    </>
  );
}

/* ═══════════════════════════════════════════════════
   Case Form (新增 / 編輯個案)
   ═══════════════════════════════════════════════════ */

function CaseForm({
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
    funding_source: editingCase?.funding_source ?? "self_pay",
    institution_id: editingCase?.institution_id?.toString() ?? "",
    therapist_id: editingCase?.therapist_id?.toString() ?? "",
    billing_cycle: editingCase?.billing_cycle ?? "once",
    referral_source: editingCase?.referral_source ?? "",
    session_location: editingCase?.session_location ?? "",
    national_id: "",
    status: editingCase?.status ?? "initial",
    notes: editingCase?.notes ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

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
        funding_source: form.funding_source,
        institution_id: form.funding_source === "institution" && form.institution_id ? parseInt(form.institution_id) : null,
        therapist_id: parseInt(form.therapist_id),
        billing_cycle: form.billing_cycle,
        referral_source: form.referral_source || null,
        session_location: form.session_location || null,
        notes: form.notes || null,
      };
      if (isEditing) {
        body.status = form.status;
        if (form.national_id) body.national_id = form.national_id;
        await clientFetch(`/cases/${editingCase.id}`, token, { method: "PUT", body: JSON.stringify(body) });
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
              <span className="mb-1 block text-xs text-gray-500">電話</span>
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
          <div className="grid grid-cols-3 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">付費方式</span>
              <select value={form.funding_source} onChange={(e) => sf("funding_source", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                <option value="self_pay">自費</option>
                <option value="institution">機構</option>
              </select>
            </label>
            {form.funding_source === "institution" && (
              <label className="block">
                <span className="mb-1 block text-xs text-gray-500">機構</span>
                <select value={form.institution_id} onChange={(e) => sf("institution_id", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                  <option value="">請選擇</option>
                  {institutions.map((inst) => <option key={inst.id} value={inst.id}>{inst.name}</option>)}
                </select>
              </label>
            )}
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">結帳週期</span>
              <select value={form.billing_cycle} onChange={(e) => sf("billing_cycle", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                <option value="once">次結</option>
                <option value="monthly">月結</option>
                <option value="multiple">多次結</option>
              </select>
            </label>
          </div>

          {/* === 完整資料（編輯時顯示，用於轉正式前補填）=== */}
          {isEditing && (
            <>
              <hr className="my-2 border-gray-200" />
              <p className="text-xs font-medium text-gray-500">轉正式所需資料（初診後補填）</p>
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
                  <span className="mb-1 block text-xs text-gray-500">出生日期</span>
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
                  <select value={form.status} onChange={(e) => sf("status", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                    {Object.entries(statusLabels).filter(([k]) => k !== "initial").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </label>
              </div>
            </>
          )}
          <label className="block">
            <span className="mb-1 block text-xs text-gray-500">備註</span>
            <textarea value={form.notes} onChange={(e) => sf("notes", e.target.value)} rows={2} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">取消</button>
            <button type="submit" disabled={saving} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">
              {saving ? "儲存中..." : "儲存"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   Appointment Form (新增單筆預約)
   ═══════════════════════════════════════════════════ */

function AppointmentForm({
  token, fixedCaseId, fixedCaseName, onClose, onSaved,
}: {
  token: string; fixedCaseId?: number; fixedCaseName?: string; onClose: () => void; onSaved: () => void;
}) {
  const [cases, setCases] = useState<{ id: number; name: string }[]>([]);
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
  });

  useEffect(() => {
    if (!fixedCaseId) clientFetch("/cases", token).then(setCases).catch(() => {});
    clientFetch("/rooms", token).then(setRooms).catch(() => {});
  }, [token, fixedCaseId]);

  const sf = (key: string, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await clientFetch("/appointments", token, {
        method: "POST",
        body: JSON.stringify({
          case_id: parseInt(form.case_id),
          room_id: form.room_id ? parseInt(form.room_id) : null,
          session_type: form.session_type,
          start_time: `${form.start_date}T${form.start_time}:00+08:00`,
          end_time: `${form.start_date}T${form.end_time}:00+08:00`,
          amount: parseFloat(form.amount),
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
        <div className={`p-6 ${showCalendar ? "w-1/2 border-r border-gray-200" : "w-full"}`}>
          <h2 className="mb-4 text-lg font-bold">新增預約{fixedCaseName ? ` — ${fixedCaseName}` : ""}</h2>
          {error && <div className="mb-3 rounded-lg bg-red-50 p-2 text-sm text-red-600">{error}</div>}
          <form onSubmit={handleSubmit} className="space-y-3">
            {!fixedCaseId && (
              <label className="block">
                <span className="mb-1 block text-xs text-gray-500">個案 <span className="text-red-500">*</span></span>
                <select required value={form.case_id} onChange={(e) => sf("case_id", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                  <option value="">請選擇</option>
                  {cases.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </label>
            )}
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">諮商類型</span>
              <select value={form.session_type} onChange={(e) => sf("session_type", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                <option value="in_person">現場</option>
                <option value="online">線上</option>
                <option value="home_visit">到宅</option>
              </select>
            </label>
            {form.session_type === "in_person" && (
              <label className="block">
                <span className="mb-1 block text-xs text-gray-500">診間 <span className="text-red-500">*</span></span>
                <select required={form.session_type === "in_person"} value={form.room_id} onChange={(e) => sf("room_id", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                  <option value="">請選擇</option>
                  {rooms.map((r) => <option key={r.id} value={r.id}>{r.name} ({r.room_code})</option>)}
                </select>
              </label>
            )}
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">日期 <span className="text-red-500">*</span></span>
              <input required type="date" value={form.start_date} onChange={(e) => sf("start_date", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="mb-1 block text-xs text-gray-500">開始時間</span>
                <input required type="time" value={form.start_time} onChange={(e) => sf("start_time", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs text-gray-500">結束時間</span>
                <input required type="time" value={form.end_time} onChange={(e) => sf("end_time", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              </label>
            </div>
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">金額 <span className="text-red-500">*</span></span>
              <input required type="number" value={form.amount} onChange={(e) => sf("amount", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            </label>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">取消</button>
              <button type="submit" disabled={saving} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">{saving ? "儲存中..." : "儲存"}</button>
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

const DOW_LABELS = ["日", "一", "二", "三", "四", "五", "六"];
const WEEK_OF_MONTH_LABELS = ["第1個", "第2個", "第3個", "第4個", "最後一個"];

function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function formatPreviewDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return `${d.getMonth() + 1}/${d.getDate()} (${DOW_LABELS[d.getDay()]})`;
}

function generateWeeklySlots(
  dowTarget: number,   // 0=Sun … 6=Sat
  startDate: string,  // YYYY-MM-DD — first possible date
  startTime: string,
  endTime: string,
  count: number,
): { date: string; start: string; end: string }[] {
  const results: { date: string; start: string; end: string }[] = [];
  const cur = new Date(startDate + "T00:00:00");
  // advance to first matching weekday
  while (cur.getDay() !== dowTarget) cur.setDate(cur.getDate() + 1);
  for (let i = 0; i < count; i++) {
    results.push({ date: isoDate(cur), start: startTime, end: endTime });
    cur.setDate(cur.getDate() + 7);
  }
  return results;
}

function nthWeekdayOfMonth(year: number, month: number, dow: number, n: number): Date | null {
  // n = 1..4 or -1 for last
  if (n === -1) {
    // last occurrence: start from last day, go back
    const d = new Date(year, month + 1, 0); // last day of month
    while (d.getDay() !== dow) d.setDate(d.getDate() - 1);
    return d;
  }
  // find nth occurrence (1-based)
  const d = new Date(year, month, 1);
  while (d.getDay() !== dow) d.setDate(d.getDate() + 1);
  d.setDate(d.getDate() + (n - 1) * 7);
  // ensure still in month
  if (d.getMonth() !== month) return null;
  return d;
}

function generateMonthlySlots(
  dow: number,
  weekOfMonth: number,  // 1..4 or -1 for last
  startMonth: string,   // YYYY-MM
  startTime: string,
  endTime: string,
  count: number,
): { date: string; start: string; end: string }[] {
  const results: { date: string; start: string; end: string }[] = [];
  const [y, m] = startMonth.split("-").map(Number);
  let year = y;
  let month = m - 1; // JS month 0-based
  while (results.length < count) {
    const d = nthWeekdayOfMonth(year, month, dow, weekOfMonth);
    if (d) results.push({ date: isoDate(d), start: startTime, end: endTime });
    month++;
    if (month > 11) { month = 0; year++; }
    if (year > y + 10) break; // safety
  }
  return results;
}

function BatchForm({
  token, fixedCaseId, fixedCaseName, onClose, onSaved,
}: {
  token: string; fixedCaseId?: number; fixedCaseName?: string; onClose: () => void; onSaved: () => void;
}) {
  const [cases, setCases] = useState<{ id: number; name: string }[]>([]);
  const [rooms, setRooms] = useState<RoomOption[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // base fields
  const [form, setForm] = useState({
    case_id: fixedCaseId?.toString() ?? "",
    room_id: "",
    session_type: "in_person",
    amount: "2000",
  });

  // recurrence settings
  const [recurrence, setRecurrence] = useState<"weekly" | "monthly">("weekly");
  const [dow, setDow] = useState(3); // Wed
  const [weekOfMonth, setWeekOfMonth] = useState(1); // 1st
  const today = new Date();
  const [startDate, setStartDate] = useState(isoDate(today));
  const [startMonth, setStartMonth] = useState(
    `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`
  );
  const [startTime, setStartTime] = useState("10:00");
  const [endTime, setEndTime] = useState("11:00");
  const [count, setCount] = useState("8");

  // generated preview slots
  const [slots, setSlots] = useState<{ date: string; start: string; end: string }[] | null>(null);

  useEffect(() => {
    if (!fixedCaseId) clientFetch("/cases", token).then(setCases).catch(() => {});
    clientFetch("/rooms", token).then(setRooms).catch(() => {});
  }, [token, fixedCaseId]);

  const sf = (key: string, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  const handleGenerate = () => {
    const n = Math.max(1, Math.min(52, parseInt(count) || 1));
    let generated: { date: string; start: string; end: string }[];
    if (recurrence === "weekly") {
      generated = generateWeeklySlots(dow, startDate, startTime, endTime, n);
    } else {
      generated = generateMonthlySlots(dow, weekOfMonth, startMonth, startTime, endTime, n);
    }
    setSlots(generated);
    setError("");
  };

  const removeSlot = (i: number) => setSlots((prev) => prev ? prev.filter((_, idx) => idx !== i) : prev);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!slots || slots.length === 0) { setError("請先產生時段預覽"); return; }
    setSaving(true);
    setError("");
    try {
      await clientFetch("/appointments/batch", token, {
        method: "POST",
        body: JSON.stringify({
          case_id: parseInt(form.case_id),
          room_id: form.room_id ? parseInt(form.room_id) : null,
          session_type: form.session_type,
          amount: parseFloat(form.amount),
          slots: slots.map((s) => ({
            start_time: `${s.date}T${s.start}:00+08:00`,
            end_time: `${s.date}T${s.end}:00+08:00`,
          })),
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
  const showCalendar = form.session_type === "in_person" && selectedRoom && slots && slots.length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className={`flex max-h-[92vh] w-full rounded-xl bg-white shadow-xl ${showCalendar ? "max-w-5xl" : "max-w-lg"}`}>
        {/* left: settings + preview */}
        <div className={`flex flex-col overflow-hidden ${showCalendar ? "w-1/2 border-r border-gray-200" : "w-full"}`}>
          <div className="flex-1 overflow-y-auto p-6">
            <h2 className="mb-4 text-lg font-bold">批次預約{fixedCaseName ? ` — ${fixedCaseName}` : ""}</h2>
            {error && <div className="mb-3 rounded-lg bg-red-50 p-2 text-sm text-red-600">{error}</div>}

            <form id="batch-form" onSubmit={handleSubmit} className="space-y-4">
              {/* case */}
              {!fixedCaseId && (
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">個案 <span className="text-red-500">*</span></span>
                  <select required value={form.case_id} onChange={(e) => sf("case_id", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                    <option value="">請選擇</option>
                    {cases.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </label>
              )}

              {/* session type + room */}
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="mb-1 block text-xs text-gray-500">諮商類型</span>
                  <select value={form.session_type} onChange={(e) => { sf("session_type", e.target.value); setSlots(null); }} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                    <option value="in_person">現場</option>
                    <option value="online">線上</option>
                    <option value="home_visit">到宅</option>
                  </select>
                </label>
                {form.session_type === "in_person" && (
                  <label className="block">
                    <span className="mb-1 block text-xs text-gray-500">診間</span>
                    <select value={form.room_id} onChange={(e) => sf("room_id", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                      <option value="">請選擇</option>
                      {rooms.map((r) => <option key={r.id} value={r.id}>{r.name} ({r.room_code})</option>)}
                    </select>
                  </label>
                )}
              </div>

              {/* amount */}
              <label className="block">
                <span className="mb-1 block text-xs text-gray-500">每次金額 <span className="text-red-500">*</span></span>
                <input required type="number" value={form.amount} onChange={(e) => sf("amount", e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              </label>

              {/* recurrence panel */}
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 space-y-3">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">循環設定</p>

                {/* frequency toggle */}
                <div className="flex gap-1 rounded-lg border border-gray-200 bg-white p-1">
                  {(["weekly", "monthly"] as const).map((f) => (
                    <button
                      key={f}
                      type="button"
                      onClick={() => { setRecurrence(f); setSlots(null); }}
                      className={`flex-1 rounded-md py-1.5 text-sm font-medium transition-colors ${recurrence === f ? "bg-primary-600 text-white shadow-sm" : "text-gray-600 hover:bg-gray-100"}`}
                    >
                      {f === "weekly" ? "每週" : "每月"}
                    </button>
                  ))}
                </div>

                {/* day of week picker — always shown */}
                <div>
                  <p className="mb-1.5 text-xs text-gray-500">
                    {recurrence === "weekly" ? "星期幾" : "第幾個禮拜幾"}
                  </p>
                  {recurrence === "monthly" && (
                    <div className="mb-2 flex flex-wrap gap-1">
                      {WEEK_OF_MONTH_LABELS.map((label, i) => {
                        const val = i === 4 ? -1 : i + 1;
                        return (
                          <button
                            key={i}
                            type="button"
                            onClick={() => { setWeekOfMonth(val); setSlots(null); }}
                            className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors ${weekOfMonth === val ? "border-primary-500 bg-primary-100 text-primary-700" : "border-gray-200 bg-white text-gray-600 hover:bg-gray-50"}`}
                          >
                            {label}
                          </button>
                        );
                      })}
                    </div>
                  )}
                  <div className="flex gap-1">
                    {DOW_LABELS.map((label, i) => (
                      <button
                        key={i}
                        type="button"
                        onClick={() => { setDow(i); setSlots(null); }}
                        className={`flex-1 rounded-lg border py-1.5 text-xs font-bold transition-colors ${dow === i ? "border-primary-500 bg-primary-500 text-white" : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50"}`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* time range */}
                <div className="flex items-center gap-2">
                  <div className="flex-1">
                    <p className="mb-1 text-xs text-gray-500">開始時間</p>
                    <input type="time" value={startTime} onChange={(e) => { setStartTime(e.target.value); setSlots(null); }} className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm" />
                  </div>
                  <span className="mt-4 text-gray-400">~</span>
                  <div className="flex-1">
                    <p className="mb-1 text-xs text-gray-500">結束時間</p>
                    <input type="time" value={endTime} onChange={(e) => { setEndTime(e.target.value); setSlots(null); }} className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm" />
                  </div>
                </div>

                {/* start + count */}
                <div className="flex items-end gap-3">
                  <div className="flex-1">
                    <p className="mb-1 text-xs text-gray-500">{recurrence === "weekly" ? "起始日期" : "起始月份"}</p>
                    {recurrence === "weekly" ? (
                      <input type="date" value={startDate} onChange={(e) => { setStartDate(e.target.value); setSlots(null); }} className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm" />
                    ) : (
                      <input type="month" value={startMonth} onChange={(e) => { setStartMonth(e.target.value); setSlots(null); }} className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm" />
                    )}
                  </div>
                  <div className="w-24">
                    <p className="mb-1 text-xs text-gray-500">循環次數</p>
                    <div className="flex items-center gap-1">
                      <input
                        type="number"
                        min={1}
                        max={52}
                        value={count}
                        onChange={(e) => { setCount(e.target.value); setSlots(null); }}
                        className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm"
                      />
                      <span className="text-xs text-gray-400 whitespace-nowrap">次</span>
                    </div>
                  </div>
                </div>

                {/* generate button */}
                <button
                  type="button"
                  onClick={handleGenerate}
                  className="w-full rounded-lg bg-gray-800 py-2 text-sm font-medium text-white hover:bg-gray-700"
                >
                  產生時段預覽
                </button>
              </div>

              {/* slot preview */}
              {slots && (
                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs font-semibold text-gray-600">
                      預覽時段（共 {slots.length} 筆）
                    </span>
                    <span className="text-xs text-gray-400">點 ✕ 可移除個別時段</span>
                  </div>
                  {slots.length === 0 ? (
                    <p className="rounded-lg bg-yellow-50 px-3 py-2 text-xs text-yellow-700">所有時段已移除</p>
                  ) : (
                    <ul className="max-h-52 divide-y divide-gray-100 overflow-y-auto rounded-xl border border-gray-200 bg-white">
                      {slots.map((s, i) => (
                        <li key={i} className="flex items-center justify-between px-3 py-2">
                          <span className="text-sm text-gray-700">
                            <span className="font-medium">{formatPreviewDate(s.date)}</span>
                            <span className="ml-2 text-gray-400">{s.start} ~ {s.end}</span>
                          </span>
                          <button
                            type="button"
                            onClick={() => removeSlot(i)}
                            className="ml-2 text-xs text-gray-300 hover:text-red-500"
                          >
                            ✕
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </form>
          </div>

          {/* footer */}
          <div className="flex justify-end gap-2 border-t border-gray-200 px-6 py-4">
            <button type="button" onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">取消</button>
            <button
              form="batch-form"
              type="submit"
              disabled={saving || !slots || slots.length === 0}
              className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-40"
            >
              {saving ? "建立中..." : slots && slots.length > 0 ? `建立 ${slots.length} 筆預約` : "請先產生預覽"}
            </button>
          </div>
        </div>

        {/* right: room calendar */}
        {showCalendar && (
          <div className="w-1/2 overflow-y-auto p-4">
            <RoomMiniCalendar
              token={token}
              roomId={selectedRoom.id}
              roomName={selectedRoom.name}
              focusDate={slots[0]?.date || undefined}
            />
          </div>
        )}
      </div>
    </div>
  );
}
