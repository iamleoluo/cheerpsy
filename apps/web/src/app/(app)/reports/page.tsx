"use client";

import { useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

interface ReportData {
  year: number;
  month: number;
  summary: {
    total_revenue: number;
    total_therapist_share: number;
    total_clinic_share: number;
    session_count: number;
    paid_count: number;
    unpaid_count: number;
    petty_cash_total: number;
    net_clinic_income: number;
  };
  therapist_summary: {
    therapist_id: number;
    therapist_name: string;
    sessions: number;
    revenue: number;
    therapist_share: number;
    clinic_share: number;
  }[];
  petty_cash_by_category: Record<string, number>;
  appointment_stats: {
    booked: number;
    cancelled: number;
    executed: number;
  };
}

const categoryLabels: Record<string, string> = {
  cleaning: "清潔費",
  supplies: "文具耗材",
  electricity: "電費",
  water: "水費",
  other: "其他",
};

export default function ReportsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;

  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [report, setReport] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchReport = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const data = await clientFetch(
        `/reports/monthly?year=${year}&month=${month}`,
        token,
      );
      setReport(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, year, month]);

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">月報表</h1>
        <div className="flex items-center gap-2">
          <select
            value={year}
            onChange={(e) => setYear(parseInt(e.target.value))}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            {[2025, 2026, 2027].map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
          <select
            value={month}
            onChange={(e) => setMonth(parseInt(e.target.value))}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
              <option key={m} value={m}>{m} 月</option>
            ))}
          </select>
          <button
            onClick={fetchReport}
            disabled={loading}
            className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
          >
            {loading ? "產生中..." : "產生報表"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">{error}</div>
      )}

      {!report ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-16 text-center text-gray-400">
          選擇年月後點擊「產生報表」
        </div>
      ) : (
        <div className="space-y-6">
          {/* Summary Cards */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="總營收" value={`$${report.summary.total_revenue.toLocaleString()}`} />
            <StatCard label="諮商次數" value={report.summary.session_count.toString()} />
            <StatCard label="心理師分潤" value={`$${report.summary.total_therapist_share.toLocaleString()}`} />
            <StatCard label="診所收入" value={`$${report.summary.total_clinic_share.toLocaleString()}`} />
          </div>

          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="已收款" value={report.summary.paid_count.toString()} color="green" />
            <StatCard label="未收款" value={report.summary.unpaid_count.toString()} color="red" />
            <StatCard label="零用金支出" value={`$${report.summary.petty_cash_total.toLocaleString()}`} />
            <StatCard label="取消預約" value={report.appointment_stats.cancelled.toString()} color="gray" />
          </div>

          {/* Therapist Summary */}
          <div>
            <h2 className="mb-3 text-lg font-semibold">心理師績效</h2>
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                  <tr>
                    <th className="px-4 py-3">心理師</th>
                    <th className="px-4 py-3 text-right">次數</th>
                    <th className="px-4 py-3 text-right">營收</th>
                    <th className="px-4 py-3 text-right">師酬</th>
                    <th className="px-4 py-3 text-right">所得</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {report.therapist_summary.map((t) => (
                    <tr key={t.therapist_id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium">{t.therapist_name}</td>
                      <td className="px-4 py-3 text-right">{t.sessions}</td>
                      <td className="px-4 py-3 text-right">${t.revenue.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right">${t.therapist_share.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right">${t.clinic_share.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Petty Cash by Category */}
          {Object.keys(report.petty_cash_by_category).length > 0 && (
            <div>
              <h2 className="mb-3 text-lg font-semibold">零用金分類</h2>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                {Object.entries(report.petty_cash_by_category).map(([cat, amt]) => (
                  <div key={cat} className="rounded-lg border border-gray-200 p-3">
                    <div className="text-xs text-gray-500">
                      {categoryLabels[cat] ?? cat}
                    </div>
                    <div className="text-lg font-bold">${amt.toLocaleString()}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  const colorClass =
    color === "green"
      ? "text-green-600"
      : color === "red"
        ? "text-red-600"
        : color === "gray"
          ? "text-gray-500"
          : "text-gray-900";
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`mt-1 text-xl font-bold ${colorClass}`}>{value}</div>
    </div>
  );
}
