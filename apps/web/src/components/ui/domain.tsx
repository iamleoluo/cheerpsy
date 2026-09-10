import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Badge } from "./badge";

/* ==========================================================================
 * 領域元件 — V2升級計畫 11 §3
 *
 * 這幾個是「這個系統獨有、外面買不到」的，也是價值最高的。shadcn/ui 沒有
 * 也不可能有，所以全部自己寫（11 §7.1 裁示 ①）。
 * ======================================================================== */

/* -------------------------------------------------------------------------
 * Money — 金額
 *
 * 機構案的一筆錢會拆成兩段，而且**各走各的流程**（09 §1.4a）：
 *   個案自付額 case_payable          → 每天都要看到（報到收款、日報表、應收）
 *   機構請款額 institution_payable   → 行政主動點開合約才處理
 * 所以金額不能只印一個數字，要能表達這個關係。
 * ---------------------------------------------------------------------- */

export function Money({
  amount,
  className,
  /** 0 要顯示成 "—" 還是 "$0"。免收的場次用 dash 比較不會被誤讀成漏填。 */
  zero = "dash",
  size = "default",
  tone,
}: {
  amount: number | null | undefined;
  className?: string;
  zero?: "dash" | "zero";
  size?: "compact" | "default" | "display";
  tone?: "default" | "muted" | "danger" | "warn" | "done";
}) {
  const sizeClass = {
    compact: "text-compact",
    default: "text-xs",
    display: "text-display-md",
  }[size];
  const toneClass = {
    default: "text-ink",
    muted: "text-st-muted",
    danger: "text-st-danger",
    warn: "text-st-warn",
    done: "text-st-done",
  }[tone ?? "default"];

  if (amount == null || (amount === 0 && zero === "dash")) {
    return <span className={cn("tabular-nums text-st-muted", sizeClass, className)}>—</span>;
  }
  return (
    <span className={cn("font-semibold tabular-nums", sizeClass, toneClass, className)}>
      {amount < 0 && "−"}${Math.abs(amount).toLocaleString("en-US")}
    </span>
  );
}

/**
 * 一筆錢的兩段拆解。診間格、日報表、應收帳冊共用同一個呈現，
 * 行政才不會在三個畫面看到三種寫法。
 */
export function MoneySplit({
  casePayable,
  institutionPayable,
  className,
}: {
  casePayable: number | null | undefined;
  institutionPayable: number | null | undefined;
  className?: string;
}) {
  const hasInst = (institutionPayable ?? 0) > 0;
  if (!hasInst) return <Money amount={casePayable} className={className} />;
  return (
    <span className={cn("inline-flex items-baseline gap-1.5 text-compact", className)}>
      <span className="text-ink-3">自付</span>
      <Money amount={casePayable} size="compact" />
      <span className="text-st-muted">·</span>
      <span className="text-ink-3">機構</span>
      <Money amount={institutionPayable} size="compact" tone="muted" />
    </span>
  );
}

/* -------------------------------------------------------------------------
 * CaseRef — 個案識別
 *
 * 全站到處出現，但目前每頁格式都不一樣（有的顯示病歷號、有的顯示 temp_seq）。
 * 這裡也是心理師端**匿名規則**的唯一實作點：只隱藏個案姓名，心理師姓名
 * 照常顯示（v7 心理師端定案 ②）。
 * ---------------------------------------------------------------------- */

export function CaseRef({
  name,
  caseNumber,
  tempSeq,
  gender,
  isCouple,
  /** 心理師端的匿名檢視。只蓋掉姓名，其餘照常。 */
  anonymous,
  className,
}: {
  name: string | null;
  caseNumber?: string | null;
  tempSeq?: number | null;
  gender?: string | null;
  isCouple?: boolean;
  anonymous?: boolean;
  className?: string;
}) {
  // 兩段式病歷號（10 §3.2）：初診有到前只有 temp_seq，之後才有 8 碼病歷號。
  const ident = caseNumber ?? (tempSeq != null ? `#${String(tempSeq).padStart(4, "0")}` : null);
  const shown = anonymous ? "（不具名）" : (name ?? "—");

  return (
    <span className={cn("inline-flex items-baseline gap-1.5", className)}>
      <span className={cn("font-semibold text-ink", anonymous && "italic text-ink-3")}>
        {shown}
      </span>
      {gender && !anonymous && <span className="text-compact text-ink-3">{gender}</span>}
      {isCouple && (
        <Badge tone="active" size="mini">
          伴侶
        </Badge>
      )}
      {ident && <span className="ident text-[10px] text-ink-3">{ident}</span>}
    </span>
  );
}

/* -------------------------------------------------------------------------
 * QuotaBar — 額度三態
 *
 * 對應 10 §1 的三態恆等式：已預留 → 已預約 → 已使用。目前只在
 * institution/[id]/page.tsx 裡寫死一份，但額度會出現在個案列表、預約表單、
 * 診間格、合約面板四個地方。
 *
 * 顏色不是隨便挑的——沿用語意色，剛好構成一條時間軸：
 * 灰（還沒發生）→ 藍（正在進行）→ 綠（已完成）。
 * ---------------------------------------------------------------------- */

export function QuotaBar({
  used,
  booked,
  reserved,
  limit,
  label,
  className,
}: {
  /** 已使用（已報到）。 */
  used: number;
  /** 已預約（status='booked' 且非 no_show，即時算出來的，不落地）。 */
  booked: number;
  /** 已預留（掛上方案時全額進這裡）。 */
  reserved: number;
  limit: number;
  label?: ReactNode;
  className?: string;
}) {
  const safeLimit = Math.max(limit, 1);
  const pct = (n: number) => `${Math.max(0, (n / safeLimit) * 100)}%`;

  // 三態恆等式：已預留 ＋ 已預約 ＋ 已使用 ＝ 上限（10 §1）。
  // 「可用」不是第四種狀態——**已預留就是可用**。掛上方案時全額進 reserved，
  // 建立預約時 reserved→booked，報到時 booked→used。
  const sum = used + booked + reserved;
  const broken = sum !== limit;

  // 「剩最後一次」要讓行政一眼看到：這次之後就沒有額度了，下次起自動回落
  // 自費。收錯金額是這個畫面最貴的錯誤（11 §2.3 / v7 診間日曆定案 ⑤）。
  const isLast = reserved === 0 && booked > 0;

  return (
    <div className={className}>
      {label && (
        <div className="mb-1.5 flex items-baseline gap-2 text-xs">
          <span className="font-semibold text-ink">{label}</span>
          <span className="ml-auto tabular-nums text-ink-3">
            上限 {limit} 次 · 可用 {reserved}
          </span>
          {isLast && (
            <Badge tone="warn" size="mini">
              最後一次
            </Badge>
          )}
        </div>
      )}
      <div
        className="flex h-5 overflow-hidden rounded-badge border border-line bg-surface-3"
        role="img"
        aria-label={`額度 ${limit} 次：已使用 ${used}、已預約 ${booked}、可用 ${reserved}`}
      >
        <span style={{ width: pct(used) }} className="bg-st-done" />
        <span style={{ width: pct(booked) }} className="bg-st-active" />
        <span style={{ width: pct(reserved) }} className="bg-st-pending" />
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-ink-2">
        <Legend swatch="bg-st-done" label="已使用" n={used} />
        <Legend swatch="bg-st-active" label="已預約" n={booked} />
        <Legend swatch="bg-st-pending" label="可用" n={reserved} />
        {/* 恆等式破了就直說。這種偏差看不出來但會愈用愈偏（10 §3 的 bug 1、2
            就是這一類），寧可畫面上吵一句，也不要靜靜顯示一條錯的長條。 */}
        {broken && (
          <Badge tone="danger" size="mini" title={`三態合計 ${sum}，與上限 ${limit} 不符`}>
            額度對不上
          </Badge>
        )}
      </div>
    </div>
  );
}

function Legend({ swatch, label, n }: { swatch: string; label: string; n: number }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={cn("h-2 w-2 rounded-[2px]", swatch)} />
      {label}
      <b className="tabular-nums text-ink">{n}</b>
    </span>
  );
}

/* -------------------------------------------------------------------------
 * QuotaMeter — 單純的「已用 / 上限」計量條
 *
 * 跟 QuotaBar 不同：那個畫的是三態流轉（已預留→已預約→已使用），用在個案
 * 層級；這個只回答「這份合約的天花板還剩多少」，用在合約清單那種一列一份
 * 的密集畫面。
 *
 * 兩種尺度（07 §1.2）：次數池（15-45青壯 378 次／年）與金額池（國軍
 * $149,000／年）——扣的東西不同，所以標籤要跟著換。
 * ---------------------------------------------------------------------- */

export function QuotaMeter({
  used,
  limit,
  unit = "count",
  className,
}: {
  used: number;
  limit: number;
  /** count 次數 / amount 金額 */
  unit?: string;
  className?: string;
}) {
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  const fmt = (n: number) =>
    unit === "amount" ? `$${n.toLocaleString("en-US")}` : `${n}`;
  // 快見底要看得出來——這是行政真正要盯的訊號（09 §3.3 國軍面板「快見底預警」）
  const tone = pct >= 90 ? "bg-st-danger" : pct >= 70 ? "bg-st-warn" : "bg-st-active";

  return (
    <div className={cn("min-w-[7rem]", className)}>
      <div className="flex items-baseline gap-1 text-[10px] tabular-nums">
        <span className="font-semibold text-ink">{fmt(used)}</span>
        <span className="text-st-muted">/ {fmt(limit)}</span>
        <span className={cn("ml-auto font-semibold", pct >= 90 ? "text-st-danger" : "text-ink-3")}>
          {pct.toFixed(0)}%
        </span>
      </div>
      <div className="mt-0.5 h-1.5 overflow-hidden rounded-badge bg-surface-3">
        <span className={cn("block h-full", tone)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
