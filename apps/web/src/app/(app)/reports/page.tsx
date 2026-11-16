"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import { AnalyticsView } from "@/components/analytics-view";
import HelpDrawer, { type HelpContent } from "@/components/HelpDrawer";
import {
  Chart as ChartJS,
  ArcElement,
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
  Title,
} from "chart.js";
import { Bar, Doughnut } from "react-chartjs-2";

ChartJS.register(ArcElement, BarElement, CategoryScale, LinearScale, Tooltip, Legend, Title);

const helpContent: HelpContent = {
  title: "營運報表",
  guideId: "reports",
  overview: "整合預約、媒合與個案資料，呈現關鍵指標、進案統計、診間使用率、心理師負荷與流失預警。系統不提供收入、酬勞或損益報表。",
  sections: [
    {
      heading: "進案統計",
      type: "steps",
      items: [
        "進入「營運報表 → 進案統計」",
        "選擇要查看的年月",
        "點「產生報表」查看該月新進案概況",
        "可匯出 Excel 供進一步分析",
      ],
    },
    {
      heading: "主要指標說明",
      type: "text",
      items: [
        "新進案定義：已轉正式（有正式案號）且完成第一次諮商的個案，以第一次諮商月份計算",
        "兒青定義：第一次諮商時未滿 18 歲",
        "流失預警：進行中個案超過指定天數沒有預約",
      ],
    },
  ],
};

/* ───── main page ───── */

export default function ReportsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [outerTab, setOuterTab] = useState<"analytics" | "operations" | "charts">("analytics");
  const [helpOpen, setHelpOpen] = useState(false);

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <HelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} guideId="reports" />
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">報表</h1>
        <button onClick={() => setHelpOpen(true)} className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50 hover:text-gray-700">
          <span>ℹ️</span> 說明
        </button>
      </div>

      {/* Outer tabs */}
      <div className="mb-4 flex gap-1 border-b border-gray-200">
        {(
          [
            ["analytics", "🎯 關鍵指標"],
            ["operations", "📊 營運報表"],
            ["charts", "📈 圖表"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setOuterTab(key)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors ${
              outerTab === key
                ? "border-b-2 border-primary-600 text-primary-700"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {outerTab === "analytics" && <AnalyticsView token={token} />}
      {outerTab === "operations" && <OperationsSection token={token} />}
      {outerTab === "charts" && <ChartsView token={token} />}
    </div>
  );
}

/* ═══════════════════════════════════════════════
   圖表總覽
   ═══════════════════════════════════════════════ */

const CHART_OPTIONS = [
  { id: "intake_source",    label: "進案來源分布",   source: "intake"    },
  { id: "intake_therapist", label: "各心理師進案量", source: "intake"    },
  { id: "intake_inst",      label: "各機構進案量",   source: "intake"    },
  { id: "room_usage",       label: "診間使用率",     source: "room"      },
  { id: "hourly",           label: "預約時段分布",   source: "room"      },
  { id: "therapist_cases",  label: "心理師接案量",   source: "therapist" },
] as const;

type ChartId = typeof CHART_OPTIONS[number]["id"];
type DataSource = typeof CHART_OPTIONS[number]["source"];

const PALETTE = [
  "#6366f1","#22c55e","#f59e0b","#ef4444","#14b8a6",
  "#a855f7","#ec4899","#0ea5e9","#f97316","#84cc16",
  "#64748b","#06b6d4","#d946ef","#eab308","#10b981",
];

function ChartsView({ token }: { token: string }) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [chartId, setChartId] = useState<ChartId>("intake_source");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // cached data per source
  const [intakeData, setIntakeData] = useState<IntakeData | null>(null);
  const [roomData, setRoomData] = useState<RoomUtilizationData | null>(null);
  const [therapistData, setTherapistData] = useState<TherapistLoadData | null>(null);

  const chartRef = useRef<ChartJS<"bar"> | ChartJS<"doughnut"> | any>(null);

  const currentSource = CHART_OPTIONS.find((o) => o.id === chartId)?.source ?? "intake";

  const fetchSource = useCallback(async (src: DataSource) => {
    const qs = `?year=${year}&month=${month}`;
    const url: Record<DataSource, string> = {
      intake:    `/reports/intake${qs}`,
      room:      `/reports/room-utilization${qs}`,
      therapist: `/reports/therapist-load${qs}`,
    };
    setLoading(true);
    setError("");
    try {
      const d = await clientFetch(url[src], token);
      if (src === "intake")    setIntakeData(d);
      if (src === "room")      setRoomData(d);
      if (src === "therapist") setTherapistData(d);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, year, month]);

  // fetch current source on mount / when year/month/chartId changes
  useEffect(() => { fetchSource(currentSource); }, [fetchSource, currentSource]);

  const handleDownload = () => {
    const chart = chartRef.current;
    if (!chart) return;
    const url = chart.toBase64Image("image/png", 1.0);
    const label = CHART_OPTIONS.find((o) => o.id === chartId)?.label ?? "chart";
    const a = document.createElement("a");
    a.href = url;
    a.download = `${label}_${year}${String(month).padStart(2, "0")}.png`;
    a.click();
  };

  // ── build chart config ──────────────────────────────────────────────────
  type ChartConfig = { type: "bar" | "doughnut"; data: any; options: any } | null;

  const chartConfig = ((): ChartConfig => {
    const baseBar = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        title: { display: false },
        tooltip: { callbacks: {} },
      },
      scales: {
        y: { beginAtZero: true, ticks: { precision: 0 } },
      },
    };

    if (chartId === "intake_source" && intakeData) {
      const s = intakeData.summary;
      return {
        type: "doughnut",
        data: {
          labels: ["機構成人", "機構兒青", "自費成人", "自費兒青"],
          datasets: [{ data: [s.institution_adult, s.institution_child, s.self_pay_adult, s.self_pay_child], backgroundColor: PALETTE.slice(0, 4), borderWidth: 2 }],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom" } } },
      };
    }

    if (chartId === "intake_therapist" && intakeData) {
      const rows = intakeData.by_therapist.slice(0, 15);
      return {
        type: "bar",
        data: {
          labels: rows.map((r) => r.therapist_name),
          datasets: [
            { label: "機構成人", data: rows.map((r) => r.institution_adult), backgroundColor: "#6366f1" },
            { label: "機構兒青", data: rows.map((r) => r.institution_child), backgroundColor: "#a855f7" },
            { label: "自費成人", data: rows.map((r) => r.self_pay_adult), backgroundColor: "#22c55e" },
            { label: "自費兒青", data: rows.map((r) => r.self_pay_child), backgroundColor: "#86efac" },
          ],
        },
        options: { ...baseBar, plugins: { ...baseBar.plugins, legend: { display: true, position: "top" } }, scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } } } },
      };
    }

    if (chartId === "intake_inst" && intakeData) {
      const rows = intakeData.by_institution;
      if (rows.length === 0) return null;
      return {
        type: "bar",
        data: {
          labels: rows.map((r) => r.institution_name),
          datasets: [
            { label: "成人", data: rows.map((r) => r.adult), backgroundColor: "#6366f1" },
            { label: "兒青", data: rows.map((r) => r.child), backgroundColor: "#f59e0b" },
          ],
        },
        options: { ...baseBar, plugins: { ...baseBar.plugins, legend: { display: true, position: "top" } }, scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } } } },
      };
    }

    if (chartId === "room_usage" && roomData) {
      const rooms = roomData.rooms.filter((r) => r.appointment_count > 0);
      return {
        type: "bar",
        data: {
          labels: rooms.map((r) => r.room_name),
          datasets: [{ label: "使用時數（h）", data: rooms.map((r) => r.used_hours), backgroundColor: PALETTE.slice(0, rooms.length), borderRadius: 4 }],
        },
        options: { ...baseBar, scales: { y: { beginAtZero: true, title: { display: true, text: "小時" } } } },
      };
    }

    if (chartId === "hourly" && roomData) {
      const dist = roomData.hourly_distribution;
      const labels = Object.keys(dist).map((h) => `${h}:00`);
      const vals = Object.values(dist);
      return {
        type: "bar",
        data: {
          labels,
          datasets: [{ label: "預約次數", data: vals, backgroundColor: "#6366f1", borderRadius: 4 }],
        },
        options: { ...baseBar, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
      };
    }

    if (chartId === "therapist_cases" && therapistData) {
      const rows = therapistData.therapists.filter((t) => t.active_cases > 0);
      return {
        type: "bar",
        data: {
          labels: rows.map((t) => t.therapist_name),
          datasets: [{ label: "進行中個案數", data: rows.map((t) => t.active_cases), backgroundColor: "#22c55e", borderRadius: 4 }],
        },
        options: { ...baseBar },
      };
    }

    return null;
  })();

  const isReady = !loading && chartConfig !== null;

  return (
    <div>
      {/* Controls */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select value={year} onChange={(e) => setYear(parseInt(e.target.value))} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
          {[2024, 2025, 2026, 2027].map((y) => <option key={y} value={y}>{y} 年</option>)}
        </select>
        <select value={month} onChange={(e) => setMonth(parseInt(e.target.value))} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
          {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => <option key={m} value={m}>{m} 月</option>)}
        </select>
        {isReady && (
          <button
            onClick={handleDownload}
            className="ml-auto flex items-center gap-1.5 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
          >
            ⬇️ 下載圖片
          </button>
        )}
      </div>

      {/* Chart type chips */}
      <div className="mb-5 flex flex-wrap gap-2">
        {CHART_OPTIONS.map((opt) => (
          <button
            key={opt.id}
            onClick={() => setChartId(opt.id)}
            className={`rounded-full px-3.5 py-1.5 text-xs font-medium transition-colors ${
              chartId === opt.id
                ? "bg-primary-600 text-white shadow-sm"
                : "border border-gray-200 bg-white text-gray-600 hover:border-primary-300 hover:text-primary-700"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">{error}</div>}

      {/* Chart area */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h3 className="mb-4 text-base font-semibold text-gray-700">
          {CHART_OPTIONS.find((o) => o.id === chartId)?.label} — {year} 年 {month} 月
        </h3>

        {loading ? (
          <div className="flex h-72 items-center justify-center text-gray-400">載入中...</div>
        ) : !chartConfig ? (
          <div className="flex h-72 items-center justify-center text-gray-400">本月無資料</div>
        ) : (
          <div className="relative h-80">
            {chartConfig.type === "doughnut" ? (
              <Doughnut ref={chartRef} data={chartConfig.data} options={chartConfig.options} />
            ) : (
              <Bar ref={chartRef} data={chartConfig.data} options={chartConfig.options} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════
   營運報表 section
   ═══════════════════════════════════════════════ */

function OperationsSection({ token }: { token: string }) {
  const [tab, setTab] = useState<"intake" | "space" | "therapist_load" | "churn">("intake");

  return (
    <div>
      <div className="mb-4 flex gap-1 border-b border-gray-100">
        {(
          [
            ["intake", "進案統計"],
            ["space", "空間利用率"],
            ["therapist_load", "心理師接案量"],
            ["churn", "流失預警"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              tab === key
                ? "border-b-2 border-primary-500 text-primary-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "intake" && <IntakeStatsTab token={token} />}
      {tab === "space" && <RoomUtilizationTab token={token} />}
      {tab === "therapist_load" && <TherapistLoadTab token={token} />}
      {tab === "churn" && <ChurnTab token={token} />}
    </div>
  );
}

/* ═══════════════════════════════════════════════
   進案統計 Tab
   ═══════════════════════════════════════════════ */

interface IntakeSummary {
  institution_adult: number;
  institution_child: number;
  self_pay_adult: number;
  self_pay_child: number;
  total: number;
}

interface IntakeTherapistRow {
  therapist_name: string;
  institution_adult: number;
  institution_child: number;
  self_pay_adult: number;
  self_pay_child: number;
  designated_institution_adult: number;
  designated_institution_child: number;
  designated_self_pay_adult: number;
  designated_self_pay_child: number;
  total: number;
}

interface IntakeInstitutionRow {
  institution_name: string;
  adult: number;
  child: number;
  total: number;
}

interface IntakeCaseRow {
  case_number: string | null;
  name: string;
  funding_source: string;
  age_group: string;
  therapist_name: string;
  institution_name: string | null;
  is_designated: boolean;
  first_session_date: string | null;
}

interface IntakeData {
  year: number;
  month: number;
  summary: IntakeSummary;
  by_therapist: IntakeTherapistRow[];
  by_institution: IntakeInstitutionRow[];
  cases: IntakeCaseRow[];
}

function IntakeStatsTab({ token }: { token: string }) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data, setData] = useState<IntakeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const d = await clientFetch(`/reports/intake?year=${year}&month=${month}`, token);
      setData(d);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, year, month]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const res = await fetch(
        `${apiBase}/reports/intake/export?year=${year}&month=${month}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) throw new Error("匯出失敗");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `intake_${year}${String(month).padStart(2, "0")}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      alert(e.message);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div>
      {/* Controls */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select
          value={year}
          onChange={(e) => setYear(parseInt(e.target.value))}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
        >
          {[2024, 2025, 2026, 2027].map((y) => (
            <option key={y} value={y}>{y} 年</option>
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
          onClick={fetchData}
          disabled={loading}
          className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
        >
          {loading ? "載入中..." : "重新查詢"}
        </button>
        {data && (
          <button
            onClick={handleExport}
            disabled={exporting}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-50"
          >
            {exporting ? "匯出中..." : "📥 匯出 Excel"}
          </button>
        )}
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">{error}</div>}

      {loading ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-16 text-center text-gray-400">
          載入中...
        </div>
      ) : !data ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-16 text-center text-gray-400">
          無資料
        </div>
      ) : (
        <div className="space-y-6">
          {/* Summary cards */}
          <div>
            <h2 className="mb-3 text-base font-semibold text-gray-700">
              {data.year} 年 {data.month} 月 新進案摘要（共 {data.summary.total} 案）
            </h2>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <IntakeSummaryCard
                label="機構成人"
                value={data.summary.institution_adult}
                color="blue"
              />
              <IntakeSummaryCard
                label="機構兒青"
                value={data.summary.institution_child}
                color="blue"
              />
              <IntakeSummaryCard
                label="自費成人"
                value={data.summary.self_pay_adult}
                color="emerald"
              />
              <IntakeSummaryCard
                label="自費兒青"
                value={data.summary.self_pay_child}
                color="emerald"
              />
            </div>
          </div>

          {/* By therapist */}
          <div>
            <h2 className="mb-3 text-base font-semibold text-gray-700">各心理師進案量</h2>
            {data.by_therapist.length === 0 ? (
              <p className="text-sm text-gray-400">無資料</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-gray-200">
                <table className="w-full text-left text-sm">
                  <thead className="bg-gray-50 text-xs text-gray-500">
                    <tr>
                      <th className="px-3 py-2.5 font-semibold">心理師</th>
                      <th className="px-3 py-2.5 text-center font-semibold" colSpan={4}>進案數</th>
                      <th className="px-3 py-2.5 text-center font-semibold" colSpan={4}>其中 — 指定</th>
                      <th className="px-3 py-2.5 text-right font-semibold">合計</th>
                    </tr>
                    <tr className="text-xs text-gray-400">
                      <th className="px-3 pb-2"></th>
                      <th className="px-2 pb-2 text-center">機構成人</th>
                      <th className="px-2 pb-2 text-center">機構兒青</th>
                      <th className="px-2 pb-2 text-center">自費成人</th>
                      <th className="px-2 pb-2 text-center">自費兒青</th>
                      <th className="px-2 pb-2 text-center">機構成人</th>
                      <th className="px-2 pb-2 text-center">機構兒青</th>
                      <th className="px-2 pb-2 text-center">自費成人</th>
                      <th className="px-2 pb-2 text-center">自費兒青</th>
                      <th className="px-3 pb-2 text-right"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {data.by_therapist.map((row, idx) => (
                      <tr key={idx} className="hover:bg-gray-50">
                        <td className="px-3 py-2 font-medium">{row.therapist_name}</td>
                        <td className="px-2 py-2 text-center">{row.institution_adult || "—"}</td>
                        <td className="px-2 py-2 text-center">{row.institution_child || "—"}</td>
                        <td className="px-2 py-2 text-center">{row.self_pay_adult || "—"}</td>
                        <td className="px-2 py-2 text-center">{row.self_pay_child || "—"}</td>
                        <td className="px-2 py-2 text-center text-violet-600">{row.designated_institution_adult || "—"}</td>
                        <td className="px-2 py-2 text-center text-violet-600">{row.designated_institution_child || "—"}</td>
                        <td className="px-2 py-2 text-center text-violet-600">{row.designated_self_pay_adult || "—"}</td>
                        <td className="px-2 py-2 text-center text-violet-600">{row.designated_self_pay_child || "—"}</td>
                        <td className="px-3 py-2 text-right font-bold">{row.total}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* By institution */}
          {data.by_institution.length > 0 && (
            <div>
              <h2 className="mb-3 text-base font-semibold text-gray-700">各機構進案量</h2>
              <div className="overflow-x-auto rounded-lg border border-gray-200">
                <table className="w-full text-left text-sm">
                  <thead className="bg-gray-50 text-xs text-gray-500">
                    <tr>
                      <th className="px-4 py-2.5 font-semibold">機構名稱</th>
                      <th className="px-4 py-2.5 text-center font-semibold">成人</th>
                      <th className="px-4 py-2.5 text-center font-semibold">兒青（&lt;18）</th>
                      <th className="px-4 py-2.5 text-right font-semibold">合計</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {data.by_institution.map((row, idx) => (
                      <tr key={idx} className="hover:bg-gray-50">
                        <td className="px-4 py-2.5 font-medium">{row.institution_name}</td>
                        <td className="px-4 py-2.5 text-center">{row.adult}</td>
                        <td className="px-4 py-2.5 text-center">{row.child}</td>
                        <td className="px-4 py-2.5 text-right font-bold">{row.total}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Case list */}
          {data.cases.length > 0 && (
            <div>
              <h2 className="mb-3 text-base font-semibold text-gray-700">新進個案清單</h2>
              <div className="overflow-x-auto rounded-lg border border-gray-200">
                <table className="w-full text-left text-sm">
                  <thead className="bg-gray-50 text-xs text-gray-500">
                    <tr>
                      <th className="px-3 py-2.5 font-semibold">案號</th>
                      <th className="px-3 py-2.5 font-semibold">姓名</th>
                      <th className="px-3 py-2.5 font-semibold">來源</th>
                      <th className="px-3 py-2.5 font-semibold">年齡層</th>
                      <th className="px-3 py-2.5 font-semibold">心理師</th>
                      <th className="px-3 py-2.5 font-semibold">機構</th>
                      <th className="px-3 py-2.5 font-semibold">指定</th>
                      <th className="px-3 py-2.5 font-semibold">首次諮商</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {data.cases.map((c, idx) => (
                      <tr key={idx} className="hover:bg-gray-50">
                        <td className="px-3 py-2 font-mono text-xs text-gray-500">{c.case_number ?? "—"}</td>
                        <td className="px-3 py-2 font-medium">{c.name}</td>
                        <td className="px-3 py-2 text-xs">
                          <span className={`rounded px-1.5 py-0.5 ${c.funding_source === "institution" ? "bg-blue-100 text-blue-700" : "bg-emerald-100 text-emerald-700"}`}>
                            {c.funding_source === "institution" ? "機構" : "自費"}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-xs">
                          <span className={`rounded px-1.5 py-0.5 ${c.age_group === "child" ? "bg-orange-100 text-orange-700" : "bg-gray-100 text-gray-600"}`}>
                            {c.age_group === "child" ? "兒青" : "成人"}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-sm">{c.therapist_name}</td>
                        <td className="px-3 py-2 text-sm text-gray-500">{c.institution_name ?? "—"}</td>
                        <td className="px-3 py-2 text-center">
                          {c.is_designated ? <span className="text-violet-600" title="指定心理師">●</span> : <span className="text-gray-200">●</span>}
                        </td>
                        <td className="px-3 py-2 text-xs text-gray-500">{c.first_session_date ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function IntakeSummaryCard({ label, value, color }: { label: string; value: number; color: "blue" | "emerald" }) {
  const colors = {
    blue: "bg-blue-50 border-blue-200 text-blue-700",
    emerald: "bg-emerald-50 border-emerald-200 text-emerald-700",
  };
  return (
    <div className={`rounded-lg border p-4 ${colors[color]}`}>
      <div className="text-xs font-medium opacity-75">{label}</div>
      <div className="mt-1 text-3xl font-bold">{value}</div>
      <div className="text-xs opacity-60">案</div>
    </div>
  );
}

/* ═══════════════════════════════════════════════
   空間利用率 Tab
   ═══════════════════════════════════════════════ */

interface RoomStat {
  room_id: number;
  room_name: string;
  floor: number;
  room_code: string;
  appointment_count: number;
  used_hours: number;
}

interface FloorStat {
  floor: number;
  room_count: number;
  total_used_hours: number;
  total_appointments: number;
}

interface RoomUtilizationData {
  year: number;
  month: number;
  total_appointments: number;
  rooms: RoomStat[];
  by_floor: FloorStat[];
  hourly_distribution: Record<string, number>;
}

function RoomUtilizationTab({ token }: { token: string }) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data, setData] = useState<RoomUtilizationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const d = await clientFetch(`/reports/room-utilization?year=${year}&month=${month}`, token);
      setData(d);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, year, month]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const maxHours = data ? Math.max(...data.rooms.map((r) => r.used_hours), 1) : 1;
  const maxHourly = data ? Math.max(...Object.values(data.hourly_distribution), 1) : 1;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select value={year} onChange={(e) => setYear(parseInt(e.target.value))} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
          {[2024, 2025, 2026, 2027].map((y) => <option key={y} value={y}>{y} 年</option>)}
        </select>
        <select value={month} onChange={(e) => setMonth(parseInt(e.target.value))} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
          {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => <option key={m} value={m}>{m} 月</option>)}
        </select>
        <button onClick={fetchData} disabled={loading} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">
          {loading ? "載入中..." : "重新查詢"}
        </button>
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">{error}</div>}

      {loading ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-16 text-center text-gray-400">載入中...</div>
      ) : !data ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-16 text-center text-gray-400">無資料</div>
      ) : (
        <div className="space-y-6">
          {/* Summary */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="text-xs text-gray-500">本月預約總數</div>
              <div className="mt-1 text-2xl font-bold text-gray-900">{data.total_appointments}</div>
              <div className="text-xs text-gray-400">次</div>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="text-xs text-gray-500">使用診間數</div>
              <div className="mt-1 text-2xl font-bold text-gray-900">
                {data.rooms.filter((r) => r.appointment_count > 0).length}
              </div>
              <div className="text-xs text-gray-400">/ {data.rooms.length} 間</div>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="text-xs text-gray-500">總使用時數</div>
              <div className="mt-1 text-2xl font-bold text-gray-900">
                {data.rooms.reduce((s, r) => s + r.used_hours, 0).toFixed(1)}
              </div>
              <div className="text-xs text-gray-400">小時</div>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="text-xs text-gray-500">最忙時段</div>
              <div className="mt-1 text-2xl font-bold text-gray-900">
                {Object.entries(data.hourly_distribution).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "—"}:00
              </div>
              <div className="text-xs text-gray-400">點</div>
            </div>
          </div>

          {/* Room table */}
          <div>
            <h2 className="mb-3 text-base font-semibold text-gray-700">各診間使用狀況</h2>
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-50 text-xs text-gray-500">
                  <tr>
                    <th className="px-4 py-2.5 font-semibold">樓層</th>
                    <th className="px-4 py-2.5 font-semibold">診間</th>
                    <th className="px-4 py-2.5 text-right font-semibold">預約次數</th>
                    <th className="px-4 py-2.5 text-right font-semibold">使用時數</th>
                    <th className="px-4 py-2.5 font-semibold">使用比例</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {data.rooms.map((r) => (
                    <tr key={r.room_id} className="hover:bg-gray-50">
                      <td className="px-4 py-2.5 text-gray-500">{r.floor}F</td>
                      <td className="px-4 py-2.5 font-medium">
                        {r.room_name}
                        <span className="ml-1.5 text-xs text-gray-400">{r.room_code}</span>
                      </td>
                      <td className="px-4 py-2.5 text-right">{r.appointment_count}</td>
                      <td className="px-4 py-2.5 text-right">{r.used_hours}h</td>
                      <td className="px-4 py-2.5 w-40">
                        <div className="flex items-center gap-2">
                          <div className="h-2 flex-1 rounded-full bg-gray-100">
                            <div
                              className="h-2 rounded-full bg-primary-500"
                              style={{ width: `${Math.round((r.used_hours / maxHours) * 100)}%` }}
                            />
                          </div>
                          <span className="w-8 text-right text-xs text-gray-500">
                            {Math.round((r.used_hours / maxHours) * 100)}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* By floor */}
          {data.by_floor.length > 0 && (
            <div>
              <h2 className="mb-3 text-base font-semibold text-gray-700">各樓層彙總</h2>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                {data.by_floor.map((f) => (
                  <div key={f.floor} className="rounded-lg border border-gray-200 bg-white p-4">
                    <div className="text-sm font-semibold text-gray-700">{f.floor}F</div>
                    <div className="mt-2 space-y-1">
                      <div className="flex justify-between text-xs text-gray-500">
                        <span>診間數</span><span className="font-medium text-gray-800">{f.room_count} 間</span>
                      </div>
                      <div className="flex justify-between text-xs text-gray-500">
                        <span>預約次數</span><span className="font-medium text-gray-800">{f.total_appointments} 次</span>
                      </div>
                      <div className="flex justify-between text-xs text-gray-500">
                        <span>使用時數</span><span className="font-medium text-gray-800">{f.total_used_hours}h</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Hourly distribution */}
          <div>
            <h2 className="mb-3 text-base font-semibold text-gray-700">預約時段分布</h2>
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="flex items-end gap-1 h-24">
                {Object.entries(data.hourly_distribution).map(([h, cnt]) => (
                  <div key={h} className="flex flex-1 flex-col items-center gap-1">
                    <div className="w-full flex flex-col justify-end" style={{ height: "80px" }}>
                      <div
                        className={`w-full rounded-t ${cnt > 0 ? "bg-primary-400" : "bg-gray-100"}`}
                        style={{ height: `${Math.max(2, Math.round((cnt / maxHourly) * 76))}px` }}
                        title={`${h}:00 — ${cnt} 次`}
                      />
                    </div>
                    <span className="text-xs text-gray-400">{h}</span>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-xs text-gray-400 text-center">預約開始時間（小時）</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════
   心理師接案量 Tab
   ═══════════════════════════════════════════════ */

interface TherapistLoadRow {
  therapist_id: number;
  therapist_name: string;
  user_code: string;
  active_cases: number;
  sessions_this_month: number;
  upcoming_appointments: number;
}

interface TherapistLoadData {
  year: number;
  month: number;
  summary: {
    total_active_cases: number;
    total_sessions: number;
    active_therapist_count: number;
  };
  therapists: TherapistLoadRow[];
}

function TherapistLoadTab({ token }: { token: string }) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data, setData] = useState<TherapistLoadData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const d = await clientFetch(`/reports/therapist-load?year=${year}&month=${month}`, token);
      setData(d);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, year, month]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const maxCases = data ? Math.max(...data.therapists.map((t) => t.active_cases), 1) : 1;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select value={year} onChange={(e) => setYear(parseInt(e.target.value))} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
          {[2024, 2025, 2026, 2027].map((y) => <option key={y} value={y}>{y} 年</option>)}
        </select>
        <select value={month} onChange={(e) => setMonth(parseInt(e.target.value))} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
          {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => <option key={m} value={m}>{m} 月</option>)}
        </select>
        <button onClick={fetchData} disabled={loading} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">
          {loading ? "載入中..." : "重新查詢"}
        </button>
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">{error}</div>}

      {loading ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-16 text-center text-gray-400">載入中...</div>
      ) : !data ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-16 text-center text-gray-400">無資料</div>
      ) : (
        <div className="space-y-6">
          {/* Summary cards */}
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="text-xs text-gray-500">進行中個案總數</div>
              <div className="mt-1 text-2xl font-bold text-gray-900">{data.summary.total_active_cases}</div>
              <div className="text-xs text-gray-400">位</div>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="text-xs text-gray-500">{data.month} 月諮商總次數</div>
              <div className="mt-1 text-2xl font-bold text-gray-900">{data.summary.total_sessions}</div>
              <div className="text-xs text-gray-400">次</div>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="text-xs text-gray-500">有接案心理師</div>
              <div className="mt-1 text-2xl font-bold text-gray-900">{data.summary.active_therapist_count}</div>
              <div className="text-xs text-gray-400">/ {data.therapists.length} 位</div>
            </div>
          </div>

          {/* Therapist table */}
          <div>
            <h2 className="mb-3 text-base font-semibold text-gray-700">各心理師接案狀況</h2>
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-50 text-xs text-gray-500">
                  <tr>
                    <th className="px-4 py-2.5 font-semibold">心理師</th>
                    <th className="px-4 py-2.5 text-right font-semibold">進行中個案</th>
                    <th className="px-4 py-2.5 font-semibold">接案量</th>
                    <th className="px-4 py-2.5 text-right font-semibold">{data.month} 月諮商</th>
                    <th className="px-4 py-2.5 text-right font-semibold">待執行預約</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {data.therapists.map((t) => (
                    <tr key={t.therapist_id} className="hover:bg-gray-50">
                      <td className="px-4 py-2.5">
                        <div className="font-medium">{t.therapist_name}</div>
                        <div className="text-xs text-gray-400">{t.user_code}</div>
                      </td>
                      <td className="px-4 py-2.5 text-right font-bold">
                        {t.active_cases}
                      </td>
                      <td className="px-4 py-2.5 w-32">
                        <div className="flex items-center gap-2">
                          <div className="h-2 flex-1 rounded-full bg-gray-100">
                            <div
                              className="h-2 rounded-full bg-emerald-400"
                              style={{ width: `${Math.round((t.active_cases / maxCases) * 100)}%` }}
                            />
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-right">{t.sessions_this_month}</td>
                      <td className="px-4 py-2.5 text-right">
                        {t.upcoming_appointments > 0 ? (
                          <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
                            {t.upcoming_appointments}
                          </span>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════
   流失預警
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

