"use client";

import { useSession } from "next-auth/react";

/** 只有管理員與行政能填金額；其他角色看不到這個欄位，後端也不會存他們送的值。 */
export function useCanEditAmount(): boolean {
  const { data } = useSession();
  const role = (data?.user as any)?.role;
  return role === "admin" || role === "staff";
}

/**
 * 預約金額（選填）。只是預約上的一個數字，會顯示在 Google 日曆事件的標題結尾；
 * 不是記帳，不會產生收款、結算或任何帳務紀錄。空白＝沒有金額。
 */
export function AmountField({
  value,
  onChange,
  className = "",
}: {
  value: string;
  onChange: (v: string) => void;
  className?: string;
}) {
  const can = useCanEditAmount();
  if (!can) return null;
  return (
    <label className={`block text-sm ${className}`}>
      <span className="mb-1 block text-xs font-medium text-gray-700">金額（選填）</span>
      <input
        type="number"
        inputMode="decimal"
        min={0}
        max={9999999}
        step="any"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="例如 1500"
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
      />
      <span className="mt-1 block text-xs text-gray-400">會顯示在 Google 日曆事件標題結尾；不填就不顯示。</span>
    </label>
  );
}

/** 表單用：空白或不是有效數字回 undefined（建立時不送）；否則回數字。 */
export function parseAmount(v: string): number | undefined {
  const t = v.trim();
  if (!t) return undefined;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 ? n : undefined;
}
