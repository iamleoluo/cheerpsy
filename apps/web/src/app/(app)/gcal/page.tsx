"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

/* ------------------------------------------------------------------ */
/*  日曆分享：每位心理師一本 Google 日曆（診所帳號擁有），這裡管分享對象。 */
/*  行政與管理員都可以填心理師的 Gmail、建立並分享、重寄邀請、取消分享；    */
/*  行政分享名單只有管理員能改。預約由背景工作者推到 Google；這裡看同步狀態。 */
/* ------------------------------------------------------------------ */

interface CalendarInfo {
  summary: string;
  share_status: "not_shared" | "invited" | "owner" | "unshared" | "error";
  shared_emails: string[];
  last_share_error: string | null;
  is_active: boolean;
  is_missing: boolean;
}

interface TherapistRow {
  id: number;
  name: string;
  user_code: string | null;
  has_account: boolean;
  is_active: boolean;
  share_email: string | null;
  calendar: CalendarInfo | null;
}

interface StaffEmails {
  emails: string[];
  can_edit: boolean;
  owner_email: string | null;
  synced?: number;
  failed?: number;
  note?: string | null;
}

interface Connection {
  status: "active" | "token_invalid" | "disconnected";
  google_email: string | null;
}

const SHARE_LABEL: Record<CalendarInfo["share_status"], { text: string; cls: string }> = {
  not_shared: { text: "尚未分享", cls: "bg-gray-100 text-gray-600" },
  invited: { text: "已送出邀請", cls: "bg-green-100 text-green-700" },
  owner: { text: "診所帳號（擁有者）", cls: "bg-blue-100 text-blue-700" },
  unshared: { text: "已取消分享", cls: "bg-amber-100 text-amber-700" },
  error: { text: "同步失敗", cls: "bg-red-100 text-red-700" },
};

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const INVITE_HELP =
  "你會收到 Google 的分享信，請在電腦版開啟並點「加入日曆」；之後場次會自動出現。請勿在這個日曆上改時間。";

export default function GcalPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const role = (session?.user as any)?.role;

  const [rows, setRows] = useState<TherapistRow[] | null>(null);
  const [staff, setStaff] = useState<StaffEmails | null>(null);
  const [conn, setConn] = useState<Connection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [r, s, c] = await Promise.all([
        clientFetch("/settings/google/therapists", token),
        clientFetch("/settings/google/staff-emails", token),
        clientFetch("/settings/clinic", token),
      ]);
      setRows(r);
      setStaff(s);
      setConn(c.connection);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, [token]);

  useEffect(() => {
    if (token) load();
  }, [token, load]);

  if (role && role !== "admin" && role !== "staff") {
    return <div className="flex h-64 items-center justify-center text-gray-400">僅行政人員與管理員可存取此頁面</div>;
  }
  if (!token) return <p className="p-6 text-gray-400">載入中...</p>;

  const connected = conn?.status === "active";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">日曆分享</h1>
        <p className="mt-1 text-sm text-gray-500">
          每位心理師有一本專屬的 Google 日曆（由診所帳號擁有），只包含他自己的場次。這裡決定誰能看到它。
          預約的新增、改期、換診間、取消會自動同步過去（背景處理，通常幾秒內）。請勿在 Google 上直接改行程，下次同步會被蓋掉。
        </p>
      </div>

      {error && <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
      {notice && <div className="rounded-lg bg-green-50 px-4 py-3 text-sm text-green-700">{notice}</div>}

      <ConnectionBanner conn={conn} role={role} />

      <SyncCard
        token={token}
        role={role}
        connected={connected}
        onNotice={(m) => {
          setNotice(m);
          setError(null);
        }}
        onError={(m) => {
          setError(m);
          setNotice(null);
        }}
      />

      <StaffEmailsCard
        token={token}
        data={staff}
        onSaved={(s) => {
          setStaff(s);
          setNotice(
            s.note ??
              (s.synced
                ? `名單已儲存，已同步 ${s.synced} 本日曆${s.failed ? `，${s.failed} 本失敗（見下表）` : ""}。`
                : "名單已儲存。"),
          );
          load();
        }}
        onError={setError}
      />

      <section className="rounded-xl border border-gray-200 bg-white">
        <div className="border-b border-gray-100 px-5 py-3">
          <h2 className="text-base font-semibold">心理師日曆</h2>
          <p className="mt-0.5 text-xs text-gray-500">
            填好心理師的 Gmail 後按「建立並分享」。對方會收到 Google 的分享信。信箱由行政統一填寫，心理師無法自己改。
          </p>
        </div>
        {!rows ? (
          <p className="p-5 text-sm text-gray-400">載入中...</p>
        ) : rows.length === 0 ? (
          <p className="p-5 text-sm text-gray-400">目前沒有心理師。</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs text-gray-500">
                <tr>
                  <th className="px-4 py-2">心理師</th>
                  <th className="px-4 py-2">分享用 Gmail</th>
                  <th className="px-4 py-2">日曆狀態</th>
                  <th className="px-4 py-2">操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <TherapistLine
                    key={r.id}
                    row={r}
                    token={token}
                    connected={connected}
                    onChanged={(next, msg) => {
                      setRows((cur) => (cur ? cur.map((x) => (x.id === next.id ? next : x)) : cur));
                      setNotice(msg ?? null);
                      setError(null);
                    }}
                    onError={(m) => {
                      setError(m);
                      setNotice(null);
                    }}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="border-t border-gray-100 bg-gray-50 px-5 py-3 text-xs text-gray-600">
          <p className="font-medium">可複製給心理師的說明：</p>
          <p className="mt-1 select-all">{INVITE_HELP}</p>
        </div>
      </section>
    </div>
  );
}

interface ProblemJob {
  id: number;
  status: "failed" | "blocked";
  attempts: number;
  last_error: string | null;
  appointment_number: string;
  therapist_name: string;
  starts_at: string | null;
}

interface SyncStatus {
  counts: Record<string, number>;
  problems: ProblemJob[];
  oldest_due_seconds: number | null;
  connection_status: string;
  can_resync: boolean;
}

function SyncCard({
  token,
  role,
  connected,
  onNotice,
  onError,
}: {
  token: string;
  role: string;
  connected: boolean;
  onNotice: (m: string) => void;
  onError: (m: string) => void;
}) {
  const [st, setSt] = useState<SyncStatus | null>(null);
  const [busy, setBusy] = useState<"retry" | "resync" | null>(null);
  const [confirmResync, setConfirmResync] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setSt(await clientFetch("/settings/google/sync", token));
    } catch (e: any) {
      onError(e.message);
    }
  }, [token, onError]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function act(kind: "retry" | "resync") {
    setBusy(kind);
    setConfirmResync(false);
    try {
      const r = await clientFetch(`/settings/google/sync/${kind}`, token, { method: "POST" });
      setSt(r.status);
      onNotice(r.message);
    } catch (e: any) {
      onError(e.message);
    } finally {
      setBusy(null);
    }
  }

  if (!st) return null;
  const c = st.counts;
  const waiting = (c.pending ?? 0) + (c.retry ?? 0) + (c.running ?? 0);
  const stuck = st.oldest_due_seconds !== null && st.oldest_due_seconds > 120;
  const hasProblems = (c.failed ?? 0) + (c.blocked ?? 0) > 0;

  return (
    <section className="rounded-xl border border-gray-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 px-5 py-3">
        <div>
          <h2 className="text-base font-semibold">預約同步狀態</h2>
          <p className="mt-0.5 text-xs text-gray-500">
            等待中 {waiting}　失敗 {c.failed ?? 0}　被擋住 {c.blocked ?? 0}　已完成 {c.done ?? 0}
          </p>
        </div>
        <div className="flex gap-2">
          {hasProblems && (
            <button
              onClick={() => act("retry")}
              disabled={busy !== null || !connected}
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50"
            >
              {busy === "retry" ? "排入中..." : "重試失敗工作"}
            </button>
          )}
          {role === "admin" &&
            (confirmResync ? (
              <span className="flex items-center gap-2 text-sm">
                <span className="text-gray-600">會重新推送區間內所有預約，確定？</span>
                <button onClick={() => act("resync")} className="rounded-lg bg-blue-600 px-3 py-1.5 text-white hover:bg-blue-700">
                  確定
                </button>
                <button onClick={() => setConfirmResync(false)} className="rounded-lg border border-gray-300 px-3 py-1.5 hover:bg-gray-50">
                  取消
                </button>
              </span>
            ) : (
              <button
                onClick={() => setConfirmResync(true)}
                disabled={busy !== null || !connected}
                className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50"
              >
                {busy === "resync" ? "排入中..." : "全部重新同步"}
              </button>
            ))}
        </div>
      </div>
      {stuck && (
        <div className="bg-amber-50 px-5 py-2 text-sm text-amber-800">
          有工作已等待超過 {Math.round((st.oldest_due_seconds ?? 0) / 60)} 分鐘還沒處理，背景同步程式可能沒有在執行，請通知系統管理員。
        </div>
      )}
      {hasProblems ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs text-gray-500">
              <tr>
                <th className="px-4 py-2">預約</th>
                <th className="px-4 py-2">心理師</th>
                <th className="px-4 py-2">狀態</th>
                <th className="px-4 py-2">原因</th>
              </tr>
            </thead>
            <tbody>
              {st.problems.map((p) => (
                <tr key={p.id} className="border-t border-gray-100">
                  <td className="px-4 py-2">
                    {p.appointment_number}
                    {p.starts_at && <span className="ml-2 text-xs text-gray-400">{new Date(p.starts_at).toLocaleString("zh-TW")}</span>}
                  </td>
                  <td className="px-4 py-2">{p.therapist_name}</td>
                  <td className="px-4 py-2">
                    <span className={`rounded px-1.5 py-0.5 text-xs ${p.status === "failed" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"}`}>
                      {p.status === "failed" ? `失敗（已試 ${p.attempts} 次）` : "被擋住"}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-600">{p.last_error ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="px-5 py-3 text-sm text-gray-500">目前沒有失敗或被擋住的工作。</p>
      )}
      <p className="border-t border-gray-100 px-5 py-2 text-xs text-gray-400">
        首次啟用時，管理員按「全部重新同步」可把既有預約（預設過去 30 天到未來 180 天）匯入各心理師的日曆。
      </p>
    </section>
  );
}

function ConnectionBanner({ conn, role }: { conn: Connection | null; role: string }) {
  if (!conn) return null;
  if (conn.status === "active") {
    return <div className="rounded-lg bg-green-50 px-4 py-2.5 text-sm text-green-700">✅ 已連結 Google：{conn.google_email ?? "（未取得帳號）"}</div>;
  }
  const who = role === "admin" ? "請到「系統管理 → 日曆同步」" : "請通知管理員";
  return (
    <div className="rounded-lg bg-red-50 px-4 py-2.5 text-sm font-medium text-red-700">
      {conn.status === "token_invalid"
        ? `同步已暫停：Google 授權已失效。${who}重新連結。`
        : `尚未連結 Google 帳號，目前無法建立日曆或分享。${who}連結。`}
    </div>
  );
}

function StaffEmailsCard({
  token,
  data,
  onSaved,
  onError,
}: {
  token: string;
  data: StaffEmails | null;
  onSaved: (s: StaffEmails) => void;
  onError: (m: string) => void;
}) {
  const [draft, setDraft] = useState<string[] | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [localErr, setLocalErr] = useState<string | null>(null);

  if (!data) return null;
  const emails = draft ?? data.emails;
  const dirty = draft !== null && JSON.stringify(draft) !== JSON.stringify(data.emails);

  function add() {
    const v = input.trim().toLowerCase();
    if (!v) return;
    if (!EMAIL_RE.test(v)) return setLocalErr("Email 格式不正確");
    setLocalErr(null);
    if (!emails.includes(v)) setDraft([...emails, v]);
    setInput("");
  }

  async function save() {
    setBusy(true);
    try {
      const r = await clientFetch("/settings/google/staff-emails", token, { method: "PUT", body: JSON.stringify({ emails }) });
      setDraft(null);
      onSaved(r);
    } catch (e: any) {
      onError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5">
      <h2 className="text-base font-semibold">行政分享名單</h2>
      <p className="mb-3 mt-0.5 text-xs text-gray-500">
        名單上的人會以「唯讀」看到每位心理師的日曆。診所帳號本人{data.owner_email ? `（${data.owner_email}）` : ""}是擁有者，不需要列入。
        {data.can_edit ? "" : "只有管理員可以修改。"}
      </p>
      <div className="flex flex-wrap gap-2">
        {emails.length === 0 && <span className="text-sm text-gray-400">（目前沒有人）</span>}
        {emails.map((e) => (
          <span key={e} className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-3 py-1 text-sm">
            {e}
            {data.can_edit && (
              <button aria-label={`移除 ${e}`} onClick={() => setDraft(emails.filter((x) => x !== e))} className="text-gray-400 hover:text-red-600">
                ×
              </button>
            )}
          </span>
        ))}
      </div>
      {data.can_edit && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder="行政人員的 Gmail"
            className="w-64 rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
          />
          <button onClick={add} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50">
            加入
          </button>
          <button
            onClick={save}
            disabled={!dirty || busy}
            className="rounded-lg bg-primary-600 px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            {busy ? "儲存並同步中..." : "儲存並同步"}
          </button>
          {dirty && (
            <button onClick={() => setDraft(null)} className="text-sm text-gray-500 hover:underline">
              還原
            </button>
          )}
          {localErr && <span className="text-sm text-red-600">{localErr}</span>}
        </div>
      )}
    </section>
  );
}

function TherapistLine({
  row,
  token,
  connected,
  onChanged,
  onError,
}: {
  row: TherapistRow;
  token: string;
  connected: boolean;
  onChanged: (r: TherapistRow, msg?: string) => void;
  onError: (m: string) => void;
}) {
  const [email, setEmail] = useState(row.share_email ?? "");
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmUnshare, setConfirmUnshare] = useState(false);
  useEffect(() => setEmail(row.share_email ?? ""), [row.share_email]);

  const cal = row.calendar;
  const emailDirty = email.trim().toLowerCase() !== (row.share_email ?? "");

  async function call(action: string, path: string, init: RequestInit, okMsg: string) {
    setBusy(action);
    try {
      const next: TherapistRow = await clientFetch(`/settings/google/therapists/${row.id}${path}`, token, init);
      const err = next.calendar?.share_status === "error" ? next.calendar.last_share_error : null;
      if (err) onError(`${row.name}：${err}`);
      onChanged(next, err ? undefined : okMsg);
    } catch (e: any) {
      onError(`${row.name}：${e.message}`);
    } finally {
      setBusy(null);
      setConfirmUnshare(false);
    }
  }

  const saveEmail = () => {
    const v = email.trim();
    if (v && !EMAIL_RE.test(v)) return onError("Email 格式不正確");
    return call("email", "/email", { method: "PUT", body: JSON.stringify({ email: v || null }) }, `${row.name} 的信箱已儲存。`);
  };

  let state = "尚未建立";
  if (cal) state = cal.is_missing ? "Google 上找不到" : !cal.is_active ? "已凍結（日曆保留）" : "已建立";
  const share = cal ? SHARE_LABEL[cal.share_status] : null;
  const canCreate = connected && row.is_active && !busy;

  return (
    <tr className="border-t border-gray-100 align-top">
      <td className="px-4 py-3">
        <div className="font-medium">{row.name}</div>
        <div className="text-xs text-gray-500">
          {row.user_code ?? ""} {row.has_account ? "" : "· 名單制"}
          {!row.is_active && <span className="ml-1 rounded bg-gray-200 px-1.5 py-0.5 text-gray-600">已離職</span>}
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@gmail.com"
            className="w-56 rounded-lg border border-gray-300 px-2.5 py-1.5 text-sm"
          />
          <button
            onClick={saveEmail}
            disabled={!emailDirty || !!busy}
            className="rounded-lg border border-gray-300 px-2.5 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-40"
          >
            {busy === "email" ? "儲存中..." : "儲存"}
          </button>
        </div>
        {cal && cal.shared_emails.length > 0 && (
          <div className="mt-1 text-xs text-gray-500">目前分享給：{cal.shared_emails.join("、")}</div>
        )}
      </td>
      <td className="px-4 py-3">
        <div className="text-sm">{state}</div>
        {share && <span className={`mt-1 inline-block rounded-full px-2 py-0.5 text-xs font-medium ${share.cls}`}>{share.text}</span>}
        {cal?.last_share_error && <div className="mt-1 max-w-xs text-xs text-red-600">{cal.last_share_error}</div>}
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          {row.is_active && (
            <button
              onClick={() => call("provision", "/provision", { method: "POST" }, `已建立並分享 ${row.name} 的日曆。`)}
              disabled={!canCreate}
              title={connected ? "" : "尚未連結 Google"}
              className="rounded-lg bg-primary-600 px-3 py-1.5 text-sm text-white disabled:opacity-40"
            >
              {busy === "provision" ? "處理中..." : cal && !cal.is_missing ? "重新同步分享" : "建立並分享"}
            </button>
          )}
          {cal && !cal.is_missing && row.is_active && cal.is_active && row.share_email && (
            <button
              onClick={() => call("resend", "/resend-invite", { method: "POST" }, "已重送邀請。")}
              disabled={!connected || !!busy}
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-40"
            >
              {busy === "resend" ? "寄送中..." : "重寄邀請"}
            </button>
          )}
          {cal && !cal.is_missing &&
            (confirmUnshare ? (
              <span className="flex items-center gap-1.5 text-sm">
                <span className="text-red-700">確定取消？日曆會保留，但他看不到了。</span>
                <button
                  onClick={() => call("unshare", "/unshare", { method: "POST" }, `已取消 ${row.name} 的分享。`)}
                  disabled={!!busy}
                  className="rounded-lg bg-red-600 px-2.5 py-1 text-white disabled:opacity-50"
                >
                  確定
                </button>
                <button onClick={() => setConfirmUnshare(false)} className="text-gray-500 hover:underline">
                  取消
                </button>
              </span>
            ) : (
              <button
                onClick={() => setConfirmUnshare(true)}
                disabled={!connected || !!busy}
                className="text-sm text-red-600 hover:underline disabled:opacity-40"
              >
                取消分享
              </button>
            ))}
        </div>
      </td>
    </tr>
  );
}
