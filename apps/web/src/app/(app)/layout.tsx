import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";
import { Sidebar } from "@/components/sidebar";

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
    <div className="flex h-screen">
      <Sidebar userName={userName} userRole={userRole} />
      <main className="flex-1 overflow-y-auto p-6">{children}</main>
    </div>
  );
}
