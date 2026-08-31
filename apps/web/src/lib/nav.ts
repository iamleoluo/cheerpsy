/**
 * 導覽設定 — 行政端與心理師端兩套。
 *
 * 對應 document_reference/gap_analysis.md §2.4 與 Phase 0。
 * 行政端 13 項分 6 群組（原型 5 群組 + 系統），心理師端 8 項。
 *
 * 註：`/products` 與 `/finance` 在 gap_analysis §2.1 規劃中會被拆併到
 * `/ledger`（分類 O）、`/ar`、`/pay`，Phase 4 與 Phase 6 完成後移除本檔的入口。
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
    ],
  },
  {
    section: "機構",
    items: [
      { href: "/contracts", label: "機構合約清冊", icon: "📑", badge: "NEW" },
      { href: "/plans", label: "機構方案清冊", icon: "🏢" },
      { href: "/claims", label: "機構核銷案", icon: "💰" },
    ],
  },
  {
    section: "財務",
    items: [
      { href: "/ledger", label: "日報表 / 對帳", icon: "📒" },
      { href: "/ar", label: "應收帳冊", icon: "💳" },
      { href: "/monthly", label: "月報表", icon: "📅", badge: "NEW" },
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
      { href: "/products", label: "商品販售", icon: "🛒", roles: ["admin", "accountant", "staff"] },
      { href: "/finance", label: "財務管理", icon: "💼", roles: ["admin", "accountant", "staff"] },
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
    section: "核銷",
    items: [{ href: "/docs", label: "文件確認", icon: "📄" }],
  },
  {
    section: "酬勞與數據",
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
  return isTherapist(role) ? "V2 · 心理師" : "V2 · 櫃台行政";
}
