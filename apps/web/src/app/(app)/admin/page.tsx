"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { UsersTab } from "@/features/admin/UsersTab";
import { InstitutionsTab } from "@/features/admin/InstitutionsTab";
import { DataTab } from "@/features/admin/DataTab";

/**
 * 系統管理（三個分頁）— V2升級計畫 11 §4.2 的拆檔。
 *
 * 這支原本 1,394 行，是 §5 裡唯一沒被任何分期計畫收編的頁面。三個分頁彼此
 * 沒有共用狀態，純粹是擠在同一個檔案裡，所以照 P3 的慣例各自搬進
 * features/admin/，路由檔只留「現在顯示哪一個分頁」。

 * 同一輪把 `/admin/users` 收掉：那是與此處 UsersTab 幾乎重複的第二份實作，
 * 而側邊欄從來只連 /admin——兩份都在改，但每次只會改到一份。
 */

/* ───── main page ───── */

export default function AdminPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const userRole = (session?.user as any)?.role;

  const [tab, setTab] = useState<"users" | "institutions" | "data">("users");

  if (userRole !== "admin") {
    return (
      <div className="flex h-64 items-center justify-center text-ink-3">
        僅管理員可存取此頁面
      </div>
    );
  }

  if (!token) return <p className="p-6 text-ink-3">載入中...</p>;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold">系統管理</h1>
      </div>

      {/* Tab bar */}
      <div className="mb-6 flex gap-1 border-b border-line">
        <button
          onClick={() => setTab("users")}
          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
            tab === "users"
              ? "border-b-2 border-accent text-accent"
              : "text-ink-3 hover:text-ink-2"
          }`}
        >
          帳號管理
        </button>
        <button
          onClick={() => setTab("institutions")}
          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
            tab === "institutions"
              ? "border-b-2 border-accent text-accent"
              : "text-ink-3 hover:text-ink-2"
          }`}
        >
          機構管理
        </button>
        <button
          onClick={() => setTab("data")}
          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
            tab === "data"
              ? "border-b-2 border-accent text-accent"
              : "text-ink-3 hover:text-ink-2"
          }`}
        >
          資料匯出入
        </button>
      </div>

      {tab === "users" ? <UsersTab token={token} /> : tab === "institutions" ? <InstitutionsTab token={token} /> : <DataTab token={token} />}
    </div>
  );
}
