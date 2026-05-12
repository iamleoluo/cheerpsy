"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

interface ChurnCase {
  case_id: number;
  case_name: string;
  therapist_name: string | null;
  phone: string | null;
  status: string;
  last_appointment_date: string | null;
  days_since_last: number | null;
  funding_source: string;
}

export default function ChurnPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;

  const [days, setDays] = useState(30);
  const [cases, setCases] = useState<ChurnCase[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await clientFetch(`/churn?inactive_days=${days}`, token);
      setCases(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [token, days]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">流失預警</h1>
          <p className="mt-1 text-sm text-gray-500">
            超過指定天數未預約的活躍個案
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-500">超過</label>
          <select value={days} onChange={(e) => setDays(parseInt(e.target.value))} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
            <option value={14}>14 天</option>
            <option value={21}>21 天</option>
            <option value={30}>30 天</option>
            <option value={45}>45 天</option>
            <option value={60}>60 天</option>
            <option value={90}>90 天</option>
          </select>
          <span className="text-sm text-gray-500">未預約</span>
        </div>
      </div>

      {loading ? (
        <p className="text-gray-400">載入中...</p>
      ) : cases.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-16 text-center text-gray-400">
          目前無流失預警個案
        </div>
      ) : (
        <>
          <div className="mb-4 text-sm text-gray-500">
            共 {cases.length} 位個案需關注
          </div>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-4 py-3">個案姓名</th>
                  <th className="px-4 py-3">負責心理師</th>
                  <th className="px-4 py-3">電話</th>
                  <th className="px-4 py-3">來源</th>
                  <th className="px-4 py-3">最後預約</th>
                  <th className="px-4 py-3">已過天數</th>
                  <th className="px-4 py-3">狀態</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {cases.map((c) => (
                  <tr key={c.case_id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium">{c.case_name}</td>
                    <td className="px-4 py-3">{c.therapist_name ?? "-"}</td>
                    <td className="px-4 py-3 text-xs">{c.phone ?? "-"}</td>
                    <td className="px-4 py-3 text-xs">
                      {c.funding_source === "institution" ? "機構" : "自費"}
                    </td>
                    <td className="px-4 py-3">{c.last_appointment_date ?? "無紀錄"}</td>
                    <td className="px-4 py-3">
                      {c.days_since_last !== null ? (
                        <span className={`font-medium ${c.days_since_last > 60 ? "text-red-600" : c.days_since_last > 30 ? "text-amber-600" : "text-gray-900"}`}>
                          {c.days_since_last} 天
                        </span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs">{c.status === "initial" ? "初談" : "持續中"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
