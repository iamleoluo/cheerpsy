"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

/**
 * 文件確認（心理師端）。機構核銷案需要雙重把關：心理師確認文件 + 行政
 * 核對，兩者皆完成該筆才算齊備。GET /institution/pending-docs、
 * /confirmed-docs 在 role=therapist 時後端已自動限定為本人資料。
 */

interface DocRow {
  id: number; session_date: string; case_name: string | null; session_type: string;
  institution_name: string | null;
}

const sessionTypeLabel: Record<string, string> = { in_person: "現場", online: "視訊", outdoor: "外展" };

export default function DocsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [tab, setTab] = useState<"pending" | "confirmed">("pending");
  const [pending, setPending] = useState<DocRow[]>([]);
  const [confirmed, setConfirmed] = useState<DocRow[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);

  const fetchAll = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [p, c] = await Promise.all([
        clientFetch("/institution/pending-docs", token),
        clientFetch("/institution/confirmed-docs", token),
      ]);
      setPending(p);
      setConfirmed(c);
      setSelected([]);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  function toggle(id: number) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }

  async function confirmSelected() {
    if (selected.length === 0) return;
    setBusy(true);
    try {
      await Promise.all(selected.map((id) => clientFetch(`/ledger/${id}/confirm-doc`, token, { method: "PUT" })));
      await fetchAll();
    } finally {
      setBusy(false);
    }
  }

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">文件確認</h1>

      <div className="mb-4 flex gap-1 border-b border-gray-200">
        {([
          ["pending", `未確認（${pending.length}）`],
          ["confirmed", "已確認文件"],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium ${tab === key ? "border-b-2 border-primary-600 text-primary-600" : "text-gray-500 hover:text-gray-700"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {loading && <p className="text-sm text-gray-400">載入中...</p>}

      {tab === "pending" && (
        <div>
          <div className="mb-3 rounded-lg bg-sky-50 px-4 py-2 text-xs text-sky-700">
            以下是您負責、且屬於核銷案但尚未確認文件的諮商紀錄。確認後行政會再核對，兩者皆完成才算齊備。
          </div>
          <div className="overflow-hidden rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500">
                <tr>
                  <th className="w-10 px-3 py-2"></th>
                  <th className="px-3 py-2 text-left">日期</th>
                  <th className="px-3 py-2 text-left">個案</th>
                  <th className="px-3 py-2 text-left">類型</th>
                  <th className="px-3 py-2 text-left">機構</th>
                </tr>
              </thead>
              <tbody>
                {pending.length === 0 && (
                  <tr><td colSpan={5} className="px-3 py-10 text-center text-sm text-gray-400">沒有待確認的紀錄</td></tr>
                )}
                {pending.map((r) => (
                  <tr key={r.id} className="hover:bg-gray-50">
                    <td className="border-t border-gray-100 px-3 py-2">
                      <input type="checkbox" checked={selected.includes(r.id)} onChange={() => toggle(r.id)} />
                    </td>
                    <td className="border-t border-gray-100 px-3 py-2">{r.session_date}</td>
                    <td className="border-t border-gray-100 px-3 py-2 font-medium">{r.case_name}</td>
                    <td className="border-t border-gray-100 px-3 py-2">{sessionTypeLabel[r.session_type] ?? r.session_type}</td>
                    <td className="border-t border-gray-100 px-3 py-2">{r.institution_name ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pending.length > 0 && (
            <div className="mt-3 flex justify-end">
              <button disabled={busy || selected.length === 0} onClick={confirmSelected} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-40">
                批次確認已勾選（{selected.length}）
              </button>
            </div>
          )}
        </div>
      )}

      {tab === "confirmed" && (
        <div className="overflow-hidden rounded-lg border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500">
              <tr>
                <th className="px-3 py-2 text-left">日期</th>
                <th className="px-3 py-2 text-left">個案</th>
                <th className="px-3 py-2 text-left">類型</th>
                <th className="px-3 py-2 text-left">機構</th>
              </tr>
            </thead>
            <tbody>
              {confirmed.length === 0 && (
                <tr><td colSpan={4} className="px-3 py-10 text-center text-sm text-gray-400">尚無已確認的紀錄</td></tr>
              )}
              {confirmed.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50">
                  <td className="border-t border-gray-100 px-3 py-2">{r.session_date}</td>
                  <td className="border-t border-gray-100 px-3 py-2 font-medium">{r.case_name}</td>
                  <td className="border-t border-gray-100 px-3 py-2">{sessionTypeLabel[r.session_type] ?? r.session_type}</td>
                  <td className="border-t border-gray-100 px-3 py-2">{r.institution_name ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
