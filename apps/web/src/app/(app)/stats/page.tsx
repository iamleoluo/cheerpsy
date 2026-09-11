"use client";

import { useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

/**
 * 我的數據（v1）。刻意只用 GET /cases、GET /ledger?month= 這兩支對
 * role=therapist 已自動限定為本人資料的端點自己彙總，不使用
 * /reports/therapist-load——那支是全所彙總報表，會洩漏其他心理師的數字，
 * 不符合「心理師只看得到自己」的權限設計（07 §C-bis）。
 */

interface CaseRow {
  id: number;
  status: string;
  funding_source: string;
}
interface LedgerRow {
  session_type: string;
  amount: number;
  therapist_share: number;
  outcall_bonus: number;
  payment_status: string;
}

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function StatsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [cases, setCases] = useState<CaseRow[]>([]);
  const [records, setRecords] = useState<LedgerRow[]>([]);
  const [month] = useState(currentMonth());
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    Promise.all([
      clientFetch("/cases", token).catch(() => []),
      clientFetch(`/ledger?month=${month}`, token).catch(() => []),
    ])
      .then(([c, r]) => { setCases(c); setRecords(r); })
      .finally(() => setLoading(false));
  }, [token, month]);

  const activeCases = cases.filter((c) => c.status === "ongoing").length;
  const bySessionType = useMemo(() => {
    const m: Record<string, number> = { in_person: 0, online: 0, outdoor: 0 };
    for (const r of records) m[r.session_type] = (m[r.session_type] ?? 0) + 1;
    return m;
  }, [records]);
  const totalRevenue = records.reduce((s, r) => s + r.amount, 0);
  const totalEarned = records.reduce((s, r) => s + r.therapist_share + r.outcall_bonus, 0);
  const paidCount = records.filter((r) => r.payment_status === "paid" || r.payment_status === "claimed").length;

  const sessionTypeLabel: Record<string, string> = { in_person: "現場", online: "視訊", outdoor: "外展" };

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <h1 className="mb-1 text-2xl font-bold">我的數據</h1>
      <p className="mb-6 text-sm text-ink-3">{month}</p>
      {loading && <p className="text-sm text-ink-3">載入中...</p>}

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-xl border border-line bg-white p-4">
          <div className="text-xs text-ink-3">進行中個案</div>
          <div className="mt-1 text-xl font-bold">{activeCases}</div>
        </div>
        <div className="rounded-xl border border-line bg-white p-4">
          <div className="text-xs text-ink-3">本月場次</div>
          <div className="mt-1 text-xl font-bold">{records.length}</div>
        </div>
        <div className="rounded-xl border border-line bg-white p-4">
          <div className="text-xs text-ink-3">本月營收（總額）</div>
          <div className="mt-1 text-xl font-bold">${totalRevenue.toLocaleString()}</div>
        </div>
        <div className="rounded-xl border border-line bg-white p-4">
          <div className="text-xs text-ink-3">本月我的酬勞</div>
          <div className="mt-1 text-xl font-bold text-accent">${totalEarned.toLocaleString()}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-line bg-white p-4">
          <h3 className="mb-3 text-sm font-medium text-ink-2">場次類型分布</h3>
          <div className="space-y-2">
            {Object.entries(bySessionType).map(([type, count]) => (
              <div key={type} className="flex items-center gap-2">
                <span className="w-10 text-xs text-ink-3">{sessionTypeLabel[type] ?? type}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-3">
                  <div
                    className="h-full rounded-full bg-accent/70"
                    style={{ width: records.length ? `${(count / records.length) * 100}%` : "0%" }}
                  />
                </div>
                <span className="w-6 text-right text-xs text-ink-3">{count}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-xl border border-line bg-white p-4">
          <h3 className="mb-3 text-sm font-medium text-ink-2">收款狀態</h3>
          <div className="flex items-center gap-2">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-3">
              <div className="h-full rounded-full bg-st-done" style={{ width: records.length ? `${(paidCount / records.length) * 100}%` : "0%" }} />
            </div>
            <span className="text-xs text-ink-3">{paidCount} / {records.length}</span>
          </div>
          <p className="mt-2 text-xs text-ink-3">已收款／已請款場次占比</p>
        </div>
      </div>
    </div>
  );
}
