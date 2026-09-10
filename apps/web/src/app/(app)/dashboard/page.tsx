"use client";

import Link from "next/link";
import { useSession } from "next-auth/react";
import { useApi } from "@/lib/useApi";
import {
  AsyncBoundary,
  Badge,
  Card,
  CardHeader,
  EmptyState,
  StatBar,
  TableSkeleton,
  type BadgeTone,
} from "@/components/ui";

/**
 * 營運總覽 — V2升級計畫 11 §4.1。
 *
 * 改寫前這頁是四張 `SELECT COUNT`（本月場次、本月營收、待收筆數、近 7 日
 * 預約）加一排跟側欄重複的捷徑。那些數字全都正確，但**沒有一個能讓人採取
 * 行動**——早上八點打開系統的人要問的是「我今天要處理什麼」。
 *
 * 而且那排捷徑指向 /ledger、/calendar、/finance、/claims——五個不在導覽裡的
 * v1 舊頁（4,402 行），這頁是它們唯一的入口。前三個已在 P2 刪除。
 *
 * 現在的形狀照 v7 營運總覽：
 *   · KPI 卡可點，帶著已套用的篩選跳到對應清單
 *   · 今日待辦依急迫度排序，每列就地跳到能處理它的地方
 *   · 待辦一律即時查詢（GET /dashboard/todos），狀態一改下次查就不見了，
 *     不會有「已讀但其實沒處理」的假象
 */

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

interface Todo {
  id: string;
  kind: string;
  label: string;
  tone: BadgeTone;
  title: string;
  subject: string;
  href: string;
  action: string;
  urgency: number;
  amount?: number;
  count?: number;
}

export default function DashboardPage() {
  const { data: session } = useSession();
  const user = session?.user as { name?: string; role?: string } | undefined;
  const isTherapist = user?.role === "therapist";

  const stats = useApi<DashboardData>("/dashboard");
  // 心理師不進本頁的待辦（v7：改看心理師版「我的今日」）；端點也會回空陣列。
  const todos = useApi<{ todos: Todo[]; as_of: string }>("/dashboard/todos", {
    enabled: !isTherapist,
  });

  const now = new Date();
  const monthLabel = `${now.getFullYear()} 年 ${now.getMonth() + 1} 月`;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-bold text-ink">營運總覽</h1>
        <p className="mt-0.5 text-xs text-ink-3">
          {user?.name}，{monthLabel}
        </p>
      </div>

      <AsyncBoundary
        loading={stats.loading}
        error={stats.error}
        data={stats.data}
        onRetry={stats.refetch}
        skeleton={<div className="h-[4.5rem] animate-pulse rounded-card bg-surface-2" />}
      >
        {(d) => (
          <StatBar
            stats={[
              {
                label: "本月場次",
                value: d.session_count,
                sub: `進行中個案 ${d.active_cases} 位`,
                href: "/cases",
              },
              { label: "本月營收", value: d.total_revenue, money: true, href: "/reports" },
              {
                label: "待收 / 待請款",
                value: d.unpaid_amount,
                money: true,
                tone: d.unpaid_count > 0 ? "danger" : "done",
                sub: `${d.unpaid_count} 筆`,
                href: "/ar",
              },
              { label: "近 7 日預約", value: d.upcoming_reminders, href: "/rooms" },
              ...(isTherapist
                ? []
                : [
                    {
                      label: "流失預警",
                      value: d.churn_count,
                      tone: (d.churn_count > 0 ? "warn" : "default") as "warn" | "default",
                      sub: "超過 45 天無預約",
                      href: "/cases",
                    },
                    {
                      label: "零用金",
                      value: d.petty_balance ?? 0,
                      money: true,
                      tone: (d.petty_alert ? "warn" : "default") as "warn" | "default",
                      sub: d.petty_alert ? "低於 $3,000" : undefined,
                    },
                  ]),
            ]}
          />
        )}
      </AsyncBoundary>

      {!isTherapist && (
        <Card>
          <CardHeader
            title="今日待辦"
            hint="依急迫度排序 · 處理完該列即消失"
            actions={
              todos.data && (
                <span className="text-[10px] tabular-nums text-ink-3">
                  {todos.data.todos.length} 項 · {todos.data.as_of}
                </span>
              )
            }
          />
          <div className="p-2">
            <AsyncBoundary
              loading={todos.loading}
              error={todos.error}
              data={todos.data?.todos}
              onRetry={todos.refetch}
              skeleton={<TableSkeleton rows={4} cols={3} />}
              empty={
                <EmptyState
                  title="今天沒有待辦"
                  hint="沒有逾期的媒合、待確認的初診、快用完的機構額度、缺件的核銷案，也沒有逾期未收的款項。"
                />
              }
            >
              {(rows) => (
                <ul className="divide-y divide-line">
                  {rows.map((t) => (
                    <li key={t.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-2 py-2.5">
                      <Badge tone={t.tone} size="sm" className="w-11 justify-center">
                        {t.label}
                      </Badge>
                      <div className="min-w-[10rem] flex-1">
                        <p className="text-xs font-medium text-ink">{t.title}</p>
                        {t.subject && <p className="text-[11px] text-ink-3">{t.subject}</p>}
                      </div>
                      {/* 就地執行：帶著篩選跳到能處理它的地方 */}
                      <Link
                        href={t.href}
                        className="rounded-control border border-ink bg-ink px-2.5 py-1 text-[11px] font-semibold text-surface transition-colors hover:bg-ink-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                      >
                        {t.action}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </AsyncBoundary>
          </div>
        </Card>
      )}
    </div>
  );
}
