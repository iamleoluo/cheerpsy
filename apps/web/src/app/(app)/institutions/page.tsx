"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch, exportCsv } from "@/lib/client-api";

interface Institution {
  id: number;
  name: string;
  is_active: boolean;
}

export default function InstitutionsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const userRole = (session?.user as any)?.role;

  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newName, setNewName] = useState("");
  const [adding, setAdding] = useState(false);
  const [search, setSearch] = useState("");
  const [confirmAction, setConfirmAction] = useState<number | null>(null);

  const fetchInstitutions = useCallback(async () => {
    if (!token) return;
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

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim() || !token) return;
    setAdding(true);
    setError("");
    try {
      await clientFetch("/institutions", token, {
        method: "POST",
        body: JSON.stringify({ name: newName.trim() }),
      });
      setNewName("");
      fetchInstitutions();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setAdding(false);
    }
  };

  const handleDeactivate = async (id: number) => {
    if (!token) return;
    setError("");
    try {
      await clientFetch(`/institutions/${id}`, token, { method: "DELETE" });
      setConfirmAction(null);
      fetchInstitutions();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handleActivate = async (id: number) => {
    if (!token) return;
    setError("");
    try {
      await clientFetch(`/institutions/${id}/activate`, token, { method: "PUT" });
      setConfirmAction(null);
      fetchInstitutions();
    } catch (e: any) {
      setError(e.message);
    }
  };

  if (userRole !== "admin") {
    return (
      <div className="flex h-64 items-center justify-center text-gray-400">
        僅管理員可存取此頁面
      </div>
    );
  }

  const filtered = search
    ? institutions.filter((i) => i.name.includes(search))
    : institutions;

  const activeCount = institutions.filter((i) => i.is_active).length;
  const inactiveCount = institutions.length - activeCount;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">機構管理</h1>
          <p className="mt-1 text-sm text-gray-500">
            管理轉介機構名稱，供個案經費來源選單使用
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="rounded-full bg-green-50 px-3 py-1 text-sm text-green-700">
            啟用 {activeCount}
          </span>
          {inactiveCount > 0 && (
            <span className="rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-500">
              已停用 {inactiveCount}
            </span>
          )}
          <button
            onClick={() => exportCsv("/export/institutions", token!, "institutions.csv")}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
          >
            匯出 CSV
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">
          {error}
          <button
            onClick={() => setError("")}
            className="ml-2 font-medium underline"
          >
            關閉
          </button>
        </div>
      )}

      <form onSubmit={handleAdd} className="mb-6 flex gap-3">
        <input
          type="text"
          placeholder="輸入新機構名稱..."
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          className="flex-1 rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-primary-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={adding || !newName.trim()}
          className="rounded-lg bg-primary-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
        >
          {adding ? "新增中..." : "+ 新增機構"}
        </button>
      </form>

      <div className="mb-4">
        <input
          type="text"
          placeholder="搜尋機構..."
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
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((inst) => (
            <div
              key={inst.id}
              className={`flex items-center justify-between rounded-lg border px-4 py-3 transition-shadow hover:shadow-sm ${
                inst.is_active
                  ? "border-gray-200 bg-white"
                  : "border-dashed border-gray-300 bg-gray-50"
              }`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={
                    inst.is_active
                      ? "font-medium text-gray-800"
                      : "font-medium text-gray-400 line-through"
                  }
                >
                  {inst.name}
                </span>
                {inst.is_active ? (
                  <span className="inline-block rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700">
                    啟用中
                  </span>
                ) : (
                  <span className="inline-block rounded-full bg-gray-200 px-2 py-0.5 text-xs text-gray-500">
                    已停用
                  </span>
                )}
              </div>
              {confirmAction === inst.id ? (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500">
                    {inst.is_active ? "確定停用？" : "確定啟用？"}
                  </span>
                  <button
                    onClick={() =>
                      inst.is_active
                        ? handleDeactivate(inst.id)
                        : handleActivate(inst.id)
                    }
                    className={`rounded px-2 py-1 text-xs text-white ${
                      inst.is_active
                        ? "bg-red-500 hover:bg-red-600"
                        : "bg-green-500 hover:bg-green-600"
                    }`}
                  >
                    確定
                  </button>
                  <button
                    onClick={() => setConfirmAction(null)}
                    className="rounded border border-gray-300 px-2 py-1 text-xs hover:bg-gray-50"
                  >
                    取消
                  </button>
                </div>
              ) : inst.is_active ? (
                <button
                  onClick={() => setConfirmAction(inst.id)}
                  className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-500 hover:border-red-300 hover:bg-red-50 hover:text-red-600"
                >
                  停用
                </button>
              ) : (
                <button
                  onClick={() => setConfirmAction(inst.id)}
                  className="rounded border border-green-300 px-2 py-1 text-xs text-green-600 hover:bg-green-50"
                >
                  重新啟用
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
