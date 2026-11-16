import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";

// 心理師不該打開的行政頁。資料端點本來就在伺服器端擋，這裡避免他們看到壞掉的空殼頁。
const STAFF_ONLY_PREFIXES = [
  "/match",
  "/reports",
  "/admin",
  "/gcal",
];

function isStaffOnly(pathname: string): boolean {
  return STAFF_ONLY_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(p + "/")
  );
}

export default auth((req) => {
  const role = (req.auth?.user as any)?.role;
  if (role === "therapist" && isStaffOnly(req.nextUrl.pathname)) {
    return NextResponse.redirect(new URL("/today", req.url));
  }
  return NextResponse.next();
});

export const config = {
  matcher: ["/((?!login|api/auth|_next/static|_next/image|favicon.ico).*)"],
};
