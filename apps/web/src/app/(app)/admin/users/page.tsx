"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import HelpDrawer, { type HelpContent } from "@/components/HelpDrawer";

const helpContent: HelpContent = {
  title: "系統管理",
  overview: "管理使用者帳號（邀請、停用）、角色設定、抽成比例，以及機構代碼維護。",
  sections: [
    {
      heading: "邀請新用戶",
      type: "steps",
      items: [
        "點「＋建立邀請」",
        "填入對方的電子郵件",
        "選擇角色（管理員 / 行政人員 / 心理師）",
        "點「產生邀請碼」",
        "將邀請碼傳給對方",
        "對方至登入頁點「首次註冊」輸入邀請碼完成帳號建立",
      ],
    },
    {
      heading: "設定心理師抽成比例",
      type: "steps",
      items: [
        "在帳號列表找到該心理師，點「編輯」",
        "輸入抽成比例（例：0.70 代表 70%）",
        "儲存後新預約即採用新比例（歷史記錄保留原比例快照）",
      ],
    },
    {
      heading: "注意事項",
      type: "tips",
      items: [
        "停用帳號後該用戶無法登入，但歷史諮商記錄與個案資料完整保留",
        "機構代碼（英數 5 碼）用於核銷案編號，設定後有交易記錄請勿修改",
        "邀請碼請勿外洩，被人使用後即失效",
      ],
    },
    {
      heading: "管理員提示",
      type: "notes",
      items: [
        "管理員角色僅應授予診所負責人或主管行政，避免過度授權",
        "抽成比例調整只影響未來新增的諮商，不追溯修改已有記錄",
      ],
    },
  ],
};

interface UserItem {
  id: number;
  email: string;
  name: string;
  role: string;
  user_code: string | null;
  is_active: boolean;
}

interface InvitationItem {
  id: number;
  invite_key: string;
  type: string;
  name: string;
  role: string | null;
  target_user_id: number | null;
  created_at: string;
  expires_at: string;
  used_at: string | null;
}

const roleLabels: Record<string, string> = {
  admin: "管理員",
  accountant: "會計",
  therapist: "心理師",
  staff: "行政人員",
};

const roleCodePrefix: Record<string, string> = {
  admin: "A",
  accountant: "C",
  staff: "S",
  therapist: "T",
};

const roleBadgeClass: Record<string, string> = {
  admin: "bg-green-100 text-green-700",
  accountant: "bg-amber-100 text-amber-700",
  staff: "bg-purple-100 text-purple-700",
  therapist: "bg-blue-100 text-blue-700",
};

export default function AdminUsersPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;

  const [users, setUsers] = useState<UserItem[]>([]);
  const [invitations, setInvitations] = useState<InvitationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [helpOpen, setHelpOpen] = useState(false);

  // Invite modal
  const [showInvite, setShowInvite] = useState(false);
  const [invName, setInvName] = useState("");
  const [invRole, setInvRole] = useState("therapist");
  const [invCode, setInvCode] = useState("");
  const [creatingInvite, setCreatingInvite] = useState(false);

  // Result modal (show key)
  const [resultKey, setResultKey] = useState("");
  const [resultLabel, setResultLabel] = useState("");

  const fetchData = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [u, i] = await Promise.all([
        clientFetch("/auth/users", token),
        clientFetch("/auth/invitations", token),
      ]);
      setUsers(u);
      setInvitations(i);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleCreateInvite = async () => {
    if (!token || !invName.trim()) return;
    setCreatingInvite(true);
    try {
      const body: any = { name: invName.trim(), role: invRole, user_code: invCode.trim() };
      const result = await clientFetch("/auth/invitations", token, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setShowInvite(false);
      setInvName("");
      setInvRole("therapist");
      setInvCode("");
      setResultKey(result.invite_key);
      setResultLabel(`${invName.trim()} 的邀請金鑰`);
      fetchData();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setCreatingInvite(false);
    }
  };

  const handleResetPassword = async (userId: number, userName: string) => {
    if (!token || !confirm(`確定要產生 ${userName} 的密碼重設金鑰？`)) return;
    try {
      const result = await clientFetch(`/auth/reset-key/${userId}`, token, {
        method: "POST",
      });
      setResultKey(result.invite_key);
      setResultLabel(`${userName} 的密碼重設金鑰`);
      fetchData();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleToggle = async (userId: number) => {
    if (!token) return;
    try {
      await clientFetch(`/auth/users/${userId}/toggle`, token, { method: "PUT" });
      fetchData();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const copyKey = () => {
    navigator.clipboard.writeText(resultKey);
    alert("已複製到剪貼簿");
  };

  if (!token) return <p>Loading...</p>;

  const pendingInvitations = invitations.filter((i) => !i.used_at && new Date(i.expires_at) > new Date());

  return (
    <div>
      <HelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} content={helpContent} />
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">帳號管理</h1>
        <div className="flex items-center gap-2">
          <button onClick={() => setHelpOpen(true)} className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50 hover:text-gray-700">
            <span>ℹ️</span> 說明
          </button>
          <button
            onClick={() => setShowInvite(true)}
            className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
          >
            + 建立邀請
          </button>
        </div>
      </div>

      {/* Users table */}
      <div className="mb-8 overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">姓名</th>
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">角色</th>
              <th className="px-4 py-3">代號</th>
              <th className="px-4 py-3">狀態</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-400">載入中...</td></tr>
            ) : users.map((u) => (
              <tr key={u.id} className={`hover:bg-gray-50 ${!u.is_active ? "opacity-50" : ""}`}>
                <td className="px-4 py-3 font-medium">{u.name}</td>
                <td className="px-4 py-3 text-gray-500">{u.email}</td>
                <td className="px-4 py-3">
                  <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${roleBadgeClass[u.role] ?? "bg-gray-100 text-gray-700"}`}>
                    {roleLabels[u.role] ?? u.role}
                  </span>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-gray-500">{u.user_code ?? "-"}</td>
                <td className="px-4 py-3">
                  <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${u.is_active ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                    {u.is_active ? "啟用" : "停用"}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex gap-2">
                    <button onClick={() => handleResetPassword(u.id, u.name)} className="text-xs text-blue-600 hover:underline">重設密碼</button>
                    <button onClick={() => handleToggle(u.id)} className="text-xs text-gray-500 hover:underline">
                      {u.is_active ? "停用" : "啟用"}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pending invitations */}
      {pendingInvitations.length > 0 && (
        <>
          <h2 className="mb-3 text-lg font-semibold">待使用的邀請 / 重設金鑰</h2>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-4 py-3">金鑰</th>
                  <th className="px-4 py-3">類型</th>
                  <th className="px-4 py-3">姓名</th>
                  <th className="px-4 py-3">角色</th>
                  <th className="px-4 py-3">到期時間</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {pendingInvitations.map((inv) => (
                  <tr key={inv.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-xs">{inv.invite_key}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${inv.type === "invite" ? "bg-primary-100 text-primary-700" : "bg-amber-100 text-amber-700"}`}>
                        {inv.type === "invite" ? "新帳號" : "重設密碼"}
                      </span>
                    </td>
                    <td className="px-4 py-3">{inv.name}</td>
                    <td className="px-4 py-3 text-xs text-gray-500">{inv.role ? (roleLabels[inv.role] ?? inv.role) : "-"}</td>
                    <td className="px-4 py-3 text-xs text-gray-400">{new Date(inv.expires_at).toLocaleString("zh-TW")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Create invitation modal */}
      {showInvite && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <h3 className="mb-4 text-lg font-semibold">建立邀請</h3>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500">姓名 *</label>
                <input type="text" value={invName} onChange={(e) => setInvName(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" placeholder="使用者姓名" autoFocus />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500">角色 *</label>
                <select value={invRole} onChange={(e) => { setInvRole(e.target.value); setInvCode(""); }} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                  <option value="therapist">心理師（T）</option>
                  <option value="accountant">會計（C）</option>
                  <option value="staff">行政人員（S）</option>
                  <option value="admin">管理員（A）</option>
                </select>
              </div>
              {(() => {
                const prefix = roleCodePrefix[invRole] ?? invRole[0].toUpperCase();
                const allCodesForRole = users.filter((u) => u.user_code?.startsWith(prefix)).map((u) => ({ code: u.user_code!, name: u.name, active: u.is_active }));
                const reusable = allCodesForRole.filter((c) => !c.active);
                let nextCode = "";
                for (let i = 1; i <= 999; i++) {
                  const candidate = `${prefix}${String(i).padStart(3, "0")}`;
                  if (!allCodesForRole.some((c) => c.code === candidate)) { nextCode = candidate; break; }
                }
                return (
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-500">使用者代號 *</label>
                    <input type="text" value={invCode} onChange={(e) => setInvCode(e.target.value.toUpperCase())} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono" placeholder={`例如 ${prefix}001`} />
                    <div className="mt-2 space-y-1">
                      {nextCode && (
                        <button type="button" onClick={() => setInvCode(nextCode)} className="rounded bg-primary-50 px-2 py-0.5 text-xs text-primary-600 hover:bg-primary-100">
                          自動：{nextCode}（下一個可用代號）
                        </button>
                      )}
                      {reusable.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {reusable.map((c) => (
                            <button key={c.code} type="button" onClick={() => setInvCode(c.code)} className={`rounded px-2 py-0.5 text-xs ${invCode === c.code ? "bg-amber-200 text-amber-800" : "bg-amber-50 text-amber-600 hover:bg-amber-100"}`}>
                              {c.code}（原 {c.name}，已停用）
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })()}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => { setShowInvite(false); setInvName(""); setInvRole("therapist"); setInvCode(""); }} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">取消</button>
              <button onClick={handleCreateInvite} disabled={!invName.trim() || !invCode.trim() || creatingInvite} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">
                {creatingInvite ? "建立中..." : "建立"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Result modal (show key) */}
      {resultKey && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <h3 className="mb-2 text-lg font-semibold">{resultLabel}</h3>
            <p className="mb-4 text-sm text-gray-500">請複製此金鑰並提供給使用者。金鑰 72 小時內有效，僅可使用一次。</p>
            <div className="flex items-center gap-2 rounded-lg bg-gray-50 p-4">
              <code className="flex-1 text-center text-lg font-bold tracking-widest text-primary-700">{resultKey}</code>
              <button onClick={copyKey} className="rounded-lg bg-primary-100 px-3 py-1.5 text-xs font-medium text-primary-700 hover:bg-primary-200">複製</button>
            </div>
            <div className="mt-5 flex justify-end">
              <button onClick={() => setResultKey("")} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">關閉</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
