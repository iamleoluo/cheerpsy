"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch, exportCsv } from "@/lib/client-api";
import HelpDrawer, { type HelpContent } from "@/components/HelpDrawer";

const helpContent: HelpContent = {
  title: "營運報表",
  overview: "整合所有模組數據，自動產出月度損益摘要。管理層可即時掌握診所營收、心理師酬勞、零用金支出、淨收益與機構墊付狀況。",
  sections: [
    {
      heading: "查看月報表",
      type: "steps",
      items: [
        "進入「營運報表 → 月報表」",
        "選擇要查看的年月（預設當月）",
        "查看：諮商總收入、心理師酬勞支出、診所毛利（30%）、零用金支出、淨收益",
        "確認目前機構墊付金額（機構未到款、診所已支付酬勞的部分）",
        "可匯出 CSV 供外部財務系統使用",
      ],
    },
    {
      heading: "主要指標說明",
      type: "text",
      items: [
        "諮商總收入：當月所有已執行諮商的費用總和",
        "心理師酬勞：依各人抽成比例（commission_rate_used）計算的應付總額",
        "診所毛利：診所應得的場地與行政費用（總收入 × 診所比例加總）",
        "零用金支出：當月記錄的所有雜項支出",
        "淨收益：診所毛利 − 零用金支出",
        "目前墊付金額：機構核銷案尚未結案、診所已付酬勞的金額",
      ],
    },
    {
      heading: "流失預警",
      type: "text",
      items: [
        "「流失預警」頁籤顯示超過 60 天未回診的進行中個案",
        "可依心理師篩選，追蹤哪些個案需要主動聯繫",
      ],
    },
    {
      heading: "管理員提示",
      type: "notes",
      items: [
        "報表即時反映帳冊狀態，帳冊更新後報表立即反映",
        "墊付金額高代表機構款項積壓，需追蹤核銷案請款進度",
        "月結產生後再查月報，數字更準確（避免酬勞未計入）",
      ],
    },
  ],
};

/* ───── main page ───── */

export default function ReportsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [tab, setTab] = useState<"monthly" | "churn">("monthly");
  const [helpOpen, setHelpOpen] = useState(false);

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <HelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} content={helpContent} />
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">營運報表</h1>
        <button onClick={() => setHelpOpen(true)} className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50 hover:text-gray-700">
          <span>ℹ️</span> 說明
        </button>
      </div>

      <div className="mb-4 flex gap-1 border-b border-gray-200">
        {(
          [
            ["monthly", "月報表"],
            ["churn", "流失預警"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              tab === key
                ? "border-b-2 border-primary-600 text-primary-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "monthly" ? <MonthlyReportTab token={token} /> : <ChurnTab token={token} />}
    </div>
  );
}

/* ═══════════════════════════════════════════════
   Tab 1 — 月報表
   ═══════════════════════════════════════════════ */

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
  product_sales?: {
    total: number;
    count: number;
    by_payment_method: Record<string, number>;
  };
  session_type_breakdown: Record<string, { count: number; revenue: number }>;
  funding_breakdown: {
    self_pay_revenue: number;
    institution_revenue: number;
    institution_unpaid: number;
  };
  pnl: {
    gross_revenue: number;
    therapist_cost: number;
    clinic_gross: number;
    petty_cash_expense: number;
    net_income: number;
    cancelled_loss: number;
  };
  kpi: {
    cancel_rate: number;
    continuation_rate: number;
    active_therapists: number;
    unique_cases: number;
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
  appointment_stats: { booked: number; cancelled: number; executed: number };
}

const categoryLabels: Record<string, string> = {
  cleaning: "清潔費",
  supplies: "文具耗材",
  electricity: "電費",
  water: "水費",
  other: "其他",
};

const sessionTypeLabels: Record<string, string> = {
  in_person: "現場諮商",
  online: "線上諮商",
  outdoor: "外出服務",
};

function MonthlyReportTab({ token }: { token: string }) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [report, setReport] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchReport = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await clientFetch(`/reports/monthly?year=${year}&month=${month}`, token);
      setReport(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, year, month]);

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <select
          value={year}
          onChange={(e) => setYear(parseInt(e.target.value))}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
        >
          {[2025, 2026, 2027].map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
        <select
          value={month}
          onChange={(e) => setMonth(parseInt(e.target.value))}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
        >
          {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
            <option key={m} value={m}>
              {m} 月
            </option>
          ))}
        </select>
        <button
          onClick={fetchReport}
          disabled={loading}
          className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
        >
          {loading ? "產生中..." : "產生報表"}
        </button>
        <button
          onClick={() =>
            exportCsv(`/export/ledger?year=${year}&month=${month}`, token, `ledger_${year}_${month}.csv`)
          }
          className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
        >
          匯出 CSV
        </button>
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">{error}</div>}

      {!report ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-16 text-center text-gray-400">
          選擇年月後點擊「產生報表」
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="總營收" value={`$${report.summary.total_revenue.toLocaleString()}`} />
            <StatCard label="諮商次數" value={report.summary.session_count.toString()} />
            <StatCard label="心理師分潤" value={`$${report.summary.total_therapist_share.toLocaleString()}`} />
            <StatCard label="診所收入" value={`$${report.summary.total_clinic_share.toLocaleString()}`} />
          </div>

          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="已收/請款" value={report.summary.paid_count.toString()} color="green" />
            <StatCard label="未收/請款" value={report.summary.unpaid_count.toString()} color="red" />
            <StatCard label="零用金支出" value={`$${report.summary.petty_cash_total.toLocaleString()}`} />
            <StatCard label="取消預約" value={report.appointment_stats.cancelled.toString()} color="gray" />
          </div>

          <div>
            <h2 className="mb-3 text-lg font-semibold">損益摘要</h2>
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
                <PnlRow label="總營收" value={report.pnl.gross_revenue} />
                <PnlRow label="心理師成本" value={-report.pnl.therapist_cost} negative />
                <PnlRow label="診所毛利" value={report.pnl.clinic_gross} />
                <PnlRow
                  label="零用金支出"
                  value={report.pnl.petty_cash_expense}
                  negative={report.pnl.petty_cash_expense < 0}
                />
                <PnlRow label="淨收入" value={report.pnl.net_income} bold />
                <PnlRow label="取消損失" value={-report.pnl.cancelled_loss} negative />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div>
              <h2 className="mb-3 text-lg font-semibold">KPI 指標</h2>
              <div className="space-y-2 rounded-lg border border-gray-200 bg-white p-4">
                <KpiRow label="取消率" value={`${report.kpi.cancel_rate}%`} warn={report.kpi.cancel_rate > 15} />
                <KpiRow label="續診率" value={`${report.kpi.continuation_rate}%`} />
                <KpiRow label="活躍心理師" value={`${report.kpi.active_therapists} 位`} />
                <KpiRow label="本月個案數" value={`${report.kpi.unique_cases} 位`} />
              </div>
            </div>

            <div>
              <h2 className="mb-3 text-lg font-semibold">諮商類型分布</h2>
              <div className="space-y-2 rounded-lg border border-gray-200 bg-white p-4">
                {Object.entries(report.session_type_breakdown).map(([type, data]) => (
                  <div key={type} className="flex items-center justify-between">
                    <span className="text-sm text-gray-600">{sessionTypeLabels[type] ?? type}</span>
                    <span className="text-sm font-medium">
                      {data.count} 次 · ${data.revenue.toLocaleString()}
                    </span>
                  </div>
                ))}
                {Object.keys(report.session_type_breakdown).length === 0 && (
                  <p className="text-sm text-gray-400">無資料</p>
                )}
              </div>
            </div>

            <div>
              <h2 className="mb-3 text-lg font-semibold">金流來源分析</h2>
              <div className="space-y-2 rounded-lg border border-gray-200 bg-white p-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">自費收入</span>
                  <span className="text-sm font-medium">
                    ${report.funding_breakdown.self_pay_revenue.toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">機構收入</span>
                  <span className="text-sm font-medium">
                    ${report.funding_breakdown.institution_revenue.toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-red-600">機構待請款</span>
                  <span className="text-sm font-medium text-red-600">
                    ${report.funding_breakdown.institution_unpaid.toLocaleString()}
                  </span>
                </div>
              </div>
            </div>

            <div>
              <h2 className="mb-3 text-lg font-semibold">其他商品販售</h2>
              <div className="space-y-2 rounded-lg border border-gray-200 bg-white p-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">銷售總額</span>
                  <span className="text-sm font-medium">
                    ${(report.product_sales?.total ?? 0).toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">筆數</span>
                  <span className="text-sm font-medium">{report.product_sales?.count ?? 0}</span>
                </div>
                {Object.entries(report.product_sales?.by_payment_method ?? {}).map(([m, v]) => (
                  <div key={m} className="flex items-center justify-between">
                    <span className="text-sm text-gray-500">{m === "cash" ? "現金" : m === "transfer" ? "匯款" : m}</span>
                    <span className="text-sm text-gray-500">${v.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

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

          {Object.keys(report.petty_cash_by_category).length > 0 && (
            <div>
              <h2 className="mb-3 text-lg font-semibold">零用金分類</h2>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                {Object.entries(report.petty_cash_by_category).map(([cat, amt]) => (
                  <div key={cat} className="rounded-lg border border-gray-200 p-3">
                    <div className="text-xs text-gray-500">{categoryLabels[cat] ?? cat}</div>
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

/* ═══════════════════════════════════════════════
   Tab 2 — 流失預警
   ═══════════════════════════════════════════════ */

interface ChurnCase {
  case_id: number;
  case_name: string;
  therapist_name: string | null;
  phone: string | null;
  status: string;
  last_appointment_date: string | null;
  days_since_last: number | null;
  funding_source: string;
}

function ChurnTab({ token }: { token: string }) {
  const [days, setDays] = useState(30);
  const [cases, setCases] = useState<ChurnCase[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await clientFetch(`/churn?inactive_days=${days}`, token);
      setCases(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token, days]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <label className="text-sm text-gray-500">超過</label>
        <select
          value={days}
          onChange={(e) => setDays(parseInt(e.target.value))}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
        >
          <option value={14}>14 天</option>
          <option value={21}>21 天</option>
          <option value={30}>30 天</option>
          <option value={45}>45 天</option>
          <option value={60}>60 天</option>
          <option value={90}>90 天</option>
        </select>
        <span className="text-sm text-gray-500">未預約的活躍個案</span>
      </div>

      {loading ? (
        <p className="text-gray-400">載入中...</p>
      ) : cases.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-16 text-center text-gray-400">
          目前無流失預警個案
        </div>
      ) : (
        <>
          <div className="mb-4 text-sm text-gray-500">共 {cases.length} 位個案需關注</div>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-4 py-3">個案姓名</th>
                  <th className="px-4 py-3">負責心理師</th>
                  <th className="px-4 py-3">電話</th>
                  <th className="px-4 py-3">來源</th>
                  <th className="px-4 py-3">最後預約</th>
                  <th className="px-4 py-3">已過天數</th>
                  <th className="px-4 py-3">狀態</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {cases.map((c) => (
                  <tr key={c.case_id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium">{c.case_name}</td>
                    <td className="px-4 py-3">{c.therapist_name ?? "-"}</td>
                    <td className="px-4 py-3 text-xs">{c.phone ?? "-"}</td>
                    <td className="px-4 py-3 text-xs">
                      {c.funding_source === "institution" ? "機構" : "自費"}
                    </td>
                    <td className="px-4 py-3">{c.last_appointment_date ?? "無紀錄"}</td>
                    <td className="px-4 py-3">
                      {c.days_since_last !== null ? (
                        <span
                          className={`font-medium ${c.days_since_last > 60 ? "text-red-600" : c.days_since_last > 30 ? "text-amber-600" : "text-gray-900"}`}
                        >
                          {c.days_since_last} 天
                        </span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs">{c.status === "initial" ? "初談" : "持續中"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

/* ───── helper components ───── */

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
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

function PnlRow({
  label,
  value,
  negative,
  bold,
}: {
  label: string;
  value: number;
  negative?: boolean;
  bold?: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className={`text-sm ${bold ? "font-semibold" : "text-gray-600"}`}>{label}</span>
      <span className={`text-sm ${bold ? "font-bold text-gray-900" : ""} ${negative ? "text-red-600" : ""}`}>
        {value < 0 ? "-" : ""}${Math.abs(value).toLocaleString()}
      </span>
    </div>
  );
}

function KpiRow({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-gray-600">{label}</span>
      <span className={`text-sm font-medium ${warn ? "text-red-600" : "text-gray-900"}`}>{value}</span>
    </div>
  );
}
