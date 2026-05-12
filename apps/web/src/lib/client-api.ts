const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `API error ${res.status}`);
  }
  return res.json();
}
