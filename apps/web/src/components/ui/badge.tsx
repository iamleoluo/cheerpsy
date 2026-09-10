import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

/**
 * 狀態徽章 — V2升級計畫 11 §2.2。
 *
 * 六個語意各自對應一種顏色，**沒有第七種**。這是為了修掉 11 §1.1 掃出來的
 * 問題：同一個「未收 / 未到 / 逾期」語意在既有頁面散成 5 個紅色階
 * （red-600 38 次、red-500 32 次、rose-600 31 次、rose-500 18 次、red-700 18 次），
 * 綠 4 種、琥珀 5 種，總計 2,628 處寫死的色階。
 *
 * 選 tone 的判準是**這件事現在怎麼了**，不是它長什麼樣：
 *   pending 還沒發生 · active 正在進行 · done 成功結束
 *   warn 要注意但沒壞 · danger 壞掉了 · muted 今天不用再碰
 */
const badge = cva(
  "inline-flex items-center gap-1 whitespace-nowrap rounded-badge font-bold leading-tight",
  {
    variants: {
      tone: {
        pending: "bg-st-pending-bg text-st-pending",
        active: "bg-st-active-bg text-st-active",
        done: "bg-st-done-bg text-st-done",
        warn: "bg-st-warn-bg text-st-warn",
        danger: "bg-st-danger-bg text-st-danger",
        /** 已完成／已結案。刻意做成外框而非填色——它要**退到背景去**。 */
        muted: "border border-st-muted/50 bg-transparent text-st-muted",
      },
      size: {
        /** 診間格右上角的狀態徽章。 */
        mini: "px-1.5 py-px text-[9px]",
        sm: "px-2 py-0.5 text-[10px]",
        md: "px-2.5 py-0.5 text-[11px]",
      },
    },
    defaultVariants: { tone: "pending", size: "sm" },
  },
);

export type BadgeTone = NonNullable<VariantProps<typeof badge>["tone"]>;

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badge> {}

export function Badge({ className, tone, size, ...props }: BadgeProps) {
  return <span className={cn(badge({ tone, size }), className)} {...props} />;
}

/* ------------------------------------------------------------------ *
 * 領域狀態 → tone 的對應表
 *
 * 集中在這裡，而不是散在每個頁面各寫一次三元運算式。後端狀態值改名時
 * 只有這裡要動；漏掉的狀態會落到 pending 而不是整個畫面沒顏色。
 * ------------------------------------------------------------------ */

/** 報到狀態（appointments.check_in_status）。 */
export const checkInTone: Record<string, BadgeTone> = {
  pending: "pending",
  arrived: "active",
  no_show: "danger",
};

/** 收款狀態（session_records.payment_status）。 */
export const paymentTone: Record<string, BadgeTone> = {
  unpaid: "danger",
  partial: "warn",
  paid: "done",
  claimed: "done",
  void: "muted",
};

/** 核銷案狀態（inst_claim_cases.status ／ claim_batches.status）。 */
export const claimTone: Record<string, BadgeTone> = {
  collecting: "active",
  ready: "active",
  submitted: "pending",
  received: "done",
  paid: "done",
  returned: "warn",
  void: "muted",
};

/** 個案狀態（cases.status）。 */
export const caseTone: Record<string, BadgeTone> = {
  initial: "pending",
  ongoing: "active",
  churn_risk: "warn",
  closed: "muted",
};
