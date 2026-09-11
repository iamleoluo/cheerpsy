"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

/**
 * 派案邀請（心理師端）：待回覆／已承接／已結束。見 document_reference/
 * cheerpsy_v7_spec_extracted.md「派案邀請」。
 */

const MODE_LABEL: Record<string, string> = { in_person: "現場", online: "線上", outdoor: "外展" };
const DECLINE_REASONS = [
  { value: "unavailable", label: "時段無法配合" },
  { value: "not_specialty", label: "非專長" },
  { value: "dual_relationship", label: "雙重關係" },
  { value: "other", label: "其他" },
];
const REPLY_LABEL: Record<string, string> = {
  declined: "已婉拒",
  superseded: "已被他人承接",
  expired: "逾時未回覆",
  released: "承接後釋出",
};

interface Invite {
  member_id: number;
  referral_id: number;
  referral_code: string;
  name: string;
  age: number | null;
  gender: string | null;
  mode: string;
  issue_note: string | null;
  issues: string[] | null;
  source: string | null;
  is_dual_relationship_risk: boolean;
  availability: string | null;
  designated_label: string;
  other_pending_count: number;
  batch_seq: number;
  sent_at: string | null;
  reply_status: string;
  decline_reason: string | null;
  proposed_slots: string[] | null;
}

export default function PoolPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [tab, setTab] = useState<"pending" | "accepted" | "history">("pending");
  const [invites, setInvites] = useState<Invite[]>([]);
  const [loading, setLoading] = useState(false);
  const [acceptTarget, setAcceptTarget] = useState<Invite | null>(null);
  const [declineTarget, setDeclineTarget] = useState<Invite | null>(null);

  const fetchList = () => {
    if (!token) return;
    setLoading(true);
    clientFetch(`/referrals/pool/${tab}`, token)
      .then(setInvites)
      .catch(() => setInvites([]))
      .finally(() => setLoading(false));
  };

  useEffect(fetchList, [token, tab]);

  async function handleRelease(memberId: number) {
    if (!confirm("確定要釋出此案嗎？行政會需要重新派案。")) return;
    await clientFetch(`/referrals/pool/${memberId}/release`, token, { method: "PUT" });
    fetchList();
  }

  if (!token) return <p>Loading...</p>;

  const isOverdue = (sentAt: string | null) => sentAt && (Date.now() - new Date(sentAt).getTime()) / 86400000 > 1;

  return (
    <div>
      <h1 className="mb-1 text-2xl font-bold">派案邀請</h1>
      <p className="mb-4 text-sm text-ink-3">諮商需求表個資僅供參考，唯讀；個資編輯權限僅行政有</p>

      <div className="mb-4 flex gap-1 border-b border-line">
        {[
          { key: "pending", label: "待回覆" },
          { key: "accepted", label: "已承接" },
          { key: "history", label: "已結束" },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key as any)}
            className={`px-4 py-2 text-sm font-medium ${tab === t.key ? "border-b-2 border-accent text-accent" : "text-ink-3 hover:text-ink-2"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading && <p className="text-sm text-ink-3">載入中...</p>}
      {!loading && invites.length === 0 && (
        <div className="rounded-xl border border-dashed border-line py-12 text-center text-sm text-ink-3">目前沒有資料</div>
      )}

      <div className="space-y-3">
        {invites.map((inv) => (
          <div key={inv.member_id} className={`rounded-lg border bg-white p-4 ${tab === "pending" && isOverdue(inv.sent_at) ? "border-st-danger/30" : "border-line"}`}>
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-ink-3">{inv.referral_code}</span>
                <span className="font-medium">{inv.name}</span>
                <span className="text-xs text-ink-3">{inv.age ? `${inv.age}歲` : ""}{inv.gender ? ` · ${inv.gender}` : ""}</span>
                <span className="rounded bg-surface-2 px-1.5 py-0.5 text-xs text-ink-3">{MODE_LABEL[inv.mode] ?? inv.mode}</span>
              </div>
              {tab === "pending" && isOverdue(inv.sent_at) && <span className="rounded bg-st-danger-bg px-2 py-0.5 text-xs text-st-danger">逾時提醒</span>}
            </div>

            <div className="mb-2 flex flex-wrap gap-2 text-xs text-ink-3">
              <span className="rounded bg-surface-3 text-ink-2 px-2 py-0.5">{inv.designated_label}</span>
              {tab === "pending" && inv.other_pending_count > 0 && (
                <span className="rounded bg-st-warn-bg px-2 py-0.5 text-st-warn">另有 {inv.other_pending_count} 位心理師評估中</span>
              )}
              {inv.is_dual_relationship_risk && <span className="rounded bg-st-danger-bg px-2 py-0.5 text-st-danger">⚠️ 親友介紹，留意雙重關係</span>}
            </div>

            <div className="mb-3 text-xs text-ink-2">
              <div>主述議題：{(inv.issues ?? []).join("、") || "—"}{inv.issue_note ? `（${inv.issue_note}）` : ""}</div>
              <div>可諮商時段：{inv.availability ?? "—"}</div>
              {inv.proposed_slots && inv.proposed_slots.length > 0 && (
                <div>我提供的時段：{inv.proposed_slots.map((s) => new Date(s).toLocaleString("zh-TW")).join("、")}</div>
              )}
              {inv.decline_reason && <div>婉拒原因：{DECLINE_REASONS.find((d) => d.value === inv.decline_reason)?.label ?? inv.decline_reason}</div>}
              {tab === "history" && <div className="text-ink-3">狀態：{REPLY_LABEL[inv.reply_status] ?? inv.reply_status}</div>}
            </div>

            {tab === "pending" && (
              <div className="flex gap-2">
                <button onClick={() => setAcceptTarget(inv)} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-st-active">
                  願意承接
                </button>
                <button onClick={() => setDeclineTarget(inv)} className="rounded-lg border border-line px-3 py-1.5 text-xs text-ink-3 hover:bg-surface-2">
                  無意願承接
                </button>
              </div>
            )}
            {tab === "accepted" && (
              <button onClick={() => handleRelease(inv.member_id)} className="rounded-lg border border-st-danger/30 px-3 py-1.5 text-xs text-st-danger hover:bg-st-danger-bg">
                釋出（不承接此案）
              </button>
            )}
          </div>
        ))}
      </div>

      {acceptTarget && (
        <AcceptModal token={token} invite={acceptTarget} onClose={() => setAcceptTarget(null)} onDone={() => { setAcceptTarget(null); fetchList(); }} />
      )}
      {declineTarget && (
        <DeclineModal token={token} invite={declineTarget} onClose={() => setDeclineTarget(null)} onDone={() => { setDeclineTarget(null); fetchList(); }} />
      )}
    </div>
  );
}

function ModalShell({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div className="w-[420px] rounded-xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 font-semibold">{title}</h3>
        {children}
      </div>
    </div>
  );
}

function AcceptModal({ token, invite, onClose, onDone }: { token: string; invite: Invite; onClose: () => void; onDone: () => void }) {
  const [slot1, setSlot1] = useState("");
  const [slot2, setSlot2] = useState("");
  const [slot3, setSlot3] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit() {
    if (!slot1) { setError("請至少提供第一個可預約時段"); return; }
    setSaving(true);
    setError("");
    try {
      const slots = [slot1, slot2, slot3].filter(Boolean).map((s) => new Date(s).toISOString());
      await clientFetch(`/referrals/pool/${invite.member_id}/accept`, token, { method: "PUT", body: JSON.stringify({ slots }) });
      onDone();
    } catch (e: any) {
      setError(e.message ?? "送出失敗");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ModalShell title={`願意承接（${invite.name}）— 提供可預約時段`} onClose={onClose}>
      {error && <div className="mb-3 rounded-lg bg-st-danger-bg px-3 py-2 text-xs text-st-danger">{error}</div>}
      <div className="space-y-2">
        <label className="block">
          <span className="mb-1 block text-xs text-ink-3">時段一 <span className="text-st-danger">*</span></span>
          <input type="datetime-local" value={slot1} onChange={(e) => setSlot1(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-ink-3">時段二（選填）</span>
          <input type="datetime-local" value={slot2} onChange={(e) => setSlot2(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-ink-3">時段三（選填）</span>
          <input type="datetime-local" value={slot3} onChange={(e) => setSlot3(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
        </label>
      </div>
      <div className="flex gap-2 pt-4">
        <button onClick={handleSubmit} disabled={saving} className="flex-1 rounded-lg bg-accent py-2 text-sm font-medium text-white hover:bg-st-active disabled:opacity-50">
          {saving ? "送出中…" : "送出"}
        </button>
        <button onClick={onClose} className="rounded-lg border border-line px-4 py-2 text-sm text-ink-3 hover:bg-surface-2">取消</button>
      </div>
    </ModalShell>
  );
}

function DeclineModal({ token, invite, onClose, onDone }: { token: string; invite: Invite; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("unavailable");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit() {
    setSaving(true);
    setError("");
    try {
      await clientFetch(`/referrals/pool/${invite.member_id}/decline`, token, { method: "PUT", body: JSON.stringify({ reason }) });
      onDone();
    } catch (e: any) {
      setError(e.message ?? "送出失敗");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ModalShell title={`無意願承接（${invite.name}）`} onClose={onClose}>
      {error && <div className="mb-3 rounded-lg bg-st-danger-bg px-3 py-2 text-xs text-st-danger">{error}</div>}
      <label className="block">
        <span className="mb-1 block text-xs text-ink-3">原因</span>
        <select value={reason} onChange={(e) => setReason(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
          {DECLINE_REASONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
        </select>
      </label>
      <div className="flex gap-2 pt-4">
        <button onClick={handleSubmit} disabled={saving} className="flex-1 rounded-lg border border-st-danger/40 py-2 text-sm font-medium text-st-danger hover:bg-st-danger hover:text-surface disabled:opacity-50">
          {saving ? "送出中…" : "確認婉拒"}
        </button>
        <button onClick={onClose} className="rounded-lg border border-line px-4 py-2 text-sm text-ink-3 hover:bg-surface-2">返回</button>
      </div>
    </ModalShell>
  );
}
