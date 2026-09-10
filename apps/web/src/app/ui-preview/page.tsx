"use client";

import { notFound } from "next/navigation";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CaseRef,
  DataTable,
  EmptyState,
  Money,
  MoneySplit,
  QuotaBar,
  StatBar,
  type Column,
} from "@/components/ui";

/**
 * 元件庫展示頁 — V2升級計畫 11 §3。
 *
 * 只在開發模式下存在（正式環境 404）。用途有三個：
 *   ① 改元件時可以直接看到全部狀態，不用登入、也不用湊出剛好的資料
 *   ② P2–P5 建新頁面時，這裡是「已經有什麼可以用」的清單
 *   ③ 顏色與密度的對照表——語意色只有在並排時才看得出是不是一套
 *
 * 刻意不放在 (app) 群組下：那層 layout 會擋登入，而這頁的價值就在於不用登入。
 */
export default function UiPreviewPage() {
  if (process.env.NODE_ENV === "production") notFound();

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-8">
        <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-ink-3">
          CheerPsy 設計系統 · V2升級計畫 11
        </p>
        <h1 className="mt-1.5 text-display-md text-ink">元件庫</h1>
        <p className="mt-2 max-w-xl text-xs leading-relaxed text-ink-2">
          核心規則：<b className="text-ink">顏色只表達狀態，不表達操作</b>
          （v7 診間日曆定案 ③）。操作鍵一律中性黑白，顏色留給右上角徽章與左緣。
        </p>
      </header>

      <div className="flex flex-col gap-6">
        <Section title="Button" note="沒有紅色實心的刪除鍵 — 破壞性操作用中性外框 ＋ 危險色文字">
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="neutral">已到</Button>
            <Button variant="solid">收款 $2,000</Button>
            <Button variant="accent">建立核銷案</Button>
            <Button variant="ghost">取消</Button>
            <Button variant="danger">作廢收據</Button>
            <Button loading>處理中</Button>
            <Button disabled>已鎖定</Button>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button size="mini" variant="solid">
              已到
            </Button>
            <Button size="mini">未到</Button>
            <Button size="sm">小</Button>
            <Button size="md">中</Button>
            <Button size="lg">大</Button>
          </div>
        </Section>

        <Section title="Badge" note="六個語意，沒有第七種 — 取代既有 2,628 處寫死的色階">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="pending">待報到</Badge>
            <Badge tone="active">已到</Badge>
            <Badge tone="done">已收款</Badge>
            <Badge tone="warn">3/3 最後一次</Badge>
            <Badge tone="danger">未到</Badge>
            <Badge tone="muted">已完成</Badge>
          </div>
        </Section>

        <Section title="Money · MoneySplit" note="機構案的一筆錢會拆成兩段，各走各的流程（09 §1.4a）">
          <div className="flex flex-col gap-2 text-xs">
            <Row label="純自費">
              <Money amount={2000} />
            </Row>
            <Row label="機構案">
              <MoneySplit casePayable={400} institutionPayable={1600} />
            </Row>
            <Row label="機構全額補助">
              <MoneySplit casePayable={0} institutionPayable={1800} />
            </Row>
            <Row label="回饋制（扣項）">
              <Money amount={-560} tone="danger" />
            </Row>
            <Row label="未填">
              <Money amount={null} />
            </Row>
          </div>
        </Section>

        <Section title="CaseRef" note="兩段式病歷號；心理師端匿名只蓋姓名，心理師姓名照常顯示">
          <div className="flex flex-col gap-2 text-xs">
            <Row label="正式個案">
              <CaseRef name="林凱文" caseNumber="26A7456126" gender="男" />
            </Row>
            <Row label="初診前">
              <CaseRef name="黃一夫" tempSeq={145} gender="男" />
            </Row>
            <Row label="伴侶案">
              <CaseRef name="李新源＆王品瑄（伴侶）" caseNumber="C260003" isCouple />
            </Row>
            <Row label="心理師匿名檢視">
              <CaseRef name="林凱文" caseNumber="26A7456126" anonymous />
            </Row>
          </div>
        </Section>

        <Section title="QuotaBar" note="三態恆等式：已預留 → 已預約 → 已使用（10 §1）">
          <div className="flex flex-col gap-5">
            <QuotaBar label="衛生局 · 15-45青壯" used={3} booked={1} reserved={2} limit={6} />
            <QuotaBar label="國防部 · 國軍 EAP（最後一次）" used={5} booked={1} reserved={0} limit={6} />
            <QuotaBar label="教育局 · 教支中心（剛掛上方案）" used={0} booked={0} reserved={4} limit={4} />
            <QuotaBar label="示範：恆等式被破壞時" used={3} booked={1} reserved={1} limit={6} />
          </div>
        </Section>

        <Section title="StatBar" note="每一格可點，帶著已套用的篩選跳頁">
          <StatBar
            stats={[
              { label: "今日應到", value: 38 },
              { label: "已報到", value: 10, tone: "done" },
              { label: "未到", value: 1, tone: "danger" },
              { label: "待報到", value: 27, tone: "warn" },
              { label: "今日已收", value: 2000, money: true, tone: "done" },
              { label: "尚待收款", value: 52200, money: true, tone: "danger", href: "/ar" },
            ]}
          />
        </Section>

        <Section title="DataTable" note="欄位定義驅動；數字欄自動 tabular-nums">
          <DemoTable />
        </Section>

        <Section title="EmptyState" note="空白要說清楚為什麼空的，以及下一步能做什麼">
          <Card>
            <EmptyState
              title="沒有未收款項"
              hint="所有已執行的場次都已收款。已到但當日未收的會自動轉入這裡，不會擋住結帳。"
              action={<Button size="sm">回到診間日曆</Button>}
            />
          </Card>
        </Section>

        <Section title="密度" note="三檔。目前既有頁面實際只有 text-sm 與 text-2xl 兩檔">
          <div className="grid gap-3 sm:grid-cols-3">
            <Card>
              <CardBody>
                <p className="text-[10px] uppercase tracking-wide text-ink-3">compact</p>
                <p className="mt-2 text-compact text-ink-2">
                  26A7456126 林凱文
                  <br />
                  $1,600 · 自付 $400
                </p>
              </CardBody>
            </Card>
            <Card>
              <CardBody>
                <p className="text-[10px] uppercase tracking-wide text-ink-3">data</p>
                <p className="mt-2 text-data text-ink-2">
                  26A7456126 林凱文
                  <br />
                  $1,600 · 自付 $400
                </p>
              </CardBody>
            </Card>
            <Card>
              <CardBody>
                <p className="text-[10px] uppercase tracking-wide text-ink-3">display</p>
                <p className="mt-1 text-display-md text-ink">$248,600</p>
              </CardBody>
            </Card>
          </div>
        </Section>
      </div>
    </div>
  );
}

function Section({
  title,
  note,
  children,
}: {
  title: string;
  note: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader title={title} hint={note} />
      <CardBody>{children}</CardBody>
    </Card>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-3">
      <span className="w-32 shrink-0 text-[10px] text-ink-3">{label}</span>
      {children}
    </div>
  );
}

interface DemoRow {
  id: number;
  date: string;
  name: string;
  caseNumber: string;
  therapist: string;
  plan: string;
  payable: number;
  inst: number;
  days: number;
  done?: boolean;
}

const demoRows: DemoRow[] = [
  { id: 1, date: "2026-09-02", name: "林凱文", caseNumber: "26A7456126", therapist: "陳慧苓", plan: "衛生局 15-45青壯", payable: 400, inst: 1600, days: 8 },
  { id: 2, date: "2026-09-05", name: "黃詠晨", caseNumber: "26A2568072", therapist: "鄭幼毅", plan: "自費 · 次結", payable: 2000, inst: 0, days: 5 },
  { id: 3, date: "2026-09-09", name: "李新源", caseNumber: "26A5669184", therapist: "劉柏宏", plan: "自費 · 月結", payable: 2000, inst: 0, days: 1 },
  { id: 4, date: "2026-09-10", name: "林小潔", caseNumber: "26A3311902", therapist: "鄭幼毅", plan: "教育局 教支中心", payable: 0, inst: 1800, days: 0, done: true },
];

function DemoTable() {
  const columns: readonly Column<DemoRow>[] = [
    { key: "d", header: "場次日期", nowrap: true, cell: (r) => <span className="ident text-ink-2">{r.date}</span> },
    { key: "c", header: "個案", cell: (r) => <CaseRef name={r.name} caseNumber={r.caseNumber} /> },
    { key: "t", header: "心理師", nowrap: true, cell: (r) => r.therapist },
    { key: "p", header: "方案", cell: (r) => r.plan },
    { key: "m", header: "應收", align: "right", nowrap: true, cell: (r) => <MoneySplit casePayable={r.payable} institutionPayable={r.inst} /> },
    {
      key: "a",
      header: "帳齡",
      nowrap: true,
      cell: (r) =>
        r.done ? (
          <Badge tone="muted">已收</Badge>
        ) : (
          <Badge tone={r.days > 7 ? "danger" : r.days >= 1 ? "warn" : "pending"}>
            {r.days > 0 ? `${r.days} 天` : "當日"}
          </Badge>
        ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={demoRows}
      rowKey={(r) => r.id}
      onRowClick={() => {}}
      // 「已完成整格轉灰」——不是「不重要」，是「今天不用再碰了」（v7 定案 ④）
      rowClassName={(r) => (r.done ? "bg-st-muted-bg text-st-muted" : undefined)}
      footer={
        <>
          <td className="px-3 py-2 text-xs" colSpan={4}>
            合計
          </td>
          <td className="px-3 py-2 text-right text-xs">
            <Money amount={4400} tone="danger" />
          </td>
          <td className="px-3 py-2 text-xs tabular-nums">4 筆</td>
        </>
      }
    />
  );
}
