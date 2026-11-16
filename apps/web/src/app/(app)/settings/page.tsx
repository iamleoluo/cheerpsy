"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

interface Me {
  id: number;
  email: string;
  name: string;
  role: string;
  user_code: string | null;
  commission_rate: number | null;
  base_price: number | null;
}

const roleLabels: Record<string, string> = {
  admin: "管理員",
  therapist: "心理師",
  staff: "行政人員",
};

export default function SettingsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;

  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const [email, setEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [basePrice, setBasePrice] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const fetchMe = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data: Me = await clientFetch("/auth/me", token);
      setMe(data);
      setEmail(data.email);
      setBasePrice(data.base_price != null ? String(data.base_price) : "");
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchMe();
  }, [fetchMe]);

  const handleSave = async () => {
    if (!token || !me) return;
    setMsg(null);
    if (!currentPassword) {
      setMsg({ type: "err", text: "請輸入目前密碼以確認身分" });
      return;
    }
    if (newPassword && newPassword !== confirmPassword) {
      setMsg({ type: "err", text: "兩次新密碼輸入不一致" });
      return;
    }
    if (newPassword && newPassword.length < 6) {
      setMsg({ type: "err", text: "新密碼至少需 6 碼" });
      return;
    }
    setSaving(true);
    try {
      const body: any = { current_password: currentPassword };
      if (email.trim() && email.trim() !== me.email) body.email = email.trim();
      if (newPassword) body.new_password = newPassword;
      if (me.role === "therapist" && basePrice !== "") {
        const bp = parseFloat(basePrice);
        if (!isNaN(bp) && bp >= 0) body.base_price = bp;
      }
      await clientFetch("/auth/me", token, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      setMsg({ type: "ok", text: "已儲存。若已變更 Email，下次登入請使用新 Email。" });
      setNewPassword("");
      setConfirmPassword("");
      setCurrentPassword("");
      fetchMe();
    } catch (e: any) {
      setMsg({ type: "err", text: e.message });
    } finally {
      setSaving(false);
    }
  };

  if (!token || loading) return <p className="text-gray-400">載入中...</p>;
  if (!me) return <p className="text-gray-400">無法載入帳號資料</p>;

  return (
    <div className="max-w-lg">
      <h1 className="mb-6 text-2xl font-bold">個人設定</h1>

      {/* Read-only account info */}
      <div className="mb-6 rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm">
        <div className="flex justify-between py-1">
          <span className="text-gray-500">姓名</span>
          <span className="font-medium">{me.name}</span>
        </div>
        <div className="flex justify-between py-1">
          <span className="text-gray-500">角色</span>
          <span className="font-medium">{roleLabels[me.role] ?? me.role}</span>
        </div>
        {me.user_code && (
          <div className="flex justify-between py-1">
            <span className="text-gray-500">代號</span>
            <span className="font-mono font-medium">{me.user_code}</span>
          </div>
        )}
      </div>

      <div className="space-y-4 rounded-lg border border-gray-200 p-5">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-gray-700">登入 Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
        </label>

        {me.role === "therapist" && (
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-gray-700">
              預約基礎價格（每次預約自動帶入，可於建立時調整）
            </span>
            <input
              type="number"
              value={basePrice}
              onChange={(e) => setBasePrice(e.target.value)}
              placeholder="例如 2000"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
          </label>
        )}

        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-gray-700">新密碼（留空則不變）</span>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-gray-700">確認新密碼</span>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
          </label>
        </div>

        <label className="block border-t border-gray-100 pt-4">
          <span className="mb-1 block text-xs font-medium text-gray-700">
            目前密碼 <span className="text-red-500">*</span>（變更任何設定都需確認）
          </span>
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
        </label>

        {msg && (
          <div
            className={`rounded-lg p-2 text-sm ${
              msg.type === "ok" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"
            }`}
          >
            {msg.text}
          </div>
        )}

        <div className="flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded-lg bg-primary-600 px-5 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
          >
            {saving ? "儲存中..." : "儲存變更"}
          </button>
        </div>
      </div>

      {me.role === "therapist" && <GcalStatusCard token={token} />}
    </div>
  );
}

interface GcalStatus {
  clinic_connected: boolean;
  calendar_created: boolean;
  shared_to_me: boolean;
  share_email: string | null;
  last_push_at: string | null;
  failed_count: number;
  pending_count: number;
  problem: string | null;
}

/** Google 行事曆同步（唯讀）：只看自己的狀態；設定與重試由行政處理。 */
function GcalStatusCard({ token }: { token: string }) {
  const [st, setSt] = useState<GcalStatus | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    clientFetch("/gcal/my-status", token)
      .then(setSt)
      .catch(() => setFailed(true));
  }, [token]);

  const Row = ({ label, ok, text }: { label: string; ok: boolean; text: string }) => (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-gray-500">{label}</span>
      <span className={ok ? "font-medium text-green-700" : "font-medium text-amber-700"}>{ok ? "✓ " : "✗ "}{text}</span>
    </div>
  );

  return (
    <div className="mt-6 rounded-lg border border-gray-200 p-5 text-sm">
      <h2 className="mb-1 text-base font-semibold">Google 行事曆同步</h2>
      <p className="mb-3 text-xs text-gray-400">唯讀。你的預約會由行政設定的診所帳號推送到你的 Google 行事曆。</p>
      {failed ? (
        <p className="text-gray-400">暫時無法取得同步狀態</p>
      ) : !st ? (
        <p className="text-gray-400">載入中...</p>
      ) : (
        <>
          <div className="divide-y divide-gray-100">
            <Row label="診所已連上 Google" ok={st.clinic_connected} text={st.clinic_connected ? "已連上" : "尚未連上"} />
            <Row label="我的行事曆" ok={st.calendar_created} text={st.calendar_created ? "已建立" : "尚未建立"} />
            <Row
              label={`共享給我的信箱${st.share_email ? `（${st.share_email}）` : ""}`}
              ok={st.shared_to_me}
              text={st.shared_to_me ? "已共享" : "尚未共享"}
            />
            <div className="flex items-center justify-between py-1.5">
              <span className="text-gray-500">最近一次推送成功</span>
              <span className="font-medium">{st.last_push_at ? new Date(st.last_push_at).toLocaleString("zh-TW", { hour12: false }) : "尚無紀錄"}</span>
            </div>
            <div className="flex items-center justify-between py-1.5">
              <span className="text-gray-500">待推送／失敗</span>
              <span className="font-medium">
                {st.pending_count} 筆 ／ <span className={st.failed_count > 0 ? "text-red-600" : ""}>{st.failed_count} 筆</span>
              </span>
            </div>
          </div>
          {st.problem && (
            <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">⚠ {st.problem}</div>
          )}
        </>
      )}
    </div>
  );
}
