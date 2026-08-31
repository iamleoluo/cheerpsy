import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";
import { AppShell } from "@/components/app-shell";
import { isTherapist, landingForRole } from "@/lib/nav";

/**
 * 心理師端 route group。
 *
 * 這裡只放「只有心理師會看到」的頁面（today / sched / pool / docs / pay / stats）。
 * `/cases` 與 `/booking` 兩頁行政與心理師共用，仍留在 (app)，
 * 依 gap_analysis.md Phase 3／6 再做角色分化。
 */
export default async function TherapistLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session?.user) redirect("/login");

  const userName = session.user.name ?? "User";
  const userRole = (session.user as any).role ?? "therapist";

  // 管理者需要能檢視心理師端頁面以供支援；會計與櫃台行政沒有理由進來
  if (!isTherapist(userRole) && userRole !== "admin") {
    redirect(landingForRole(userRole));
  }

  return (
    <AppShell userName={userName} userRole={userRole}>
      {children}
    </AppShell>
  );
}
