"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import Link from "next/link";
import HelpDrawer, { type HelpContent } from "@/components/HelpDrawer";

const helpContent: HelpContent = {
  title: "儀表板",
  overview: "診所當日與本月運營狀況的快速總覽。所有數字即時從各模組彙整，無需手動更新。",
  sections: [
    {
      heading: "主要數字說明",
      type: "text",
      items: [
        "今日預約：今天狀態為「已預約」的場次數",
        "本月場次：本月已執行的諮商總場次",
        "待收款筆數：日結帳冊中尚未歸入核銷案的帳單數",
        "零用金餘額：目前零用金帳戶的可用金額",
      ],
    },
    {
      heading: "日常工作流程",
      type: "steps",
      items: [
        "早上：查看今日預約場次，確認排程無誤",
        "每日：進入日結帳冊，執行日結確保前日資料寫入",
        "每日：至「待處理」分頁，將未歸入的帳單建立核銷案",
        "月底：進入財務管理，執行心理師酬勞月結，查看月報表",
      ],
    },
    {
      heading: "角色說明",
      type: "text",
      items: [
        "管理員（A）：完整操作權限，包含月結、帳號管理",
        "會計（C）：可查看所有財務報表與核銷案",
        "行政人員（S）：可建立個案、預約、核銷案",
        "心理師（T）：只能看自己的預約與帳務，需確認機構案文件",
      ],
    },
    {
      heading: "管理員提示",
      type: "notes",
      items: [
        "數字顯示「-」代表資料載入中，請稍待",
        "零用金餘額偏低時請至財務管理補款記錄",
        "待收款數字高時，進入日結帳冊待處理分頁批次建立核銷案",
      ],
    },
  ],
};

interface DashboardData {
  session_count: number;
  total_revenue: number;
  unpaid_count: number;
  unpaid_amount: number;
  upcoming_reminders: number;
  active_cases: number;
  petty_balance: number | null;
  petty_alert: boolean;
  churn_count: number;
}

export default function DashboardPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const userRole = (session?.user as any)?.role;
  const userName = (session?.user as any)?.name ?? "";

  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [helpOpen, setHelpOpen] = useState(false);

  const fetchData = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const d = await clientFetch("/dashboard", token);
      setData(d);
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

  return (
    <div>
      <HelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} content={helpContent} />
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">儀表板</h1>
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
              title="本月諮商場次"
              value={data.session_count.toString()}
              sub={`活躍個案 ${data.active_cases} 位`}
              href="/ledger"
            />
            <StatCard
              title="本月營收"
              value={`$${data.total_revenue.toLocaleString()}`}
              sub={`師 $${Math.round(data.total_revenue * 0.7).toLocaleString()} / 所 $${Math.round(data.total_revenue * 0.3).toLocaleString()}`}
              href="/reports"
            />
            <StatCard
              title="待收/待請款"
              value={`${data.unpaid_count} 筆`}
              sub={`$${data.unpaid_amount.toLocaleString()}`}
              color={data.unpaid_count > 0 ? "red" : "green"}
              href="/ledger"
            />
            <StatCard
              title="近 7 日預約"
              value={data.upcoming_reminders.toString()}
              sub="待提醒"
              href="/calendar"
            />
          </div>

          {userRole !== "therapist" && (
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {data.petty_balance !== null && (
                <AlertCard
                  title="零用金餘額"
                  value={`$${data.petty_balance.toLocaleString()}`}
                  alert={data.petty_alert}
                  alertText="餘額低於 $3,000，請補充"
                  href="/finance"
                />
              )}
              {data.churn_count > 0 && (
                <AlertCard
                  title="流失預警"
                  value={`${data.churn_count} 位個案`}
                  alert={true}
                  alertText="超過 30 天未預約"
                  href="/reports"
                />
              )}
            </div>
          )}

          <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <QuickLink href="/cases" label="個案管理" desc="查看與管理個案資料" />
            <QuickLink href="/calendar" label="預約日曆" desc="查看各治療室使用狀況" />
            <QuickLink href="/ledger" label="日結帳冊" desc="每日結帳與收款管理" />
            {userRole !== "therapist" && (
              <>
                <QuickLink href="/reports" label="營運報表" desc="營收、績效、損益分析" />
                <QuickLink href="/finance" label="財務管理" desc="收據、酬勞、零用金" />
                <QuickLink href="/claims" label="核銷案管理" desc="自費/機構分群核銷" />
              </>
            )}
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
