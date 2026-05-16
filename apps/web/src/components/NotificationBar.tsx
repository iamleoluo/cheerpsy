"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

interface LiveAlert {
  type: string;
  title: string;
  link: string;
  severity: "info" | "warning" | "error";
}

interface NotificationItem {
  id: number;
  type: string;
  title: string;
  message: string | null;
  link: string | null;
  is_read: boolean;
  created_at: string;
}

interface NotificationData {
  unread_count: number;
  notifications: NotificationItem[];
  live_alerts: LiveAlert[];
}

export function NotificationBar() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [data, setData] = useState<NotificationData | null>(null);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const fetchNotifications = useCallback(async () => {
    if (!token) return;
    try {
      const d = await clientFetch("/notifications", token);
      setData(d);
    } catch {
      // ignore
    }
  }, [token]);

  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 60000); // refresh every 60s
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const markRead = async (id: number) => {
    if (!token) return;
    try {
      await clientFetch(`/notifications/${id}/read`, token, { method: "PUT" });
      fetchNotifications();
    } catch { /* ignore */ }
  };

  const markAllRead = async () => {
    if (!token) return;
    try {
      await clientFetch("/notifications/read-all", token, { method: "PUT" });
      fetchNotifications();
    } catch { /* ignore */ }
  };

  if (!data) return null;

  const totalUnread = data.unread_count;
  const allItems = [
    ...data.live_alerts.map((a, i) => ({
      id: `live-${i}`,
      type: a.type,
      title: a.title,
      link: a.link,
      severity: a.severity,
      isLive: true,
      is_read: false,
    })),
    ...data.notifications.map((n) => ({
      id: `n-${n.id}`,
      realId: n.id,
      type: n.type,
      title: n.title,
      link: n.link,
      severity: "info" as const,
      isLive: false,
      is_read: n.is_read,
      message: n.message,
      created_at: n.created_at,
    })),
  ];

  const severityColor = {
    info: "bg-blue-50 border-blue-200 text-blue-700",
    warning: "bg-amber-50 border-amber-200 text-amber-700",
    error: "bg-red-50 border-red-200 text-red-700",
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="relative flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
      >
        <span className="text-lg">🔔</span>
        {totalUnread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
            {totalUnread > 99 ? "99+" : totalUnread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 rounded-xl border border-gray-200 bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
            <h3 className="text-sm font-bold text-gray-900">系統通知</h3>
            {data.notifications.some((n) => !n.is_read) && (
              <button
                onClick={markAllRead}
                className="text-xs text-primary-600 hover:underline"
              >
                全部已讀
              </button>
            )}
          </div>

          <div className="max-h-80 overflow-y-auto">
            {allItems.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-gray-400">
                目前沒有通知
              </div>
            ) : (
              allItems.map((item) => (
                <a
                  key={item.id}
                  href={item.link || "#"}
                  onClick={() => {
                    if (!item.isLive && "realId" in item && item.realId) {
                      markRead(item.realId as number);
                    }
                    setOpen(false);
                  }}
                  className={`block border-b border-gray-50 px-4 py-3 transition-colors hover:bg-gray-50 ${
                    !item.is_read ? "bg-blue-50/30" : ""
                  }`}
                >
                  <div className="flex items-start gap-2">
                    {item.isLive && (
                      <span
                        className={`mt-0.5 inline-block rounded px-1.5 py-0.5 text-[10px] font-bold ${
                          item.severity === "warning"
                            ? "bg-amber-100 text-amber-700"
                            : item.severity === "error"
                            ? "bg-red-100 text-red-700"
                            : "bg-blue-100 text-blue-700"
                        }`}
                      >
                        即時
                      </span>
                    )}
                    <div className="flex-1">
                      <p className="text-sm font-medium text-gray-800">
                        {item.title}
                      </p>
                      {"message" in item && item.message && (
                        <p className="mt-0.5 text-xs text-gray-500">
                          {item.message}
                        </p>
                      )}
                      {"created_at" in item && item.created_at && (
                        <p className="mt-1 text-[10px] text-gray-400">
                          {new Date(item.created_at as string).toLocaleString("zh-TW")}
                        </p>
                      )}
                    </div>
                    {!item.is_read && (
                      <span className="mt-1 h-2 w-2 rounded-full bg-blue-500" />
                    )}
                  </div>
                </a>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
