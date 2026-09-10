"use client";

import { useMemo, useState } from "react";
import { useApi, useApiMutation } from "@/lib/useApi";
import {
  AsyncBoundary,
  Badge,
  Button,
  Card,
  CaseRef,
  DataTable,
  EmptyState,
  StatBar,
  Tabs,
  type Column,
} from "@/components/ui";

/**
 * 文件確認（心理師端）— 09 §6 ⑥。
 *
 * 機構核銷需要**雙閘門**：心理師確認文件 ＋ 行政核對，兩者皆完成該筆才算齊備；
 * 只要有一筆沒齊備，整個核銷案就送不出去。
 *
 * 這次改寫補的是 10 §6 記錄的那個洞——**退回補件的可見性**：
 *
 *   「原本只有 admin-unverify：清一側、沒原因、不通知，
 *     心理師根本不知道自己被退件」
 *
 * 後端退回時會清掉兩個閘門、寫稽核、發通知，但**原因沒有存在紀錄上**，
 * 所以被退回的那筆在這頁看起來跟「從沒交過」一模一樣。現在把最後一次退回的
 * 時間與原因帶出來，被退件的排在最上面並標紅——那是要重做的事，不是待辦。
 */

interface DocRow {
  id: number;
  session_date: string;
  case_name: string | null;
  case_number?: string | null;
  session_type: string;
  institution_name: string | null;
  plan_name: string | null;
  /** 最後一次被退回補件的時間／原因。沒被退過就是 null。 */
  returned_at: string | null;
  returned_reason: string | null;
}

const sessionTypeLabel: Record<string, string> = {
  in_person: "現場",
  online: "視訊",
  outdoor: "外展",
};

export default function DocsPage() {
  const [tab, setTab] = useState<"pending" | "confirmed">("pending");
  const [selected, setSelected] = useState<number[]>([]);
  const { mutate, pending: busy } = useApiMutation();

  const p = useApi<DocRow[]>("/institution/pending-docs");
  const c = useApi<DocRow[]>("/institution/confirmed-docs");

  // 被退回的排最前面——那是「要重做」，跟「還沒做」不是同一件事
  const pendingRows = useMemo(() => {
    const rows = [...(p.data ?? [])];
    rows.sort((a, b) => {
      if (!!a.returned_at !== !!b.returned_at) return a.returned_at ? -1 : 1;
      return b.session_date.localeCompare(a.session_date);
    });
    return rows;
  }, [p.data]);

  const returnedCount = pendingRows.filter((r) => r.returned_at).length;

  async function confirmSelected() {
    if (selected.length === 0) return;
    try {
      // 逐筆送——後端沒有批次端點，而且一筆失敗不該讓其他筆一起回滾
      for (const id of selected) {
        await mutate(`/ledger/${id}/confirm-doc`, { method: "PUT" });
      }
    } finally {
      setSelected([]);
      p.refetch();
      c.refetch();
    }
  }

  const toggle = (id: number) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const baseColumns: readonly Column<DocRow>[] = [
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
    {
      key: "type",
      header: "型式",
      nowrap: true,
      width: "w-16",
      cell: (r) => sessionTypeLabel[r.session_type] ?? r.session_type,
    },
    {
      key: "plan",
      header: "機構 / 方案",
      cell: (r) => (
        <div className="min-w-0">
          <div className="truncate text-ink-2">{r.institution_name ?? "—"}</div>
          {r.plan_name && <div className="truncate text-[10px] text-ink-3">{r.plan_name}</div>}
        </div>
      ),
    },
  ];

  const pendingColumns: readonly Column<DocRow>[] = [
    {
      key: "sel",
      header: "",
      width: "w-10",
      cell: (r) => (
        <input
          type="checkbox"
          checked={selected.includes(r.id)}
          onChange={() => toggle(r.id)}
          onClick={(e) => e.stopPropagation()}
          aria-label={`勾選 ${r.session_date} ${r.case_name ?? ""}`}
          className="h-3.5 w-3.5 accent-[hsl(var(--accent))]"
        />
      ),
    },
    ...baseColumns,
    {
      key: "state",
      header: "狀態",
      width: "w-56",
      cell: (r) =>
        r.returned_at ? (
          <div className="flex flex-col gap-0.5">
            <Badge tone="danger" className="w-fit">退回補件</Badge>
            {r.returned_reason && (
              <span className="text-[10px] leading-snug text-st-danger">{r.returned_reason}</span>
            )}
          </div>
        ) : (
          <Badge tone="pending">待提交</Badge>
        ),
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-xl font-bold text-ink">文件確認</h1>
        <span className="text-xs text-ink-3">
          機構核銷需要雙重把關：你確認文件 ＋ 行政核對，兩者皆完成才算齊備
        </span>
      </div>

      <StatBar
        stats={[
          { label: "待提交", value: pendingRows.length - returnedCount },
          {
            label: "退回補件",
            value: returnedCount,
            tone: returnedCount > 0 ? "danger" : "default",
            sub: returnedCount > 0 ? "需要重新處理" : undefined,
          },
          { label: "已確認", value: (c.data ?? []).length, tone: "done", sub: "待行政核對" },
        ]}
      />

      <Card>
        <Tabs
          value={tab}
          onChange={setTab}
          tabs={[
            { key: "pending", label: "未確認", count: pendingRows.length },
            { key: "confirmed", label: "已確認", count: (c.data ?? []).length },
          ]}
          className="px-2"
        />

        <div className="p-3">
          {tab === "pending" ? (
            <AsyncBoundary
              loading={p.loading}
              error={p.error}
              data={pendingRows}
              onRetry={p.refetch}
              empty={
                <EmptyState
                  title="沒有待確認的文件"
                  hint="你負責的機構場次文件都已提交。行政核對完成後，那些場次就能被收進核銷案。"
                />
              }
            >
              {(rows) => (
                <div className="flex flex-col gap-3">
                  <DataTable
                    columns={pendingColumns}
                    rows={rows}
                    rowKey={(r) => r.id}
                    minWidth="48rem"
                    onRowClick={(r) => toggle(r.id)}
                    // 被退回的整列標紅底，滑過清單時一眼看得到
                    rowClassName={(r) => (r.returned_at ? "bg-st-danger-bg/40" : undefined)}
                  />
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] text-ink-3">
                      {selected.length > 0 ? `已勾選 ${selected.length} 筆` : "點列或勾選方框以選取"}
                    </span>
                    <Button
                      variant="accent"
                      size="sm"
                      className="ml-auto"
                      loading={busy}
                      disabled={selected.length === 0}
                      onClick={confirmSelected}
                    >
                      確認已勾選（{selected.length}）
                    </Button>
                  </div>
                </div>
              )}
            </AsyncBoundary>
          ) : (
            <AsyncBoundary
              loading={c.loading}
              error={c.error}
              data={c.data}
              onRetry={c.refetch}
              empty={
                <EmptyState
                  title="尚無已確認的文件"
                  hint="在「未確認」分頁勾選並確認之後，紀錄會移到這裡等待行政核對。"
                />
              }
            >
              {(rows) => (
                <DataTable columns={baseColumns} rows={rows} rowKey={(r) => r.id} minWidth="42rem" />
              )}
            </AsyncBoundary>
          )}
        </div>
      </Card>
    </div>
  );
}
