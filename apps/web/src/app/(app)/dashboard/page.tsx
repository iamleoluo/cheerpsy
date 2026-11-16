"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import Link from "next/link";
import { SESSION_TYPE, hhmm } from "@/lib/format";
import HelpDrawer, { type HelpContent } from "@/components/HelpDrawer";

const helpContent: HelpContent = {
  title: "營運總覽",
  guideId: "overview",
  overview: "診所今日與本週預約、媒合與個案狀況的快速總覽。所有數字即時從預約與媒合資料彙整。",
  sections: [
    {
      heading: "主要數字說明",
      type: "text",
      items: [
        "今日應到／已到／未到：今天未取消的場次與報到結果",
        "本週預約：本週（週一到週日）未取消的場次數",
        "近 7 日待提醒：未來 7 天已預約、尚未報到的場次",
        "本月新媒合／媒合中：本月新增的諮商需求表，以及尚未成案的件數",
        "流失預警：進行中個案超過 45 天沒有任何有效預約，也沒有未來預約",
      ],
    },
    {
      heading: "角色說明",
      type: "text",
      items: [
        "管理員、行政人員：可看到全所數字",
        "心理師：只看到自己的預約與個案，不顯示媒合與流失統計",
      ],
    },
  ],
};

interface DashboardData {
  today_expected: number;
  today_arrived: number;
  today_absent: number;
  week_appointments: number;
  upcoming_reminders: number;
  active_cases: number;
  new_referrals_month: number | null;
  matching_count: number | null;
  churn_count: number | null;
}

interface PendingItem {
  appointment_id: number;
  start_time: string;
  end_time: string;
  therapist_name: string | null;
  subject_name: string | null;
  is_intake: boolean;
  session_type: string;
}
interface PendingCheckin {
  count: number;
  items: PendingItem[];
}

export default function DashboardPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const userRole = (session?.user as any)?.role;
  const userName = (session?.user as any)?.name ?? "";

  const [data, setData] = useState<DashboardData | null>(null);
  const [pending, setPending] = useState<PendingCheckin | null>(null);
  const [loading, setLoading] = useState(true);
  const [helpOpen, setHelpOpen] = useState(false);

  const fetchData = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const d = await clientFetch("/dashboard", token);
      setData(d);
      // 昨天以前仍待報到：失敗不影響其他數字
      setPending(await clientFetch("/dashboard/pending-checkin", token).catch(() => null));
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (!token) return <p>Loading...</p>;

  const now = new Date();
  const monthLabel = `${now.getFullYear()} 年 ${now.getMonth() + 1} 月`;
  const isTherapist = userRole === "therapist";

  return (
    <div>
      <HelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} guideId="overview" />
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">營運總覽</h1>
          <p className="mt-1 text-sm text-gray-500">
            {userName}，{monthLabel}概覽
          </p>
        </div>
        <button onClick={() => setHelpOpen(true)} className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50 hover:text-gray-700">
          <span>ℹ️</span> 說明
        </button>
      </div>

      {loading || !data ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-lg border border-gray-200 bg-gray-50" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              title="今日應到"
              value={data.today_expected.toString()}
              sub={`已到 ${data.today_arrived}／未到 ${data.today_absent}`}
              href="/calendar"
            />
            <StatCard
              title="本週預約"
              value={data.week_appointments.toString()}
              sub={`活躍個案 ${data.active_cases} 位`}
              href="/appts"
            />
            <StatCard
              title="近 7 日預約"
              value={data.upcoming_reminders.toString()}
              sub="待提醒"
              href="/calendar"
            />
            {!isTherapist && data.matching_count !== null && (
              <StatCard
                title="媒合中"
                value={data.matching_count.toString()}
                sub={`本月新媒合 ${data.new_referrals_month ?? 0} 件`}
                href="/match"
              />
            )}
          </div>

          {!isTherapist && data.churn_count !== null && data.churn_count > 0 && (
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <AlertCard
                title="流失預警"
                value={`${data.churn_count} 位個案`}
                alert={true}
                alertText="超過 45 天沒有預約"
                href="/cases"
              />
            </div>
          )}

          {pending && pending.count > 0 && (
            <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-4">
              <div className="mb-2 flex items-baseline justify-between">
                <h2 className="text-sm font-medium text-amber-900">昨日（含更早）仍待報到</h2>
                <span className="text-lg font-bold text-amber-700">{pending.count} 筆</span>
              </div>
              <p className="mb-2 text-xs text-amber-800">
                這些預約開始時間已過、狀態仍是「已預約」。點進去補按「有到」或「未到」；系統不會自動更改。
              </p>
              <ul className="divide-y divide-amber-200 text-sm">
                {pending.items.map((p) => {
                  const day = p.start_time.slice(0, 10);
                  return (
                    <li key={p.appointment_id}>
                      <Link
                        href={`/appts?date=${day}`}
                        className="flex flex-wrap items-center gap-x-3 gap-y-0.5 py-1.5 hover:bg-amber-100"
                      >
                        <span className="tabular-nums text-gray-700">
                          {day.slice(5)} {hhmm(p.start_time)}–{hhmm(p.end_time)}
                        </span>
                        <span className="font-medium">
                          {p.is_intake && <span className="mr-1 text-amber-600">⭐初診</span>}
                          {p.subject_name ?? "—"}
                        </span>
                        {!isTherapist && <span className="text-gray-500">{p.therapist_name}</span>}
                        <span className="text-xs text-gray-500">{SESSION_TYPE[p.session_type] ?? p.session_type}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
              {pending.count > pending.items.length && (
                <p className="mt-2 text-xs text-amber-800">僅顯示最早的 {pending.items.length} 筆。</p>
              )}
            </div>
          )}

          <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <QuickLink href="/cases" label="個案管理" desc="查看與管理個案資料" />
            <QuickLink href="/calendar" label="診間日曆" desc="查看各治療室使用狀況" />
            {!isTherapist && <QuickLink href="/match" label="媒合管理" desc="諮商需求表與派案" />}
          </div>
        </>
      )}
    </div>
  );
}

function StatCard({
  title,
  value,
  sub,
  color,
  href,
}: {
  title: string;
  value: string;
  sub?: string;
  color?: string;
  href?: string;
}) {
  const colorClass =
    color === "red" ? "text-red-600" : color === "green" ? "text-green-600" : "text-gray-900";

  const inner = (
    <div className="rounded-lg border border-gray-200 bg-white p-4 transition-shadow hover:shadow-md">
      <p className="text-sm text-gray-500">{title}</p>
      <p className={`mt-1 text-2xl font-bold ${colorClass}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-400">{sub}</p>}
    </div>
  );

  return href ? <Link href={href}>{inner}</Link> : inner;
}

function AlertCard({
  title,
  value,
  alert,
  alertText,
  href,
}: {
  title: string;
  value: string;
  alert: boolean;
  alertText: string;
  href?: string;
}) {
  const inner = (
    <div
      className={`rounded-lg border p-4 transition-shadow hover:shadow-md ${
        alert ? "border-amber-300 bg-amber-50" : "border-gray-200 bg-white"
      }`}
    >
      <p className="text-sm text-gray-500">{title}</p>
      <p className={`mt-1 text-xl font-bold ${alert ? "text-amber-700" : "text-gray-900"}`}>
        {value}
      </p>
      {alert && <p className="mt-1 text-xs text-amber-600">{alertText}</p>}
    </div>
  );
  return href ? <Link href={href}>{inner}</Link> : inner;
}

function QuickLink({ href, label, desc }: { href: string; label: string; desc: string }) {
  return (
    <Link
      href={href}
      className="rounded-lg border border-gray-200 bg-white p-4 transition-all hover:border-primary-400 hover:shadow-md"
    >
      <p className="font-medium text-gray-900">{label}</p>
      <p className="mt-1 text-xs text-gray-400">{desc}</p>
    </Link>
  );
}
