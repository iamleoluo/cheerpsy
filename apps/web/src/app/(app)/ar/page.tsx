"use client";

import { useMemo, useState } from "react";
import { useApi } from "@/lib/useApi";
import {
  AsyncBoundary,
  Badge,
  CaseRef,
  Card,
  DataTable,
  EmptyState,
  Money,
  StatBar,
  Tabs,
  type Column,
} from "@/components/ui";
import { InstitutionReceivable } from "@/features/institution/InstitutionReceivable";

/**
 * 應收帳冊 — V2升級計畫 11 P1 的示範頁。
 *
 * 選這頁當第一個轉換對象是因為它最小（129 行）、風險最低，但涵蓋了元件庫
 * 的主要面：分頁、統計列、表格、三態、語意色、金額。
 *
 * 這次轉換修掉的三件事：
 *   ① 失敗不再偽裝成沒資料。舊版 `.catch(() => setRows([]))`，token 過期時
 *      畫面顯示「沒有符合條件的紀錄」——行政會以為今天都收完了（11 §5）。
 *   ② 逾期天數的顏色從三個寫死的色階（rose-100/amber-100/gray-100）
 *      改成語意 token。
 *   ③ 合計從一行小字改成頂部統計列，並且可以點——「未收」是行政每天要
 *      追的數字，不該藏在表格底下。
 *
 * 資料來源 GET /ledger/self-pay-unpaid——名稱沿用舊的，但語意已是 09 §1.4a
 * 裁示的「自付款待收」：**不分 funding_source**，機構案的個案自付額跟自費案
 * 一起出現在這裡。判準集中在後端 services/copay.py，前端不重算（09 §5）。
 */

interface Row {
  id: number;
  appointment_id: number | null;
  session_date: string;
  case_name: string | null;
  case_number?: string | null;
  therapist_name: string | null;
  amount: number;
  case_payable: number | null;
  /** 後端算好的「個案還要付多少」（09 §5：這條規則只有一個來源）。 */
  due_amount: number;
  funding_source: string | null;
  plan_name: string | null;
  institution_name: string | null;
  billing_cycle: string | null;
}

type Tab = "unpaid" | "monthly" | "institution";

function daysAgo(dateStr: string): number {
  const d = new Date(dateStr);
  return Math.floor((Date.now() - d.getTime()) / 86_400_000);
}

/**
 * 個案實際要付的錢 —— **讀後端算好的欄位，不在前端重算**。
 *
 * 原本這裡寫 `case_payable ?? amount`，漏掉了優待減免，於是統計列比後端多算
 * $200。09 §5 要求這條規則「全部共用同一個來源」，前端也算在內。
 */
const payable = (r: Row) => r.due_amount;

function planLabel(r: Row) {
  if (r.plan_name) return r.plan_name;
  if (r.funding_source === "institution") return r.institution_name ?? "機構";
  return "自費";
}

export default function ARPage() {
  const [tab, setTab] = useState<Tab>("unpaid");
  const { data, error, loading, refetch } = useApi<Row[]>("/ledger/self-pay-unpaid");

  const { general, monthly, total } = useMemo(() => {
    const rows = data ?? [];
    const general = rows.filter((r) => r.billing_cycle !== "monthly");
    const monthly = rows.filter((r) => r.billing_cycle === "monthly");
    return {
      general,
      monthly,
      total: rows.reduce((s, r) => s + payable(r), 0),
    };
  }, [data]);

  const shown = tab === "monthly" ? monthly : general;
  // 逾期超過 7 天的才是真的要追的——其餘只是還沒到收款時機。
  const overdue = shown.filter((r) => daysAgo(r.session_date) > 7);

  const columns: readonly Column<Row>[] = [
    {
      key: "date",
      header: "場次日期",
      nowrap: true,
      width: "w-28",
      cell: (r) => <span className="ident text-ink-2">{r.session_date}</span>,
    },
    {
      key: "case",
      header: "個案",
      cell: (r) => <CaseRef name={r.case_name} caseNumber={r.case_number} />,
    },
    { key: "therapist", header: "心理師", nowrap: true, cell: (r) => r.therapist_name ?? "—" },
    { key: "plan", header: "方案", cell: (r) => planLabel(r) },
    {
      key: "amount",
      header: "應收金額",
      align: "right",
      nowrap: true,
      cell: (r) => <Money amount={payable(r)} zero="zero" />,
    },
    {
      key: "aging",
      header: "帳齡",
      nowrap: true,
      width: "w-20",
      cell: (r) => {
        const d = daysAgo(r.session_date);
        // 逾期愈久語意愈嚴重：當日只是還沒收，超過 7 天就是真的漏了。
        return (
          <Badge tone={d > 7 ? "danger" : d >= 1 ? "warn" : "pending"} size="sm">
            {d > 0 ? `${d} 天` : "當日"}
          </Badge>
        );
      },
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-bold text-ink">應收帳冊</h1>
        <p className="mt-0.5 text-xs text-ink-3">
          個案自己要付的錢，不分自費案或機構案的自付額（09 §1.4a）
        </p>
      </div>

      <StatBar
        stats={[
          { label: "未收合計", value: total, money: true, tone: total > 0 ? "danger" : "done", sub: `${(data ?? []).length} 筆` },
          { label: "次結／多次結", value: general.length, sub: "當日應結未結" },
          { label: "月結", value: monthly.length, sub: "月底一併收款" },
          {
            label: "逾期逾 7 天",
            value: overdue.length,
            tone: overdue.length > 0 ? "warn" : "default",
            sub: "需主動追收",
          },
        ]}
      />

      <Card>
        <Tabs
          value={tab}
          onChange={setTab}
          tabs={[
            { key: "unpaid", label: "未收", count: general.length },
            { key: "monthly", label: "月結", count: monthly.length },
            { key: "institution", label: "機構應收" },
          ]}
          className="px-2"
        />

        <div className="p-3">
          {tab === "institution" ? (
            <InstitutionReceivable />
          ) : (
            <AsyncBoundary
              loading={loading}
              error={error}
              data={shown}
              onRetry={refetch}
              empty={
                <EmptyState
                  title={tab === "monthly" ? "沒有月結待收" : "沒有未收款項"}
                  hint={
                    tab === "monthly"
                      ? "月結個案報到即列入本頁，月底一併收款。目前沒有累積中的月結帳。"
                      : "所有已執行的場次都已收款。已到但當日未收的會自動轉入這裡，不會擋住結帳。"
                  }
                />
              }
            >
              {(rows) => (
                <DataTable
                  columns={columns}
                  rows={rows}
                  rowKey={(r) => r.id}
                  footer={
                    <>
                      <td className="px-3 py-2 text-xs" colSpan={4}>
                        合計
                      </td>
                      <td className="px-3 py-2 text-right text-xs">
                        <Money
                          amount={rows.reduce((s, r) => s + payable(r), 0)}
                          zero="zero"
                          tone="danger"
                        />
                      </td>
                      <td className="px-3 py-2 text-xs tabular-nums">{rows.length} 筆</td>
                    </>
                  }
                />
              )}
            </AsyncBoundary>
          )}
        </div>
      </Card>
    </div>
  );
}
