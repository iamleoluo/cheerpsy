"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { clientFetch } from "@/lib/client-api";

/**
 * 機構合約清單（09 §3.7）：所有合約，依機構分組，點入每份合約各自的
 * 專頁（四分頁骨架，見 [id]/page.tsx）。一頁的單位是「合約」，方案包在
 * 裡面——這是 09 §3 已定案的分層架構。
 */

interface ContractRow {
  id: number;
  institution_id: number;
  institution_name: string | null;
  name: string;
  contact_name: string | null;
  contact_phone: string | null;
  valid_from: string | null;
  valid_until: string | null;
  is_active: boolean;
}

export default function InstitutionContractListPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [contracts, setContracts] = useState<ContractRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    clientFetch("/institution/contracts?include_inactive=true", token)
      .then(setContracts)
      .catch(() => setContracts([]))
      .finally(() => setLoading(false));
  }, [token]);

  const byInstitution = contracts.reduce<Record<string, ContractRow[]>>((acc, c) => {
    const key = c.institution_name ?? "（未分類）";
    (acc[key] ??= []).push(c);
    return acc;
  }, {});

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <h1 className="mb-1 text-2xl font-bold">機構合約</h1>
      <p className="mb-6 text-sm text-gray-400">一份合約 = 與某機構的一段合作，底下的方案（含額度、費率、核銷路由）都在合約專頁裡管理</p>

      {loading && <p className="text-sm text-gray-400">載入中...</p>}
      {!loading && contracts.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-200 py-12 text-center text-sm text-gray-400">尚無合約資料</div>
      )}

      <div className="space-y-6">
        {Object.entries(byInstitution).map(([institutionName, rows]) => (
          <div key={institutionName}>
            <h2 className="mb-2 text-sm font-semibold text-gray-500">{institutionName}</h2>
            <div className="overflow-hidden rounded-lg border border-gray-200">
              {rows.map((c) => (
                <Link
                  key={c.id}
                  href={`/institution/${c.id}`}
                  className="flex items-center justify-between border-b border-gray-100 bg-white px-4 py-3 text-sm last:border-b-0 hover:bg-gray-50"
                >
                  <div>
                    <span className="font-medium">{c.name}</span>
                    {!c.is_active && <span className="ml-2 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-400">已停用</span>}
                    {c.contact_name && <span className="ml-2 text-xs text-gray-400">承辦 {c.contact_name}{c.contact_phone ? ` · ${c.contact_phone}` : ""}</span>}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-400">
                    {c.valid_from && c.valid_until && <span>{c.valid_from} ~ {c.valid_until}</span>}
                    <span className="text-primary-500">查看 →</span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
