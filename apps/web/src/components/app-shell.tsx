import { Sidebar } from "@/components/sidebar";
import { TopBar } from "@/components/TopBar";

/**
 * 行政端與心理師端共用的外框。
 *
 * 側邊欄依 role 決定顯示哪一套 nav（見 lib/nav.ts），因此不論路由屬於
 * (app) 還是 (therapist) route group，使用者看到的都是自己身分的導覽。
 */
export function AppShell({
  userName,
  userRole,
  children,
}: {
  userName: string;
  userRole: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen">
      <Sidebar userName={userName} userRole={userRole} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
