import type { Metadata } from "next";
import { Providers } from "@/components/providers";
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
      <body className="bg-surface-2 text-ink antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
