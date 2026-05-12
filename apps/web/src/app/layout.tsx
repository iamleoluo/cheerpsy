import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CheerPsy 心理診療所管理系統",
  description: "營運管理系統 v2",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-TW">
      <body className="bg-gray-50 text-gray-900 antialiased">{children}</body>
    </html>
  );
}
