"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { clientFetch } from "@/lib/client-api";
import { SESSION_TYPE, hhmm } from "@/lib/format";

interface Slot {
  id: number;
  case_name: string | null;
  start: string;
  end: string;
  session_type: string;
  room_name: string | null;
  status: string;
  checkin_status: string;
  action: "front_desk" | "self";
  funding_source: string;
  quota: { used: number; total: number; is_last: boolean } | null;
}
interface Todo { type: string; label: string; count: number; link: string }
interface Data {
  date: string;
  schedule: Slot[];
  todos: Todo[];
  stats: { today_sessions: number; pending_invites: number; pending_docs: number };
}

const TODO_ICON: Record<string, string> = { invite: "🤝", doc: "📄", quota: "⚠️" };

export default function TodayPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const name = session?.user?.name ?? "";
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setData(await clientFetch("/me/today", token));
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  if (!data) return <p className="p-6 text-gray-400">載入中...</p>;

  return (
    <div>
      <h1 className="text-2xl font-bold">我的今日</h1>
      <p className="mt-1 text-sm text-gray-500">
        {name}，{data.date} — 今天要做什麼，以及別人在等你什麼。
      </p>

      {error && <div className="my-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      <div className="mb-5 mt-4 grid grid-cols-3 gap-3">
        {[
          ["今日場次", data.stats.today_sessions, "/sched"],
          ["派案邀請", data.stats.pending_invites, "/pool"],
          ["待確認文件", data.stats.pending_docs, "/docs"],
        ].map(([label, n, href]) => (
          <Link key={label as string} href={href as string} className="rounded-xl border border-gray-200 bg-white px-4 py-3 hover:border-primary-300">
            <div className="text-xs text-gray-500">{label}</div>
            <div className={`text-2xl font-semibold ${Number(n) > 0 && label !== "今日場次" ? "text-red-600" : ""}`}>{n}</div>
          </Link>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-gray-200 bg-white">
          <div className="border-b border-gray-100 px-4 py-3 text-sm font-medium">今日班表</div>
          {data.schedule.length === 0 ? (
            <p className="px-4 py-10 text-center text-sm text-gray-400">今天沒有排程</p>
          ) : (
            <div className="divide-y divide-gray-100">
              {data.schedule.map((s) => (
                <div key={s.id} className="flex items-start gap-3 px-4 py-3">
                  <div className="w-24 shrink-0 text-sm tabular-nums">{hhmm(s.start)}–{hhmm(s.end)}</div>
                  <div className="min-w-0 flex-1">
                    <div className="font-medium">{s.case_name}</div>
                    <div className="text-xs text-gray-500">
                      {s.room_name ?? SESSION_TYPE[s.session_type]} ·{" "}
                      {s.funding_source === "institution"
                        ? `機構 ${s.quota?.used ?? "?"}/${s.quota?.total ?? "?"}`
                        : "自費"}
                    </div>
                    {s.quota?.is_last && (
                      <div className="text-xs font-medium text-red-600">機構最後一次 · 下次轉自費</div>
                    )}
                  </div>
                  <div className="shrink-0 text-xs">
                    {s.status === "executed" ? (
                      <span className="rounded bg-green-100 px-1.5 py-0.5 text-green-700">已完成</span>
                    ) : s.action === "front_desk" ? (
                      <span className="text-gray-400">櫃檯報到</span>
                    ) : (
                      <Link href="/sched" className="text-primary-600 hover:underline">在班表處理</Link>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl border border-gray-200 bg-white">
          <div className="border-b border-gray-100 px-4 py-3 text-sm font-medium">
            待辦（依急迫度排序）
          </div>
          {data.todos.length === 0 ? (
            <p className="px-4 py-10 text-center text-sm text-gray-400">目前沒有待辦事項</p>
          ) : (
            <div className="divide-y divide-gray-100">
              {data.todos.map((t, i) => (
                <Link key={i} href={t.link} className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50">
                  <span>{TODO_ICON[t.type] ?? "•"}</span>
                  <span className="flex-1 text-sm">{t.label}</span>
                  {t.count > 1 && (
                    <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700">{t.count}</span>
                  )}
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      <p className="mt-4 text-xs text-gray-400">
        此頁不顯示收款金額與收據操作（屬櫃檯行政），也不顯示他人個案與所內總營收。
      </p>
    </div>
  );
}
