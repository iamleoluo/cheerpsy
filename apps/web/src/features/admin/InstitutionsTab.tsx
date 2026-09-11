"use client";

import { useEffect, useState, useCallback } from "react";
import { clientFetch, exportCsv } from "@/lib/client-api";
import type { Institution } from "./types";

/** 機構管理：機構單位的建檔與「是否需要心理師文件確認」開關。 */

export function InstitutionsTab({ token }: { token: string }) {
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
          <p className="text-sm text-ink-3">管理轉介機構名稱與代號，供個案經費來源與核銷案使用</p>
          <span className="rounded-full bg-st-done-bg px-2.5 py-0.5 text-xs text-st-done">
            啟用 {activeCount}
          </span>
          {inactiveCount > 0 && (
            <span className="rounded-full bg-surface-3 px-2.5 py-0.5 text-xs text-ink-3">
              已停用 {inactiveCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => exportCsv("/export/institutions", token, "institutions.csv")}
            className="rounded-lg border border-line-2 px-3 py-2 text-sm hover:bg-surface-2"
          >
            匯出 CSV
          </button>
          <button
            onClick={() => setShowAdd(true)}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-st-active"
          >
            + 新增機構
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-st-danger-bg p-3 text-sm text-st-danger">
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
          className="w-64 rounded-lg border border-line-2 px-3 py-2 text-sm focus:border-accent focus:outline-none"
        />
      </div>

      {loading ? (
        <div className="py-12 text-center text-ink-3">載入中...</div>
      ) : filtered.length === 0 ? (
        <div className="py-12 text-center text-ink-3">
          {search ? "找不到符合的機構" : "尚無機構資料"}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface-2 text-xs uppercase text-ink-3">
              <tr>
                <th className="px-4 py-3">機構代號</th>
                <th className="px-4 py-3">機構名稱</th>
                <th className="px-4 py-3">繳交資料</th>
                <th className="px-4 py-3">狀態</th>
                <th className="px-4 py-3">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {filtered.map((inst) => (
                <tr key={inst.id} className={`hover:bg-surface-2 ${!inst.is_active ? "opacity-50" : ""}`}>
                  {editingId === inst.id ? (
                    <>
                      <td className="px-4 py-3">
                        <input
                          type="text"
                          value={editCode}
                          onChange={(e) => setEditCode(e.target.value)}
                          className="w-24 rounded border border-line-2 px-2 py-1 text-xs font-mono"
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
                          className="w-full rounded border border-line-2 px-2 py-1 text-sm"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <label className="flex items-center gap-1 text-xs text-ink-2">
                          <input
                            type="checkbox"
                            checked={editRequiresDocs}
                            onChange={(e) => setEditRequiresDocs(e.target.checked)}
                          />
                          需心理師繳交資料
                        </label>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${inst.is_active ? "bg-st-done-bg text-st-done" : "bg-surface-3 text-ink-3"}`}>
                          {inst.is_active ? "啟用" : "停用"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleSaveEdit(inst.id)}
                            className="text-xs text-st-done hover:underline"
                          >
                            儲存
                          </button>
                          <button
                            onClick={() => setEditingId(null)}
                            className="text-xs text-ink-3 hover:underline"
                          >
                            取消
                          </button>
                        </div>
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="px-4 py-3 font-mono text-xs text-ink-3">
                        {inst.code || "—"}
                      </td>
                      <td className="px-4 py-3 font-medium">{inst.name}</td>
                      <td className="px-4 py-3">
                        {inst.requires_therapist_docs ? (
                          <span className="text-xs text-ink-3">需繳資料</span>
                        ) : (
                          <span className="inline-block rounded-full bg-surface-3 px-2 py-0.5 text-xs text-ink-3">免繳資料</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${inst.is_active ? "bg-st-done-bg text-st-done" : "bg-surface-3 text-ink-3"}`}>
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
                            className="text-xs text-accent hover:underline"
                          >
                            編輯
                          </button>
                          <button
                            onClick={() => handleToggle(inst)}
                            className={`text-xs hover:underline ${inst.is_active ? "text-st-danger" : "text-st-done"}`}
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
                <label className="mb-1 block text-xs font-medium text-ink-3">機構名稱 *</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm"
                  placeholder="例如：新北市教育局"
                  autoFocus
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-ink-3">機構代號（最多 5 碼，用於核銷案編號）</label>
                <input
                  type="text"
                  value={newCode}
                  onChange={(e) => setNewCode(e.target.value)}
                  className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm font-mono"
                  placeholder="例如：NTC01"
                  maxLength={5}
                />
              </div>
              <div>
                <label className="flex items-center gap-2 text-sm text-ink-2">
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
                className="rounded-lg border border-line-2 px-4 py-2 text-sm hover:bg-surface-2"
              >
                取消
              </button>
              <button
                onClick={handleAdd}
                disabled={!newName.trim() || adding}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-st-active disabled:opacity-50"
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
