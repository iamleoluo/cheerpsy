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
  therapist_code: string | null;
  commission_rate: number | null;
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

interface Institution {
  id: number;
  name: string;
  code: string | null;
  is_active: boolean;
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

  const [tab, setTab] = useState<"users" | "institutions">("users");

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
      </div>

      {tab === "users" ? <UsersTab token={token} /> : <InstitutionsTab token={token} />}
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

  const handleCreateInvite = async () => {
    if (!invName.trim()) return;
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

      if (invRole === "therapist" && invCommission) {
        const newUser = (await clientFetch("/auth/users", token) as UserItem[])
          .find((u) => u.therapist_code === invCode.trim());
        if (newUser) {
          await clientFetch(`/auth/users/${newUser.id}/commission-rate`, token, {
            method: "PUT",
            body: JSON.stringify({ commission_rate: parseFloat(invCommission) }),
          }).catch(() => {});
        }
      }

      setShowInvite(false);
      setInvName("");
      setInvRole("therapist");
      setInvCode("");
      setInvCommission("0.70");
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
              <th className="px-4 py-3">狀態</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-400">載入中...</td>
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
                  <td className="px-4 py-3 font-mono text-xs text-gray-400">
                    {u.therapist_code ?? "—"}
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

              {invRole === "therapist" && (() => {
                const allCodes = users.filter((u) => u.therapist_code).map((u) => ({
                  code: u.therapist_code!,
                  name: u.name,
                  active: u.is_active,
                }));
                const reusable = allCodes.filter((c) => !c.active);
                let nextCode = "";
                for (let i = 1; i <= 999; i++) {
                  const candidate = `T${String(i).padStart(3, "0")}`;
                  if (!allCodes.some((c) => c.code === candidate)) {
                    nextCode = candidate;
                    break;
                  }
                }
                return (
                  <>
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-500">心理師代號 *</label>
                      <input
                        type="text"
                        value={invCode}
                        onChange={(e) => setInvCode(e.target.value)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono"
                        placeholder="例如 T018"
                      />
                      <div className="mt-2 space-y-1">
                        {nextCode && (
                          <button
                            type="button"
                            onClick={() => setInvCode(nextCode)}
                            className="rounded bg-primary-50 px-2 py-0.5 text-xs text-primary-600 hover:bg-primary-100"
                          >
                            自動：{nextCode}（新代號）
                          </button>
                        )}
                        {reusable.length > 0 && (
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
                        )}
                      </div>
                    </div>
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
                  </>
                );
              })()}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => {
                  setShowInvite(false);
                  setInvName("");
                  setInvRole("therapist");
                  setInvCode("");
                  setInvCommission("0.70");
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
  const [adding, setAdding] = useState(false);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editCode, setEditCode] = useState("");

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
      const body: any = { name: newName.trim() };
      if (newCode.trim()) body.code = newCode.trim();
      await clientFetch("/institutions", token, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setShowAdd(false);
      setNewName("");
      setNewCode("");
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
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => { setShowAdd(false); setNewName(""); setNewCode(""); }}
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
