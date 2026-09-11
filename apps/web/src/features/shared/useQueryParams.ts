"use client";

import { useEffect, useState } from "react";

/**
 * 讀網址上的查詢參數，掛載後讀一次。
 *
 * 為什麼不是 `useState(() => new URLSearchParams(location.search))`：那支初始化
 * 函式在伺服器與瀏覽器各會跑一次，伺服器上沒有 window，兩邊算出不同的初值就是
 * hydration 不一致。
 *
 * 為什麼不是 `useSearchParams()`：Next 14 要求它包在 Suspense 邊界裡，否則整條
 * 路由會被推去動態渲染並在 build 時警告。為了一個參數把整頁拆成兩個元件不划算。
 *
 * 回傳 null 代表「還沒讀到」（第一次渲染），不是「沒有參數」——呼叫端要分得開，
 * 才不會在第一幀就用預設值覆蓋掉網址帶來的值。
 */
export function useQueryParams(): URLSearchParams | null {
  const [params, setParams] = useState<URLSearchParams | null>(null);
  useEffect(() => {
    setParams(new URLSearchParams(window.location.search));
  }, []);
  return params;
}

/** `YYYY-MM-DD` → 當地時間的當天零點。格式不對回 null。 */
export function parseLocalDate(value: string | null | undefined): Date | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  // 不用 new Date("2026-09-11")——那會被當成 UTC 午夜，在台北會變成前一天早上八點
  const d = new Date(`${value}T00:00:00`);
  return Number.isNaN(d.getTime()) ? null : d;
}
