"use client";

import { useCallback, useEffect, useState } from "react";
import { clientFetch } from "@/lib/client-api";

/**
 * 機構額度（金流資訊，保留）。只顯示總堂數、已用、已預約、剩餘；額度不足不會擋預約。
 * 管理（新增／調整總堂數／刪除）限 admin／staff；心理師只讀自己個案的額度。
 */
export type QuotaRow = {
  id: number;
  case_id: number;
  case_name: string | null;
  institution_id: number;
  institution_name: string | null;
  plan_id: number | null;
  plan_name: string | null;
  total_count: number;
  used_count: number;
  reserved_count: number; // 已預約
  remaining: number;
  valid_from: string | null;
  valid_until: string | null;
  note: string | null;
};

type PlanOpt = { id: number; name: string; institution_id: number; institution_name: string | null; status: string };
type InstOpt = { id: number; name: string; is_active: boolean };

function QuotaTable({
  rows,
  showCase,
  canManage,
  onEdit,
  onDelete,
}: {
  rows: QuotaRow[];
  showCase: boolean;
  canManage: boolean;
  onEdit: (q: QuotaRow) => void;
  onDelete: (q: QuotaRow) => void;
}) {
  if (rows.length === 0) return <p className="py-3 text-sm text-gray-400">尚無機構額度。</p>;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="bg-gray-50 text-left text-xs text-gray-500">
          <tr>
            {showCase && <th className="px-3 py-2">個案</th>}
            <th className="px-3 py-2">機構／方案</th>
            <th className="px-3 py-2 text-right">總堂數</th>
            <th className="px-3 py-2 text-right">已用</th>
            <th className="px-3 py-2 text-right">已預約</th>
            <th className="px-3 py-2 text-right">剩餘</th>
            <th className="px-3 py-2">有效期間</th>
            {canManage && <th className="px-3 py-2" />}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map((q) => (
            <tr key={q.id}>
              {showCase && <td className="px-3 py-2">{q.case_name ?? "—"}</td>}
              <td className="px-3 py-2">
                {q.institution_name ?? "—"}
                {q.plan_name ? <span className="ml-1 text-xs text-gray-500">／{q.plan_name}</span> : null}
              </td>
              <td className="px-3 py-2 text-right">{q.total_count}</td>
              <td className="px-3 py-2 text-right">{q.used_count}</td>
              <td className="px-3 py-2 text-right">{q.reserved_count}</td>
              <td className={`px-3 py-2 text-right font-medium ${q.remaining <= 1 ? "text-red-600" : ""}`}>{q.remaining}</td>
              <td className="px-3 py-2 text-xs text-gray-500">
                {q.valid_from ?? "—"} ~ {q.valid_until ?? "不限"}
              </td>
              {canManage && (
                <td className="whitespace-nowrap px-3 py-2 text-right text-xs">
                  <button onClick={() => onEdit(q)} className="mr-2 text-blue-600 hover:underline">調整</button>
                  <button onClick={() => onDelete(q)} className="text-red-500 hover:underline">刪除</button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function QuotaForm({
  token,
  caseId,
  editing,
  onClose,
  onSaved,
}: {
  token: string;
  caseId: number;
  editing: QuotaRow | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [insts, setInsts] = useState<InstOpt[]>([]);
  const [plans, setPlans] = useState<PlanOpt[]>([]);
  const [instId, setInstId] = useState(editing ? String(editing.institution_id) : "");
  const [planId, setPlanId] = useState(editing?.plan_id ? String(editing.plan_id) : "");
  const [total, setTotal] = useState(editing ? String(editing.total_count) : "6");
  const [from, setFrom] = useState(editing?.valid_from ?? "");
  const [until, setUntil] = useState(editing?.valid_until ?? "");
  const [note, setNote] = useState(editing?.note ?? "");
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    clientFetch("/institutions", token).then(setInsts).catch(() => {});
    clientFetch("/institution-plans", token).then(setPlans).catch(() => {});
  }, [token]);

  const planOptions = plans.filter((p) => String(p.institution_id) === instId && p.status === "active");

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr("");
    try {
      if (editing) {
        await clientFetch(`/quotas/${editing.id}`, token, {
          method: "PUT",
          body: JSON.stringify({
            total_count: Number(total),
            valid_from: from || null,
            valid_until: until || null,
            clear_valid_from: !from,
            clear_valid_until: !until,
            note: note || null,
          }),
        });
      } else {
        await clientFetch(`/cases/${caseId}/quotas`, token, {
          method: "POST",
          body: JSON.stringify({
            institution_id: Number(instId),
            plan_id: planId ? Number(planId) : null,
            total_count: Number(total),
            valid_from: from || null,
            valid_until: until || null,
            note: note || null,
          }),
        });
      }
      onSaved();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  const input = "mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm";
  return (
    <form onSubmit={save} className="mt-3 space-y-3 rounded-lg border border-gray-200 bg-gray-50 p-4">
      <div className="text-sm font-medium">{editing ? "調整額度" : "新增機構額度"}</div>
      {!editing && (
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-xs text-gray-600">
            機構
            <select required value={instId} onChange={(e) => { setInstId(e.target.value); setPlanId(""); }} className={input}>
              <option value="">— 選擇 —</option>
              {insts.filter((i) => i.is_active).map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
            </select>
          </label>
          <label className="block text-xs text-gray-600">
            方案（依方案帶出價目與自付額）
            <select value={planId} onChange={(e) => setPlanId(e.target.value)} className={input}>
              <option value="">— 不指定 —</option>
              {planOptions.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
        </div>
      )}
      <div className="grid grid-cols-3 gap-3">
        <label className="block text-xs text-gray-600">
          總堂數
          <input required type="number" min={1} value={total} onChange={(e) => setTotal(e.target.value)} className={input} />
        </label>
        <label className="block text-xs text-gray-600">
          有效起日
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className={input} />
        </label>
        <label className="block text-xs text-gray-600">
          有效迄日
          <input type="date" value={until} onChange={(e) => setUntil(e.target.value)} className={input} />
        </label>
      </div>
      <label className="block text-xs text-gray-600">
        備註
        <input value={note} onChange={(e) => setNote(e.target.value)} className={input} />
      </label>
      {err && <p className="text-xs text-red-600">{err}</p>}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onClose} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-white">取消</button>
        <button disabled={saving} className="rounded-lg bg-primary-600 px-3 py-1.5 text-sm text-white hover:bg-primary-700 disabled:opacity-50">
          {saving ? "儲存中..." : "儲存"}
        </button>
      </div>
    </form>
  );
}

/** 個案詳情裡的「機構與方案、額度」區塊。 */
export function CaseQuotaSection({
  token,
  caseId,
  funding,
  institutionName,
  canManage,
}: {
  token: string;
  caseId: number;
  funding: string;
  institutionName: string | null;
  canManage: boolean;
}) {
  const [rows, setRows] = useState<QuotaRow[]>([]);
  const [form, setForm] = useState<{ editing: QuotaRow | null } | null>(null);
  const load = useCallback(() => {
    clientFetch(`/cases/${caseId}/quotas`, token).then(setRows).catch(() => setRows([]));
  }, [token, caseId]);
  useEffect(load, [load]);

  async function remove(q: QuotaRow) {
    if (!confirm(`確定刪除這筆額度（${q.plan_name ?? q.institution_name}）？`)) return;
    try {
      await clientFetch(`/quotas/${q.id}`, token, { method: "DELETE" });
      load();
    } catch (e: any) {
      alert(e.message);
    }
  }

  return (
    <div className="mb-5 rounded-lg border border-gray-200 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-sm font-semibold">
          機構與方案・額度
          <span className="ml-2 text-xs font-normal text-gray-500">
            付款方式：{funding === "institution" ? `機構${institutionName ? `（${institutionName}）` : ""}` : "自費"}
          </span>
        </h4>
        {canManage && !form && (
          <button onClick={() => setForm({ editing: null })} className="text-xs text-primary-700 hover:underline">＋ 新增額度</button>
        )}
      </div>
      <QuotaTable rows={rows} showCase={false} canManage={canManage} onEdit={(q) => setForm({ editing: q })} onDelete={remove} />
      {form && (
        <QuotaForm
          token={token}
          caseId={caseId}
          editing={form.editing}
          onClose={() => setForm(null)}
          onSaved={() => { setForm(null); load(); }}
        />
      )}
      <p className="mt-2 text-xs text-gray-400">額度只作提醒，不會擋預約；額度不足時預約照常建立並顯示提示。</p>
    </div>
  );
}

/** 「機構額度」分頁：跨個案總覽（行政用；心理師只看得到自己個案的）。 */
export function QuotasOverview({ token }: { token: string }) {
  const [rows, setRows] = useState<QuotaRow[]>([]);
  const [activeOnly, setActiveOnly] = useState(true);
  useEffect(() => {
    clientFetch(`/quotas?active_only=${activeOnly}`, token).then(setRows).catch(() => setRows([]));
  }, [token, activeOnly]);
  return (
    <div>
      <label className="mb-3 flex items-center gap-2 text-sm text-gray-600">
        <input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} />
        只看有效且還有剩餘的額度
      </label>
      <div className="rounded-lg border border-gray-200 bg-white p-3">
        <QuotaTable rows={rows} showCase canManage={false} onEdit={() => {}} onDelete={() => {}} />
      </div>
    </div>
  );
}
