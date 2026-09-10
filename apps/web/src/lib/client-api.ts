const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * 帶得動 HTTP 狀態碼的錯誤。
 *
 * 舊版一律 `throw new Error(detail)`，呼叫端拿不到狀態碼，所以沒有任何地方
 * 分得出「token 過期」與「這筆資料真的不存在」。結果就是 V2升級計畫 11 §1.4
 * 記錄的那個黑洞：session 過期時 /rooms 永遠停在「載入診間中…」，console 裡
 * 9 個 401 但畫面完全沒說發生什麼事。
 *
 * 繼承 Error，所以既有 200+ 個 `catch (e) { e.message }` 的呼叫端不受影響。
 */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly path: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** token 過期或無效——要重新登入，不是資料問題。 */
  get isAuthError() {
    return this.status === 401;
  }

  /** 已登入但權限不足——重新登入也沒用，該顯示「你沒有權限看這頁」。 */
  get isForbidden() {
    return this.status === 403;
  }
}

export async function clientFetch(
  path: string,
  token: string,
  init?: RequestInit,
) {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
    ...(init?.headers as Record<string, string>),
  };

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    // fetch 只有在網路層失敗才 reject（斷線、CORS、後端沒起來）。
    // 這跟 4xx/5xx 是兩回事，訊息要分開講，否則使用者會以為是自己輸入錯。
    throw new ApiError("無法連線到伺服器，請確認網路連線後重試。", 0, path);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = Array.isArray(body.detail)
      ? body.detail.map((e: any) => e.msg ?? JSON.stringify(e)).join("; ")
      : body.detail;
    throw new ApiError(detail ?? `API error ${res.status}`, res.status, path);
  }

  if (res.status === 204) return null;
  return res.json();
}

export async function exportCsv(path: string, token: string, filename: string) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new ApiError(`匯出失敗（${res.status}）`, res.status, path);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
