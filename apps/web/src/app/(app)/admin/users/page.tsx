"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

interface UserItem {
  id: number;
  email: string;
  name: string;
  role: string;
  therapist_code: string | null;
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
};

export default function AdminUsersPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;

  const [users, setUsers] = useState<UserItem[]>([]);
  const [invitations, setInvitations] = useState<InvitationItem[]>([]);
  const [loading, setLoading] = useState(true);

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
      const body: any = { name: invName.trim(), role: invRole };
      if (invRole === "therapist" && invCode.trim()) {
        body.therapist_code = invCode.trim();
      }
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
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">帳號管理</h1>
        <button
          onClick={() => setShowInvite(true)}
          className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
        >
          + 建立邀請
        </button>
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
                  <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                    u.role === "admin" ? "bg-green-100 text-green-700" :
                    u.role === "accountant" ? "bg-amber-100 text-amber-700" :
                    "bg-blue-100 text-blue-700"
                  }`}>{roleLabels[u.role] ?? u.role}</span>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-gray-400">{u.therapist_code ?? "-"}</td>
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
                <select value={invRole} onChange={(e) => setInvRole(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                  <option value="therapist">心理師</option>
                  <option value="accountant">會計</option>
                  <option value="admin">管理員</option>
                </select>
              </div>
              {invRole === "therapist" && (() => {
                const allCodes = users.filter((u) => u.therapist_code).map((u) => ({ code: u.therapist_code!, name: u.name, active: u.is_active }));
                const reusable = allCodes.filter((c) => !c.active);
                const usedSet = new Set(allCodes.filter((c) => c.active).map((c) => c.code));
                let nextCode = "";
                for (let i = 1; i <= 999; i++) {
                  const candidate = `T${String(i).padStart(3, "0")}`;
                  if (!allCodes.some((c) => c.code === candidate)) { nextCode = candidate; break; }
                }
                return (
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-500">心理師代號 *</label>
                    <input type="text" value={invCode} onChange={(e) => setInvCode(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono" placeholder="例如 T018" />
                    <div className="mt-2 space-y-1">
                      {nextCode && (
                        <button type="button" onClick={() => setInvCode(nextCode)} className="rounded bg-primary-50 px-2 py-0.5 text-xs text-primary-600 hover:bg-primary-100">
                          自動：{nextCode}（新代號）
                        </button>
                      )}
                      {reusable.length > 0 && (
                        <div className="flex flex-wrap gap-1">
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
              <button onClick={handleCreateInvite} disabled={!invName.trim() || creatingInvite} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">
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
