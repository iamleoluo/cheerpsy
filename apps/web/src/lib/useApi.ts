"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSession, signIn } from "next-auth/react";
import { ApiError, clientFetch } from "@/lib/client-api";

/**
 * 取資料的唯一入口 — V2升級計畫 11 §5。
 *
 * 在這之前全站是 204 次裸 clientFetch ＋ 669 個 useState，每頁自己管
 * loading / error / data 三個狀態，而且多數寫成 `.catch(() => setRows([]))`
 * ——**把失敗偽裝成沒資料**。在財務畫面上這等於謊報：行政看到應收帳冊
 * 空的，會以為今天都收完了。
 *
 * 這支 hook 做四件事：
 *   1. 三態一次給齊（loading / error / data），交給 <AsyncBoundary> 呈現
 *   2. 401 統一導回登入，並記住原本要去哪
 *   3. 同一個 path 併發去重（多個元件同時掛載不會打三次）
 *   4. refetch() 讓「重試」與「改完資料重載」共用同一條路
 *
 * 刻意不引入 SWR / react-query：真正的痛點是上面四件事，不是快取策略；
 * 少一個相依、少一套心智模型。之後若真的需要背景重驗證再換不遲。
 */

type State<T> = {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
};

/** 同一輪事件迴圈內，相同 key 的請求共用一個 promise。 */
const inflight = new Map<string, Promise<unknown>>();

function dedupe<T>(key: string, run: () => Promise<T>): Promise<T> {
  const existing = inflight.get(key);
  if (existing) return existing as Promise<T>;
  const p = run().finally(() => inflight.delete(key));
  inflight.set(key, p);
  return p;
}

export interface UseApiOptions {
  /** false 時不發請求（例如還在等使用者選日期）。預設 true。 */
  enabled?: boolean;
}

export function useApi<T>(
  path: string | null,
  { enabled = true }: UseApiOptions = {},
) {
  const { data: session } = useSession();
  const token = (session?.user as { accessToken?: string } | undefined)?.accessToken;

  const [state, setState] = useState<State<T>>({
    data: undefined,
    error: undefined,
    loading: true,
  });

  // 元件已卸載後不要 setState，也避免慢的舊請求覆蓋掉快的新請求。
  const reqId = useRef(0);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const run = useCallback(async () => {
    if (!token || !path || !enabled) return;
    const id = ++reqId.current;
    setState((s) => ({ ...s, loading: true, error: undefined }));
    try {
      const data = await dedupe(`${token.slice(-8)}:${path}`, () =>
        clientFetch(path, token),
      );
      if (!alive.current || id !== reqId.current) return;
      setState({ data: data as T, error: undefined, loading: false });
    } catch (e) {
      if (!alive.current || id !== reqId.current) return;
      const err = e as Error;
      // token 過期：導回登入並記住原本要去哪，而不是讓畫面卡在載入中。
      if (err instanceof ApiError && err.isAuthError) {
        signIn(undefined, { callbackUrl: window.location.pathname + window.location.search });
        return;
      }
      setState({ data: undefined, error: err, loading: false });
    }
  }, [token, path, enabled]);

  useEffect(() => {
    if (!token || !path || !enabled) {
      // 還在等 session，或呼叫端刻意關掉——維持 loading，不要閃一下空白。
      if (!enabled || !path) setState((s) => ({ ...s, loading: false }));
      return;
    }
    void run();
  }, [run, token, path, enabled]);

  return { ...state, refetch: run };
}

/**
 * 寫入用。跟 useApi 共用同一套 401 處理，回傳 pending 讓按鈕能鎖住。
 *
 * 之所以要有這支：目前每個表單都自己寫一次 try/catch/setSubmitting，
 * 而且沒有任何一個處理 401——存到一半 token 過期會靜默失敗。
 */
export function useApiMutation() {
  const { data: session } = useSession();
  const token = (session?.user as { accessToken?: string } | undefined)?.accessToken;
  const [pending, setPending] = useState(false);

  const mutate = useCallback(
    async <T = unknown>(
      path: string,
      init: RequestInit & { method: string },
    ): Promise<T> => {
      if (!token) throw new ApiError("尚未登入。", 401, path);
      setPending(true);
      try {
        return (await clientFetch(path, token, init)) as T;
      } catch (e) {
        if (e instanceof ApiError && e.isAuthError) {
          signIn(undefined, { callbackUrl: window.location.pathname });
        }
        throw e;
      } finally {
        setPending(false);
      }
    },
    [token],
  );

  return { mutate, pending };
}
