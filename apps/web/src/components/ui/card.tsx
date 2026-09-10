import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * 卡片 — V2升級計畫 11 §3。
 *
 * 取代既有 30 種各自手寫的 `rounded-lg border border-gray-200 bg-white p-4`。
 *
 * 「不是每個東西都是卡片」：邊框、填色、圓角、陰影各自都在說「這是一個獨立
 * 物件」，全部蓋在每個區塊上會把層級壓平。所以這裡只有一階陰影，需要被抬起來
 * 的那一個才加 `elevated`。
 */

export function Card({
  className,
  elevated,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { elevated?: boolean }) {
  return (
    <div
      className={cn(
        "rounded-card border border-line bg-surface",
        elevated && "shadow-2",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({
  title,
  hint,
  actions,
  className,
}: {
  title: ReactNode;
  /** 副標。放「這頁在做什麼」，不是重複標題。 */
  hint?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-4 py-3",
        className,
      )}
    >
      <h3 className="text-sm font-bold text-ink">{title}</h3>
      {hint && <span className="text-xs text-ink-3">{hint}</span>}
      {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function CardBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-4", className)} {...props} />;
}

/**
 * 分頁列。既有頁面每個都自己刻一份 border-b + map + 三元運算式。
 */
export function Tabs<T extends string>({
  value,
  onChange,
  tabs,
  className,
}: {
  value: T;
  onChange: (v: T) => void;
  tabs: readonly { key: T; label: ReactNode; count?: number }[];
  className?: string;
}) {
  return (
    <div className={cn("flex gap-1 border-b border-line", className)} role="tablist">
      {tabs.map((t) => {
        const on = t.key === value;
        return (
          <button
            key={t.key}
            role="tab"
            aria-selected={on}
            onClick={() => onChange(t.key)}
            className={cn(
              "-mb-px flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-xs font-medium transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
              on
                ? "border-accent text-accent"
                : "border-transparent text-ink-3 hover:text-ink-2",
            )}
          >
            {t.label}
            {t.count !== undefined && (
              <span
                className={cn(
                  "rounded-badge px-1.5 py-px text-[10px] tabular-nums",
                  on ? "bg-accent-soft text-accent" : "bg-surface-2 text-ink-3",
                )}
              >
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
