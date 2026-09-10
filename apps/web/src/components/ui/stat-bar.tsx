"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { cn } from "@/lib/cn";
import { Money } from "./domain";

/**
 * 頂部即時統計列 — 對應 v7 診間日曆的「應到 / 已報到 / 未到 / 待報到 /
 * 今日已收 / 尚待收款」。
 *
 * 關鍵是 `href`：v7 營運總覽定案寫著「每張 KPI 卡**可點擊**，帶著已套用的
 * 篩選條件跳到對應清單」——例如「未收 $52,200」要能直接跳到應收帳冊且已篩
 * 未收。既有 dashboard 的四張卡片只是數字，點了什麼都沒有。
 */

export interface Stat {
  label: string;
  value: number | string;
  /** 給了就當金額渲染（含 $ 與千分位）。 */
  money?: boolean;
  /** 次要說明，例如「已收 $196,400 · 未收 $52,200」。 */
  sub?: ReactNode;
  /** 帶著篩選條件跳過去。 */
  href?: string;
  tone?: "default" | "warn" | "danger" | "done";
}

const toneClass = {
  default: "text-ink",
  warn: "text-st-warn",
  danger: "text-st-danger",
  done: "text-st-done",
} as const;

export function StatBar({ stats, className }: { stats: readonly Stat[]; className?: string }) {
  return (
    <div
      className={cn(
        "grid grid-cols-2 divide-x divide-y divide-line overflow-hidden rounded-card border border-line bg-surface",
        "sm:grid-cols-3 sm:divide-y-0 lg:grid-cols-6",
        className,
      )}
    >
      {stats.map((s) => {
        const body = (
          <>
            <div className="text-[10px] font-medium uppercase tracking-wide text-ink-3">
              {s.label}
            </div>
            <div className={cn("mt-1 text-display-sm tabular-nums", toneClass[s.tone ?? "default"])}>
              {s.money && typeof s.value === "number" ? (
                <Money amount={s.value} size="display" zero="zero" tone={s.tone === "default" ? undefined : s.tone} />
              ) : (
                s.value
              )}
            </div>
            {s.sub && <div className="mt-0.5 text-[10px] leading-snug text-ink-3">{s.sub}</div>}
          </>
        );

        return s.href ? (
          <Link
            key={s.label}
            href={s.href}
            className="px-3.5 py-3 transition-colors hover:bg-accent-soft/50 focus-visible:bg-accent-soft/50 focus-visible:outline-none"
          >
            {body}
          </Link>
        ) : (
          <div key={s.label} className="px-3.5 py-3">
            {body}
          </div>
        );
      })}
    </div>
  );
}

/**
 * 篩選列。既有頁面每個都自己刻一排 select + input。
 */
export function FilterBar({
  children,
  actions,
  className,
}: {
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-card border border-line bg-surface px-3 py-2.5",
        className,
      )}
    >
      {children}
      {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
    </div>
  );
}
