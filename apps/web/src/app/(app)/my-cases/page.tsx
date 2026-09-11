"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

interface CaseRow {
  id: number;
  case_number: string | null;
  name: string;
  case_type: string;
  funding_source: string;
  institution_name: string | null;
  status: string;
  phone: string | null;
}

const statusLabel: Record<string, string> = {
  intake: "初診中",
  ongoing: "進行中",
  paused: "暫停",
  closed: "已結案",
};

export default function MyCasesPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [cases, setCases] = useState<CaseRow[]>([]);
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    clientFetch("/cases", token)
      .then(setCases)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token]);

  const filtered = keyword
    ? cases.filter((c) => c.name.toLowerCase().includes(keyword.toLowerCase()) || c.case_number?.includes(keyword))
    : cases;

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">我的個案</h1>
      <input
        value={keyword}
        onChange={(e) => setKeyword(e.target.value)}
        placeholder="搜尋姓名或病歷號"
        className="mb-4 w-64 rounded-lg border border-line px-3 py-2 text-sm"
      />
      {loading && <p className="text-sm text-ink-3">載入中...</p>}
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-xs text-ink-3">
            <tr>
              <th className="border-b border-line px-3 py-2 text-left">病歷號</th>
              <th className="border-b border-line px-3 py-2 text-left">姓名</th>
              <th className="border-b border-line px-3 py-2 text-left">付款方式</th>
              <th className="border-b border-line px-3 py-2 text-left">狀態</th>
              <th className="border-b border-line px-3 py-2 text-left">電話</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-10 text-center text-sm text-ink-3">沒有符合條件的個案</td></tr>
            )}
            {filtered.map((c) => (
              <tr key={c.id} className="hover:bg-surface-2">
                <td className="border-b border-line px-3 py-2 font-mono text-xs">{c.case_number ?? "—"}</td>
                <td className="border-b border-line px-3 py-2 font-medium">{c.case_type === "couple" ? "👫 " : ""}{c.name}</td>
                <td className="border-b border-line px-3 py-2">{c.funding_source === "institution" ? (c.institution_name ?? "機構") : "自費"}</td>
                <td className="border-b border-line px-3 py-2">{statusLabel[c.status] ?? c.status}</td>
                <td className="border-b border-line px-3 py-2">{c.phone ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
