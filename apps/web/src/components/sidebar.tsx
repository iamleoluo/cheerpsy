"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut } from "next-auth/react";

import { navForRole, ROLE_LABEL, shellLabelForRole, type NavItem } from "@/lib/nav";

function isActive(pathname: string, href: string): boolean {
  // /admin 與 /admin/users 皆算 /admin；但 /cases 不該把 /casesomething 算進來
  return pathname === href || pathname.startsWith(`${href}/`);
}

function badgeClass(badge: string): string {
  return badge === "NEW"
    ? "bg-primary-100 text-primary-700"
    : "bg-amber-100 text-amber-700";
}

export function Sidebar({ userName, userRole }: { userName: string; userRole: string }) {
  const pathname = usePathname();
  const groups = navForRole(userRole);

  const visible = (item: NavItem) =>
    !item.roles || (item.roles as readonly string[]).includes(userRole);

  return (
    <aside className="flex h-screen w-60 flex-col border-r border-gray-200 bg-white">
      <div className="border-b border-gray-200 px-4 py-5">
        <h1 className="text-lg font-bold text-primary-700">CheerPsy</h1>
        <p className="mt-0.5 text-sm text-gray-500">慈恩心理治療所</p>
        <span className="mt-2 inline-block rounded bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-500">
          {shellLabelForRole(userRole)}
        </span>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-3">
        {groups.map((group) => {
          const items = group.items.filter(visible);
          if (items.length === 0) return null;

          return (
            <div key={group.section} className="mb-3">
              <div className="px-3 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-gray-400">
                {group.section}
              </div>
              {items.map((item) => {
                const active = isActive(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`mb-0.5 flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                      active
                        ? "bg-primary-50 font-medium text-primary-700"
                        : "text-gray-600 hover:bg-gray-100"
                    }`}
                  >
                    <span>{item.icon}</span>
                    <span className="flex-1">{item.label}</span>
                    {item.badge && (
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${badgeClass(item.badge)}`}
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

      <div className="border-t border-gray-200 px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">{userName}</p>
            <p className="text-xs text-gray-500">{ROLE_LABEL[userRole] ?? userRole}</p>
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
