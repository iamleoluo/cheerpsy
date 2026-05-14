"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut } from "next-auth/react";

const navItems = [
  { href: "/dashboard", label: "儀表板", icon: "📊" },
  { href: "/cases", label: "個案管理", icon: "👤" },
  { href: "/appointments", label: "預約管理", icon: "📅" },
  { href: "/rooms", label: "空間預約", icon: "🏢" },
  { href: "/reminders", label: "預約提醒", icon: "📞" },
  { href: "/ledger", label: "諮商流水帳", icon: "📒" },
  { href: "/reconciliation", label: "財務核銷", icon: "💰", roles: ["admin", "accountant"] },
  { href: "/payouts", label: "心理師酬勞", icon: "💳", roles: ["admin", "accountant"] },
  { href: "/petty-cash", label: "零用金", icon: "🪙", roles: ["admin", "accountant"] },
  { href: "/reports", label: "月報表", icon: "📈", roles: ["admin", "accountant"] },
  { href: "/churn", label: "流失預警", icon: "⚠️", roles: ["admin", "accountant"] },
  { href: "/institutions", label: "機構管理", icon: "🏛️", roles: ["admin"] },
  { href: "/admin/users", label: "帳號管理", icon: "🔑", roles: ["admin"] },
  { href: "/guide", label: "使用簡介", icon: "📖" },
] as const;

export function Sidebar({ userName, userRole }: { userName: string; userRole: string }) {
  const pathname = usePathname();

  const roleLabel: Record<string, string> = {
    admin: "管理員",
    accountant: "會計",
    therapist: "心理師",
  };

  return (
    <aside className="flex h-screen w-60 flex-col border-r border-gray-200 bg-white">
      <div className="border-b border-gray-200 px-4 py-5">
        <h1 className="text-lg font-bold text-primary-700">CheerPsy</h1>
        <p className="mt-1 text-sm text-gray-500">心理診療所管理系統</p>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-4">
        {navItems.filter((item) => !("roles" in item) || (item.roles as readonly string[]).includes(userRole)).map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`mb-1 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                active
                  ? "bg-primary-50 font-medium text-primary-700"
                  : "text-gray-600 hover:bg-gray-100"
              }`}
            >
              <span>{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-gray-200 px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">{userName}</p>
            <p className="text-xs text-gray-500">{roleLabel[userRole] ?? userRole}</p>
          </div>
          <button
            onClick={() => signOut({ callbackUrl: "/login" })}
            className="rounded-lg px-2 py-1 text-xs text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            title="登出"
          >
            登出
          </button>
        </div>
      </div>
    </aside>
  );
}
