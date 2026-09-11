import { redirect } from "next/navigation";

/**
 * 帳號管理已經整併進 /admin 的第一個分頁。
 *
 * 這一頁原本是 539 行、與 `/admin` 的 UsersTab 幾乎重複的第二份實作：同一批
 * 端點、同一張表、同一份 computeNextCode()、同一張角色徽章對照表各寫一遍。
 * 兩份還長得不太一樣——這邊用彈窗編輯、那邊用就地編輯——所以任何一次修改都
 * 只會改到其中一份，另一份靜靜地舊下去。色階清理時就撞到過：兩份角色徽章
 * 對照表要分別改，改漏一份也不會有人發現。
 *
 * 側邊欄從頭到尾只連 `/admin`，這一頁沒有任何入口。保留成轉址而不是直接刪掉，
 * 是因為它曾經是可以直接輸入的網址，也可能還躺在誰的書籤裡。
 */
export default function AdminUsersRedirect() {
  redirect("/admin");
}
