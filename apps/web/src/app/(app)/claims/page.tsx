"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";

export default function ClaimsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [tab, setTab] = useState<"batches" | "docs">("batches");

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">核銷案管理</h1>

      <div className="mb-4 flex gap-1 border-b border-gray-200">
        {(
          [
            ["batches", "核銷案列表"],
            ["docs", "文件確認"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              tab === key
                ? "border-b-2 border-primary-600 text-primary-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="rounded-lg border border-dashed border-gray-300 p-16 text-center">
        {tab === "batches" ? (
          <div>
            <p className="text-lg font-medium text-gray-500">核銷案列表</p>
            <p className="mt-2 text-sm text-gray-400">
              建立及管理自費/機構核銷案，追蹤收款進度
            </p>
            <div className="mt-4 text-xs text-gray-400">
              功能包含：建立核銷案、勾選諮商紀錄、狀態流轉（collecting → ready → submitted → received/closed）、下載收據/請款單 PDF
            </div>
          </div>
        ) : (
          <div>
            <p className="text-lg font-medium text-gray-500">心理師文件確認</p>
            <p className="mt-2 text-sm text-gray-400">
              心理師確認諮商紀錄已完成，全部確認後核銷案自動升為「ready」
            </p>
            <div className="mt-4 text-xs text-gray-400">
              心理師角色在此頁面確認自己負責的諮商紀錄文件，確認後 claim batch 自動檢查是否所有紀錄都已確認
            </div>
          </div>
        )}
        <p className="mt-6 rounded-lg bg-amber-50 px-4 py-2 text-sm text-amber-700 inline-block">
          待後端 claim_batches API 完成後啟用
        </p>
      </div>
    </div>
  );
}
