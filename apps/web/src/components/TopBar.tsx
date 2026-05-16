"use client";

import { NotificationBar } from "./NotificationBar";

export function TopBar() {
  return (
    <div className="flex h-12 items-center justify-end border-b border-gray-100 px-6">
      <NotificationBar />
    </div>
  );
}
