"use client";

import * as Dialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Button } from "./button";

/**
 * 彈窗與側邊抽屜 — V2升級計畫 11 §3。取代既有 40 個手寫的 `fixed inset-0`。
 *
 * 依 11 §7.1 裁示 ①：Modal / Drawer / Select 這種「難寫對」的走 shadcn 路線
 * （Radix 底），因為焦點鎖定、Esc 關閉、捲動鎖、aria 這些自己寫幾乎一定漏。
 * 既有那 40 個都沒有焦點鎖定，鍵盤使用者 Tab 會跑到彈窗後面的頁面去。
 *
 * 但**版面與密度自己控制**——不讓元件庫的預設 padding 把 v7 的密度撐開。
 */

export interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  /** 標題下方的一行說明，例如「機構：衛生局 15-45青壯（2/3）」。 */
  hint?: ReactNode;
  children: ReactNode;
  /** 置底操作列。慣例是左取消、右主要動作。 */
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
}

const sizeClass = {
  sm: "max-w-md",
  md: "max-w-xl",
  lg: "max-w-3xl",
} as const;

export function Modal({
  open,
  onOpenChange,
  title,
  hint,
  children,
  footer,
  size = "md",
}: ModalProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink/40 backdrop-blur-[1px]" />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2",
            "max-h-[calc(100vh-4rem)] overflow-hidden rounded-card border border-line bg-surface shadow-modal",
            "flex flex-col focus:outline-none",
            sizeClass[size],
          )}
        >
          <div className="flex items-start gap-3 border-b border-line px-4 py-3">
            <div className="min-w-0 flex-1">
              <Dialog.Title className="text-sm font-bold text-ink">{title}</Dialog.Title>
              {hint && (
                <Dialog.Description className="mt-0.5 text-xs leading-relaxed text-ink-3">
                  {hint}
                </Dialog.Description>
              )}
            </div>
            <Dialog.Close asChild>
              <Button variant="ghost" size="sm" aria-label="關閉" className="-mr-1 -mt-0.5 px-2">
                ✕
              </Button>
            </Dialog.Close>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">{children}</div>

          {footer && (
            <div className="flex items-center justify-end gap-2 border-t border-line bg-surface-2 px-4 py-3">
              {footer}
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/**
 * 側邊抽屜。給「看細節但不想離開清單」的情境——個案詳情、預約明細、
 * 診間格點開後的完整資料。
 */
export function Drawer({
  open,
  onOpenChange,
  title,
  hint,
  children,
  footer,
}: Omit<ModalProps, "size">) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink/30" />
        <Dialog.Content
          className={cn(
            "fixed right-0 top-0 z-50 flex h-full w-[min(30rem,100vw)] flex-col",
            "border-l border-line bg-surface shadow-modal focus:outline-none",
          )}
        >
          <div className="flex items-start gap-3 border-b border-line px-4 py-3">
            <div className="min-w-0 flex-1">
              <Dialog.Title className="text-sm font-bold text-ink">{title}</Dialog.Title>
              {hint && (
                <Dialog.Description className="mt-0.5 text-xs text-ink-3">{hint}</Dialog.Description>
              )}
            </div>
            <Dialog.Close asChild>
              <Button variant="ghost" size="sm" aria-label="關閉" className="-mr-1 -mt-0.5 px-2">
                ✕
              </Button>
            </Dialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">{children}</div>
          {footer && (
            <div className="flex items-center justify-end gap-2 border-t border-line bg-surface-2 px-4 py-3">
              {footer}
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
