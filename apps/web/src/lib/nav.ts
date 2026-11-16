/**
 * 導覽設定 — 行政端與心理師端兩套。
 *
 * 帳務拆除（階段 2）之後：不再有機構、財務、核銷、酬勞相關入口。
 * 行政端分 5 群組，心理師端 4 群組。
 */

export type NavItem = {
  href: string;
  label: string;
  icon: string;
  /** 側邊欄右側小標籤，如 NEW / 主控 */
  badge?: string;
  /** 未設定＝所有角色可見 */
  roles?: readonly string[];
};

export type NavGroup = {
  section: string;
  items: readonly NavItem[];
};

export const ADMIN_NAV: readonly NavGroup[] = [
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
      { href: "/calendar", label: "診間日曆", icon: "🗓️", badge: "主控" },
      { href: "/booking", label: "預約作業", icon: "➕" },
      { href: "/appts", label: "預約總表", icon: "📋" },
      { href: "/gcal", label: "日曆分享", icon: "📤", roles: ["admin", "staff"] },
    ],
  },
  {
    section: "分析",
    items: [
      { href: "/reports", label: "數據分析", icon: "📈", roles: ["admin", "accountant"] },
    ],
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

export const THERAPIST_NAV: readonly NavGroup[] = [
  {
    section: "每日",
    items: [
      { href: "/today", label: "我的今日", icon: "🏠" },
      { href: "/sched", label: "我的班表", icon: "🗓️" },
      { href: "/booking", label: "預約作業", icon: "➕" },
    ],
  },
  {
    section: "個案",
    items: [
      { href: "/pool", label: "派案邀請", icon: "🤝", badge: "NEW" },
      { href: "/cases", label: "我的個案", icon: "👤" },
    ],
  },
  {
    section: "數據",
    items: [{ href: "/stats", label: "我的數據", icon: "📈" }],
  },
  {
    section: "系統",
    items: [
      { href: "/settings", label: "個人設定", icon: "⚙️" },
      { href: "/guide", label: "操作指南", icon: "📖" },
    ],
  },
];

export const ROLE_LABEL: Record<string, string> = {
  admin: "管理員",
  accountant: "會計",
  staff: "櫃台行政",
  therapist: "心理師",
};

export function isTherapist(role: string): boolean {
  return role === "therapist";
}

/** 側邊欄要用哪一套 */
export function navForRole(role: string): readonly NavGroup[] {
  return isTherapist(role) ? THERAPIST_NAV : ADMIN_NAV;
}

/** 登入後 / 進站首頁要導去哪 */
export function landingForRole(role: string): string {
  return isTherapist(role) ? "/today" : "/dashboard";
}

/** 側邊欄右下角顯示的身分別 */
export function shellLabelForRole(role: string): string {
  return `V2 · ${ROLE_LABEL[role] ?? role}`;
}
