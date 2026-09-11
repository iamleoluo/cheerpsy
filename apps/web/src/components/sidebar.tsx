"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut } from "next-auth/react";

/**
 * 分群導覽，對應 document_reference/cheerpsy_v7_prototype_20260817.html 的
 * IA（行政端 nav-sec 分組／心理師端 nav-sec 分組），並依 V2升級計畫 09 §2、
 * §3.7 的裁示：機構原本 3 項（合約清冊/方案清冊/核銷案）收斂成 2 項
 * （機構合約＝合約面板、核銷案總表＝跨機構唯讀查詢）。
 */
type NavItem = {
  href: string;
  label: string;
  icon: string;
  roles?: readonly string[];
  badge?: string;
};
type NavGroup = { section: string; items: readonly NavItem[] };

const adminGroups: readonly NavGroup[] = [
  {
    section: "營運",
    items: [{ href: "/dashboard", label: "營運總覽", icon: "📊" }],
  },
  {
    section: "個案流程",
    items: [
      { href: "/match", label: "媒合管理", icon: "🤝", badge: "NEW" },
      { href: "/cases", label: "個案管理", icon: "👤" },
    ],
  },
  {
    section: "每日作業",
    items: [
      { href: "/rooms", label: "診間日曆", icon: "🗓️", badge: "主控" },
      { href: "/booking", label: "預約作業", icon: "➕" },
      { href: "/appts", label: "預約總表", icon: "📋" },
    ],
  },
  {
    section: "機構",
    items: [
      { href: "/institution", label: "機構合約", icon: "📑", roles: ["admin", "staff"] },
      { href: "/institution/claims", label: "核銷案總表", icon: "💰", roles: ["admin", "staff", "accountant"] },
    ],
  },
  {
    section: "財務",
    items: [
      { href: "/daily", label: "日報表 / 對帳", icon: "📒", roles: ["admin", "staff", "accountant"] },
      { href: "/ar", label: "應收帳冊", icon: "💳", roles: ["admin", "staff", "accountant"] },
    ],
  },
  {
    section: "分析",
    items: [{ href: "/reports", label: "數據分析", icon: "📈", roles: ["admin", "accountant"] }],
  },
  {
    section: "系統",
    items: [
      { href: "/admin", label: "系統管理", icon: "🔑", roles: ["admin"] },
      { href: "/settings", label: "個人設定", icon: "⚙️" },
      { href: "/guide", label: "操作指南", icon: "📖" },
    ],
  },
];

const therapistGroups: readonly NavGroup[] = [
  {
    section: "每日",
    items: [
      { href: "/today", label: "我的今日", icon: "🏠" },
      { href: "/sched", label: "我的班表", icon: "🗓️" },
      { href: "/my-booking", label: "預約作業", icon: "➕" },
    ],
  },
  {
    section: "派案",
    items: [{ href: "/pool", label: "派案邀請", icon: "🤝" }],
  },
  {
    section: "個案",
    items: [{ href: "/my-cases", label: "我的個案", icon: "👤" }],
  },
  {
    section: "行政配合",
    items: [{ href: "/docs", label: "文件確認", icon: "📄" }],
  },
  {
    section: "我的",
    items: [
      { href: "/pay", label: "我的酬勞", icon: "💵" },
      { href: "/stats", label: "我的數據", icon: "📈" },
    ],
  },
  {
    section: "系統",
    items: [
      { href: "/settings", label: "個人設定", icon: "⚙️" },
      { href: "/guide", label: "操作指南", icon: "📖" },
    ],
  },
];

const roleLabel: Record<string, string> = {
  admin: "管理員",
  accountant: "會計",
  staff: "行政人員",
  therapist: "心理師",
};

export function Sidebar({ userName, userRole }: { userName: string; userRole: string }) {
  const pathname = usePathname();
  const groups = userRole === "therapist" ? therapistGroups : adminGroups;
  const shellLabel = userRole === "therapist" ? "心理師端" : "行政端";

  return (
    <aside className="flex h-screen w-60 flex-col border-r border-line bg-white">
      <div className="border-b border-line px-4 py-5">
        <h1 className="text-lg font-bold text-accent">CheerPsy</h1>
        <p className="mt-1 text-sm text-ink-3">慈恩心理治療所</p>
        <span className="mt-1 inline-block rounded bg-accent-soft px-1.5 py-0.5 text-[10px] font-medium text-accent">
          V2 · {shellLabel}
        </span>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-3">
        {groups.map((group) => {
          const visibleItems = group.items.filter(
            (item) => !item.roles || item.roles.includes(userRole),
          );
          if (visibleItems.length === 0) return null;
          return (
            <div key={group.section} className="mb-3">
              <div className="px-3 pb-1 pt-2 text-[10px] font-bold uppercase tracking-wide text-ink-3">
                {group.section}
              </div>
              {visibleItems.map((item) => {
                const active = pathname === item.href || pathname.startsWith(item.href + "/");
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`mb-0.5 flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                      active
                        ? "bg-accent-soft font-medium text-accent"
                        : "text-ink-2 hover:bg-surface-3"
                    }`}
                  >
                    <span>{item.icon}</span>
                    <span className="flex-1">{item.label}</span>
                    {item.badge && (
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                          item.badge === "NEW"
                            ? "bg-st-done-bg text-st-done"
                            : "bg-st-warn-bg text-st-warn"
                        }`}
                      >
                        {item.badge}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          );
        })}
      </nav>

      <div className="border-t border-line px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">{userName}</p>
            <p className="text-xs text-ink-3">{roleLabel[userRole] ?? userRole}</p>
          </div>
          <button
            onClick={() => signOut({ callbackUrl: "/login" })}
            className="rounded-lg px-2 py-1 text-xs text-ink-3 hover:bg-surface-3 hover:text-ink-2"
            title="登出"
          >
            登出
          </button>
        </div>
      </div>
    </aside>
  );
}
