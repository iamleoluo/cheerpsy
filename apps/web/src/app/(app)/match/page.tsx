"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

/**
 * 媒合管理：照 V7 原型全部搬過來（見 document_reference/
 * cheerpsy_v7_spec_extracted.md「媒合管理」）。媒合出第一次（初診）預約
 * 後即轉為正式個案、離開本頁——後續一律用既有的個案／預約系統操作。
 */

const MODE_LABEL: Record<string, string> = { in_person: "現場", online: "線上", outdoor: "外展" };
const STATUS_LABEL: Record<string, string> = {
  new: "新增",
  matching: "媒合中",
  unmatched: "不成功 / 已退回",
  accepted: "成功轉預約",
  booked: "初診已預約",
  converted: "已轉個案",
  cancelled: "取消媒合",
  closed: "已結案",
};
const STATUS_COLOR: Record<string, string> = {
  new: "bg-surface-3 text-ink-2",
  matching: "bg-st-warn-bg text-st-warn",
  unmatched: "bg-st-danger-bg text-st-danger",
  accepted: "bg-st-active-bg text-st-active",
  booked: "bg-st-active-bg text-st-active",
  converted: "bg-st-done-bg text-st-done",
  cancelled: "bg-surface-3 text-ink-3",
  closed: "bg-surface-3 text-ink-3",
};
const DECLINE_LABEL: Record<string, string> = {
  unavailable: "時段無法配合",
  not_specialty: "非專長",
  dual_relationship: "雙重關係",
  other: "其他",
};
const REPLY_LABEL: Record<string, string> = {
  pending: "未回覆",
  accepted: "承接",
  declined: "無意願承接",
  superseded: "已被他人承接",
  expired: "逾時未回覆",
  released: "承接後釋出",
};

interface BatchMember {
  id: number;
  therapist_id: number;
  therapist_name: string | null;
  reply_status: string;
  decline_reason: string | null;
  proposed_slots: string[] | null;
  replied_at: string | null;
}
interface Batch {
  id: number;
  batch_seq: number;
  is_open: boolean;
  sent_at: string | null;
  members: BatchMember[];
}
interface Referral {
  id: number;
  referral_code: string;
  name: string;
  age: number | null;
  gender: string | null;
  phone: string | null;
  mode: string;
  institution_id: number | null;
  institution_name: string | null;
  funding_note: string | null;
  issues: string[] | null;
  issue_note: string | null;
  designated_therapist_id: number | null;
  designated_therapist_name: string | null;
  source: string | null;
  availability: string | null;
  note: string | null;
  status: string;
  accepted_therapist_id: number | null;
  accepted_therapist_name: string | null;
  converted_case_id: number | null;
  appointment_id: number | null;
  close_reason: string | null;
  closed_at: string | null;
  created_at: string | null;
  batches: Batch[];
}
interface TherapistOption { id: number; name: string; }
interface InstitutionOption { id: number; name: string; }
interface RoomOption { id: number; name: string; room_code: string; }

const ISSUE_OPTIONS = ["情緒困擾", "人際關係", "家庭議題", "婚姻/伴侶", "職涯壓力", "創傷", "親職教養", "其他"];
const SOURCE_OPTIONS = ["自行來電", "機構轉介", "親友介紹", "網路查詢", "其他"];

export default function MatchPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [tab, setTab] = useState<"list" | "closed">("list");
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [therapists, setTherapists] = useState<TherapistOption[]>([]);
  const [institutions, setInstitutions] = useState<InstitutionOption[]>([]);
  const [rooms, setRooms] = useState<RoomOption[]>([]);
  const [modal, setModal] = useState<{ type: "assign" | "cancel" | "convert" | "arrival"; referral: Referral } | null>(null);

  const fetchList = () => {
    if (!token) return;
    setLoading(true);
    clientFetch(`/referrals?active_only=${tab === "list"}`, token)
      .then(setReferrals)
      .catch(() => setReferrals([]))
      .finally(() => setLoading(false));
  };

  useEffect(fetchList, [token, tab]);
  useEffect(() => {
    if (!token) return;
    clientFetch("/auth/therapists", token).then(setTherapists).catch(() => {});
    clientFetch("/institutions", token).then(setInstitutions).catch(() => {});
    clientFetch("/rooms", token).then(setRooms).catch(() => {});
  }, [token]);

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <h1 className="text-2xl font-bold">媒合管理</h1>
        <button onClick={() => setShowCreate(true)} className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-st-active">
          ＋ 新增諮商需求表
        </button>
      </div>
      <p className="mb-4 text-sm text-ink-3">媒合出第一次（初診）預約後，個案會自動出現在個案管理，本頁不再需要它</p>

      <div className="mb-4 flex gap-1 border-b border-line">
        {[
          { key: "list", label: "媒合列表" },
          { key: "closed", label: "媒合結案表" },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => { setTab(t.key as any); setExpanded(null); }}
            className={`px-4 py-2 text-sm font-medium ${tab === t.key ? "border-b-2 border-accent text-accent" : "text-ink-3 hover:text-ink-2"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading && <p className="text-sm text-ink-3">載入中...</p>}
      {!loading && referrals.length === 0 && (
        <div className="rounded-xl border border-dashed border-line py-12 text-center text-sm text-ink-3">目前沒有資料</div>
      )}

      <div className="space-y-2">
        {referrals.map((r) => (
          <div key={r.id} className="overflow-hidden rounded-lg border border-line bg-white">
            <div
              className="flex cursor-pointer items-center justify-between px-4 py-3 hover:bg-surface-2"
              onClick={() => setExpanded(expanded === r.id ? null : r.id)}
            >
              <div className="flex items-center gap-3">
                <span className="text-xs text-ink-3">{expanded === r.id ? "▾" : "▸"}</span>
                <span className="font-mono text-xs text-ink-3">{r.referral_code}</span>
                <span className="font-medium">{r.name}</span>
                <span className="text-xs text-ink-3">{r.age ? `${r.age}歲` : ""}{r.gender ? ` · ${r.gender}` : ""}</span>
                <span className="rounded bg-surface-2 px-1.5 py-0.5 text-xs text-ink-3">{MODE_LABEL[r.mode] ?? r.mode}</span>
                {r.designated_therapist_name && (
                  <span className="rounded bg-surface-3 text-ink-2 px-1.5 py-0.5 text-xs">指定：{r.designated_therapist_name}</span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className={`rounded px-2 py-0.5 text-xs font-medium ${STATUS_COLOR[r.status]}`}>{STATUS_LABEL[r.status] ?? r.status}</span>
              </div>
            </div>

            {expanded === r.id && (
              <div className="border-t border-line bg-surface-2 px-4 py-3">
                <div className="mb-3 grid grid-cols-2 gap-2 text-xs text-ink-2 md:grid-cols-4">
                  <div>電話：{r.phone ?? "—"}</div>
                  <div>轉介來源：{r.source ?? "—"}</div>
                  <div>可諮商時段：{r.availability ?? "—"}</div>
                  <div>疑似方案：{r.institution_name ?? r.funding_note ?? "自費"}</div>
                  <div className="col-span-2">主述議題：{(r.issues ?? []).join("、") || "—"}{r.issue_note ? `（${r.issue_note}）` : ""}</div>
                  <div className="col-span-2">備註：{r.note ?? "—"}</div>
                </div>

                {r.batches.length > 0 && (
                  <div className="mb-3 overflow-x-auto rounded border border-line bg-white">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-line text-left text-ink-3">
                          <th className="px-3 py-2">第幾次派案</th>
                          <th className="px-3 py-2">派案日期</th>
                          <th className="px-3 py-2">狀態</th>
                          <th className="px-3 py-2">受邀心理師</th>
                        </tr>
                      </thead>
                      <tbody>
                        {r.batches.map((b) => (
                          <tr key={b.id} className="border-b border-line last:border-b-0">
                            <td className="whitespace-nowrap px-3 py-2">第 {b.batch_seq} 次</td>
                            <td className="whitespace-nowrap px-3 py-2">{b.sent_at ? new Date(b.sent_at).toLocaleString("zh-TW") : "—"}</td>
                            <td className="whitespace-nowrap px-3 py-2">{b.is_open ? "等待回覆" : "已結束"}</td>
                            <td className="px-3 py-2">
                              {b.members.map((m) => (
                                <div key={m.id} className="mb-0.5 last:mb-0">
                                  {m.therapist_name} — {REPLY_LABEL[m.reply_status] ?? m.reply_status}
                                  {m.decline_reason ? `（${DECLINE_LABEL[m.decline_reason] ?? m.decline_reason}）` : ""}
                                  {m.proposed_slots && m.proposed_slots.length > 0 && (
                                    <span className="text-ink-3"> · 提供時段：{m.proposed_slots.map((s) => new Date(s).toLocaleString("zh-TW")).join("、")}</span>
                                  )}
                                </div>
                              ))}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {r.status === "booked" && (
                  <div className="mb-3 rounded border border-accent/40 bg-accent-soft px-3 py-2 text-xs text-accent">
                    已建立初診預約（appointment #{r.appointment_id}），心理師：{r.accepted_therapist_name}
                  </div>
                )}
                {(r.status === "converted" || r.status === "cancelled" || r.status === "closed") && (
                  <div className="mb-3 text-xs text-ink-3">
                    {r.status === "converted" && `已轉個案 #${r.converted_case_id}`}
                    {r.close_reason && ` · 原因：${r.close_reason}`}
                    {r.closed_at && ` · ${new Date(r.closed_at).toLocaleString("zh-TW")}`}
                  </div>
                )}

                <div className="flex flex-wrap gap-2">
                  {(r.status === "new" || r.status === "unmatched") && (
                    <button onClick={() => setModal({ type: "assign", referral: r })} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-st-active">
                      派案心理師
                    </button>
                  )}
                  {r.status === "accepted" && (
                    <button onClick={() => setModal({ type: "convert", referral: r })} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-st-active">
                      轉預約
                    </button>
                  )}
                  {r.status === "booked" && (
                    <button onClick={() => setModal({ type: "arrival", referral: r })} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-st-active">
                      初診報到 ▸
                    </button>
                  )}
                  {["new", "matching", "unmatched", "accepted", "booked"].includes(r.status) && (
                    <button onClick={() => setModal({ type: "cancel", referral: r })} className="rounded-lg border border-line px-3 py-1.5 text-xs text-ink-3 hover:bg-surface-2">
                      取消媒合
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {showCreate && (
        <CreateReferralModal
          token={token}
          therapists={therapists}
          institutions={institutions}
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); fetchList(); }}
        />
      )}
      {modal?.type === "assign" && (
        <AssignModal token={token} referral={modal.referral} therapists={therapists} onClose={() => setModal(null)} onDone={() => { setModal(null); fetchList(); }} />
      )}
      {modal?.type === "cancel" && (
        <CancelModal token={token} referral={modal.referral} onClose={() => setModal(null)} onDone={() => { setModal(null); fetchList(); }} />
      )}
      {modal?.type === "convert" && (
        <ConvertModal token={token} referral={modal.referral} rooms={rooms} institutions={institutions} onClose={() => setModal(null)} onDone={() => { setModal(null); fetchList(); }} />
      )}
      {modal?.type === "arrival" && (
        <ArrivalModal token={token} referral={modal.referral} onClose={() => setModal(null)} onDone={() => { setModal(null); fetchList(); }} />
      )}
    </div>
  );
}

function ModalShell({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div className="max-h-[85vh] w-[480px] overflow-y-auto rounded-xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 font-semibold">{title}</h3>
        {children}
      </div>
    </div>
  );
}

function CreateReferralModal({
  token, therapists, institutions, onClose, onCreated,
}: { token: string; therapists: TherapistOption[]; institutions: InstitutionOption[]; onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState("");
  const [phone, setPhone] = useState("");
  const [mode, setMode] = useState("in_person");
  const [institutionId, setInstitutionId] = useState("");
  const [fundingNote, setFundingNote] = useState("");
  const [issues, setIssues] = useState<string[]>([]);
  const [issueNote, setIssueNote] = useState("");
  const [designatedId, setDesignatedId] = useState("");
  const [source, setSource] = useState("");
  const [availability, setAvailability] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const toggleIssue = (v: string) => setIssues((prev) => (prev.includes(v) ? prev.filter((x) => x !== v) : [...prev, v]));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await clientFetch("/referrals", token, {
        method: "POST",
        body: JSON.stringify({
          name, age: age ? Number(age) : null, gender: gender || null, phone: phone || null, mode,
          institution_id: institutionId ? Number(institutionId) : null,
          funding_note: fundingNote || null,
          issues: issues.length ? issues : null,
          issue_note: issueNote || null,
          designated_therapist_id: designatedId ? Number(designatedId) : null,
          source: source || null,
          availability: availability || null,
          note: note || null,
        }),
      });
      onCreated();
    } catch (e: any) {
      setError(e.message ?? "建立失敗");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ModalShell title="新增諮商需求表" onClose={onClose}>
      {error && <div className="mb-3 rounded-lg bg-st-danger-bg px-3 py-2 text-xs text-st-danger">{error}</div>}
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-3 gap-2">
          <label className="col-span-2 block">
            <span className="mb-1 block text-xs text-ink-3">姓名 <span className="text-st-danger">*</span></span>
            <input required value={name} onChange={(e) => setName(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">年齡</span>
            <input type="number" value={age} onChange={(e) => setAge(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">性別</span>
            <select value={gender} onChange={(e) => setGender(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
              <option value="">未填</option>
              <option value="male">男</option>
              <option value="female">女</option>
              <option value="other">其他</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">電話</span>
            <input value={phone} onChange={(e) => setPhone(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
          </label>
        </div>
        <label className="block">
          <span className="mb-1 block text-xs text-ink-3">諮商型態</span>
          <select value={mode} onChange={(e) => setMode(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
            <option value="in_person">現場</option>
            <option value="online">線上</option>
            <option value="outdoor">外展</option>
          </select>
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">疑似機構方案</span>
            <select value={institutionId} onChange={(e) => setInstitutionId(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
              <option value="">自費</option>
              {institutions.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">方案備註</span>
            <input value={fundingNote} onChange={(e) => setFundingNote(e.target.value)} placeholder="如「衛生局市民方案」" className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
          </label>
        </div>
        <div>
          <span className="mb-1 block text-xs text-ink-3">主述議題</span>
          <div className="flex flex-wrap gap-2">
            {ISSUE_OPTIONS.map((opt) => (
              <label key={opt} className={`cursor-pointer rounded-full border px-2.5 py-1 text-xs ${issues.includes(opt) ? "border-accent bg-accent-soft text-accent" : "border-line text-ink-3"}`}>
                <input type="checkbox" className="hidden" checked={issues.includes(opt)} onChange={() => toggleIssue(opt)} />
                {opt}
              </label>
            ))}
          </div>
        </div>
        <label className="block">
          <span className="mb-1 block text-xs text-ink-3">議題補充說明</span>
          <textarea value={issueNote} onChange={(e) => setIssueNote(e.target.value)} rows={2} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">指定心理師</span>
            <select value={designatedId} onChange={(e) => setDesignatedId(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
              <option value="">不指定</option>
              {therapists.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">轉介來源</span>
            <select value={source} onChange={(e) => setSource(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
              <option value="">未填</option>
              {SOURCE_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
        </div>
        {source === "親友介紹" && (
          <div className="rounded bg-st-warn-bg px-3 py-2 text-xs text-st-warn">⚠️ 管道來源為親友介紹，請留意雙重關係風險</div>
        )}
        <label className="block">
          <span className="mb-1 block text-xs text-ink-3">可諮商時段</span>
          <input value={availability} onChange={(e) => setAvailability(e.target.value)} placeholder="如「週二下午、週四晚上」" className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-ink-3">備註</span>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
        </label>
        <div className="flex gap-2 pt-2">
          <button type="submit" disabled={saving} className="flex-1 rounded-lg bg-accent py-2 text-sm font-medium text-white hover:bg-st-active disabled:opacity-50">
            {saving ? "建立中…" : "建立"}
          </button>
          <button type="button" onClick={onClose} className="rounded-lg border border-line px-4 py-2 text-sm text-ink-3 hover:bg-surface-2">取消</button>
        </div>
      </form>
    </ModalShell>
  );
}

function AssignModal({
  token, referral, therapists, onClose, onDone,
}: { token: string; referral: Referral; therapists: TherapistOption[]; onClose: () => void; onDone: () => void }) {
  const [selected, setSelected] = useState<number[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const toggle = (id: number) => setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 3 ? [...prev, id] : prev));

  async function handleSubmit() {
    if (selected.length === 0) { setError("請至少選擇一位心理師"); return; }
    setSaving(true);
    setError("");
    try {
      await clientFetch(`/referrals/${referral.id}/assign`, token, { method: "PUT", body: JSON.stringify({ therapist_ids: selected }) });
      onDone();
    } catch (e: any) {
      setError(e.message ?? "派案失敗");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ModalShell title={`派案心理師（${referral.name}）`} onClose={onClose}>
      {error && <div className="mb-3 rounded-lg bg-st-danger-bg px-3 py-2 text-xs text-st-danger">{error}</div>}
      <p className="mb-2 text-xs text-ink-3">可同時詢問 1～3 位，先回先得</p>
      <div className="max-h-64 space-y-1 overflow-y-auto">
        {therapists.map((t) => (
          <label key={t.id} className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm ${selected.includes(t.id) ? "border-accent bg-accent-soft" : "border-line"}`}>
            <input type="checkbox" checked={selected.includes(t.id)} onChange={() => toggle(t.id)} />
            {t.name}
            {referral.designated_therapist_id === t.id && <span className="text-xs font-bold text-ink">（指定）</span>}
          </label>
        ))}
      </div>
      <div className="flex gap-2 pt-4">
        <button onClick={handleSubmit} disabled={saving} className="flex-1 rounded-lg bg-accent py-2 text-sm font-medium text-white hover:bg-st-active disabled:opacity-50">
          {saving ? "送出中…" : `送出（已選 ${selected.length}/3）`}
        </button>
        <button onClick={onClose} className="rounded-lg border border-line px-4 py-2 text-sm text-ink-3 hover:bg-surface-2">取消</button>
      </div>
    </ModalShell>
  );
}

function CancelModal({ token, referral, onClose, onDone }: { token: string; referral: Referral; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit() {
    if (!reason.trim()) { setError("請填寫取消原因"); return; }
    setSaving(true);
    setError("");
    try {
      await clientFetch(`/referrals/${referral.id}/cancel`, token, { method: "PUT", body: JSON.stringify({ reason }) });
      onDone();
    } catch (e: any) {
      setError(e.message ?? "取消失敗");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ModalShell title={`取消媒合（${referral.name}）`} onClose={onClose}>
      {error && <div className="mb-3 rounded-lg bg-st-danger-bg px-3 py-2 text-xs text-st-danger">{error}</div>}
      <label className="block">
        <span className="mb-1 block text-xs text-ink-3">取消原因</span>
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
      </label>
      <div className="flex gap-2 pt-4">
        <button onClick={handleSubmit} disabled={saving} className="flex-1 rounded-lg border border-st-danger/40 py-2 text-sm font-medium text-st-danger hover:bg-st-danger hover:text-surface disabled:opacity-50">
          {saving ? "送出中…" : "確認取消"}
        </button>
        <button onClick={onClose} className="rounded-lg border border-line px-4 py-2 text-sm text-ink-3 hover:bg-surface-2">返回</button>
      </div>
    </ModalShell>
  );
}

function ConvertModal({
  token, referral, rooms, institutions, onClose, onDone,
}: { token: string; referral: Referral; rooms: RoomOption[]; institutions: InstitutionOption[]; onClose: () => void; onDone: () => void }) {
  const acceptedBatch = referral.batches[referral.batches.length - 1];
  const acceptedMember = acceptedBatch?.members.find((m) => m.therapist_id === referral.accepted_therapist_id);
  const firstSlot = acceptedMember?.proposed_slots?.[0] ?? "";

  const [sessionType, setSessionType] = useState(referral.mode || "in_person");
  const [roomId, setRoomId] = useState("");
  const [startTime, setStartTime] = useState(firstSlot ? firstSlot.slice(0, 16) : "");
  const [durationMin, setDurationMin] = useState(60);
  const [amount, setAmount] = useState("1600");
  const [fundingSource, setFundingSource] = useState(referral.institution_id ? "institution" : "self_pay");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit() {
    if (!startTime) { setError("請選擇開始時間"); return; }
    if (sessionType === "in_person" && !roomId) { setError("現場諮商需選擇診間"); return; }
    setSaving(true);
    setError("");
    try {
      const start = new Date(startTime);
      const end = new Date(start.getTime() + durationMin * 60000);
      await clientFetch(`/referrals/${referral.id}/convert`, token, {
        method: "PUT",
        body: JSON.stringify({
          room_id: roomId ? Number(roomId) : null,
          session_type: sessionType,
          start_time: start.toISOString(),
          end_time: end.toISOString(),
          amount: amount ? Number(amount) : null,
          funding_source: fundingSource,
        }),
      });
      onDone();
    } catch (e: any) {
      setError(e.message ?? "轉預約失敗");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ModalShell title={`轉預約（${referral.name}）`} onClose={onClose}>
      {error && <div className="mb-3 rounded-lg bg-st-danger-bg px-3 py-2 text-xs text-st-danger">{error}</div>}
      {acceptedMember?.proposed_slots && (
        <div className="mb-3 rounded bg-accent-soft text-accent px-3 py-2 text-xs">
          {acceptedMember.therapist_name} 提供的時段：{acceptedMember.proposed_slots.map((s) => new Date(s).toLocaleString("zh-TW")).join("、")}
        </div>
      )}
      <div className="space-y-3">
        <label className="block">
          <span className="mb-1 block text-xs text-ink-3">諮商型態</span>
          <select value={sessionType} onChange={(e) => setSessionType(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
            <option value="in_person">現場</option>
            <option value="online">線上</option>
            <option value="outdoor">外展</option>
          </select>
        </label>
        {sessionType === "in_person" && (
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">診間</span>
            <select value={roomId} onChange={(e) => setRoomId(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
              <option value="">請選擇</option>
              {rooms.map((r) => <option key={r.id} value={r.id}>{r.name}（{r.room_code}）</option>)}
            </select>
          </label>
        )}
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">開始時間</span>
            <input type="datetime-local" value={startTime} onChange={(e) => setStartTime(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">時長（分鐘）</span>
            <input type="number" step={15} value={durationMin} onChange={(e) => setDurationMin(Number(e.target.value))} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">繳費方式</span>
            <select value={fundingSource} onChange={(e) => setFundingSource(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
              <option value="self_pay">自費</option>
              <option value="institution">機構</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">金額</span>
            <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
          </label>
        </div>
        {fundingSource === "institution" && (
          <p className="text-xs text-ink-3">機構方案額度與自付額請至個案管理／機構合約頁面掛入方案後再調整；此處先以自付額試算。</p>
        )}
      </div>
      <div className="flex gap-2 pt-4">
        <button onClick={handleSubmit} disabled={saving} className="flex-1 rounded-lg bg-accent py-2 text-sm font-medium text-white hover:bg-st-active disabled:opacity-50">
          {saving ? "建立中…" : "存檔並寫入診間日曆"}
        </button>
        <button onClick={onClose} className="rounded-lg border border-line px-4 py-2 text-sm text-ink-3 hover:bg-surface-2">取消</button>
      </div>
    </ModalShell>
  );
}

function ArrivalModal({ token, referral, onClose, onDone }: { token: string; referral: Referral; onClose: () => void; onDone: () => void }) {
  const [mode, setMode] = useState<"arrived" | "no_show" | null>(null);
  const [nationalId, setNationalId] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [phone, setPhone] = useState(referral.phone ?? "");
  const [noShowReason, setNoShowReason] = useState("unreachable");
  const [nextAction, setNextAction] = useState<"rebook" | "reassign" | "close">("rebook");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function submitArrived() {
    setSaving(true);
    setError("");
    try {
      await clientFetch(`/referrals/${referral.id}/arrived`, token, {
        method: "PUT",
        body: JSON.stringify({ national_id: nationalId || null, birth_date: birthDate || null, phone: phone || null }),
      });
      onDone();
    } catch (e: any) {
      setError(e.message ?? "報到失敗");
    } finally {
      setSaving(false);
    }
  }

  async function submitNoShow() {
    setSaving(true);
    setError("");
    try {
      await clientFetch(`/referrals/${referral.id}/no-show`, token, {
        method: "PUT",
        body: JSON.stringify({ reason: noShowReason, next_action: nextAction }),
      });
      onDone();
    } catch (e: any) {
      setError(e.message ?? "操作失敗");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ModalShell title={`初診報到（${referral.name}）`} onClose={onClose}>
      {error && <div className="mb-3 rounded-lg bg-st-danger-bg px-3 py-2 text-xs text-st-danger">{error}</div>}
      {mode === null && (
        <div className="flex gap-2">
          {/* v7 定案 ③：已到／未到一律中性黑白，不用綠紅實心——顏色留給狀態。
              跟診間日曆的報到面板同一個寫法，行政在兩個地方看到的是同一組鍵 */}
          <button onClick={() => setMode("arrived")} className="flex-1 rounded-lg bg-accent py-3 text-sm font-medium text-white hover:bg-st-active">初診有到</button>
          <button onClick={() => setMode("no_show")} className="flex-1 rounded-lg border border-line-2 py-3 text-sm text-ink-2 hover:bg-surface-2">初診未到</button>
        </div>
      )}
      {mode === "arrived" && (
        <div className="space-y-3">
          <p className="text-xs text-ink-3">需求表資料已自動帶入，只需補身分證等個資以產生病歷號</p>
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">身分證字號</span>
            <input value={nationalId} onChange={(e) => setNationalId(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">出生日期</span>
              <input type="date" value={birthDate} onChange={(e) => setBirthDate(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">電話</span>
              <input value={phone} onChange={(e) => setPhone(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
            </label>
          </div>
          <div className="flex gap-2 pt-2">
            <button onClick={submitArrived} disabled={saving} className="flex-1 rounded-lg bg-accent py-2 text-sm font-medium text-white hover:bg-st-active disabled:opacity-50">
              {saving ? "處理中…" : "產生病歷號並轉為個案"}
            </button>
            <button onClick={() => setMode(null)} className="rounded-lg border border-line px-4 py-2 text-sm text-ink-3 hover:bg-surface-2">返回</button>
          </div>
        </div>
      )}
      {mode === "no_show" && (
        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">未到原因</span>
            <select value={noShowReason} onChange={(e) => setNoShowReason(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
              <option value="case_leave">個案來電請假</option>
              <option value="last_minute_cancel">臨時取消</option>
              <option value="unreachable">未聯繫上</option>
              <option value="other">其他</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">後續處理</span>
            <select value={nextAction} onChange={(e) => setNextAction(e.target.value as any)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
              <option value="rebook">轉預約（同一心理師重排時間）</option>
              <option value="reassign">派案（改派其他心理師）</option>
              <option value="close">轉媒合結案</option>
            </select>
          </label>
          <div className="flex gap-2 pt-2">
            <button onClick={submitNoShow} disabled={saving} className="flex-1 rounded-lg bg-ink py-2 text-sm font-medium text-surface hover:bg-ink-2 disabled:opacity-50">
              {saving ? "處理中…" : "確認"}
            </button>
            <button onClick={() => setMode(null)} className="rounded-lg border border-line px-4 py-2 text-sm text-ink-3 hover:bg-surface-2">返回</button>
          </div>
        </div>
      )}
    </ModalShell>
  );
}
