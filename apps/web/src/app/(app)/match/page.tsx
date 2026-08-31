"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

interface Referral {
  id: number;
  dispatch_code: string;
  name: string;
  age: number | null;
  gender: string | null;
  phone: string | null;
  referral_source: string | null;
  chief_complaint: string | null;
  complaint_note: string | null;
  consultation_mode: string;
  partner_name: string | null;
  funding_source: string;
  plan_id: number | null;
  plan_name: string | null;
  status: string;
  cancel_reason: string | null;
  designated_therapists: string[];
  dispatch_count: number;
  case_id: number | null;
  case_number: string | null;
  created_at: string;
  dual_relationship_warning: boolean;
}

interface Slot {
  id: number;
  seq: number;
  slot_date: string;
  start_time: string;
  end_time: string;
  is_selected: boolean;
}
interface Target {
  id: number;
  therapist_id: number;
  therapist_name: string | null;
  status: string;
  decline_reason: string | null;
  decline_note: string | null;
  responded_at: string | null;
  slots: Slot[];
}
interface Dispatch {
  id: number;
  seq: number;
  status: string;
  dispatched_at: string;
  resolved_at: string | null;
  targets: Target[];
}

const STATUS: Record<string, { label: string; cls: string }> = {
  new: { label: "新增", cls: "bg-gray-100 text-gray-700" },
  matching: { label: "媒合中", cls: "bg-amber-100 text-amber-700" },
  failed: { label: "不成功", cls: "bg-red-100 text-red-700" },
  converted: { label: "成功轉預約", cls: "bg-green-100 text-green-700" },
  cancelled: { label: "取消媒合", cls: "bg-gray-200 text-gray-600" },
  closed: { label: "已結案", cls: "bg-gray-200 text-gray-600" },
  intake_done: { label: "初診有到", cls: "bg-primary-100 text-primary-700" },
};
const TARGET_STATUS: Record<string, string> = {
  pending: "待回覆",
  accepted: "已承接",
  declined: "已婉拒",
  taken: "被他人承接",
  expired: "已退回",
  released: "承接後釋出",
};
const DECLINE: Record<string, string> = {
  not_my_field: "此議題非我專長領域",
  fully_booked: "近期案量已滿",
  dual_relationship: "可能構成雙重關係",
  other: "其他",
};
const CANCEL: Record<string, string> = {
  match_failed: "媒合不成功",
  time_unavailable: "指定時間無法安排",
  designated_unavailable: "指定心理師無法安排",
  all_unavailable: "所有心理師皆無法安排",
};
const MODE: Record<string, string> = {
  individual: "個人一對一",
  couple: "伴侶諮商",
  visitation: "會面交往",
  family_group: "親子／團體",
};

const FLOW = ["諮商需求表", "派案心理師", "心理師承接", "成功轉預約", "初診有到", "產生病歷號"];

export default function MatchPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [tab, setTab] = useState<"list" | "closed" | "form">("list");
  const [rows, setRows] = useState<Referral[]>([]);
  const [therapists, setTherapists] = useState<{ id: number; name: string }[]>([]);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [dispatches, setDispatches] = useState<Record<number, Dispatch[]>>({});
  const [modal, setModal] = useState<
    | { kind: "dispatch" | "cancel" | "intake"; referral: Referral }
    | { kind: "edit"; referral: Referral | null }
    | null
  >(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (tab === "closed") params.set("closed", "true");
      if (q) params.set("q", q);
      if (statusFilter) params.set("status", statusFilter);
      const [rs, us] = await Promise.all([
        clientFetch(`/referrals?${params}`, token),
        clientFetch("/auth/therapists", token).catch(() => null),
      ]);
      setRows(rs);
      if (us) setTherapists(us);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, tab, q, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  async function toggle(id: number) {
    if (expanded === id) return setExpanded(null);
    setExpanded(id);
    try {
      const d = await clientFetch(`/referrals/${id}/dispatches`, token);
      setDispatches((m) => ({ ...m, [id]: d }));
    } catch (e: any) {
      setError(e.message);
    }
  }

  const refresh = () => {
    setModal(null);
    setDispatches({});
    setExpanded(null);
    load();
  };

  return (
    <div>
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">媒合管理</h1>
          <p className="mt-1 text-sm text-gray-500">
            派案碼 YYMMDD＋流水號3碼。同時發送 1–3 位、先回先得；逾 1 天提醒、逾 3 個自然日自動退回。
          </p>
        </div>
        <button
          onClick={() => setModal({ kind: "edit", referral: null })}
          className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
        >
          ＋新增諮商需求
        </button>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs text-gray-500">
        {FLOW.map((s, i) => (
          <span key={s} className="flex items-center gap-1">
            <span
              className={`rounded border px-2 py-1 ${
                i === FLOW.length - 1
                  ? "border-green-400 font-medium text-green-700"
                  : "border-gray-200"
              }`}
            >
              {s}
            </span>
            {i < FLOW.length - 1 && <span className="text-gray-300">→</span>}
          </span>
        ))}
      </div>

      <div className="mb-4 flex gap-2 border-b border-gray-200">
        {([["list", "媒合列表"], ["closed", "媒合結案表"]] as const).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`px-4 py-2 text-sm ${
              tab === k
                ? "border-b-2 border-primary-600 font-medium text-primary-700"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜尋 姓名／電話／機構方案"
          className="w-64 rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="">全部狀態</option>
          {Object.entries(STATUS).map(([k, v]) => (
            <option key={k} value={k}>
              {v.label}
            </option>
          ))}
        </select>
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
      {loading && <p className="text-gray-400">載入中...</p>}

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="w-full text-sm">
          <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs text-gray-500">
            <tr>
              <th className="w-8 px-3 py-3" />
              <th className="px-3 py-3">派案碼</th>
              <th className="px-3 py-3">姓名</th>
              <th className="px-3 py-3">年齡</th>
              <th className="px-3 py-3">性別</th>
              <th className="px-3 py-3">方案</th>
              <th className="px-3 py-3">指定心理師</th>
              <th className="px-3 py-3">諮商型態</th>
              <th className="px-3 py-3">媒合狀態</th>
              <th className="px-3 py-3">操作</th>
            </tr>
          </thead>
          <tbody>
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={10} className="px-4 py-10 text-center text-gray-400">
                  {tab === "closed" ? "尚無結案紀錄" : "尚無媒合案，點右上角新增諮商需求"}
                </td>
              </tr>
            )}
            {rows.map((r) => {
              const st = STATUS[r.status] ?? { label: r.status, cls: "bg-gray-100" };
              const open = expanded === r.id;
              return (
                <>
                  <tr
                    key={r.id}
                    onClick={() => toggle(r.id)}
                    className="cursor-pointer border-b border-gray-100 hover:bg-gray-50"
                  >
                    <td className="px-3 py-3 text-gray-400">{open ? "▾" : "▸"}</td>
                    <td className="px-3 py-3 font-mono text-xs">{r.dispatch_code}</td>
                    <td className="px-3 py-3 font-medium">
                      {r.name}
                      {r.dual_relationship_warning && (
                        <span
                          className="ml-1.5 rounded bg-amber-100 px-1 py-0.5 text-[10px] text-amber-700"
                          title="管道來源為親友介紹，留意雙重關係"
                        >
                          雙重關係
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-3">{r.age ?? "—"}</td>
                    <td className="px-3 py-3">
                      {r.gender === "male" ? "男" : r.gender === "female" ? "女" : "—"}
                    </td>
                    <td className="px-3 py-3 text-xs">
                      {r.funding_source === "self_pay" ? "自費" : r.plan_name || "機構"}
                    </td>
                    <td className="px-3 py-3 text-xs">
                      {r.designated_therapists.length ? r.designated_therapists.join("、") : "－"}
                    </td>
                    <td className="px-3 py-3 text-xs">{MODE[r.consultation_mode] ?? r.consultation_mode}</td>
                    <td className="px-3 py-3">
                      <span className={`rounded px-1.5 py-0.5 text-xs ${st.cls}`}>{st.label}</span>
                      {r.status === "cancelled" && r.cancel_reason && (
                        <span className="ml-1 text-[11px] text-gray-500">
                          {CANCEL[r.cancel_reason]}
                        </span>
                      )}
                      {r.case_number && (
                        <span className="ml-1 font-mono text-[11px] text-gray-500">
                          {r.case_number}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-3" onClick={(e) => e.stopPropagation()}>
                      <div className="flex flex-wrap gap-2 text-xs">
                        <button
                          onClick={() => setModal({ kind: "edit", referral: r })}
                          className="text-primary-600 hover:underline"
                        >
                          {r.status === "intake_done" ? "查看" : "編輯/查看"}
                        </button>
                        {!["cancelled", "closed", "intake_done"].includes(r.status) && (
                          <>
                            <button
                              onClick={() => setModal({ kind: "dispatch", referral: r })}
                              className="text-primary-600 hover:underline"
                            >
                              派案
                            </button>
                            <button
                              onClick={() => setModal({ kind: "cancel", referral: r })}
                              className="text-red-500 hover:underline"
                            >
                              取消媒合
                            </button>
                          </>
                        )}
                        {r.status === "converted" && (
                          <button
                            onClick={() => setModal({ kind: "intake", referral: r })}
                            className="font-medium text-green-600 hover:underline"
                          >
                            初診有到
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {open && (
                    <tr key={`${r.id}-sub`} className="bg-gray-50">
                      <td colSpan={10} className="px-6 py-3">
                        <div className="mb-2 text-xs font-medium text-gray-600">
                          媒合子列表（歷次派案批次）
                        </div>
                        {!dispatches[r.id] ? (
                          <p className="text-xs text-gray-400">載入中...</p>
                        ) : dispatches[r.id].length === 0 ? (
                          <p className="text-xs text-gray-400">尚未派案</p>
                        ) : (
                          <table className="w-full text-xs">
                            <thead className="text-left text-gray-500">
                              <tr>
                                <th className="py-1 pr-4 whitespace-nowrap">媒合日期</th>
                                <th className="py-1 pr-4 whitespace-nowrap">次數</th>
                                <th className="py-1 pr-4">媒合心理師</th>
                                <th className="py-1 pr-4 whitespace-nowrap">批次狀態</th>
                                <th className="py-1">回覆</th>
                              </tr>
                            </thead>
                            <tbody>
                              {dispatches[r.id].map((d) => (
                                <tr key={d.id} className="border-t border-gray-200">
                                  <td className="py-1.5 pr-4 whitespace-nowrap">
                                    {d.dispatched_at.slice(0, 10)}
                                  </td>
                                  <td className="py-1.5 pr-4 whitespace-nowrap">第 {d.seq} 次</td>
                                  <td className="py-1.5 pr-4">
                                    {d.targets.map((t) => t.therapist_name).join("、")}
                                  </td>
                                  <td className="py-1.5 pr-4 whitespace-nowrap">{d.status}</td>
                                  <td className="py-1.5">
                                    {d.targets.map((t) => (
                                      <div key={t.id}>
                                        {t.therapist_name}：{TARGET_STATUS[t.status] ?? t.status}
                                        {t.decline_reason && (
                                          <span className="text-gray-500">
                                            （{DECLINE[t.decline_reason]}
                                            {t.decline_note ? `：${t.decline_note}` : ""}）
                                          </span>
                                        )}
                                        {t.slots.length > 0 && (
                                          <span className="ml-1 text-primary-600">
                                            可預約：
                                            {t.slots
                                              .map(
                                                (s) =>
                                                  `${s.slot_date} ${s.start_time}-${s.end_time}`
                                              )
                                              .join("／")}
                                          </span>
                                        )}
                                      </div>
                                    ))}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>

      {modal?.kind === "edit" && (
        <ReferralForm
          token={token}
          referral={modal.referral}
          therapists={therapists}
          onClose={() => setModal(null)}
          onSaved={refresh}
        />
      )}
      {modal?.kind === "dispatch" && (
        <DispatchModal
          token={token}
          referral={modal.referral}
          therapists={therapists}
          onClose={() => setModal(null)}
          onSaved={refresh}
        />
      )}
      {modal?.kind === "cancel" && (
        <CancelModal
          token={token}
          referral={modal.referral}
          onClose={() => setModal(null)}
          onSaved={refresh}
        />
      )}
      {modal?.kind === "intake" && (
        <IntakeModal
          token={token}
          referral={modal.referral}
          therapists={therapists}
          onClose={() => setModal(null)}
          onSaved={refresh}
        />
      )}
    </div>
  );
}

function Modal({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-bold">{title}</h2>
        {children}
      </div>
    </div>
  );
}

function ReferralForm({
  token,
  referral,
  therapists,
  onClose,
  onSaved,
}: {
  token: string;
  referral: Referral | null;
  therapists: { id: number; name: string }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const readOnly = referral?.status === "intake_done";
  const [f, setF] = useState({
    name: referral?.name ?? "",
    age: referral?.age != null ? String(referral.age) : "",
    gender: referral?.gender ?? "",
    phone: referral?.phone ?? "",
    referral_source: referral?.referral_source ?? "",
    chief_complaint: referral?.chief_complaint ?? "",
    complaint_note: referral?.complaint_note ?? "",
    consultation_mode: referral?.consultation_mode ?? "individual",
    partner_name: referral?.partner_name ?? "",
  });
  const [designated, setDesignated] = useState<number[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const set = (k: string, v: string) => setF((s) => ({ ...s, [k]: v }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    const payload = {
      ...f,
      age: f.age === "" ? null : Number(f.age),
      gender: f.gender || null,
      funding_source: "self_pay",
      designated_therapist_ids: designated,
    };
    try {
      if (referral) {
        await clientFetch(`/referrals/${referral.id}`, token, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      } else {
        await clientFetch("/referrals", token, { method: "POST", body: JSON.stringify(payload) });
      }
      onSaved();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={referral ? (readOnly ? "諮商需求表（已鎖定）" : "編輯諮商需求表") : "新增諮商需求表"}>
      <form onSubmit={submit}>
        {readOnly && (
          <p className="mb-3 rounded bg-amber-50 px-3 py-2 text-xs text-amber-800">
            初診有到後個資改至「個案管理 → 個人資料」，此表已鎖定。
          </p>
        )}
        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}
        <fieldset disabled={readOnly} className="grid grid-cols-2 gap-3">
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">姓名 *</span>
            <input
              required
              value={f.name}
              onChange={(e) => set("name", e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">電話</span>
            <input
              value={f.phone}
              onChange={(e) => set("phone", e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">年齡</span>
            <input
              type="number"
              value={f.age}
              onChange={(e) => set("age", e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">性別</span>
            <select
              value={f.gender}
              onChange={(e) => set("gender", e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            >
              <option value="">未填</option>
              <option value="male">男</option>
              <option value="female">女</option>
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">管道來源</span>
            <select
              value={f.referral_source}
              onChange={(e) => set("referral_source", e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            >
              <option value="">未填</option>
              {["自己有意願", "親友介紹", "自行前來／住在附近", "社群媒體", "他院所推薦", "員工協助方案 EAP", "機構轉介"].map(
                (s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                )
              )}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">諮商型態</span>
            <select
              value={f.consultation_mode}
              onChange={(e) => set("consultation_mode", e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            >
              {Object.entries(MODE).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          {["couple", "visitation"].includes(f.consultation_mode) && (
            <label className="col-span-2 text-sm">
              <span className="mb-1 block text-gray-600">第二位個案姓名 *</span>
              <input
                required
                value={f.partner_name}
                onChange={(e) => set("partner_name", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2"
              />
            </label>
          )}
          <label className="col-span-2 text-sm">
            <span className="mb-1 block text-gray-600">主述議題</span>
            <input
              value={f.chief_complaint}
              onChange={(e) => set("chief_complaint", e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>
          <label className="col-span-2 text-sm">
            <span className="mb-1 block text-gray-600">議題補充說明（選填）</span>
            <textarea
              rows={2}
              value={f.complaint_note}
              onChange={(e) => set("complaint_note", e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>
          {!referral && (
            <div className="col-span-2">
              <span className="mb-1 block text-sm text-gray-600">
                指定心理師（選填，上限 3 位）
              </span>
              <div className="flex flex-wrap gap-2">
                {therapists.map((t) => (
                  <label key={t.id} className="flex items-center gap-1 text-xs">
                    <input
                      type="checkbox"
                      checked={designated.includes(t.id)}
                      onChange={(e) =>
                        setDesignated((d) =>
                          e.target.checked ? [...d, t.id] : d.filter((x) => x !== t.id)
                        )
                      }
                    />
                    {t.name}
                  </label>
                ))}
              </div>
            </div>
          )}
        </fieldset>
        {f.referral_source === "親友介紹" && (
          <p className="mt-3 rounded bg-amber-50 px-3 py-2 text-xs text-amber-800">
            ⚠️ 管道來源為親友介紹，派案時請留意雙重關係。
          </p>
        )}
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
          >
            {readOnly ? "關閉" : "取消"}
          </button>
          {!readOnly && (
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {saving ? "儲存中..." : "儲存"}
            </button>
          )}
        </div>
      </form>
    </Modal>
  );
}

function DispatchModal({
  token,
  referral,
  therapists,
  onClose,
  onSaved,
}: {
  token: string;
  referral: Referral;
  therapists: { id: number; name: string }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [sel, setSel] = useState<number[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function go() {
    setSaving(true);
    setErr(null);
    try {
      await clientFetch(`/referrals/${referral.id}/dispatch`, token, {
        method: "POST",
        body: JSON.stringify({ therapist_ids: sel }),
      });
      onSaved();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={`派案心理師 — ${referral.name}（${referral.dispatch_code}）`}>
      <p className="mb-3 text-sm text-gray-500">
        可同時發送 1–3 位，<b>先回先得</b>。逾 1 天提醒、逾 3 個自然日自動退回。
      </p>
      {referral.dual_relationship_warning && (
        <p className="mb-3 rounded bg-amber-50 px-3 py-2 text-xs text-amber-800">
          ⚠️ 管道來源為親友介紹，請留意雙重關係。
        </p>
      )}
      {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}
      <div className="grid max-h-64 grid-cols-2 gap-2 overflow-y-auto rounded-lg border border-gray-200 p-3">
        {therapists.map((t) => {
          const checked = sel.includes(t.id);
          const full = sel.length >= 3 && !checked;
          return (
            <label
              key={t.id}
              className={`flex items-center gap-2 text-sm ${full ? "text-gray-300" : ""}`}
            >
              <input
                type="checkbox"
                disabled={full}
                checked={checked}
                onChange={(e) =>
                  setSel((s) => (e.target.checked ? [...s, t.id] : s.filter((x) => x !== t.id)))
                }
              />
              {t.name}
            </label>
          );
        })}
      </div>
      <p className="mt-2 text-xs text-gray-400">已選 {sel.length} / 3</p>
      <div className="mt-6 flex justify-end gap-2">
        <button onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">
          取消
        </button>
        <button
          onClick={go}
          disabled={saving || sel.length === 0}
          className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {saving ? "送出中..." : "送出派案"}
        </button>
      </div>
    </Modal>
  );
}

function CancelModal({
  token,
  referral,
  onClose,
  onSaved,
}: {
  token: string;
  referral: Referral;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [reason, setReason] = useState("match_failed");
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);

  async function go() {
    try {
      await clientFetch(`/referrals/${referral.id}/cancel`, token, {
        method: "POST",
        body: JSON.stringify({ reason, note: note || null }),
      });
      onSaved();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <Modal title={`取消媒合 — ${referral.name}`}>
      {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}
      <div className="space-y-2">
        {Object.entries(CANCEL).map(([k, v]) => (
          <label key={k} className="flex items-center gap-2 text-sm">
            <input type="radio" checked={reason === k} onChange={() => setReason(k)} />
            {v}
          </label>
        ))}
      </div>
      <textarea
        rows={2}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="補充說明（選填）"
        className="mt-3 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
      />
      <div className="mt-6 flex justify-end gap-2">
        <button onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">
          返回
        </button>
        <button onClick={go} className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white">
          確認取消媒合
        </button>
      </div>
    </Modal>
  );
}

function IntakeModal({
  token,
  referral,
  therapists,
  onClose,
  onSaved,
}: {
  token: string;
  referral: Referral;
  therapists: { id: number; name: string }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [nid, setNid] = useState("");
  const [birth, setBirth] = useState("");
  const [addr, setAddr] = useState("");
  const [ec, setEc] = useState("");
  const [ep, setEp] = useState("");
  const [tid, setTid] = useState(therapists[0]?.id ?? 0);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function go(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    try {
      const r = await clientFetch(`/referrals/${referral.id}/intake-arrived`, token, {
        method: "POST",
        body: JSON.stringify({
          national_id: nid,
          birth_date: birth || null,
          address: addr || null,
          emergency_contact: ec || null,
          emergency_phone: ep || null,
          therapist_id: tid,
        }),
      });
      alert(`初診完成，病歷號 ${r.case_number}`);
      onSaved();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={`初診單 — ${referral.name}（${referral.dispatch_code}）`}>
      <form onSubmit={go}>
        <p className="mb-3 text-sm text-gray-500">
          需求表資料已自動帶入，只需補身分證等個資。送出後<b>產生病歷號</b>，個案轉「進行中」並離開媒合列表。
        </p>
        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}
        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">身分證字號 *</span>
            <input
              required
              value={nid}
              onChange={(e) => setNid(e.target.value.toUpperCase())}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">出生日期</span>
            <input
              type="date"
              value={birth}
              onChange={(e) => setBirth(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>
          <label className="col-span-2 text-sm">
            <span className="mb-1 block text-gray-600">地址</span>
            <input
              value={addr}
              onChange={(e) => setAddr(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">緊急聯絡人</span>
            <input
              value={ec}
              onChange={(e) => setEc(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-gray-600">緊急聯絡電話</span>
            <input
              value={ep}
              onChange={(e) => setEp(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>
          <label className="col-span-2 text-sm">
            <span className="mb-1 block text-gray-600">承接心理師 *</span>
            <select
              value={tid}
              onChange={(e) => setTid(Number(e.target.value))}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            >
              {therapists.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {saving ? "處理中..." : "確認初診有到"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
