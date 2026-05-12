"use client";

import { useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

interface RecordRow {
  id: number;
  session_date: string;
  case_id: number;
  case_name: string | null;
  therapist_name: string | null;
  amount: number;
  payment_status: string;
  claim_number: string | null;
  receipt_number: string | null;
}

interface GroupSummary {
  total: number;
  paid: number;
  unpaid: number;
  count: number;
}

interface InstitutionGroup {
  institution_name: string;
  summary: GroupSummary;
  records: RecordRow[];
}

interface ReconData {
  year: number;
  month: number;
  self_pay: { summary: GroupSummary; records: RecordRow[] };
  institutions: InstitutionGroup[];
}

const statusLabels: Record<string, string> = {
  unpaid: "未收/未請款",
  paid: "已收款",
  claiming: "請款中",
  claimed: "已請款",
};

const statusColors: Record<string, string> = {
  unpaid: "bg-red-100 text-red-700",
  paid: "bg-green-100 text-green-700",
  claiming: "bg-blue-100 text-blue-700",
  claimed: "bg-green-100 text-green-700",
};

export default function ReconciliationPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;

  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data, setData] = useState<ReconData | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const d = await clientFetch(`/reports/reconciliation?year=${year}&month=${month}`, token);
      setData(d);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [token, year, month]);

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">財務核銷報表</h1>
        <div className="flex items-center gap-2">
          <select value={year} onChange={(e) => setYear(parseInt(e.target.value))} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
            {[2025, 2026, 2027].map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <select value={month} onChange={(e) => setMonth(parseInt(e.target.value))} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => <option key={m} value={m}>{m} 月</option>)}
          </select>
          <button onClick={fetchData} disabled={loading} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">
            {loading ? "產生中..." : "產生報表"}
          </button>
        </div>
      </div>

      {!data ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-16 text-center text-gray-400">
          選擇年月後點擊「產生報表」
        </div>
      ) : (
        <div className="space-y-8">
          {/* Self-pay section */}
          <GroupSection
            title="自費個案"
            summary={data.self_pay.summary}
            records={data.self_pay.records}
            isSelfPay={true}
          />

          {/* Institution sections */}
          {data.institutions.map((inst) => (
            <GroupSection
              key={inst.institution_name}
              title={`機構：${inst.institution_name}`}
              summary={inst.summary}
              records={inst.records}
              isSelfPay={false}
            />
          ))}

          {data.institutions.length === 0 && data.self_pay.records.length === 0 && (
            <p className="text-center text-gray-400">本月無流水帳資料</p>
          )}
        </div>
      )}
    </div>
  );
}

function GroupSection({
  title,
  summary,
  records,
  isSelfPay,
}: {
  title: string;
  summary: GroupSummary;
  records: RecordRow[];
  isSelfPay: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  if (records.length === 0) return null;

  return (
    <div className="rounded-lg border border-gray-200 bg-white">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-5 py-4 text-left hover:bg-gray-50"
      >
        <div>
          <h2 className="text-lg font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-gray-500">
            {summary.count} 筆 · 合計 ${summary.total.toLocaleString()}
          </p>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-green-600">
            已{isSelfPay ? "收" : "請"}款 ${summary.paid.toLocaleString()}
          </span>
          <span className="text-red-600">
            未{isSelfPay ? "收" : "請"}款 ${summary.unpaid.toLocaleString()}
          </span>
          <span className="text-gray-400">{expanded ? "▲" : "▼"}</span>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-gray-200">
          <table className="w-full text-left text-sm">
            <thead className="bg-gray-50 text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-3">日期</th>
                <th className="px-4 py-3">個案</th>
                <th className="px-4 py-3">心理師</th>
                <th className="px-4 py-3 text-right">金額</th>
                <th className="px-4 py-3">狀態</th>
                {!isSelfPay && <th className="px-4 py-3">單號</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {records.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">{r.session_date}</td>
                  <td className="px-4 py-3">{r.case_name ?? "-"}</td>
                  <td className="px-4 py-3">{r.therapist_name ?? "-"}</td>
                  <td className="px-4 py-3 text-right">${r.amount.toLocaleString()}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[r.payment_status] ?? "bg-gray-100"}`}>
                      {statusLabels[r.payment_status] ?? r.payment_status}
                    </span>
                  </td>
                  {!isSelfPay && (
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {r.claim_number && <div>請款: {r.claim_number}</div>}
                      {r.receipt_number && <div>收據: {r.receipt_number}</div>}
                      {!r.claim_number && !r.receipt_number && "-"}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
