"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch, exportCsv } from "@/lib/client-api";

interface CaseItem {
  id: number;
  name: string;
  birth_date: string | null;
  gender: string | null;
  phone: string | null;
  emergency_contact: string | null;
  initial_visit_date: string | null;
  funding_source: string;
  institution_id: number | null;
  institution_name: string | null;
  therapist_id: number;
  therapist_name: string | null;
  status: string;
  notes: string | null;
}

interface Therapist {
  id: number;
  name: string;
  email: string;
  role: string;
}

interface InstitutionItem {
  id: number;
  name: string;
  is_active: boolean;
}

const statusLabels: Record<string, string> = {
  initial: "初談",
  ongoing: "進行中",
  paused: "暫停",
  closed: "結案",
  lost: "流失",
};

const statusColors: Record<string, string> = {
  initial: "bg-blue-100 text-blue-700",
  ongoing: "bg-green-100 text-green-700",
  paused: "bg-yellow-100 text-yellow-700",
  closed: "bg-gray-100 text-gray-600",
  lost: "bg-red-100 text-red-700",
};

const fundingLabels: Record<string, string> = {
  self_pay: "自費",
  institution: "機構",
};

export default function CasesPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const userRole = (session?.user as any)?.role;

  const [cases, setCases] = useState<CaseItem[]>([]);
  const [therapists, setTherapists] = useState<Therapist[]>([]);
  const [institutions, setInstitutions] = useState<InstitutionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editingCase, setEditingCase] = useState<CaseItem | null>(null);
  const [error, setError] = useState("");

  const fetchCases = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set("q", search);
      if (statusFilter) params.set("status", statusFilter);
      const qs = params.toString();
      const data = await clientFetch(`/cases${qs ? `?${qs}` : ""}`, token);
      setCases(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, search, statusFilter]);

  const fetchTherapists = useCallback(async () => {
    if (!token) return;
    try {
      const data = await clientFetch("/auth/therapists", token);
      setTherapists(data);
    } catch {
      // therapists endpoint may not exist yet, use empty
    }
  }, [token]);

  const fetchInstitutions = useCallback(async () => {
    if (!token) return;
    try {
      const data = await clientFetch("/institutions", token);
      setInstitutions(data);
    } catch {
      // institutions endpoint may not exist yet
    }
  }, [token]);

  useEffect(() => {
    fetchCases();
    fetchTherapists();
    fetchInstitutions();
  }, [fetchCases, fetchTherapists, fetchInstitutions]);

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">個案管理</h1>
        <div className="flex items-center gap-2">
          {userRole !== "therapist" && (
            <button
              onClick={() => exportCsv("/export/cases", token, "cases.csv")}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
            >
              匯出 CSV
            </button>
          )}
          <button
            onClick={() => {
              setEditingCase(null);
              setShowForm(true);
            }}
            className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
          >
            + 新增個案
          </button>
        </div>
      </div>

      <div className="mb-4 flex gap-3">
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
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
        >
          <option value="">全部狀態</option>
          {Object.entries(statusLabels).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">
          {error}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">姓名</th>
              <th className="px-4 py-3">狀態</th>
              <th className="px-4 py-3">性別</th>
              <th className="px-4 py-3">電話</th>
              <th className="px-4 py-3">付費方式</th>
              <th className="px-4 py-3">負責心理師</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                  載入中...
                </td>
              </tr>
            ) : cases.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                  尚無個案資料
                </td>
              </tr>
            ) : (
              cases.map((c) => (
                <tr key={c.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">{c.name}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[c.status] ?? "bg-gray-100"}`}
                    >
                      {statusLabels[c.status] ?? c.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {c.gender === "male" ? "男" : c.gender === "female" ? "女" : c.gender ?? "-"}
                  </td>
                  <td className="px-4 py-3">{c.phone ?? "-"}</td>
                  <td className="px-4 py-3">
                    {fundingLabels[c.funding_source] ?? c.funding_source}
                    {c.institution_name && ` (${c.institution_name})`}
                  </td>
                  <td className="px-4 py-3">{c.therapist_name ?? "-"}</td>
                  <td className="px-4 py-3">
                    {userRole !== "therapist" && (
                      <button
                        onClick={() => {
                          setEditingCase(c);
                          setShowForm(true);
                        }}
                        className="text-primary-600 hover:underline"
                      >
                        編輯
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
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
          onClose={() => {
            setShowForm(false);
            setEditingCase(null);
          }}
          onSaved={() => {
            setShowForm(false);
            setEditingCase(null);
            fetchCases();
          }}
        />
      )}
    </div>
  );
}

function CaseForm({
  token,
  therapists,
  institutions,
  editingCase,
  userRole,
  onClose,
  onSaved,
}: {
  token: string;
  therapists: Therapist[];
  institutions: InstitutionItem[];
  editingCase: CaseItem | null;
  userRole: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    name: editingCase?.name ?? "",
    gender: editingCase?.gender ?? "",
    phone: editingCase?.phone ?? "",
    emergency_contact: editingCase?.emergency_contact ?? "",
    birth_date: editingCase?.birth_date ?? "",
    initial_visit_date: editingCase?.initial_visit_date ?? "",
    funding_source: editingCase?.funding_source ?? "self_pay",
    institution_id: editingCase?.institution_id?.toString() ?? "",
    therapist_id: editingCase?.therapist_id?.toString() ?? "",
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
        gender: form.gender || null,
        phone: form.phone || null,
        emergency_contact: form.emergency_contact || null,
        birth_date: form.birth_date || null,
        initial_visit_date: form.initial_visit_date || null,
        funding_source: form.funding_source,
        institution_id: form.funding_source === "institution" && form.institution_id
          ? parseInt(form.institution_id)
          : null,
        therapist_id: parseInt(form.therapist_id),
        notes: form.notes || null,
      };

      if (editingCase) {
        body.status = form.status;
        await clientFetch(`/cases/${editingCase.id}`, token, {
          method: "PUT",
          body: JSON.stringify(body),
        });
      } else {
        if (form.national_id) body.national_id = form.national_id;
        await clientFetch("/cases", token, {
          method: "POST",
          body: JSON.stringify(body),
        });
      }
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const setField = (key: string, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-bold">
          {editingCase ? "編輯個案" : "新增個案"}
        </h2>

        {error && (
          <div className="mb-3 rounded-lg bg-red-50 p-2 text-sm text-red-600">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">
                姓名 <span className="text-red-500">*</span>
              </span>
              <input
                required
                value={form.name}
                onChange={(e) => setField("name", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">性別</span>
              <select
                value={form.gender}
                onChange={(e) => setField("gender", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
              >
                <option value="">未填寫</option>
                <option value="male">男</option>
                <option value="female">女</option>
              </select>
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">電話</span>
              <input
                value={form.phone}
                onChange={(e) => setField("phone", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">
                緊急聯絡人
              </span>
              <input
                value={form.emergency_contact}
                onChange={(e) => setField("emergency_contact", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
              />
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">出生日期</span>
              <input
                type="date"
                value={form.birth_date}
                onChange={(e) => setField("birth_date", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">
                初談日期
              </span>
              <input
                type="date"
                value={form.initial_visit_date}
                onChange={(e) => setField("initial_visit_date", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
              />
            </label>
          </div>

          {!editingCase && (
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">
                身份證字號（加密儲存）
              </span>
              <input
                value={form.national_id}
                onChange={(e) => setField("national_id", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
                placeholder="可選填"
              />
            </label>
          )}

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">
                付費方式
              </span>
              <select
                value={form.funding_source}
                onChange={(e) => setField("funding_source", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
              >
                <option value="self_pay">自費</option>
                <option value="institution">機構</option>
              </select>
            </label>
            {form.funding_source === "institution" && (
              <label className="block">
                <span className="mb-1 block text-xs text-gray-500">
                  機構名稱
                </span>
                <select
                  value={form.institution_id}
                  onChange={(e) => setField("institution_id", e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
                >
                  <option value="">請選擇機構</option>
                  {institutions.map((inst) => (
                    <option key={inst.id} value={inst.id}>
                      {inst.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          <label className="block">
            <span className="mb-1 block text-xs text-gray-500">
              負責心理師 <span className="text-red-500">*</span>
            </span>
            <select
              required
              value={form.therapist_id}
              onChange={(e) => setField("therapist_id", e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
            >
              <option value="">請選擇</option>
              {therapists.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>

          {editingCase && (
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">狀態</span>
              <select
                value={form.status}
                onChange={(e) => setField("status", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
              >
                {Object.entries(statusLabels).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className="block">
            <span className="mb-1 block text-xs text-gray-500">備註</span>
            <textarea
              value={form.notes}
              onChange={(e) => setField("notes", e.target.value)}
              rows={2}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
            />
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
            >
              {saving ? "儲存中..." : "儲存"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
