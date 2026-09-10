"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * 時間軸網格 — V2升級計畫 11 §3。
 *
 * 08:00–22:00、30 分半格（v7 診間日曆定案 ②）。診間日曆、我的班表、預約週
 * 檢視、5F 雲燈教室**四個地方都要這個東西**，目前各寫各的，所以四個畫面的
 * 格線對不齊。
 *
 * 兩個既有實作沒做對的事：
 *   ① **跨格用 rowSpan**。既有 /rooms 是把同一筆預約在它涵蓋的每一格都畫
 *      一次，所以 90 分鐘的伴侶案會長出三個一模一樣的方塊，看起來像三筆。
 *   ② **空白格可點**（v7 定案 ⑨：點空白格直接新增預約）。既有實作空白格
 *      完全沒有互動。
 */

export interface TimeGridColumn {
  id: number | string;
  label: ReactNode;
  /** 欄標題下方的小字，例如「2F · 晤談」。 */
  sub?: ReactNode;
}

export interface TimeGridItem {
  id: number | string;
  columnId: number | string;
  /** 距離 00:00 的分鐘數。 */
  startMin: number;
  endMin: number;
}

export interface TimeGridProps<T extends TimeGridItem> {
  columns: readonly TimeGridColumn[];
  items: readonly T[];
  renderItem: (item: T) => ReactNode;
  onEmptyClick?: (columnId: number | string, startMin: number) => void;
  /** 預設 8（08:00）。 */
  startHour?: number;
  /** 預設 22（22:00）。 */
  endHour?: number;
  stepMin?: number;
  /** 每欄最小寬度，避免欄位被壓扁到看不懂。 */
  minColumnWidth?: string;
  className?: string;
}

const fmt = (min: number) =>
  `${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;

export function TimeGrid<T extends TimeGridItem>({
  columns,
  items,
  renderItem,
  onEmptyClick,
  startHour = 8,
  endHour = 22,
  stepMin = 30,
  minColumnWidth = "7.5rem",
  className,
}: TimeGridProps<T>) {
  const gridStart = startHour * 60;
  const gridEnd = endHour * 60;
  const slots: number[] = [];
  for (let m = gridStart; m < gridEnd; m += stepMin) slots.push(m);

  // 每一格屬於誰：先算好起始格與要跨幾格，再標記被蓋住的格子不要再畫 <td>。
  const startAt = new Map<string, { item: T; span: number }>();
  const covered = new Set<string>();
  const key = (col: number | string, min: number) => `${col}@${min}`;

  for (const item of items) {
    // 貼齊格線：早於 08:00 或晚於 22:00 的預約仍要看得到，只是被夾到邊界。
    const s = Math.max(gridStart, Math.floor(item.startMin / stepMin) * stepMin);
    const e = Math.min(gridEnd, Math.ceil(item.endMin / stepMin) * stepMin);
    if (e <= gridStart || s >= gridEnd) continue;
    const span = Math.max(1, (e - s) / stepMin);
    startAt.set(key(item.columnId, s), { item, span });
    for (let i = 1; i < span; i++) covered.add(key(item.columnId, s + i * stepMin));
  }

  return (
    <div className={cn("overflow-x-auto rounded-card border border-line bg-surface", className)}>
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 w-14 border-b border-r border-line bg-surface-2 px-2 py-2 text-left text-[10px] font-medium text-ink-3">
              時段
            </th>
            {columns.map((c) => (
              <th
                key={c.id}
                scope="col"
                style={{ minWidth: minColumnWidth }}
                className="border-b border-r border-line bg-surface-2 px-2 py-2 text-center last:border-r-0"
              >
                <div className="text-[11px] font-bold leading-tight text-ink">{c.label}</div>
                {c.sub && <div className="text-[9.5px] font-normal text-ink-3">{c.sub}</div>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {slots.map((min) => {
            const onHour = min % 60 === 0;
            return (
              <tr key={min}>
                <td
                  className={cn(
                    "sticky left-0 z-10 whitespace-nowrap border-r bg-surface px-2 py-1 text-[10px] tabular-nums",
                    // 半點的線做成虛線，整點才是實線——一眼看得出小時的邊界。
                    onHour ? "border-b border-line text-ink-2" : "border-b border-dashed border-line text-ink-3",
                  )}
                >
                  {onHour ? fmt(min) : ""}
                </td>
                {columns.map((c) => {
                  const k = key(c.id, min);
                  if (covered.has(k)) return null;
                  const hit = startAt.get(k);
                  if (hit) {
                    return (
                      <td
                        key={c.id}
                        rowSpan={hit.span}
                        className="border-b border-r border-line p-0.5 align-top last:border-r-0"
                      >
                        {renderItem(hit.item)}
                      </td>
                    );
                  }
                  return (
                    <td
                      key={c.id}
                      onClick={onEmptyClick ? () => onEmptyClick(c.id, min) : undefined}
                      className={cn(
                        "border-r last:border-r-0",
                        onHour ? "border-b border-line" : "border-b border-dashed border-line",
                        onEmptyClick &&
                          "group cursor-pointer hover:bg-accent-soft/60 focus-within:bg-accent-soft/60",
                      )}
                    >
                      {onEmptyClick && (
                        <button
                          type="button"
                          tabIndex={-1}
                          aria-label={`在 ${fmt(min)} 新增預約`}
                          className="block h-6 w-full text-center text-[11px] text-transparent group-hover:text-accent"
                        >
                          ＋
                        </button>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** 把 ISO 時間字串換成「距離當天 00:00 的分鐘數」。 */
export function minutesOfDay(iso: string): number {
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes();
}
