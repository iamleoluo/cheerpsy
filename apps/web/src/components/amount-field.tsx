"use client";

import { useSession } from "next-auth/react";

/**
 * 誰能建立／編輯預約，誰就能填金額：心理師填自己的、行政與管理員填任何人的。
 * 隔離的單位是心理師，不是欄位；後端另外保證心理師碰不到別人的預約。會計不能建立預約，所以不顯示。
 */
export function useCanEditAmount(): boolean {
  const { data } = useSession();
  const role = (data?.user as any)?.role;
  return role === "admin" || role === "staff" || role === "therapist";
}

/**
 * 預約金額。自費預約必填（免費請填 0）；機構預約的金額由方案帶出，不必填。
 * 只是預約上的數字：個案這次要付的錢會顯示在 Google 日曆事件標題結尾（0 不顯示），
 * 不會產生核銷、流水或對帳。
 */
export function AmountField({
  value,
  onChange,
  className = "",
  required = false,
}: {
  value: string;
  onChange: (v: string) => void;
  className?: string;
  required?: boolean;
}) {
  const can = useCanEditAmount();
  if (!can) return null;
  return (
    <label className={`block text-sm ${className}`}>
      <span className="mb-1 block text-xs font-medium text-gray-700">{required ? "金額（必填，免費請填 0）" : "金額"}</span>
      <input
        type="number"
        inputMode="decimal"
        min={0}
        max={9999999}
        step="any"
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="例如 1500"
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
      />
      <span className="mt-1 block text-xs text-gray-400">會顯示在 Google 日曆事件標題結尾；0 元不顯示。</span>
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
