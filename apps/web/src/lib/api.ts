import { auth } from "@/lib/auth";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function apiFetch(path: string, init?: RequestInit) {
  const session = await auth();
  const token = (session?.user as any)?.accessToken;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  return fetch(`${API_URL}${path}`, { ...init, headers });
}
