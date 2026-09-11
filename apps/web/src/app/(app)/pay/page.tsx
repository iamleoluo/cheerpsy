"use client";

import { useMemo, useState } from "react";
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
 * 我的酬勞 — V2升級計畫 09 §4.3 的分區呈現。
 *
 * 為什麼要分區而不是加一欄（09 §1.6）：原型的酬勞明細是固定五欄
 * 「場次金額 × 抽成率 ＋ 外出保底 ＝ 我的酬勞」，但在 compensation_mode
 * 之下那條公式只對其中一種模式成立——
 *
 *   A 抽成 commission   診所收全額 → 依抽成率拆給心理師
 *   B 回饋 kickback     **心理師先收到全額**，欠診所回饋金。金流方向相反，
 *                       這一區是**扣項**，混在同一張表會讓心理師誤讀成收入
 *   C 場地費扣回        私人借用診間（督導模式 B：心理師自收督導費、場地費
 *                       照收並由酬勞回扣）→ 從當月酬勞扣下來
 *
 * C 區是這次補的。10 §7.1 原本標成「計算與場地租借的連結已建，酬勞單上的
 * 扣回明細列尚未呈現」——實際查證後更嚴重：`generate_payouts` 完全沒有引用
 * VenueRental，**不是明細沒顯示，是錢根本沒扣**（實測 2026 年少扣 $12,400）。
 *
 * 每一區的金額都由後端算好（payout_line_amount / venue_deductions），帳冊、
 * 月結算、這頁共用同一支函式，不會出現「畫面算的跟實際發的不一樣」。
 */

interface SessionLine {
  session_id: number;
  session_date: string;
  amount: number;
  therapist_share: number;
  compensation_mode: string;
  outcall_bonus: number;
  session_type: string;
  fee_category: string;
}

interface VenueDeduction {
  rental_id: number;
  rental_no: string;
  date: string | null;
  purpose: string | null;
  supervision_fee_mode: string | null;
  amount: number;
}

interface PayoutDetail {
  payout_id: number;
  payout_month: string;
  status: string;
  total_amount: number;
  commission_sessions: SessionLine[];
  kickback_sessions: SessionLine[];
  other_sessions: SessionLine[];
  venue_deductions: VenueDeduction[];
  subtotals: { commission: number; kickback: number; other: number; venue: number };
}

interface Payout {
  id: number;
  payout_month: string;
  total_amount: number;
  status: string;
  paid_at: string | null;
}

const sessionTypeLabel: Record<string, string> = {
  in_person: "現場",
  online: "視訊",
  outdoor: "外展",
};

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function PayPage() {
  const [month, setMonth] = useState(currentMonth());

  const list = useApi<Payout[]>(`/payouts?payout_month=${month}`);
  const payoutId = list.data?.[0]?.id;
  const detail = useApi<PayoutDetail>(
    payoutId ? `/payouts/${payoutId}/details` : null,
    { enabled: !!payoutId },
  );

  const sessionColumns: readonly Column<SessionLine>[] = useMemo(
    () => [
      {
        key: "date",
        header: "場次日期",
        nowrap: true,
        width: "w-28",
        cell: (s) => <span className="ident text-ink-2">{s.session_date}</span>,
      },
      {
        key: "type",
        header: "型式",
        nowrap: true,
        width: "w-16",
        cell: (s) => sessionTypeLabel[s.session_type] ?? s.session_type,
      },
      { key: "cat", header: "收費名目", cell: (s) => s.fee_category },
      {
        key: "amount",
        header: "場次金額",
        align: "right",
        nowrap: true,
        cell: (s) => <Money amount={s.amount} tone="muted" />,
      },
      {
        key: "bonus",
        header: "外出保底",
        align: "right",
        nowrap: true,
        cell: (s) => <Money amount={s.outcall_bonus} />,
      },
      {
        key: "share",
        header: "我的酬勞",
        align: "right",
        nowrap: true,
        cell: (s) => (
          <Money amount={s.therapist_share} tone={s.therapist_share < 0 ? "danger" : "done"} />
        ),
      },
    ],
    [],
  );

  const venueColumns: readonly Column<VenueDeduction>[] = [
    {
      key: "no",
      header: "租借單號",
      nowrap: true,
      cell: (v) => <span className="ident text-ink-2">{v.rental_no}</span>,
    },
    {
      key: "date",
      header: "日期",
      nowrap: true,
      cell: (v) => <span className="ident text-[10.5px] text-ink-3">{v.date ?? "—"}</span>,
    },
    { key: "purpose", header: "用途", cell: (v) => v.purpose ?? "—" },
    {
      key: "mode",
      header: "督導模式",
      nowrap: true,
      width: "w-24",
      cell: (v) =>
        v.supervision_fee_mode ? (
          <Badge tone="pending">模式 {v.supervision_fee_mode}</Badge>
        ) : (
          <span className="text-st-muted">—</span>
        ),
    },
    {
      key: "amt",
      header: "扣回金額",
      align: "right",
      nowrap: true,
      cell: (v) => <Money amount={-v.amount} tone="danger" />,
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1 className="text-xl font-bold text-ink">我的酬勞</h1>
        <input
          type="month"
          value={month}
          onChange={(e) => e.target.value && setMonth(e.target.value)}
          className="rounded-control border border-line-2 bg-surface px-2 py-1 text-xs tabular-nums text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25"
        />
      </div>

      <AsyncBoundary
        loading={list.loading || detail.loading}
        error={list.error ?? detail.error}
        data={payoutId ? detail.data : (list.data as unknown as PayoutDetail | undefined)}
        onRetry={() => {
          list.refetch();
          detail.refetch();
        }}
        skeleton={<div className="h-[4.5rem] animate-pulse rounded-card bg-surface-2" />}
      >
        {() =>
          !payoutId || !detail.data ? (
            <Card>
              <EmptyState
                title={`${month} 還沒有酬勞單`}
                hint="酬勞單由管理員在月結時產生。產生之後這裡會顯示當月的分區明細。"
              />
            </Card>
          ) : (
            <PayoutBody
              d={detail.data}
              sessionColumns={sessionColumns}
              venueColumns={venueColumns}
            />
          )
        }
      </AsyncBoundary>
    </div>
  );
}

function PayoutBody({
  d,
  sessionColumns,
  venueColumns,
}: {
  d: PayoutDetail;
  sessionColumns: readonly Column<SessionLine>[];
  venueColumns: readonly Column<VenueDeduction>[];
}) {
  const st = d.subtotals;
  return (
    <div className="flex flex-col gap-4">
      <StatBar
        stats={[
          {
            label: "本月實得",
            value: d.total_amount,
            money: true,
            tone: d.total_amount < 0 ? "danger" : "done",
            sub: d.status === "paid" ? "已發放" : "待發放",
          },
          {
            label: "A · 抽成場次",
            value: st.commission,
            money: true,
            sub: `${d.commission_sessions.length} 場`,
          },
          {
            label: "B · 回饋制",
            value: st.kickback,
            money: true,
            tone: st.kickback < 0 ? "warn" : "default",
            sub: `${d.kickback_sessions.length} 場 · 應回繳診所`,
          },
          {
            label: "C · 場地費扣回",
            value: -st.venue,
            money: true,
            tone: st.venue > 0 ? "warn" : "default",
            sub: `${d.venue_deductions.length} 筆`,
          },
        ]}
      />

      <Card>
        <CardHeader
          title="A · 抽成場次"
          hint="診所向機構或個案收全額，再依你的抽成率拆給你"
          actions={<Money amount={st.commission} tone="done" />}
        />
        <div className="p-3">
          {d.commission_sessions.length === 0 ? (
            <EmptyState title="本月沒有抽成場次" />
          ) : (
            <DataTable
              columns={sessionColumns}
              rows={d.commission_sessions}
              rowKey={(s) => s.session_id}
              density="compact"
              minWidth="44rem"
            />
          )}
        </div>
      </Card>

      {d.kickback_sessions.length > 0 && (
        <Card>
          <CardHeader
            title="B · 回饋制場次"
            // 金流方向相反，這件事必須講出來，否則心理師會把它讀成收入
            hint="鐘點費由你直接向機構請領；這一區是你應回繳診所的部分，所以是扣項"
            actions={<Money amount={st.kickback} tone="danger" />}
          />
          <div className="p-3">
            <DataTable
              columns={sessionColumns}
              rows={d.kickback_sessions}
              rowKey={(s) => s.session_id}
              density="compact"
              minWidth="44rem"
            />
          </div>
        </Card>
      )}

      {d.venue_deductions.length > 0 && (
        <Card>
          <CardHeader
            title="C · 場地費扣回"
            hint="你個人借用診間的場地費（督導模式 B：你自收督導費、場地費由酬勞回扣）"
            actions={<Money amount={-st.venue} tone="danger" />}
          />
          <div className="p-3">
            <DataTable
              columns={venueColumns}
              rows={d.venue_deductions}
              rowKey={(v) => v.rental_id}
              density="compact"
              minWidth="40rem"
            />
          </div>
        </Card>
      )}

      {d.other_sessions.length > 0 && (
        <Card>
          <CardHeader
            title="不計酬場次"
            hint="借場地等沒有心理師勞務的場次，列出供對帳，不計入酬勞"
          />
          <div className="p-3">
            <DataTable
              columns={sessionColumns}
              rows={d.other_sessions}
              rowKey={(s) => s.session_id}
              density="compact"
              minWidth="44rem"
            />
          </div>
        </Card>
      )}
    </div>
  );
}
