/**
 * /admin 三個分頁共用的型別與對照表 — V2升級計畫 11 §4.2 的拆檔慣例。
 *
 * 角色代號規則放這裡，因為 `/admin/users` 曾經抄過第二份：同一支
 * computeNextCode()、同一張角色徽章對照表各寫一遍，改了一邊另一邊不會跟上。
 * 那一頁已經收掉，規則只留這一份。
 */

export interface UserItem {
  id: number;
  email: string;
  name: string;
  role: string;
  user_code: string | null;
  commission_rate: number | null;
  base_price: number | null;
  is_active: boolean;
}

export interface InvitationItem {
  id: number;
  invite_key: string;
  type: string;
  name: string;
  role: string | null;
  target_user_id: number | null;
  created_at: string;
  expires_at: string;
  used_at: string | null;
}

export interface Institution {
  id: number;
  name: string;
  code: string | null;
  is_active: boolean;
  requires_therapist_docs: boolean;
}

export const ROLE_CODE_PREFIX: Record<string, string> = {
  admin: "A", accountant: "C", staff: "S", therapist: "T",
};

/** 下一個沒被用掉的代號。角色決定字首，流水號補到三位。 */
export function computeNextCode(users: UserItem[], role: string): string {
  const prefix = ROLE_CODE_PREFIX[role] ?? role[0].toUpperCase();
  const used = users.filter((u) => u.user_code?.startsWith(prefix)).map((u) => u.user_code!);
  for (let i = 1; i <= 999; i++) {
    const c = `${prefix}${String(i).padStart(3, "0")}`;
    if (!used.includes(c)) return c;
  }
  return `${prefix}001`;
}

export const roleLabels: Record<string, string> = {
  admin: "管理員",
  accountant: "會計",
  staff: "行政人員",
  therapist: "心理師",
};

/**
 * 角色徽章。**一律中性**——角色是屬性不是狀態（v7 定案 ③：顏色只表達狀態）。
 * 原本 admin 是綠、accountant 是琥珀，換成語意 token 之後「管理員」讀起來
 * 像已完成、「會計」像要注意。字面本來就寫著是哪一種，顏色不必再說一次。
 */
export const roleBadge: Record<string, string> = {
  admin: "bg-surface-3 text-ink font-bold",
  accountant: "bg-surface-3 text-ink-2",
  staff: "bg-surface-3 text-ink-2",
  therapist: "bg-surface-3 text-ink-2",
};
