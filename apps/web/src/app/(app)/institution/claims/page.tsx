"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { getSession } from "next-auth/react";
import { useApi } from "@/lib/useApi";
import {
  AsyncBoundary,
  Badge,
  Card,
  DataTable,
  EmptyState,
  FilterBar,
  Input,
  Money,
  Select,
  StatBar,
  claimTone,
  type Column,
} from "@/components/ui";

/**
 * 核銷案總表 — 跨機構的**唯讀**查詢（09 §3.7 已裁示）。
 *
 * 這頁回答一個問題：**「這個月所有待送出的有哪些」**。
 *
 * 所以重點不是列出 67 個容器，而是把「收集中、文件齊備、可以送出」那幾個
 * 挑出來——「能不能送」取決於文件雙閘門，光有編號與狀態答不了這個問題。
 * docs_pending / ready_to_submit 由後端一次算完（11 §4.1）。
 *
 * 刻意不做任何寫入：建立／收納／送出／入帳／作廢一律回合約專頁執行，
 * 避免同一筆錢有兩個地方可以改、狀態打架（09 §3.7）。
 */

interface ClaimCaseRow {
  id: number;
  claim_no: string;
  claim_group_key: string;
  status: string;
  grouping_mode: string;
  capacity: number | null;
  period_start: string | null;
  period_end: string | null;
  record_count: number;
  applied_amount: number | null;
  net_received: number | null;
  institution_name: string | null;
  contract_name: string | null;
  /** 容器裡還有幾筆心理師沒交文件。豁免過的算 0。 */
  docs_pending: number;
  docs_waived: boolean;
  /** 收集中 ＋ 有紀錄 ＋ 文件齊備 —— 這頁存在的目的就是挑出這些。 */
  ready_to_submit: boolean;
}

const statusLabel: Record<string, string> = {
  collecting: "收集中",
  ready: "待送出",
  submitted: "已送出",
  received: "已入帳",
  closed: "已結案",
  void: "已作廢",
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * 下載請款單 PDF。
 *
 * 走 fetch 再轉 blob 而不是直接開連結，因為端點要帶 Authorization header；
 * 直接 window.open 會少掉 token 變成 401。
 */
async function downloadClaimForm(claimCaseId: number, claimNo: string) {
  const res = await fetch(`${API_URL}/institution/claim-cases/${claimCaseId}/claim-form`, {
    headers: { Authorization: `Bearer ${await getToken()}` },
  });
  if (!res.ok) return;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `claim-${claimNo}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

async function getToken(): Promise<string> {
  const s = await getSession();
  return (s?.user as { accessToken?: string } | undefined)?.accessToken ?? "";
}

export default function ClaimCasesOverviewPage() {
  const router = useRouter();
  const [statusFilter, setStatusFilter] = useState("collecting");
  const [q, setQ] = useState("");

  const { data, error, loading, refetch } = useApi<ClaimCaseRow[]>("/institution/claim-cases");

  const { rows, stats } = useMemo(() => {
    const all = data ?? [];
    const kw = q.trim().toLowerCase();
    const rows = all
      .filter((c) => (statusFilter ? c.status === statusFilter : true))
      .filter(
        (c) =>
          !kw ||
          c.claim_no.toLowerCase().includes(kw) ||
          (c.institution_name ?? "").toLowerCase().includes(kw) ||
          c.claim_group_key.toLowerCase().includes(kw),
      );
    const collecting = all.filter((c) => c.status === "collecting");
    return {
      rows,
      stats: {
        collecting: collecting.length,
        ready: collecting.filter((c) => c.ready_to_submit).length,
        blocked: collecting.filter((c) => !c.ready_to_submit).length,
        submitted: all.filter((c) => c.status === "submitted").length,
      },
    };
  }, [data, statusFilter, q]);

  const columns: readonly Column<ClaimCaseRow>[] = [
    {
      key: "no",
      header: "核銷案",
      nowrap: true,
      cell: (c) => (
        <div>
          <span className="ident font-semibold text-ink">{c.claim_no}</span>
          <div className="text-[10px] text-ink-3">
            {c.grouping_mode === "per_case_count" ? `每滿 ${c.capacity} 次` : "期間制"}
          </div>
        </div>
      ),
    },
    {
      key: "inst",
      header: "機構 / 核銷群組",
      cell: (c) => (
        <div className="min-w-0">
          <div className="truncate text-ink-2">{c.institution_name ?? "—"}</div>
          <div className="truncate text-[10px] text-ink-3">{c.claim_group_key}</div>
        </div>
      ),
    },
    {
      key: "period",
      header: "期間",
      nowrap: true,
      cell: (c) =>
        c.period_start || c.period_end ? (
          <span className="ident text-[10.5px] text-ink-3">
            {c.period_start ?? "—"} ~ {c.period_end ?? "—"}
          </span>
        ) : (
          <span className="text-st-muted">—</span>
        ),
    },
    {
      key: "count",
      header: "筆數",
      align: "right",
      nowrap: true,
      width: "w-16",
      cell: (c) => <span className="text-ink-2">{c.record_count}</span>,
    },
    {
      key: "docs",
      header: "文件",
      nowrap: true,
      width: "w-24",
      cell: (c) =>
        c.docs_waived ? (
          <Badge tone="muted">已豁免</Badge>
        ) : c.docs_pending > 0 ? (
          // 缺件擋住送出，是這頁唯一真正要人動作的訊號
          <Badge tone="warn">缺 {c.docs_pending} 筆</Badge>
        ) : (
          <Badge tone="done">齊備</Badge>
        ),
    },
    {
      key: "amount",
      header: "申請 / 實收",
      align: "right",
      nowrap: true,
      cell: (c) => (
        <div className="flex flex-col items-end">
          <Money amount={c.applied_amount} />
          {c.net_received != null && <Money amount={c.net_received} size="compact" tone="done" />}
        </div>
      ),
    },
    {
      key: "status",
      header: "狀態",
      nowrap: true,
      width: "w-24",
      cell: (c) =>
        c.ready_to_submit ? (
          <Badge tone="active">可送出</Badge>
        ) : (
          <Badge tone={claimTone[c.status] ?? "pending"}>{statusLabel[c.status] ?? c.status}</Badge>
        ),
    },
    {
      key: "pdf",
      header: "",
      nowrap: true,
      width: "w-20",
      // 請款單原本只印得出來自舊的 /claims，所以「要印單子就得回舊頁面」——
      // 那是新舊兩套並存最說不清楚的地方（13 §D2）
      cell: (c) => (
        <button
          onClick={(e) => {
            e.stopPropagation();
            downloadClaimForm(c.id, c.claim_no);
          }}
          className="rounded border border-line-2 px-2 py-0.5 text-[11px] text-ink-2 hover:bg-surface-2"
        >
          請款單
        </button>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-xl font-bold text-ink">核銷案總表</h1>
        <span className="text-xs text-ink-3">
          跨機構的唯讀查詢 · 建立／收納／送出／入帳一律回合約專頁執行
        </span>
      </div>

      <AsyncBoundary
        loading={loading}
        error={error}
        data={data}
        onRetry={refetch}
        skeleton={<div className="h-[4.5rem] animate-pulse rounded-card bg-surface-2" />}
      >
        {() => (
          <StatBar
            stats={[
              { label: "收集中", value: stats.collecting },
              {
                label: "文件齊備 · 可送出",
                value: stats.ready,
                tone: stats.ready > 0 ? "done" : "default",
                sub: "回合約專頁送出",
              },
              {
                label: "缺件卡住",
                value: stats.blocked,
                tone: stats.blocked > 0 ? "warn" : "default",
                sub: "心理師文件未齊",
              },
              { label: "已送出待入帳", value: stats.submitted },
            ]}
          />
        )}
      </AsyncBoundary>

      <FilterBar>
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜尋核銷案編號、機構或群組"
          className="max-w-xs"
        />
        <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="w-32">
          <option value="collecting">收集中</option>
          <option value="submitted">已送出</option>
          <option value="closed">已結案</option>
          <option value="void">已作廢</option>
          <option value="">全部狀態</option>
        </Select>
        <span className="text-[10.5px] text-ink-3">{rows.length} 筆</span>
      </FilterBar>

      <Card>
        <div className="p-3">
          <AsyncBoundary
            loading={loading}
            error={error}
            data={rows}
            onRetry={refetch}
            empty={
              <EmptyState
                title={statusFilter === "collecting" ? "目前沒有收集中的核銷案" : "沒有符合條件的核銷案"}
                hint={
                  statusFilter === "collecting"
                    ? "核銷案是容器——行政可以先開一個空的，系統再依方案規則把紀錄撈進來。開容器請到合約專頁的「核銷」分頁。"
                    : "換個狀態或關鍵字看看。"
                }
              />
            }
          >
            {(list) => (
              <DataTable
                columns={columns}
                rows={list}
                rowKey={(c) => c.id}
                minWidth="60rem"
                // 唯讀頁——點進去是回合約專頁做事，不是在這裡改
                onRowClick={(c) =>
                  router.push(`/institution?claim=${encodeURIComponent(c.claim_group_key)}`)
                }
                rowClassName={(c) => (c.status === "void" ? "opacity-50" : undefined)}
              />
            )}
          </AsyncBoundary>
        </div>
      </Card>
    </div>
  );
}
