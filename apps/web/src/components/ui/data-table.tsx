"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * 表格 — V2升級計畫 11 §3。取代既有 54 份手寫的 `<table>`。
 *
 * 為什麼值得抽成元件：這 54 份裡表頭字級、padding、右對齊規則、hover 顏色、
 * 空白呈現全部不一樣，而且沒有一份對數字做 tabular-nums——金額欄位對不齊，
 * 掃不動（11 §2.5）。
 *
 * 刻意做成**欄位定義驅動**而不是 children 驅動：對齊與密度才有辦法由元件
 * 統一決定，而不是靠每個呼叫端記得加 class。
 */

/**
 * 注意：`cell` 是函式，所以**用到 DataTable 的頁面必須是 Client Component**
 * （函式無法跨 server→client 邊界）。既有 33 頁全部都已經是 "use client"，
 * 所以實務上不構成限制，但新開的頁面要記得加。
 */
export interface Column<T> {
  key: string;
  header: ReactNode;
  /** 一列渲染成什麼。 */
  cell: (row: T, index: number) => ReactNode;
  /** 數字欄請用 "right"——會一併套用 tabular-nums。 */
  align?: "left" | "center" | "right";
  /** 例如 "w-28"、"min-w-[10rem]"。 */
  width?: string;
  /** 不要換行（日期、編號、金額）。 */
  nowrap?: boolean;
}

export interface DataTableProps<T> {
  columns: readonly Column<T>[];
  rows: readonly T[];
  rowKey: (row: T, index: number) => string | number;
  /** 整列可點時給這個；會一併加上 hover 與鍵盤可及性。 */
  onRowClick?: (row: T, index: number) => void;
  /** 依資料回傳額外 class，例如「已完成整格轉灰」。 */
  rowClassName?: (row: T, index: number) => string | undefined;
  /** 置底統計列（合計）。 */
  footer?: ReactNode;
  /** compact 給流水帳這種一屏要塞得下一整天的畫面。 */
  density?: "compact" | "default";
  className?: string;
}

const alignClass = {
  left: "text-left",
  center: "text-center",
  right: "text-right tabular-nums",
} as const;

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  rowClassName,
  footer,
  density = "default",
  className,
}: DataTableProps<T>) {
  const cellPad = density === "compact" ? "px-2.5 py-1.5" : "px-3 py-2.5";
  const cellText = density === "compact" ? "text-compact" : "text-xs";

  return (
    // 寬表格在自己的容器裡橫向捲動，頁面本體永遠不左右捲。
    <div className={cn("overflow-x-auto rounded-card border border-line bg-surface", className)}>
      <table className="w-full border-collapse">
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                className={cn(
                  "border-b border-line bg-surface-2 font-medium uppercase tracking-wide text-ink-3",
                  "whitespace-nowrap text-[10px]",
                  cellPad,
                  alignClass[c.align ?? "left"],
                  c.width,
                )}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={rowKey(row, i)}
              onClick={onRowClick ? () => onRowClick(row, i) : undefined}
              onKeyDown={
                onRowClick
                  ? (e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onRowClick(row, i);
                      }
                    }
                  : undefined
              }
              tabIndex={onRowClick ? 0 : undefined}
              className={cn(
                "border-b border-line last:border-b-0",
                onRowClick &&
                  "cursor-pointer hover:bg-accent-soft/50 focus-visible:bg-accent-soft/50 focus-visible:outline-none",
                rowClassName?.(row, i),
              )}
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={cn(
                    "align-top text-ink-2",
                    cellPad,
                    cellText,
                    alignClass[c.align ?? "left"],
                    c.nowrap && "whitespace-nowrap",
                  )}
                >
                  {c.cell(row, i)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {footer && (
          <tfoot>
            <tr className="border-t-2 border-line-2 bg-surface-2 font-bold text-ink">
              {footer}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}
