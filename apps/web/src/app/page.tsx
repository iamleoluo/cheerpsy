import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";
import { landingForRole } from "@/lib/nav";

export default async function Home() {
  const session = await auth();
  if (!session?.user) redirect("/login");

  const userRole = (session.user as any).role ?? "therapist";
  redirect(landingForRole(userRole));
}
