import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";
import { AppShell } from "@/components/app-shell";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session?.user) redirect("/login");

  const userName = session.user.name ?? "User";
  const userRole = (session.user as any).role ?? "therapist";

  return (
    <AppShell userName={userName} userRole={userRole}>
      {children}
    </AppShell>
  );
}
