"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch, exportCsv } from "@/lib/client-api";

/* ───── types ───── */

interface UserItem {
  id: number;
  email: string;
  name: string;
  role: string;
  user_code: string | null;
  commission_rate: number | null;
  base_price: number | null;
  is_active: boolean;
}

const ROLE_CODE_PREFIX: Record<string, string> = {
  admin: "A", accountant: "C", staff: "S", therapist: "T",
};

function computeNextCode(users: UserItem[], role: string): string {
  const prefix = ROLE_CODE_PREFIX[role] ?? role[0].toUpperCase();
  const used = users.filter((u) => u.user_code?.startsWith(prefix)).map((u) => u.user_code!);
  for (let i = 1; i <= 999; i++) {
    const c = `${prefix}${String(i).padStart(3, "0")}`;
    if (!used.includes(c)) return c;
  }
  return `${prefix}001`;
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

interface Institution {
  id: number;
  name: string;
  code: string | null;
  is_active: boolean;
  requires_therapist_docs: boolean;
}

const roleLabels: Record<string, string> = {
  admin: "管理員",
  accountant: "會計",
  staff: "行政人員",
  therapist: "心理師",
};

const roleBadge: Record<string, string> = {
  admin: "bg-green-100 text-green-700",
  accountant: "bg-amber-100 text-amber-700",
  staff: "bg-purple-100 text-purple-700",
  therapist: "bg-blue-100 text-blue-700",
};

/* ───── main page ───── */

export default function AdminPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const userRole = (session?.user as any)?.role;

  const [tab, setTab] = useState<"users" | "institutions" | "data">("users");

  if (userRole !== "admin") {
    return (
      <div className="flex h-64 items-center justify-center text-gray-400">
        僅管理員可存取此頁面
      </div>
    );
  }

  if (!token) return <p className="p-6 text-gray-400">載入中...</p>;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold">系統管理</h1>
      </div>

      {/* Tab bar */}
      <div className="mb-6 flex gap-1 border-b border-gray-200">
        <button
          onClick={() => setTab("users")}
          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
            tab === "users"
              ? "border-b-2 border-primary-600 text-primary-700"
              : "text-gray-500 hover:text-gray-700"
          }`}
        >
          帳號管理
        </button>
        <button
          onClick={() => setTab("institutions")}
          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
            tab === "institutions"
              ? "border-b-2 border-primary-600 text-primary-700"
              : "text-gray-500 hover:text-gray-700"
          }`}
        >
          機構管理
        </button>
        <button
          onClick={() => setTab("data")}
          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
            tab === "data"
              ? "border-b-2 border-primary-600 text-primary-700"
              : "text-gray-500 hover:text-gray-700"
          }`}
        >
          資料匯出入
        </button>
      </div>

      {tab === "users" ? <UsersTab token={token} /> : tab === "institutions" ? <InstitutionsTab token={token} /> : <DataTab token={token} />}
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   Tab 1: 帳號管理
   ═══════════════════════════════════════════════════ */

function UsersTab({ token }: { token: string }) {
  const [users, setUsers] = useState<UserItem[]>([]);
  const [invitations, setInvitations] = useState<InvitationItem[]>([]);
  const [loading, setLoading] = useState(true);

  const [showInvite, setShowInvite] = useState(false);
  const [invName, setInvName] = useState("");
  const [invRole, setInvRole] = useState("therapist");
  const [invCode, setInvCode] = useState("");
  const [invCommission, setInvCommission] = useState("0.70");
  const [creatingInvite, setCreatingInvite] = useState(false);

  const [resultKey, setResultKey] = useState("");
  const [resultLabel, setResultLabel] = useState("");

  const [editingRate, setEditingRate] = useState<number | null>(null);
  const [editRateValue, setEditRateValue] = useState("");
  const [editingBase, setEditingBase] = useState<number | null>(null);
  const [editBaseValue, setEditBaseValue] = useState("");
  const [invBase, setInvBase] = useState("2000");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [u, i] = await Promise.all([
        clientFetch("/auth/users", token),
        clientFetch("/auth/invitations", token),
      ]);
      setUsers(u);
      setInvitations(i);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-populate the suggested code when modal opens or role changes
  useEffect(() => {
    if (!showInvite) return;
    setInvCode(computeNextCode(users, invRole));
  }, [showInvite, invRole, users]);

  const handleCreateInvite = async () => {
    if (!invName.trim()) return;
    setCreatingInvite(true);
    try {
      // user_code optional — backend auto-generates if blank (all roles)
      const body: any = { name: invName.trim(), role: invRole, user_code: invCode.trim() || null };
      const result = await clientFetch("/auth/invitations", token, {
        method: "POST",
        body: JSON.stringify(body),
      });
      const finalCode: string = result.user_code;

      if (invRole === "therapist") {
        const newUser = (await clientFetch("/auth/users", token) as UserItem[])
          .find((u) => u.user_code === finalCode);
        if (newUser) {
          if (invCommission) {
            await clientFetch(`/auth/users/${newUser.id}/commission-rate`, token, {
              method: "PUT",
              body: JSON.stringify({ commission_rate: parseFloat(invCommission) }),
            }).catch(() => {});
          }
          if (invBase) {
            await clientFetch(`/auth/users/${newUser.id}`, token, {
              method: "PUT",
              body: JSON.stringify({ base_price: parseFloat(invBase) }),
            }).catch(() => {});
          }
        }
      }

      setShowInvite(false);
      setInvName("");
      setInvRole("therapist");
      setInvCode("");
      setInvCommission("0.70");
      setInvBase("2000");
      setResultKey(result.invite_key);
      setResultLabel(`${invName.trim()} 的邀請金鑰（代號 ${finalCode}）`);
      fetchData();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setCreatingInvite(false);
    }
  };

  const handleSaveBase = async (userId: number) => {
    const val = parseFloat(editBaseValue);
    if (isNaN(val) || val < 0) {
      alert("請輸入有效的價格（≥ 0）");
      return;
    }
    try {
      await clientFetch(`/auth/users/${userId}`, token, {
        method: "PUT",
        body: JSON.stringify({ base_price: val }),
      });
      setEditingBase(null);
      fetchData();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleResetPassword = async (userId: number, userName: string) => {
    if (!confirm(`確定要產生 ${userName} 的密碼重設金鑰？`)) return;
    try {
      const result = await clientFetch(`/auth/reset-key/${userId}`, token, { method: "POST" });
      setResultKey(result.invite_key);
      setResultLabel(`${userName} 的密碼重設金鑰`);
      fetchData();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleToggle = async (userId: number) => {
    try {
      await clientFetch(`/auth/users/${userId}/toggle`, token, { method: "PUT" });
      fetchData();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleSaveRate = async (userId: number) => {
    const val = parseFloat(editRateValue);
    if (isNaN(val) || val < 0 || val > 1) {
      alert("請輸入 0 ~ 1 之間的數字（例如 0.70）");
      return;
    }
    try {
      await clientFetch(`/auth/users/${userId}/commission-rate`, token, {
        method: "PUT",
        body: JSON.stringify({ commission_rate: val }),
      });
      setEditingRate(null);
      fetchData();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const copyKey = () => {
    navigator.clipboard.writeText(resultKey);
    alert("已複製到剪貼簿");
  };

  const pendingInvitations = invitations.filter(
    (i) => !i.used_at && new Date(i.expires_at) > new Date(),
  );

  return (
    <>
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-gray-500">管理帳號、角色權限與心理師抽成比例</p>
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
              <th className="px-4 py-3">抽成比例</th>
              <th className="px-4 py-3">預設價格</th>
              <th className="px-4 py-3">狀態</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-400">載入中...</td>
              </tr>
            ) : (
              users.map((u) => (
                <tr key={u.id} className={`hover:bg-gray-50 ${!u.is_active ? "opacity-50" : ""}`}>
                  <td className="px-4 py-3 font-medium">{u.name}</td>
                  <td className="px-4 py-3 text-gray-500">{u.email}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${roleBadge[u.role] ?? "bg-gray-100 text-gray-600"}`}>
                      {roleLabels[u.role] ?? u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-500">
                    {u.user_code ? u.user_code : <span className="text-red-400">未設定</span>}
                  </td>
                  <td className="px-4 py-3">
                    {u.role === "therapist" ? (
                      editingRate === u.id ? (
                        <div className="flex items-center gap-1">
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            max="1"
                            value={editRateValue}
                            onChange={(e) => setEditRateValue(e.target.value)}
                            className="w-20 rounded border border-gray-300 px-2 py-1 text-xs"
                            autoFocus
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleSaveRate(u.id);
                              if (e.key === "Escape") setEditingRate(null);
                            }}
                          />
                          <button
                            onClick={() => handleSaveRate(u.id)}
                            className="text-xs text-green-600 hover:text-green-700"
                          >
                            ✓
                          </button>
                          <button
                            onClick={() => setEditingRate(null)}
                            className="text-xs text-gray-400 hover:text-gray-600"
                          >
                            ✕
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => {
                            setEditingRate(u.id);
                            setEditRateValue(String(u.commission_rate ?? 0.7));
                          }}
                          className="rounded px-2 py-0.5 text-xs font-medium text-blue-600 hover:bg-blue-50"
                          title="點擊編輯"
                        >
                          {Math.round((u.commission_rate ?? 0.7) * 100)}%
                        </button>
                      )
                    ) : (
                      <span className="text-xs text-gray-300">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {u.role === "therapist" ? (
                      editingBase === u.id ? (
                        <div className="flex items-center gap-1">
                          <input
                            type="number"
                            min="0"
                            value={editBaseValue}
                            onChange={(e) => setEditBaseValue(e.target.value)}
                            className="w-24 rounded border border-gray-300 px-2 py-1 text-xs"
                            autoFocus
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleSaveBase(u.id);
                              if (e.key === "Escape") setEditingBase(null);
                            }}
                          />
                          <button
                            onClick={() => handleSaveBase(u.id)}
                            className="text-xs text-green-600 hover:text-green-700"
                          >
                            ✓
                          </button>
                          <button
                            onClick={() => setEditingBase(null)}
                            className="text-xs text-gray-400 hover:text-gray-600"
                          >
                            ✕
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => {
                            setEditingBase(u.id);
                            setEditBaseValue(String(u.base_price ?? 2000));
                          }}
                          className="rounded px-2 py-0.5 text-xs font-medium text-blue-600 hover:bg-blue-50"
                          title="點擊編輯"
                        >
                          {u.base_price != null ? `$${Number(u.base_price).toLocaleString()}` : "未設定"}
                        </button>
                      )
                    ) : (
                      <span className="text-xs text-gray-300">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${u.is_active ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                      {u.is_active ? "啟用" : "停用"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button onClick={() => handleResetPassword(u.id, u.name)} className="text-xs text-blue-600 hover:underline">
                        重設密碼
                      </button>
                      <button onClick={() => handleToggle(u.id)} className="text-xs text-gray-500 hover:underline">
                        {u.is_active ? "停用" : "啟用"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
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
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {inv.role ? (roleLabels[inv.role] ?? inv.role) : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-400">
                      {new Date(inv.expires_at).toLocaleString("zh-TW")}
                    </td>
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
                <input
                  type="text"
                  value={invName}
                  onChange={(e) => setInvName(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  placeholder="使用者姓名"
                  autoFocus
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500">角色 *</label>
                <select
                  value={invRole}
                  onChange={(e) => setInvRole(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                >
                  <option value="therapist">心理師</option>
                  <option value="staff">行政人員</option>
                  <option value="accountant">會計</option>
                  <option value="admin">管理員</option>
                </select>
              </div>

              {(() => {
                const prefix = ROLE_CODE_PREFIX[invRole] ?? invRole[0].toUpperCase();
                const reusable = users
                  .filter((u) => u.user_code?.startsWith(prefix) && !u.is_active)
                  .map((u) => ({ code: u.user_code!, name: u.name }));
                return (
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-500">
                      使用者代號（留空自動產生）
                    </label>
                    <input
                      type="text"
                      value={invCode}
                      onChange={(e) => setInvCode(e.target.value.toUpperCase())}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono"
                      placeholder={`留空自動產生（如 ${prefix}001）`}
                    />
                    {reusable.length > 0 && (
                      <div className="mt-2">
                        <p className="mb-1 text-xs text-gray-400">可重用停用帳號的代號：</p>
                        <div className="flex flex-wrap gap-1">
                          {reusable.map((c) => (
                            <button
                              key={c.code}
                              type="button"
                              onClick={() => setInvCode(c.code)}
                              className={`rounded px-2 py-0.5 text-xs ${
                                invCode === c.code
                                  ? "bg-amber-200 text-amber-800"
                                  : "bg-amber-50 text-amber-600 hover:bg-amber-100"
                              }`}
                            >
                              {c.code}（原 {c.name}，已停用）
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}

              {invRole === "therapist" && (
                <>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-500">抽成比例</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        max="1"
                        value={invCommission}
                        onChange={(e) => setInvCommission(e.target.value)}
                        className="w-24 rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      />
                      <span className="text-sm text-gray-500">
                        （{Math.round(parseFloat(invCommission || "0") * 100)}% 歸心理師）
                      </span>
                    </div>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-500">預約基礎價格</label>
                    <input
                      type="number"
                      min="0"
                      value={invBase}
                      onChange={(e) => setInvBase(e.target.value)}
                      className="w-32 rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      placeholder="例如 2000"
                    />
                    <p className="mt-1 text-xs text-gray-400">建立預約時自動帶入，可於當下調整</p>
                  </div>
                </>
              )}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => {
                  setShowInvite(false);
                  setInvName("");
                  setInvRole("therapist");
                  setInvCode("");
                  setInvCommission("0.70");
                  setInvBase("2000");
                }}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
              >
                取消
              </button>
              <button
                onClick={handleCreateInvite}
                disabled={!invName.trim() || creatingInvite}
                className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
              >
                {creatingInvite ? "建立中..." : "建立"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Result modal */}
      {resultKey && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <h3 className="mb-2 text-lg font-semibold">{resultLabel}</h3>
            <p className="mb-4 text-sm text-gray-500">
              請複製此金鑰並提供給使用者。金鑰 72 小時內有效，僅可使用一次。
            </p>
            <div className="flex items-center gap-2 rounded-lg bg-gray-50 p-4">
              <code className="flex-1 text-center text-lg font-bold tracking-widest text-primary-700">
                {resultKey}
              </code>
              <button
                onClick={copyKey}
                className="rounded-lg bg-primary-100 px-3 py-1.5 text-xs font-medium text-primary-700 hover:bg-primary-200"
              >
                複製
              </button>
            </div>
            <div className="mt-5 flex justify-end">
              <button
                onClick={() => setResultKey("")}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
              >
                關閉
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/* ═══════════════════════════════════════════════════
   Tab 2: 機構管理
   ═══════════════════════════════════════════════════ */

function InstitutionsTab({ token }: { token: string }) {
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState("");
  const [newCode, setNewCode] = useState("");
  const [newRequiresDocs, setNewRequiresDocs] = useState(true);
  const [adding, setAdding] = useState(false);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editCode, setEditCode] = useState("");
  const [editRequiresDocs, setEditRequiresDocs] = useState(true);

  const [search, setSearch] = useState("");

  const fetchInstitutions = useCallback(async () => {
    setLoading(true);
    try {
      const data = await clientFetch("/institutions?include_inactive=true", token);
      setInstitutions(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchInstitutions();
  }, [fetchInstitutions]);

  const handleAdd = async () => {
    if (!newName.trim()) return;
    setAdding(true);
    setError("");
    try {
      const body: any = { name: newName.trim(), requires_therapist_docs: newRequiresDocs };
      if (newCode.trim()) body.code = newCode.trim();
      await clientFetch("/institutions", token, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setShowAdd(false);
      setNewName("");
      setNewCode("");
      setNewRequiresDocs(true);
      fetchInstitutions();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setAdding(false);
    }
  };

  const handleSaveEdit = async (id: number) => {
    setError("");
    try {
      const body: any = {};
      if (editName.trim()) body.name = editName.trim();
      body.code = editCode.trim() || "";
      body.requires_therapist_docs = editRequiresDocs;
      await clientFetch(`/institutions/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      setEditingId(null);
      fetchInstitutions();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handleToggle = async (inst: Institution) => {
    if (!confirm(`確定要${inst.is_active ? "停用" : "啟用"} ${inst.name}？`)) return;
    setError("");
    try {
      if (inst.is_active) {
        await clientFetch(`/institutions/${inst.id}`, token, { method: "DELETE" });
      } else {
        await clientFetch(`/institutions/${inst.id}/activate`, token, { method: "PUT" });
      }
      fetchInstitutions();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const filtered = search
    ? institutions.filter((i) => i.name.includes(search) || (i.code && i.code.includes(search.toUpperCase())))
    : institutions;

  const activeCount = institutions.filter((i) => i.is_active).length;
  const inactiveCount = institutions.length - activeCount;

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <p className="text-sm text-gray-500">管理轉介機構名稱與代號，供個案經費來源與核銷案使用</p>
          <span className="rounded-full bg-green-50 px-2.5 py-0.5 text-xs text-green-700">
            啟用 {activeCount}
          </span>
          {inactiveCount > 0 && (
            <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs text-gray-500">
              已停用 {inactiveCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => exportCsv("/export/institutions", token, "institutions.csv")}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm hover:bg-gray-50"
          >
            匯出 CSV
          </button>
          <button
            onClick={() => setShowAdd(true)}
            className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
          >
            + 新增機構
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">
          {error}
          <button onClick={() => setError("")} className="ml-2 font-medium underline">關閉</button>
        </div>
      )}

      <div className="mb-4">
        <input
          type="text"
          placeholder="搜尋機構名稱或代號..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
        />
      </div>

      {loading ? (
        <div className="py-12 text-center text-gray-400">載入中...</div>
      ) : filtered.length === 0 ? (
        <div className="py-12 text-center text-gray-400">
          {search ? "找不到符合的機構" : "尚無機構資料"}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full text-left text-sm">
            <thead className="bg-gray-50 text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-3">機構代號</th>
                <th className="px-4 py-3">機構名稱</th>
                <th className="px-4 py-3">繳交資料</th>
                <th className="px-4 py-3">狀態</th>
                <th className="px-4 py-3">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {filtered.map((inst) => (
                <tr key={inst.id} className={`hover:bg-gray-50 ${!inst.is_active ? "opacity-50" : ""}`}>
                  {editingId === inst.id ? (
                    <>
                      <td className="px-4 py-3">
                        <input
                          type="text"
                          value={editCode}
                          onChange={(e) => setEditCode(e.target.value)}
                          className="w-24 rounded border border-gray-300 px-2 py-1 text-xs font-mono"
                          placeholder="代號"
                          maxLength={5}
                          autoFocus
                        />
                      </td>
                      <td className="px-4 py-3">
                        <input
                          type="text"
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <label className="flex items-center gap-1 text-xs text-gray-600">
                          <input
                            type="checkbox"
                            checked={editRequiresDocs}
                            onChange={(e) => setEditRequiresDocs(e.target.checked)}
                          />
                          需心理師繳交資料
                        </label>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${inst.is_active ? "bg-green-100 text-green-700" : "bg-gray-200 text-gray-500"}`}>
                          {inst.is_active ? "啟用" : "停用"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleSaveEdit(inst.id)}
                            className="text-xs text-green-600 hover:underline"
                          >
                            儲存
                          </button>
                          <button
                            onClick={() => setEditingId(null)}
                            className="text-xs text-gray-400 hover:underline"
                          >
                            取消
                          </button>
                        </div>
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="px-4 py-3 font-mono text-xs text-gray-500">
                        {inst.code || "—"}
                      </td>
                      <td className="px-4 py-3 font-medium">{inst.name}</td>
                      <td className="px-4 py-3">
                        {inst.requires_therapist_docs ? (
                          <span className="text-xs text-gray-400">需繳資料</span>
                        ) : (
                          <span className="inline-block rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">免繳資料</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${inst.is_active ? "bg-green-100 text-green-700" : "bg-gray-200 text-gray-500"}`}>
                          {inst.is_active ? "啟用" : "停用"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2">
                          <button
                            onClick={() => {
                              setEditingId(inst.id);
                              setEditName(inst.name);
                              setEditCode(inst.code ?? "");
                              setEditRequiresDocs(inst.requires_therapist_docs);
                            }}
                            className="text-xs text-blue-600 hover:underline"
                          >
                            編輯
                          </button>
                          <button
                            onClick={() => handleToggle(inst)}
                            className={`text-xs hover:underline ${inst.is_active ? "text-red-500" : "text-green-600"}`}
                          >
                            {inst.is_active ? "停用" : "啟用"}
                          </button>
                        </div>
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add modal */}
      {showAdd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <h3 className="mb-4 text-lg font-semibold">新增機構</h3>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500">機構名稱 *</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  placeholder="例如：新北市教育局"
                  autoFocus
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500">機構代號（最多 5 碼，用於核銷案編號）</label>
                <input
                  type="text"
                  value={newCode}
                  onChange={(e) => setNewCode(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono"
                  placeholder="例如：NTC01"
                  maxLength={5}
                />
              </div>
              <div>
                <label className="flex items-center gap-2 text-sm text-gray-600">
                  <input
                    type="checkbox"
                    checked={newRequiresDocs}
                    onChange={(e) => setNewRequiresDocs(e.target.checked)}
                  />
                  需心理師繳交資料
                </label>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => { setShowAdd(false); setNewName(""); setNewCode(""); setNewRequiresDocs(true); }}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
              >
                取消
              </button>
              <button
                onClick={handleAdd}
                disabled={!newName.trim() || adding}
                className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
              >
                {adding ? "新增中..." : "新增"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/* ═══════════════════════════════════════════════════
   Tab 3: 資料匯出入
   ═══════════════════════════════════════════════════ */

interface ImportResult {
  table: string;
  mode: string;
  total_rows: number;
  would_insert: number;
  would_update: number;
  would_skip: number;
  errors: { row: number; field: string; value?: string; message: string }[];
  warnings: { row: number; field: string; message: string }[];
  committed: boolean;
}

const IMPORT_TABLES = [
  { value: "session_records", label: "帳冊流水帳（session_records）" },
  { value: "cases", label: "個案（cases）" },
  { value: "users", label: "使用者帳號（users）" },
  { value: "institutions", label: "機構（institutions）" },
  { value: "petty_cash", label: "零用金（petty_cash）" },
  { value: "product_sales", label: "商品販售（product_sales）" },
];

function DataTab({ token }: { token: string }) {
  const [tables, setTables] = useState<{ key: string; label: string; endpoint: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState<string | null>(null);

  // Import state
  const [impTable, setImpTable] = useState("session_records");
  const [impMode, setImpMode] = useState<"dry_run" | "supplement" | "clean">("dry_run");
  const [impFile, setImpFile] = useState<File | null>(null);
  const [impPassword, setImpPassword] = useState("");
  const [impResult, setImpResult] = useState<ImportResult | null>(null);
  const [impLoading, setImpLoading] = useState(false);
  const [impError, setImpError] = useState<string | null>(null);
  const [showErrors, setShowErrors] = useState(true);
  const [showWarnings, setShowWarnings] = useState(true);

  const fetchTables = useCallback(async () => {
    setLoading(true);
    try {
      const data = await clientFetch("/export/tables", token);
      setTables(data);
    } catch {
      setTables([
        { key: "cases", label: "個案", endpoint: "/export/cases" },
        { key: "appointments", label: "預約", endpoint: "/export/appointments" },
        { key: "ledger", label: "帳冊流水帳", endpoint: "/export/ledger" },
        { key: "claim-batches", label: "核銷案", endpoint: "/export/claim-batches" },
        { key: "invoices", label: "收據", endpoint: "/export/invoices" },
        { key: "petty-cash", label: "零用金", endpoint: "/export/petty-cash" },
        { key: "users", label: "使用者", endpoint: "/export/users" },
        { key: "rooms", label: "諮商室", endpoint: "/export/rooms" },
        { key: "institutions", label: "機構", endpoint: "/export/institutions" },
        { key: "audit-log", label: "稽核日誌", endpoint: "/export/audit-log" },
      ]);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchTables(); }, [fetchTables]);

  const handleDownload = async (table: { key: string; endpoint: string }) => {
    setDownloading(table.key);
    try {
      await exportCsv(table.endpoint, token, `${table.key}.csv`);
    } catch (e: any) {
      alert(`匯出失敗：${e.message}`);
    } finally {
      setDownloading(null);
    }
  };

  const handlePreview = async () => {
    if (!impFile) { setImpError("請先選擇 CSV 檔案"); return; }
    setImpLoading(true);
    setImpResult(null);
    setImpError(null);
    try {
      const form = new FormData();
      form.append("table", impTable);
      form.append("file", impFile);
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/data-import/preview`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "預覽失敗" }));
        throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
      }
      setImpResult(await res.json());
    } catch (e: any) {
      setImpError(e.message);
    } finally {
      setImpLoading(false);
    }
  };

  const handleImport = async () => {
    if (!impFile) { setImpError("請先選擇 CSV 檔案"); return; }
    if (impMode === "clean" && !impPassword) { setImpError("清洗模式需要輸入管理員密碼"); return; }
    if (!window.confirm(`確定要執行「${impMode === "supplement" ? "補登" : "清洗覆蓋"}」匯入？此操作不可撤銷。`)) return;
    setImpLoading(true);
    setImpResult(null);
    setImpError(null);
    try {
      const form = new FormData();
      form.append("table", impTable);
      form.append("file", impFile);
      if (impMode === "clean") form.append("admin_password", impPassword);
      const endpoint = impMode === "supplement" ? "supplement" : "clean";
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/data-import/${endpoint}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "匯入失敗" }));
        const detail = err.detail;
        if (detail && typeof detail === "object" && detail.errors) {
          setImpResult({ table: impTable, mode: impMode, total_rows: 0, would_insert: 0, would_update: 0, would_skip: 0, errors: detail.errors, warnings: [], committed: false });
          throw new Error(detail.message || "匯入失敗");
        }
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      }
      const result = await res.json();
      setImpResult(result);
      setImpPassword("");
    } catch (e: any) {
      setImpError(e.message);
    } finally {
      setImpLoading(false);
    }
  };

  const canImport = impResult && impResult.errors.length === 0 && impMode !== "dry_run";

  return (
    <>
      <div className="mb-6">
        <p className="text-sm text-gray-500">匯出各資料表為 CSV 格式（含所有欄位），或上傳 CSV 進行資料匯入。</p>
      </div>

      {/* Export section */}
      <div className="mb-10">
        <h2 className="mb-4 text-lg font-semibold">📥 資料匯出</h2>
        {loading ? (
          <div className="py-8 text-center text-gray-400">載入中...</div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {tables.map((t) => (
              <div key={t.key} className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-3">
                <div>
                  <p className="text-sm font-medium text-gray-900">{t.label}</p>
                  <p className="text-xs text-gray-400">{t.key}.csv</p>
                </div>
                <button
                  onClick={() => handleDownload(t)}
                  disabled={downloading === t.key}
                  className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                >
                  {downloading === t.key ? "下載中..." : "下載 CSV"}
                </button>
              </div>
            ))}
          </div>
        )}
        <button
          onClick={async () => {
            for (const t of tables) {
              await exportCsv(t.endpoint, token, `${t.key}.csv`);
              await new Promise((r) => setTimeout(r, 300));
            }
          }}
          className="mt-4 rounded-lg bg-gray-800 px-4 py-2 text-sm font-medium text-white hover:bg-gray-900"
        >
          全部下載
        </button>
      </div>

      {/* Import section */}
      <div>
        <h2 className="mb-4 text-lg font-semibold">📤 資料匯入</h2>
        <div className="rounded-lg border border-gray-200 bg-white p-6">
          {/* Step 1: Table */}
          <div className="mb-4">
            <label className="mb-1 block text-xs font-semibold text-gray-700">① 選擇資料表</label>
            <select
              value={impTable}
              onChange={(e) => { setImpTable(e.target.value); setImpResult(null); setImpError(null); }}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            >
              {IMPORT_TABLES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          {/* Step 2: Mode */}
          <div className="mb-4">
            <label className="mb-2 block text-xs font-semibold text-gray-700">② 匯入模式</label>
            <div className="flex flex-col gap-2">
              {[
                { value: "dry_run", icon: "🔍", label: "除錯模式（只驗證，不寫入資料庫）", desc: "安全，無副作用", cls: "border-blue-200 bg-blue-50" },
                { value: "supplement", icon: "➕", label: "補登（只新增不存在的記錄）", desc: "跳過 ID 已存在的列", cls: "border-green-200 bg-green-50" },
                { value: "clean", icon: "⚠️", label: "清洗覆蓋（更新現有 + 新增）", desc: "高風險，需輸入管理員密碼", cls: "border-orange-200 bg-orange-50" },
              ].map((m) => (
                <label
                  key={m.value}
                  className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 ${impMode === m.value ? m.cls : "border-gray-200 bg-gray-50"}`}
                >
                  <input
                    type="radio"
                    name="impMode"
                    value={m.value}
                    checked={impMode === m.value}
                    onChange={() => { setImpMode(m.value as any); setImpResult(null); setImpError(null); }}
                    className="mt-0.5"
                  />
                  <div>
                    <span className="text-sm font-medium">{m.icon} {m.label}</span>
                    <p className="text-xs text-gray-500">{m.desc}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Step 3: File */}
          <div className="mb-4">
            <label className="mb-1 block text-xs font-semibold text-gray-700">③ 上傳 CSV 檔案</label>
            <input
              type="file"
              accept=".csv"
              onChange={(e) => { setImpFile(e.target.files?.[0] ?? null); setImpResult(null); setImpError(null); }}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
            {impFile && <p className="mt-1 text-xs text-gray-400">已選擇：{impFile.name}（{(impFile.size / 1024).toFixed(1)} KB）</p>}
          </div>

          {/* Step 4: Password (clean only) */}
          {impMode === "clean" && (
            <div className="mb-4 rounded-lg border border-orange-200 bg-orange-50 p-4">
              <label className="mb-1 block text-xs font-semibold text-orange-700">④ 管理員密碼確認 <span className="text-red-500">*</span></label>
              <input
                type="password"
                value={impPassword}
                onChange={(e) => setImpPassword(e.target.value)}
                placeholder="請輸入您的管理員密碼"
                className="w-full rounded-lg border border-orange-300 bg-white px-3 py-2 text-sm"
              />
              <p className="mt-1 text-xs text-orange-600">清洗模式將更新現有記錄，所有變更將記錄於稽核日誌</p>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={handlePreview}
              disabled={!impFile || impLoading}
              className="rounded-lg border border-blue-300 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-50"
            >
              {impLoading ? "處理中..." : "🔍 執行預覽（Dry Run）"}
            </button>
            {canImport && (
              <button
                onClick={handleImport}
                disabled={impLoading}
                className={`rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50 ${impMode === "clean" ? "bg-orange-500 hover:bg-orange-600" : "bg-green-600 hover:bg-green-700"}`}
              >
                {impLoading ? "匯入中..." : `確認匯入（${impMode === "supplement" ? "補登" : "清洗覆蓋"}）`}
              </button>
            )}
            {impResult && impResult.errors.length > 0 && impMode !== "dry_run" && (
              <p className="text-xs text-red-500">⛔ 請先修正 {impResult.errors.length} 個錯誤後才能執行匯入</p>
            )}
          </div>

          {/* Error message */}
          {impError && (
            <div className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-600">{impError}</div>
          )}

          {/* Preview result panel */}
          {impResult && (
            <div className="mt-5 rounded-lg border border-gray-200 bg-gray-50">
              {/* Summary */}
              <div className={`rounded-t-lg px-4 py-3 ${impResult.committed ? "bg-green-50 border-b border-green-200" : "bg-white border-b border-gray-200"}`}>
                <div className="flex flex-wrap items-center gap-4 text-sm">
                  {impResult.committed && <span className="font-semibold text-green-700">✅ 匯入完成</span>}
                  {!impResult.committed && <span className="font-semibold text-gray-700">預覽結果</span>}
                  <span className="text-gray-600">共 <strong>{impResult.total_rows}</strong> 列</span>
                  {impResult.would_insert > 0 && <span className="text-green-600">新增 <strong>{impResult.would_insert}</strong></span>}
                  {impResult.would_update > 0 && <span className="text-blue-600">更新 <strong>{impResult.would_update}</strong></span>}
                  {impResult.would_skip > 0 && <span className="text-gray-500">跳過 <strong>{impResult.would_skip}</strong></span>}
                  {impResult.errors.length > 0 && <span className="text-red-600 font-semibold">❌ {impResult.errors.length} 個錯誤</span>}
                  {impResult.warnings.length > 0 && <span className="text-amber-600">⚠️ {impResult.warnings.length} 個警告</span>}
                  {impResult.errors.length === 0 && impResult.mode === "dry_run" && (
                    <span className="text-blue-600">✅ 驗證通過，可切換至補登或清洗模式執行匯入</span>
                  )}
                </div>
              </div>

              {/* Errors */}
              {impResult.errors.length > 0 && (
                <div className="border-b border-gray-200">
                  <button
                    onClick={() => setShowErrors((v) => !v)}
                    className="flex w-full items-center justify-between px-4 py-2 text-left text-sm font-medium text-red-700 hover:bg-red-50"
                  >
                    <span>❌ 錯誤列表（{impResult.errors.length} 個）</span>
                    <span>{showErrors ? "▲" : "▼"}</span>
                  </button>
                  {showErrors && (
                    <div className="max-h-60 overflow-y-auto">
                      <table className="w-full text-xs">
                        <thead className="bg-red-50 text-red-700">
                          <tr>
                            <th className="px-3 py-1.5 text-left">列</th>
                            <th className="px-3 py-1.5 text-left">欄位</th>
                            <th className="px-3 py-1.5 text-left">值</th>
                            <th className="px-3 py-1.5 text-left">錯誤訊息</th>
                          </tr>
                        </thead>
                        <tbody>
                          {impResult.errors.map((e, i) => (
                            <tr key={i} className="border-t border-red-100">
                              <td className="px-3 py-1 text-red-600">第 {e.row} 列</td>
                              <td className="px-3 py-1 font-mono">{e.field}</td>
                              <td className="px-3 py-1 text-gray-500">{e.value ?? ""}</td>
                              <td className="px-3 py-1">{e.message}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* Warnings */}
              {impResult.warnings.length > 0 && (
                <div>
                  <button
                    onClick={() => setShowWarnings((v) => !v)}
                    className="flex w-full items-center justify-between px-4 py-2 text-left text-sm font-medium text-amber-700 hover:bg-amber-50"
                  >
                    <span>⚠️ 警告列表（{impResult.warnings.length} 個）</span>
                    <span>{showWarnings ? "▲" : "▼"}</span>
                  </button>
                  {showWarnings && (
                    <div className="max-h-48 overflow-y-auto">
                      <table className="w-full text-xs">
                        <thead className="bg-amber-50 text-amber-700">
                          <tr>
                            <th className="px-3 py-1.5 text-left">列</th>
                            <th className="px-3 py-1.5 text-left">欄位</th>
                            <th className="px-3 py-1.5 text-left">警告訊息</th>
                          </tr>
                        </thead>
                        <tbody>
                          {impResult.warnings.map((w, i) => (
                            <tr key={i} className="border-t border-amber-100">
                              <td className="px-3 py-1 text-amber-600">第 {w.row} 列</td>
                              <td className="px-3 py-1 font-mono">{w.field}</td>
                              <td className="px-3 py-1">{w.message}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Usage note */}
        <div className="mt-4 rounded-lg bg-blue-50 p-4 text-xs text-blue-700">
          <p className="font-semibold mb-1">💡 使用說明</p>
          <ul className="list-disc pl-4 space-y-1">
            <li>CSV 格式需與匯出格式相符（可先匯出後修改再匯入）</li>
            <li>CSV 必須含 <code className="bg-blue-100 px-1 rounded">id</code> 欄位；<strong>除錯模式</strong>可先驗證格式與資料正確性</li>
            <li><strong>補登</strong>：只新增 id 不存在的記錄，已存在的記錄不動</li>
            <li><strong>清洗覆蓋</strong>：依 id 更新現有記錄 + 新增不存在的記錄，所有更新會記錄到稽核日誌</li>
            <li>有驗證錯誤的列一律跳過（不寫入），警告不影響匯入</li>
          </ul>
        </div>
      </div>
    </>
  );
}
