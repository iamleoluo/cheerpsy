"use client";

import { useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { useApi, useApiMutation } from "@/lib/useApi";
import {
  AsyncBoundary,
  Badge,
  Button,
  Card,
  CaseRef,
  DataTable,
  EmptyState,
  Money,
  StatBar,
  Tabs,
  type Column,
} from "@/components/ui";

/**
 * 日報表 / 對帳 — V2升級計畫 09 §4.1、11 §6 的 P2 第三頁。
 *
 * 定位：櫃檯整天用診間日曆，**當日結束後才切到這一頁**做對帳（現金 / 匯款 /
 * 未收）。所以這頁的重點不是「有哪些場次」，而是「今天收到的錢跟手上的錢
 * 對不對得起來」。
 *
 * 依 09 §1.4a：這頁的應收清單**不分 funding_source**——機構案的個案自付額
 * 跟自費案一樣是每天要收的錢，不能只顯示純自費案。
 *
 * 已知後端缺口（09 §1.5，尚未補）：優待／減免、拆帳、帳款作廢、完成當日
 * 對帳鎖定、商品販售併入。所以這裡先做「大概版」（09 §4.1 已裁示），
 * 欄位補上後再擴。
 */

interface LedgerRow {
  id: number;
  session_date: string;
  case_name: string | null;
  case_number?: string | null;
  therapist_name: string | null;
  session_type: string;
  amount: number;
  funding_source: string | null;
  plan_name: string | null;
  case_payable: number | null;
  /** 後端算好的「個案還要付多少」（09 §5）。 */
  due_amount: number;
  institution_payable: number | null;
  payment_status: string;
  payment_method: string | null;
  copay_collected_at: string | null;
  copay_payment_method: string | null;
  /**
   * ⚠️ 預先配發的號碼，**不代表收據已開立**。build_session_record() 在建立場次
   * 當下就配好（settlement.py:99），同一行下面 payment_status 還是 'unpaid'。
   * 實測 1,022 筆非作廢場次每一筆都有值，拿它當「已開立」會誤判 81 筆。
   */
  receipt_no: string | null;
  /** 真正開立出去的那張（receipts 表 status='issued'）。沒開就是 null。 */
  issued_receipt_no: string | null;
}

const sessionTypeLabel: Record<string, string> = {
  in_person: "現場",
  online: "視訊",
  outdoor: "外展",
};

function todayStr(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** 個案實際要付的錢 —— 讀後端算好的欄位，不在前端重算（09 §5）。 */
const payable = (r: LedgerRow) => r.due_amount;

/**
 * 這筆「個案自付款」收了沒。
 *
 * 機構案與自費案走的是**兩個不同欄位**：機構案看 copay_collected_at（櫃檯
 * 當場收的自付額），純自費案看 payment_status。這是 session_records 上刻意
 * 分開的設計——payment_status 對機構案的語意是「機構請款進度」，不是「個案
 * 付錢了沒」。
 */
function isCollected(r: LedgerRow): boolean {
  if (r.funding_source === "institution" || r.case_payable != null) {
    return r.copay_collected_at != null || payable(r) <= 0;
  }
  return r.payment_status === "paid" || r.payment_status === "claimed";
}

/** 現金／匯款。機構案的自付額有自己的付款方式欄位。 */
const methodOf = (r: LedgerRow) => r.copay_payment_method ?? r.payment_method;

export default function DailyPage() {
  const { data: session } = useSession();
  const isAdmin = (session?.user as { role?: string } | undefined)?.role === "admin";
  const [date, setDate] = useState(todayStr());
  const [view, setView] = useState<"unpaid" | "paid">("unpaid");
  const [settleMsg, setSettleMsg] = useState<string | null>(null);
  const { mutate, pending } = useApiMutation();

  // 既有端點沒有單日篩選參數，先抓當月再於前端篩今天（09 §5 已列為後端缺口）。
  const { data, error, loading, refetch } = useApi<LedgerRow[]>(
    `/ledger?month=${date.slice(0, 7)}`,
  );

  const { collected, uncollected, cash, transfer, unpaidTotal, dueTotal } = useMemo(() => {
    const rows = (data ?? []).filter((r) => r.session_date === date);
    const collected = rows.filter(isCollected);
    const uncollected = rows.filter((r) => !isCollected(r));
    const sumBy = (list: LedgerRow[], m: string) =>
      list.filter((r) => methodOf(r) === m).reduce((s, r) => s + payable(r), 0);
    return {
      collected,
      uncollected,
      cash: sumBy(collected, "cash"),
      transfer: sumBy(collected, "transfer"),
      unpaidTotal: uncollected.reduce((s, r) => s + payable(r), 0),
      dueTotal: rows.reduce((s, r) => s + payable(r), 0),
    };
  }, [data, date]);

  const shown = view === "unpaid" ? uncollected : collected;

  const columns: readonly Column<LedgerRow>[] = [
    {
      key: "receipt",
      header: "收據編號",
      nowrap: true,
      // 用 issued_receipt_no（真的開出去的那張），不是 receipt_no（預先配號）。
      // 之前這裡印 receipt_no，所以未收款的 81 筆照樣顯示收據編號——帳面上
      // 看起來「開了收據但錢還欠著」，那是畫面在說謊，資料其實是對的。
      cell: (r) =>
        r.issued_receipt_no ? (
          <span className="ident text-ink-2">{r.issued_receipt_no}</span>
        ) : (
          <span className="text-st-muted">未開立</span>
        ),
    },
    {
      key: "case",
      header: "個案",
      cell: (r) => <CaseRef name={r.case_name} caseNumber={r.case_number} />,
    },
    { key: "therapist", header: "心理師", nowrap: true, cell: (r) => r.therapist_name ?? "—" },
    {
      key: "type",
      header: "型式",
      nowrap: true,
      cell: (r) => sessionTypeLabel[r.session_type] ?? r.session_type,
    },
    {
      key: "plan",
      header: "方案",
      cell: (r) => r.plan_name ?? (r.funding_source === "institution" ? "機構" : "自費"),
    },
    {
      key: "copay",
      header: "個案自付額",
      align: "right",
      nowrap: true,
      cell: (r) => <Money amount={payable(r)} zero="zero" />,
    },
    {
      key: "inst",
      header: "機構請款額",
      align: "right",
      nowrap: true,
      // 這一欄走的是另一條流程（合約專頁的核銷），刻意畫淡——它不是今天要收的錢
      cell: (r) => <Money amount={r.institution_payable} tone="muted" />,
    },
    {
      key: "method",
      header: "結帳方式",
      nowrap: true,
      cell: (r) => {
        const m = methodOf(r);
        if (!isCollected(r)) return <Badge tone="danger">未收</Badge>;
        if (m === "cash") return <Badge tone="done">現金</Badge>;
        if (m === "transfer") return <Badge tone="done">匯款</Badge>;
        return <Badge tone="muted">免收</Badge>;
      },
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-xl font-bold text-ink">日報表 / 對帳</h1>
        <span className="text-xs text-ink-3">當日結束後的對帳工具 · 現金 / 匯款 / 未收</span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input
          type="date"
          value={date}
          onChange={(e) => e.target.value && setDate(e.target.value)}
          className="rounded-control border border-line-2 bg-surface px-2 py-1 text-xs tabular-nums text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25"
        />
        {loading && <span className="text-[10px] text-ink-3">載入中…</span>}

        {/*
         * 「執行日結」原本掛在已刪除的 /ledger 頁上，改放這裡——日報表就是
         * 當日結束後的對帳工具，補登漏按的報到本來就是這個動作的一部分。
         *
         * 更重要的是：這動作以前是**讀取端點的副作用**（五個 GET 都會呼叫
         * materialize_due_appointments），所以光是打開頁面就會把逾時未報到的
         * 預約標成已到、產生場次紀錄、並扣掉個案的機構額度。已改成只有這裡
         * 按下去才會發生。
         */}
        {isAdmin && (
          <div className="ml-auto flex items-center gap-2">
            {settleMsg && <span className="text-[10px] text-ink-3">{settleMsg}</span>}
            <Button
              size="sm"
              loading={pending}
              onClick={async () => {
                setSettleMsg(null);
                try {
                  const r = await mutate<{ date: string; executed: number; skipped: number }>(
                    "/ledger/settle",
                    { method: "POST", body: JSON.stringify({ target_date: date }) },
                  );
                  setSettleMsg(`已補登 ${r.executed} 筆，略過 ${r.skipped} 筆`);
                  refetch();
                } catch (e) {
                  setSettleMsg((e as Error).message);
                }
              }}
            >
              執行日結
            </Button>
          </div>
        )}
      </div>

      <StatBar
        stats={[
          { label: "當日應收", value: dueTotal, money: true },
          { label: "已收 — 現金", value: cash, money: true, tone: "done" },
          { label: "已收 — 匯款", value: transfer, money: true, tone: "done" },
          {
            label: "未收",
            value: unpaidTotal,
            money: true,
            tone: unpaidTotal > 0 ? "danger" : "done",
            sub: `${uncollected.length} 筆`,
            href: "/ar",
          },
        ]}
      />

      <Card>
        <Tabs
          value={view}
          onChange={setView}
          tabs={[
            { key: "unpaid", label: "未收", count: uncollected.length },
            { key: "paid", label: "已收", count: collected.length },
          ]}
          className="px-2"
        />
        <div className="p-3">
          <AsyncBoundary
            loading={loading}
            error={error}
            data={shown}
            onRetry={refetch}
            empty={
              <EmptyState
                title={view === "unpaid" ? "當日沒有未收款項" : "當日還沒有收款紀錄"}
                hint={
                  view === "unpaid"
                    ? "今天的場次都收完了。已到但當日未收的會自動轉入應收帳冊，不會擋住結帳。"
                    : "櫃檯在診間日曆按下「收款」後，該筆就會出現在這裡。"
                }
              />
            }
          >
            {(rows) => (
              <DataTable
                columns={columns}
                rows={rows}
                rowKey={(r) => r.id}
                density="compact"
                // 八欄，其中個案名可能長到「楊若瑄＆許建良（伴侶）」
                minWidth="52rem"
                footer={
                  <>
                    <td className="px-2.5 py-2 text-compact" colSpan={5}>
                      合計
                    </td>
                    <td className="px-2.5 py-2 text-right text-compact">
                      <Money
                        amount={rows.reduce((s, r) => s + payable(r), 0)}
                        zero="zero"
                        tone={view === "unpaid" ? "danger" : "done"}
                      />
                    </td>
                    <td className="px-2.5 py-2 text-right text-compact">
                      <Money
                        amount={rows.reduce((s, r) => s + (r.institution_payable ?? 0), 0)}
                        tone="muted"
                      />
                    </td>
                    <td className="px-2.5 py-2 text-compact tabular-nums">{rows.length} 筆</td>
                  </>
                }
              />
            )}
          </AsyncBoundary>
        </div>
      </Card>
    </div>
  );
}
