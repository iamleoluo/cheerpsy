"use client";

import { useApi } from "@/lib/useApi";
import {
  AsyncBoundary,
  Badge,
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  Money,
  StatBar,
  type Column,
} from "@/components/ui";

/**
 * 機構應收 — 應收帳冊第三分頁（V2升級計畫 09 §4.2）。
 *
 * 前兩個分頁講的是**個案自己要付的錢**；這一頁是完全另一段——**機構要撥給
 * 診所的那一段**（institution_payable）。09 §1.4a 的界線：自付款每天都要
 * 看到，機構請款主動點開才處理。
 *
 * **唯讀**（09 §4.2）：收款動作一律回合約專頁執行，避免同一筆錢有兩個地方
 * 可以按「已收到款項」、狀態打架。
 *
 * 分兩段呈現，因為那是兩種不同的錢：
 *   已送出等撥款  已經開單請款了，在等對方付
 *   尚未收納      做完了但還沒被任何核銷案撈進去 —— **還沒開始要錢**
 *
 * 第二段是行政最容易漏的（07 §4.3 建議做成常駐檢視）：它在合約專頁裡分散在
 * 各個合約底下，跨機構看不到全貌。實測資料庫裡最舊的一筆是快一年前的。
 */

interface Awaiting {
  claim_case_id: number;
  claim_no: string;
  institution_name: string | null;
  period_start: string | null;
  period_end: string | null;
  record_count: number;
  applied_amount: number;
  waiting_days: number | null;
  is_overdue: boolean;
}

interface Uncollected {
  plan_id: number | null;
  plan_name: string | null;
  institution_name: string | null;
  count: number;
  amount: number;
  oldest: string | null;
  newest: string | null;
  is_stale: boolean;
}

interface Payload {
  as_of: string;
  awaiting_payment: Awaiting[];
  uncollected: Uncollected[];
  summary: {
    awaiting_count: number;
    awaiting_total: number;
    awaiting_overdue: number;
    uncollected_count: number;
    uncollected_total: number;
    uncollected_stale: number;
    total: number;
  };
}

export function InstitutionReceivable() {
  const { data, error, loading, refetch } = useApi<Payload>("/institution/receivable");

  const awaitingColumns: readonly Column<Awaiting>[] = [
    {
      key: "no",
      header: "核銷案",
      nowrap: true,
      cell: (a) => <span className="ident font-semibold text-ink">{a.claim_no}</span>,
    },
    { key: "inst", header: "機構", cell: (a) => a.institution_name ?? "—" },
    {
      key: "period",
      header: "期間",
      nowrap: true,
      cell: (a) => (
        <span className="ident text-[10.5px] text-ink-3">
          {a.period_start ?? "—"} ~ {a.period_end ?? "—"}
        </span>
      ),
    },
    { key: "n", header: "筆數", align: "right", nowrap: true, width: "w-16", cell: (a) => a.record_count },
    {
      key: "amt",
      header: "申請金額",
      align: "right",
      nowrap: true,
      cell: (a) => <Money amount={a.applied_amount} />,
    },
    {
      key: "wait",
      header: "已等待",
      nowrap: true,
      width: "w-24",
      cell: (a) =>
        a.waiting_days == null ? (
          <span className="text-st-muted">—</span>
        ) : (
          <Badge tone={a.is_overdue ? "warn" : "pending"}>{a.waiting_days} 天</Badge>
        ),
    },
  ];

  const uncollectedColumns: readonly Column<Uncollected>[] = [
    { key: "inst", header: "機構", cell: (u) => u.institution_name ?? "—" },
    {
      key: "plan",
      header: "方案",
      cell: (u) => <span className="text-ink-2">{u.plan_name ?? "—"}</span>,
    },
    {
      key: "range",
      header: "場次區間",
      nowrap: true,
      cell: (u) => (
        <span className="ident text-[10.5px] text-ink-3">
          {u.oldest ?? "—"} ~ {u.newest ?? "—"}
        </span>
      ),
    },
    { key: "n", header: "筆數", align: "right", nowrap: true, width: "w-16", cell: (u) => u.count },
    {
      key: "amt",
      header: "未請款金額",
      align: "right",
      nowrap: true,
      cell: (u) => <Money amount={u.amount} tone={u.is_stale ? "warn" : "default"} />,
    },
    {
      key: "stale",
      header: "",
      nowrap: true,
      width: "w-24",
      // 跨月遺留＝這筆錢已經拖過一個月還沒開單，是這頁最該處理的東西
      cell: (u) => (u.is_stale ? <Badge tone="warn">跨月遺留</Badge> : null),
    },
  ];

  return (
    <AsyncBoundary loading={loading} error={error} data={data} onRetry={refetch}>
      {(d) => (
        <div className="flex flex-col gap-4">
          <StatBar
            stats={[
              { label: "機構應收合計", value: d.summary.total, money: true },
              {
                label: "已送出待撥款",
                value: d.summary.awaiting_total,
                money: true,
                sub: `${d.summary.awaiting_count} 案`,
              },
              {
                label: "尚未收納",
                value: d.summary.uncollected_total,
                money: true,
                tone: d.summary.uncollected_total > 0 ? "warn" : "default",
                sub: `${d.summary.uncollected_count} 筆還沒開單請款`,
              },
              {
                label: "跨月遺留",
                value: d.summary.uncollected_stale,
                tone: d.summary.uncollected_stale > 0 ? "danger" : "default",
                sub: "拖過一個月",
              },
            ]}
          />

          <Card>
            <CardHeader
              title="尚未收納"
              hint="做完了但還沒被任何核銷案撈進去——這段錢還沒開始要"
              actions={
                <span className="text-[10px] text-ink-3">開核銷案請到合約專頁的「核銷」分頁</span>
              }
            />
            <div className="p-3">
              {d.uncollected.length === 0 ? (
                <EmptyState
                  title="沒有漏掉的機構請款"
                  hint="所有已執行的機構場次都已被核銷案收納。"
                />
              ) : (
                <DataTable
                  columns={uncollectedColumns}
                  rows={d.uncollected}
                  rowKey={(u) => String(u.plan_id)}
                  minWidth="52rem"
                  rowClassName={(u) => (u.is_stale ? "bg-st-warn-bg/40" : undefined)}
                />
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="已送出 · 等待撥款" hint={`資料時間 ${d.as_of}`} />
            <div className="p-3">
              {d.awaiting_payment.length === 0 ? (
                <EmptyState
                  title="沒有等待撥款的核銷案"
                  hint="送出的核銷案都已入帳，或目前還沒有送出中的案子。"
                />
              ) : (
                <DataTable
                  columns={awaitingColumns}
                  rows={d.awaiting_payment}
                  rowKey={(a) => a.claim_case_id}
                  minWidth="52rem"
                  rowClassName={(a) => (a.is_overdue ? "bg-st-warn-bg/40" : undefined)}
                />
              )}
            </div>
          </Card>
        </div>
      )}
    </AsyncBoundary>
  );
}
