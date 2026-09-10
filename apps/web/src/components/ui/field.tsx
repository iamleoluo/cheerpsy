"use client";

import { forwardRef, useId } from "react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * 表單欄位 — V2升級計畫 11 §3。
 *
 * 既有頁面每個 input 都自己寫一次 label + border + focus ring，而且多數
 * **沒有把 label 綁到 input**（沒有 htmlFor/id），點標籤不會聚焦，螢幕閱讀器
 * 也讀不出這格是什麼。這裡用 useId 自動綁定，呼叫端不用記。
 */

const controlClass =
  "w-full rounded-control border border-line-2 bg-surface px-2.5 py-1.5 text-xs text-ink " +
  "placeholder:text-ink-3 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25 " +
  "disabled:bg-surface-2 disabled:text-ink-3";

export function Field({
  label,
  hint,
  error,
  required,
  children,
  className,
}: {
  label: ReactNode;
  /** 欄位下方的說明。放規則（「僅匯款需填」），不是重複 label。 */
  hint?: ReactNode;
  error?: string;
  required?: boolean;
  children: (props: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => ReactNode;
  className?: string;
}) {
  const id = useId();
  const describedBy = error ? `${id}-err` : hint ? `${id}-hint` : undefined;

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <label htmlFor={id} className="text-[11px] font-medium text-ink-2">
        {label}
        {required && <span className="ml-0.5 text-st-danger">*</span>}
      </label>
      {children({ id, "aria-describedby": describedBy, "aria-invalid": !!error || undefined })}
      {error ? (
        <p id={`${id}-err`} className="text-[10px] text-st-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-[10px] text-ink-3">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input ref={ref} className={cn(controlClass, "tabular-nums", className)} {...props} />
  ),
);
Input.displayName = "Input";

export const Select = forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...props }, ref) => (
    <select ref={ref} className={cn(controlClass, "h-[30px] py-0", className)} {...props} />
  ),
);
Select.displayName = "Select";

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea ref={ref} className={cn(controlClass, "min-h-[4rem] leading-relaxed", className)} {...props} />
));
Textarea.displayName = "Textarea";
