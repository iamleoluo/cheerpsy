"use client";

import type { ReactNode } from "react";
import { ApiError } from "@/lib/client-api";
import { Button } from "./button";
import { cn } from "@/lib/cn";

/**
 * 載入 / 錯誤 / 空白三態 — V2升級計畫 11 §5。
 *
 * 這組元件存在的理由是一條正確性要求，不是體驗優化：既有頁面多數寫
 * `.catch(() => setRows([]))`，**把失敗偽裝成沒資料**。在應收帳冊上，
 * 行政看到空清單會以為今天都收完了——那是謊報，不是體驗不好。
 *
 * <AsyncBoundary> 強迫三件事都要有交代：
 *   載入 → 骨架屏（不是空白，也不是「Loading...」）
 *   錯誤 → 說清楚哪裡壞了 ＋ 可以重試
 *   空白 → 說清楚為什麼空的 ＋ 下一步可以做什麼
 */

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn("animate-pulse rounded-control bg-surface-2", className)}
      aria-hidden
    />
  );
}

/** 表格骨架。列數預設 5，跟多數清單首屏的量差不多。 */
export function TableSkeleton({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2" role="status" aria-label="載入中">
      <Skeleton className="h-9" />
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="flex gap-2">
          {Array.from({ length: cols }, (_, c) => (
            <Skeleton key={c} className={cn("h-8 flex-1", c === 0 && "max-w-[28%]")} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  /** 為什麼是空的。空清單最讓人不安的是分不清「沒資料」還是「壞掉了」。 */
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-14 text-center">
      <p className="text-sm font-medium text-ink-2">{title}</p>
      {hint && <p className="max-w-sm text-xs leading-relaxed text-ink-3">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const api = error instanceof ApiError ? error : undefined;

  // 訊息要說「怎麼辦」，不是只說「錯了」。
  const { title, hint } =
    api?.status === 0
      ? { title: "連不上伺服器", hint: "請確認網路連線，或後端服務是否已啟動。" }
      : api?.isForbidden
        ? { title: "沒有權限查看這筆資料", hint: "這個功能限定其他角色使用。若你認為這是設定錯誤，請聯繫管理員。" }
        : api?.status === 404
          ? { title: "找不到資料", hint: "這筆資料可能已被刪除，或連結已經過期。" }
          : api && api.status >= 500
            ? { title: "伺服器發生錯誤", hint: error.message }
            : { title: "載入失敗", hint: error.message };

  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center gap-2 rounded-card border border-st-danger/25 bg-st-danger-bg/40 px-4 py-10 text-center"
    >
      <p className="text-sm font-semibold text-st-danger">{title}</p>
      <p className="max-w-md text-xs leading-relaxed text-ink-2">{hint}</p>
      {onRetry && (
        <Button size="sm" onClick={onRetry} className="mt-2">
          重試
        </Button>
      )}
    </div>
  );
}

export interface AsyncBoundaryProps<T> {
  /** 直接把 useApi() 的回傳攤進來即可。 */
  loading: boolean;
  error: Error | undefined;
  data: T | undefined;
  onRetry?: () => void;
  /** 自訂載入態；預設是表格骨架。 */
  skeleton?: ReactNode;
  /** data 為空陣列時顯示。給了才會判斷「空」，否則空陣列照樣交給 children。 */
  empty?: ReactNode;
  children: (data: T) => ReactNode;
}

export function AsyncBoundary<T>({
  loading,
  error,
  data,
  onRetry,
  skeleton,
  empty,
  children,
}: AsyncBoundaryProps<T>) {
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (loading || data === undefined) return <>{skeleton ?? <TableSkeleton />}</>;
  if (empty && Array.isArray(data) && data.length === 0) return <>{empty}</>;
  return <>{children(data)}</>;
}
