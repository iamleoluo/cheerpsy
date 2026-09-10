"use client";

import { forwardRef } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

/**
 * V2升級計畫 11 §2.1 的核心規則就寫在這個檔案的 variant 清單裡：
 * **顏色只表達狀態，不表達操作**（v7 診間日曆定案 ③：「已到／未到按鈕改為
 * 中性黑白，狀態改由右上角小圖示標色」）。
 *
 * 在一天要掃 38 格的診間日曆上，如果按鈕也有顏色，眼睛就沒辦法用顏色掃狀態。
 * 這也是為什麼這裡**沒有紅色實心的刪除鍵**——破壞性操作用 `danger` variant，
 * 它是中性外框 ＋ 危險色文字，紅色留給「未到 / 未收」這種真正的狀態。
 *
 * 既有 33 頁的 73 個 bg-primary-600 按鈕不在此列，P0 已裁示不回頭改；
 * 它們會在各自的頁面被重寫時（P2–P5）自然換掉。
 */
const button = cva(
  "inline-flex items-center justify-center gap-1.5 font-medium whitespace-nowrap " +
    "transition-colors disabled:pointer-events-none disabled:opacity-50 " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1",
  {
    variants: {
      variant: {
        /** 預設。清單列、日曆格裡的操作鍵一律用這個。 */
        neutral:
          "border border-line-2 bg-surface text-ink-2 hover:bg-ink hover:text-surface hover:border-ink",
        /** 這一格／這一列裡最主要的那個動作（v7 的 .mini2.hi）。 */
        solid: "border border-ink bg-ink text-surface hover:bg-ink-2 hover:border-ink-2",
        /** 整頁層級的主要動作，一個畫面最多一個。 */
        accent: "border border-accent bg-accent text-accent-fg hover:bg-st-active hover:border-st-active",
        /** 次要、不需要邊框的動作（取消、關閉）。 */
        ghost: "border border-transparent text-ink-2 hover:bg-surface-2",
        /** 破壞性操作。中性外框，只有文字帶危險色——不做紅色實心。 */
        danger:
          "border border-st-danger/40 bg-surface text-st-danger hover:bg-st-danger hover:text-surface hover:border-st-danger",
      },
      size: {
        /** 診間格、表格列內的操作鍵。 */
        mini: "h-6 rounded-badge px-2 text-[10px]",
        sm: "h-8 rounded-control px-3 text-xs",
        md: "h-9 rounded-control px-4 text-sm",
        lg: "h-11 rounded-control px-6 text-sm",
      },
    },
    defaultVariants: { variant: "neutral", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof button> {
  /** 進行中：鎖住按鈕並顯示狀態，避免重複送出。 */
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, disabled, children, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(button({ variant, size }), className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && (
        <span
          aria-hidden
          className="h-3 w-3 animate-spin rounded-full border-[1.5px] border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  ),
);
Button.displayName = "Button";
