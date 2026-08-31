"use client";

import { useCallback, useEffect, useState } from "react";
import { clientFetch } from "@/lib/client-api";

interface Data {
  period: { start: string; end: string; days: number };
  metrics: Record<string, number | null>;
  adherence: { label: string; count: number }[];
  sources: { label: string; count: number; percent: number }[];
  top_complaints: { label: string; count: number }[];
  time_slots: { morning: number; afternoon: number; evening: number };
  caveats: Record<string, string>;
  scope?: string;
}

const PERIODS: [string, string][] = [["week", "週"], ["month", "月"], ["quarter", "季"]];

function Metric({
  label,
  value,
  suffix = "%",
  sub,
  caveat,
}: {
  label: string;
  value: number | null;
  suffix?: string;
  sub?: string;
  caveat?: string;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white px-4 py-3">
      <div className="flex items-center gap-1 text-xs text-gray-500">
        {label}
        {caveat && (
          <span className="cursor-help text-amber-500" title={caveat}>ⓘ</span>
        )}
      </div>
      <div className="text-2xl font-semibold">
        {value == null ? <span className="text-gray-300">—</span> : <>{value}<span className="text-base">{suffix}</span></>}
      </div>
      {sub && <div className="mt-0.5 text-xs text-gray-400">{sub}</div>}
    </div>
  );
}

function Bars({ rows, total }: { rows: { label: string; count: number }[]; total: number }) {
  if (rows.length === 0) return <p className="py-6 text-center text-sm text-gray-400">無資料</p>;
  return (
    <div className="space-y-2.5">
      {rows.map((r) => (
        <div key={r.label}>
          <div className="mb-1 flex text-xs">
            <span>{r.label}</span>
            <span className="ml-auto font-medium tabular-nums">
              {r.count}
              {total > 0 && <span className="ml-1 text-gray-400">{Math.round((r.count / total) * 100)}%</span>}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-gray-100">
            <div className="h-full bg-primary-500" style={{ width: total > 0 ? `${(r.count / total) * 100}%` : "0%" }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function AnalyticsView({ token, mine = false }: { token: string; mine?: boolean }) {
  const [period, setPeriod] = useState("month");
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setData(await clientFetch(`/analytics${mine ? "/mine" : ""}?period=${period}`, token));
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, [token, period, mine]);

  useEffect(() => { load(); }, [load]);

  if (error) return <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>;
  if (!data) return <p className="text-gray-400">載入中...</p>;

  const m = data.metrics;
  const adherenceTotal = data.adherence.reduce((s, x) => s + x.count, 0);
  const slotRows = [
    { label: "上午 08–12", count: data.time_slots.morning },
    { label: "下午 12–18", count: data.time_slots.afternoon },
    { label: "晚上 18–22", count: data.time_slots.evening },
  ];
  const slotTotal = slotRows.reduce((s, x) => s + x.count, 0);

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        {PERIODS.map(([k, label]) => (
          <button
            key={k}
            onClick={() => setPeriod(k)}
            className={`rounded-lg px-3 py-1.5 text-sm ${
              period === k ? "bg-primary-600 text-white" : "border border-gray-300 hover:bg-gray-50"
            }`}
          >
            {label}
          </button>
        ))}
        <span className="ml-auto text-xs text-gray-500">
          {data.period.start} ~ {data.period.end}（{data.period.days} 天）
        </span>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric label="到案率" value={m.attendance_rate} sub={`到案 ${m.arrived_count} / 預約 ${m.booked_count}`} />
        <Metric label="媒合成功率" value={m.match_success_rate} sub={`承接 ${m.match_accepted} / 被派案 ${m.match_dispatched}`} />
        <Metric label="留案率" value={m.retention_rate} sub={`留案 ${m.retained_cases} / 進行中 ${m.ongoing_cases}`} caveat={data.caveats.retention_rate} />
        <Metric label="空間使用率" value={m.room_utilization} caveat={data.caveats.room_utilization} />
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <h3 className="mb-3 text-sm font-medium">個案黏著度分布</h3>
          <Bars rows={data.adherence} total={adherenceTotal} />
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <h3 className="mb-3 text-sm font-medium">時段分析</h3>
          <Bars rows={slotRows} total={slotTotal} />
        </div>
        {!mine && (
          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <h3 className="mb-3 text-sm font-medium">來源分析</h3>
            <Bars rows={data.sources.map((s) => ({ label: s.label, count: s.count }))}
                  total={data.sources.reduce((a, b) => a + b.count, 0)} />
            {data.top_complaints.length > 0 && (
              <div className="mt-4 rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-600">
                💡 主述議題 TOP{data.top_complaints.length}：
                {data.top_complaints.map((c) => `${c.label} ${c.count}`).join(" · ")}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="mt-4 rounded-lg bg-amber-50 px-4 py-3 text-xs text-amber-900">
        <div className="mb-1 font-medium">指標定義說明</div>
        <ul className="space-y-1">
          {Object.values(data.caveats).map((c, i) => <li key={i}>· {c}</li>)}
        </ul>
      </div>

      {mine && (
        <p className="mt-3 text-xs text-gray-400">
          只呈現你自己的數據，不與其他心理師橫向比較。
        </p>
      )}
    </div>
  );
}
