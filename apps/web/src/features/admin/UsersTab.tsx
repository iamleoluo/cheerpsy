"use client";

import { useEffect, useState, useCallback } from "react";
import { clientFetch } from "@/lib/client-api";
import { ROLE_CODE_PREFIX, computeNextCode, roleBadge, roleLabels, type InvitationItem, type UserItem } from "./types";

/** 帳號管理：邀請、代號、抽成比例與預設價格、停用啟用、重設密碼金鑰。 */

export function UsersTab({ token }: { token: string }) {
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
        <p className="text-sm text-ink-3">管理帳號、角色權限與心理師抽成比例</p>
        <button
          onClick={() => setShowInvite(true)}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-st-active"
        >
          + 建立邀請
        </button>
      </div>

      {/* Users table */}
      <div className="mb-8 overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-2 text-xs uppercase text-ink-3">
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
          <tbody className="divide-y divide-line">
            {loading ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-ink-3">載入中...</td>
              </tr>
            ) : (
              users.map((u) => (
                <tr key={u.id} className={`hover:bg-surface-2 ${!u.is_active ? "opacity-50" : ""}`}>
                  <td className="px-4 py-3 font-medium">{u.name}</td>
                  <td className="px-4 py-3 text-ink-3">{u.email}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${roleBadge[u.role] ?? "bg-surface-3 text-ink-2"}`}>
                      {roleLabels[u.role] ?? u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-ink-3">
                    {u.user_code ? u.user_code : <span className="text-st-danger">未設定</span>}
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
                            className="w-20 rounded border border-line-2 px-2 py-1 text-xs"
                            autoFocus
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleSaveRate(u.id);
                              if (e.key === "Escape") setEditingRate(null);
                            }}
                          />
                          <button
                            onClick={() => handleSaveRate(u.id)}
                            className="text-xs text-st-done hover:text-st-done"
                          >
                            ✓
                          </button>
                          <button
                            onClick={() => setEditingRate(null)}
                            className="text-xs text-ink-3 hover:text-ink-2"
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
                          className="rounded px-2 py-0.5 text-xs font-medium text-accent hover:bg-accent-soft"
                          title="點擊編輯"
                        >
                          {Math.round((u.commission_rate ?? 0.7) * 100)}%
                        </button>
                      )
                    ) : (
                      <span className="text-xs text-st-muted">—</span>
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
                            className="w-24 rounded border border-line-2 px-2 py-1 text-xs"
                            autoFocus
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleSaveBase(u.id);
                              if (e.key === "Escape") setEditingBase(null);
                            }}
                          />
                          <button
                            onClick={() => handleSaveBase(u.id)}
                            className="text-xs text-st-done hover:text-st-done"
                          >
                            ✓
                          </button>
                          <button
                            onClick={() => setEditingBase(null)}
                            className="text-xs text-ink-3 hover:text-ink-2"
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
                          className="rounded px-2 py-0.5 text-xs font-medium text-accent hover:bg-accent-soft"
                          title="點擊編輯"
                        >
                          {u.base_price != null ? `$${Number(u.base_price).toLocaleString()}` : "未設定"}
                        </button>
                      )
                    ) : (
                      <span className="text-xs text-st-muted">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${u.is_active ? "bg-st-done-bg text-st-done" : "bg-st-danger-bg text-st-danger"}`}>
                      {u.is_active ? "啟用" : "停用"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button onClick={() => handleResetPassword(u.id, u.name)} className="text-xs text-accent hover:underline">
                        重設密碼
                      </button>
                      <button onClick={() => handleToggle(u.id)} className="text-xs text-ink-3 hover:underline">
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
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full text-left text-sm">
              <thead className="bg-surface-2 text-xs uppercase text-ink-3">
                <tr>
                  <th className="px-4 py-3">金鑰</th>
                  <th className="px-4 py-3">類型</th>
                  <th className="px-4 py-3">姓名</th>
                  <th className="px-4 py-3">角色</th>
                  <th className="px-4 py-3">到期時間</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {pendingInvitations.map((inv) => (
                  <tr key={inv.id} className="hover:bg-surface-2">
                    <td className="px-4 py-3 font-mono text-xs">{inv.invite_key}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${inv.type === "invite" ? "bg-accent-soft text-accent" : "bg-st-warn-bg text-st-warn"}`}>
                        {inv.type === "invite" ? "新帳號" : "重設密碼"}
                      </span>
                    </td>
                    <td className="px-4 py-3">{inv.name}</td>
                    <td className="px-4 py-3 text-xs text-ink-3">
                      {inv.role ? (roleLabels[inv.role] ?? inv.role) : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-ink-3">
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
                <label className="mb-1 block text-xs font-medium text-ink-3">姓名 *</label>
                <input
                  type="text"
                  value={invName}
                  onChange={(e) => setInvName(e.target.value)}
                  className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm"
                  placeholder="使用者姓名"
                  autoFocus
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-ink-3">角色 *</label>
                <select
                  value={invRole}
                  onChange={(e) => setInvRole(e.target.value)}
                  className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm"
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
                    <label className="mb-1 block text-xs font-medium text-ink-3">
                      使用者代號（留空自動產生）
                    </label>
                    <input
                      type="text"
                      value={invCode}
                      onChange={(e) => setInvCode(e.target.value.toUpperCase())}
                      className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm font-mono"
                      placeholder={`留空自動產生（如 ${prefix}001）`}
                    />
                    {reusable.length > 0 && (
                      <div className="mt-2">
                        <p className="mb-1 text-xs text-ink-3">可重用停用帳號的代號：</p>
                        <div className="flex flex-wrap gap-1">
                          {reusable.map((c) => (
                            <button
                              key={c.code}
                              type="button"
                              onClick={() => setInvCode(c.code)}
                              className={`rounded px-2 py-0.5 text-xs ${
                                invCode === c.code
                                  ? "bg-st-warn-bg text-st-warn"
                                  : "bg-st-warn-bg text-st-warn hover:bg-st-warn-bg"
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
                    <label className="mb-1 block text-xs font-medium text-ink-3">抽成比例</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        max="1"
                        value={invCommission}
                        onChange={(e) => setInvCommission(e.target.value)}
                        className="w-24 rounded-lg border border-line-2 px-3 py-2 text-sm"
                      />
                      <span className="text-sm text-ink-3">
                        （{Math.round(parseFloat(invCommission || "0") * 100)}% 歸心理師）
                      </span>
                    </div>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-ink-3">預約基礎價格</label>
                    <input
                      type="number"
                      min="0"
                      value={invBase}
                      onChange={(e) => setInvBase(e.target.value)}
                      className="w-32 rounded-lg border border-line-2 px-3 py-2 text-sm"
                      placeholder="例如 2000"
                    />
                    <p className="mt-1 text-xs text-ink-3">建立預約時自動帶入，可於當下調整</p>
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
                className="rounded-lg border border-line-2 px-4 py-2 text-sm hover:bg-surface-2"
              >
                取消
              </button>
              <button
                onClick={handleCreateInvite}
                disabled={!invName.trim() || creatingInvite}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-st-active disabled:opacity-50"
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
            <p className="mb-4 text-sm text-ink-3">
              請複製此金鑰並提供給使用者。金鑰 72 小時內有效，僅可使用一次。
            </p>
            <div className="flex items-center gap-2 rounded-lg bg-surface-2 p-4">
              <code className="flex-1 text-center text-lg font-bold tracking-widest text-accent">
                {resultKey}
              </code>
              <button
                onClick={copyKey}
                className="rounded-lg bg-accent-soft px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/20"
              >
                複製
              </button>
            </div>
            <div className="mt-5 flex justify-end">
              <button
                onClick={() => setResultKey("")}
                className="rounded-lg border border-line-2 px-4 py-2 text-sm hover:bg-surface-2"
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
