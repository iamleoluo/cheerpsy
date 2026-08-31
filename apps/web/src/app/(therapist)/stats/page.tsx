"use client";

import { useSession } from "next-auth/react";
import { AnalyticsView } from "@/components/analytics-view";

export default function StatsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;

  return (
    <div>
      <h1 className="text-2xl font-bold">我的數據</h1>
      <p className="mb-4 mt-1 text-sm text-gray-500">
        到案率、留案率、黏著度與媒合成功率。可切換週／月／季。
      </p>
      {token && <AnalyticsView token={token} mine />}
    </div>
  );
}
