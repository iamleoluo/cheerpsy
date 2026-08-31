"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

interface Slot {
  id: number;
  seq: number;
  slot_date: string;
  start_time: string;
  end_time: string;
  is_selected: boolean;
}

interface Invite {
  target_id: number;
  referral_id: number;
  dispatch_code: string;
  name: string;
  age: number | null;
  gender: string | null;
  chief_complaint: string | null;
  complaint_note: string | null;
  consultation_mode: string;
  funding_source: string;
  plan_name: string | null;
  status: string;
  dispatched_at: string;
  designation: "self" | "none" | "other_unavailable";
  others_evaluating: number;
  is_overdue: boolean;
  dual_relationship_warning: boolean;
  slots: Slot[];
  decline_reason: string | null;
}

const MODE: Record<string, string> = {
  individual: "個人一對一",
  couple: "伴侶諮商",
  visitation: "會面交往",
  family_group: "親子／團體",
};
const TARGET_STATUS: Record<string, string> = {
  pending: "待回覆",
  accepted: "已承接",
  declined: "已婉拒",
  taken: "被他人承接",
  expired: "已退回",
  released: "承接後釋出",
};
const DECLINE_OPTIONS: [string, string][] = [
  ["not_my_field", "此議題非我專長領域"],
  ["fully_booked", "近期案量已滿"],
  ["dual_relationship", "可能構成雙重關係"],
  ["other", "其他"],
];

const TABS = [
  ["pending", "待回覆"],
  ["accepted", "已承接"],
  ["closed", "已結束"],
] as const;

export default function PoolPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [tab, setTab] = useState<"pending" | "accepted" | "closed">("pending");
  const [items, setItems] = useState<Invite[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState<{ kind: "accept" | "decline"; invite: Invite } | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      setItems(await clientFetch(`/referrals/invites?tab=${tab}`, token));
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, tab]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <p className="p-6 text-gray-400">載入中...</p>;

  return (
    <div>
      <h1 className="text-2xl font-bold">派案邀請</h1>
      <p className="mt-1 text-sm text-gray-500">
        行政派案後會出現在這裡，<b>先回先得</b>。逾 3 個自然日未回覆會自動退回行政。
      </p>

      <div className="mb-4 mt-4 flex gap-2 border-b border-gray-200">
        {TABS.map(([k, label]) => (
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
            {k === "pending" && items.length > 0 && tab === "pending" && (
              <span className="ml-1.5 rounded-full bg-red-500 px-1.5 text-[10px] text-white">
                {items.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      {items.length === 0 && (
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-12 text-center text-gray-400">
          目前沒有{TABS.find((t) => t[0] === tab)?.[1]}的派案
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {items.map((it) => (
          <div
            key={it.target_id}
            className={`rounded-xl border bg-white p-4 ${
              it.is_overdue ? "border-red-300" : "border-gray-200"
            }`}
          >
            <div className="mb-2 flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-base font-semibold">{it.name}</span>
                  <span className="text-xs text-gray-500">
                    {it.age ?? "—"} 歲 ·{" "}
                    {it.gender === "male" ? "男" : it.gender === "female" ? "女" : "—"}
                  </span>
                </div>
                <div className="mt-0.5 font-mono text-xs text-gray-400">{it.dispatch_code}</div>
              </div>
              <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
                {TARGET_STATUS[it.status] ?? it.status}
              </span>
            </div>

            {it.is_overdue && (
              <div className="mb-2 rounded bg-red-50 px-2 py-1 text-xs text-red-700">
                ⏰ 已逾 1 天未回覆，逾 3 天將自動退回行政
              </div>
            )}
            {it.dual_relationship_warning && (
              <div className="mb-2 rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">
                ⚠️ 管道來源為親友介紹，請留意雙重關係
              </div>
            )}

            <dl className="space-y-1 text-sm">
              <div className="flex gap-2">
                <dt className="w-20 shrink-0 text-gray-500">主述議題</dt>
                <dd>{it.chief_complaint || "—"}</dd>
              </div>
              {it.complaint_note && (
                <div className="flex gap-2">
                  <dt className="w-20 shrink-0 text-gray-500">補充說明</dt>
                  <dd className="text-gray-600">{it.complaint_note}</dd>
                </div>
              )}
              <div className="flex gap-2">
                <dt className="w-20 shrink-0 text-gray-500">諮商型態</dt>
                <dd>{MODE[it.consultation_mode] ?? it.consultation_mode}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-20 shrink-0 text-gray-500">繳費方式</dt>
                <dd>{it.funding_source === "self_pay" ? "自費" : it.plan_name || "機構"}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-20 shrink-0 text-gray-500">指定</dt>
                <dd>
                  {it.designation === "self" ? (
                    <span className="font-medium text-primary-700">指定本人</span>
                  ) : it.designation === "other_unavailable" ? (
                    "指定心理師無法安排"
                  ) : (
                    "不指定"
                  )}
                </dd>
              </div>
            </dl>

            {it.status === "pending" && it.others_evaluating > 0 && (
              <p className="mt-2 text-xs text-gray-500">
                另有 {it.others_evaluating} 位心理師評估中（先回先得）
              </p>
            )}

            {it.slots.length > 0 && (
              <div className="mt-3 rounded-lg bg-gray-50 px-3 py-2">
                <div className="mb-1 text-xs text-gray-500">我提供的可預約時段</div>
                {it.slots.map((s) => (
                  <div key={s.id} className="text-sm">
                    {s.seq}. {s.slot_date} {s.start_time}–{s.end_time}
                    {s.is_selected && (
                      <span className="ml-2 rounded bg-green-100 px-1.5 text-xs text-green-700">
                        行政已選定
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {it.decline_reason && (
              <p className="mt-2 text-xs text-gray-500">
                婉拒原因：{DECLINE_OPTIONS.find((d) => d[0] === it.decline_reason)?.[1]}
              </p>
            )}

            {it.status === "pending" && (
              <div className="mt-4 flex gap-2">
                <button
                  onClick={() => setActing({ kind: "accept", invite: it })}
                  className="flex-1 rounded-lg bg-primary-600 px-3 py-2 text-sm font-medium text-white hover:bg-primary-700"
                >
                  願意承接
                </button>
                <button
                  onClick={() => setActing({ kind: "decline", invite: it })}
                  className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm hover:bg-gray-50"
                >
                  無意願承接
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {acting?.kind === "accept" && (
        <AcceptModal
          token={token}
          invite={acting.invite}
          onClose={() => setActing(null)}
          onDone={() => {
            setActing(null);
            load();
          }}
        />
      )}
      {acting?.kind === "decline" && (
        <DeclineModal
          token={token}
          invite={acting.invite}
          onClose={() => setActing(null)}
          onDone={() => {
            setActing(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function AcceptModal({
  token,
  invite,
  onClose,
  onDone,
}: {
  token: string;
  invite: Invite;
  onClose: () => void;
  onDone: () => void;
}) {
  const empty = { slot_date: "", start_time: "", end_time: "" };
  const [slots, setSlots] = useState([{ ...empty }, { ...empty }, { ...empty }]);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function upd(i: number, k: string, v: string) {
    setSlots((s) => {
      const n = [...s];
      n[i] = { ...n[i], [k]: v };
      // 選了開始時間自動 +1 小時
      if (k === "start_time" && v && !n[i].end_time) {
        const [h, m] = v.split(":").map(Number);
        n[i].end_time = `${String((h + 1) % 24).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
      }
      return n;
    });
  }

  async function go(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    const filled = slots.filter((s) => s.slot_date && s.start_time && s.end_time);
    try {
      await clientFetch(`/referrals/invites/${invite.target_id}/accept`, token, {
        method: "POST",
        body: JSON.stringify({ slots: filled }),
      });
      onDone();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <form
        onSubmit={go}
        className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl"
      >
        <h2 className="mb-1 text-lg font-bold">可預約時段</h2>
        <p className="mb-4 text-sm text-gray-500">
          承接 {invite.name}（{invite.dispatch_code}）。<b>第 1 個必填</b>，第 2、3 個選填，
          行政會從中挑一個安排初診。
        </p>
        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}
        {slots.map((s, i) => (
          <div key={i} className="mb-2 flex items-center gap-2">
            <span className="w-12 shrink-0 text-sm text-gray-500">
              {i + 1}.{i === 0 ? " *" : ""}
            </span>
            <input
              type="date"
              required={i === 0}
              value={s.slot_date}
              onChange={(e) => upd(i, "slot_date", e.target.value)}
              className="flex-1 rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
            />
            <input
              type="time"
              step="900"
              required={i === 0}
              value={s.start_time}
              onChange={(e) => upd(i, "start_time", e.target.value)}
              className="w-28 rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
            />
            <span className="text-gray-400">–</span>
            <input
              type="time"
              step="900"
              required={i === 0}
              value={s.end_time}
              onChange={(e) => upd(i, "end_time", e.target.value)}
              className="w-28 rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
            />
          </div>
        ))}
        <p className="mt-2 text-xs text-gray-400">
          提示：可先到「我的班表」確認空檔再回來填。
        </p>
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
            className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {saving ? "送出中..." : "確認承接"}
          </button>
        </div>
      </form>
    </div>
  );
}

function DeclineModal({
  token,
  invite,
  onClose,
  onDone,
}: {
  token: string;
  invite: Invite;
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("not_my_field");
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function go(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    try {
      await clientFetch(`/referrals/invites/${invite.target_id}/decline`, token, {
        method: "POST",
        body: JSON.stringify({ reason, note: note || null }),
      });
      onDone();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <form onSubmit={go} className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-bold">婉拒原因</h2>
        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}
        <div className="space-y-2">
          {DECLINE_OPTIONS.map(([k, label]) => (
            <label key={k} className="flex items-center gap-2 text-sm">
              <input type="radio" checked={reason === k} onChange={() => setReason(k)} />
              {label}
            </label>
          ))}
        </div>
        <textarea
          rows={2}
          required={reason === "other"}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={reason === "other" ? "請說明原因（必填）" : "補充說明（選填）"}
          className="mt-3 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm"
          >
            返回
          </button>
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-gray-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {saving ? "送出中..." : "確認婉拒"}
          </button>
        </div>
      </form>
    </div>
  );
}
