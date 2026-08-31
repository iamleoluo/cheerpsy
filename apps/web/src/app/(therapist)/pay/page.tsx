"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import { SESSION_TYPE, money } from "@/lib/format";

interface Detail {
  id: number;
  session_date: string;
  case_name: string | null;
  session_type: string;
  amount: number;
  discount_amount: number;
  commission_rate: number;
  outcall_bonus: number;
  share: number;
  status: "settled" | "pending";
}
interface Payout {
  month: string;
  period_start: string;
  period_end: string;
  payout_date: string;
  settled_total: number;
  pending_count: number;
  details: Detail[];
  note: string;
}

function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function PayPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [month, setMonth] = useState(thisMonth());
  const [q, setQ] = useState("");
  const [data, setData] = useState<Payout | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rateOpen, setRateOpen] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const p = new URLSearchParams({ month });
      if (q) p.set("q", q);
      setData(await clientFetch(`/me/payout?${p}`, token));
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, [token, month, q]);

  useEffect(() => {
    load();
  }, [load]);

  if (!data) return <p className="p-6 text-gray-400">載入中...</p>;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">我的酬勞</h1>
          <p className="mt-1 text-sm text-gray-500">
            資料來源為月報表：只計已完成當日對帳的紀錄。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setRateOpen(true)} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50">
            調整我的鐘點費
          </button>
          <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm" />
        </div>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          ["結算區間", `${data.period_start.slice(5)} ~ ${data.period_end.slice(5)}`],
          ["薪資發放日", data.payout_date],
          ["已結算合計", money(data.settled_total)],
          ["待結算", `${data.pending_count} 筆`],
        ].map(([l, v]) => (
          <div key={l} className="rounded-lg border border-gray-200 bg-white px-3 py-2">
            <div className="text-xs text-gray-500">{l}</div>
            <div className="text-lg font-semibold">{v}</div>
          </div>
        ))}
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      <div className="mb-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜尋個案姓名，方便確認紀錄"
          className="w-64 rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
        />
      </div>

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="w-full text-sm">
          <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs text-gray-500">
            <tr>
              <th className="px-3 py-3">日期</th>
              <th className="px-3 py-3">個案</th>
              <th className="px-3 py-3">類型</th>
              <th className="px-3 py-3 text-right">場次金額</th>
              <th className="px-3 py-3 text-right">優待減免</th>
              <th className="px-3 py-3 text-right">抽成率</th>
              <th className="px-3 py-3 text-right">外展保底</th>
              <th className="px-3 py-3 text-right">酬勞</th>
              <th className="px-3 py-3">狀態</th>
            </tr>
          </thead>
          <tbody>
            {data.details.length === 0 && (
              <tr><td colSpan={9} className="px-4 py-10 text-center text-gray-400">本月尚無紀錄</td></tr>
            )}
            {data.details.map((d) => (
              <tr key={d.id} className="border-b border-gray-100 last:border-0">
                <td className="px-3 py-2.5">{d.session_date}</td>
                <td className="px-3 py-2.5 font-medium">{d.case_name}</td>
                <td className="px-3 py-2.5">{SESSION_TYPE[d.session_type] ?? d.session_type}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{money(d.amount)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums text-gray-500">
                  {d.discount_amount ? `−${money(d.discount_amount)}` : "—"}
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums">{(d.commission_rate * 100).toFixed(0)}%</td>
                <td className="px-3 py-2.5 text-right tabular-nums text-gray-500">
                  {d.outcall_bonus ? money(d.outcall_bonus) : "—"}
                </td>
                <td className="px-3 py-2.5 text-right font-semibold tabular-nums">{money(d.share)}</td>
                <td className="px-3 py-2.5">
                  <span className={`rounded px-1.5 py-0.5 text-xs ${
                    d.status === "settled" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"
                  }`}>
                    {d.status === "settled" ? "已結算" : "待結算"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-gray-400">{data.note}</p>
      <p className="mt-1 text-xs text-gray-400">
        只看得到自己的酬勞。看得到場次金額（作為計算依據），但看不到個案是否已付款與收據資訊。
        鐘點費若被回溯修改，酬勞不會自動重算，會標記提示由相關人員人工確認。
      </p>

      {rateOpen && <RateModal token={token} onClose={() => setRateOpen(false)} onDone={() => { setRateOpen(false); load(); }} />}
    </div>
  );
}

function RateModal({ token, onClose, onDone }: { token: string; onClose: () => void; onDone: () => void }) {
  const [price, setPrice] = useState("");
  const [scope, setScope] = useState("new_only");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function go(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      const r = await clientFetch("/me/base-price", token, {
        method: "PUT",
        body: JSON.stringify({ base_price: Number(price), scope }),
      });
      setMsg(`${r.note}（影響 ${r.appointments_updated} 筆預約）`);
      setTimeout(onDone, 1500);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <form onSubmit={go} className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-1 text-lg font-bold">調整鐘點費</h2>
        <p className="mb-4 text-sm text-gray-500">
          鐘點費為浮動制。調價時請選擇套用範圍 —— 有些心理師調漲是全部個案都漲，
          有的是舊案維持舊價、新預約才用新價，兩種都支援。
        </p>
        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}
        {msg && <div className="mb-3 rounded bg-green-50 px-3 py-2 text-sm text-green-700">{msg}</div>}
        <label className="block text-sm">
          <span className="mb-1 block text-gray-600">新的鐘點費 *</span>
          <input
            required
            type="number"
            min="0"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 tabular-nums"
          />
        </label>
        <div className="mt-3 space-y-2">
          <label className="flex items-start gap-2 text-sm">
            <input type="radio" className="mt-1" checked={scope === "new_only"} onChange={() => setScope("new_only")} />
            <span>
              <b>僅新案適用</b>
              <span className="block text-xs text-gray-500">既有進行中個案沿用舊價</span>
            </span>
          </label>
          <label className="flex items-start gap-2 text-sm">
            <input type="radio" className="mt-1" checked={scope === "all_ongoing"} onChange={() => setScope("all_ongoing")} />
            <span>
              <b>套用到所有進行中個案</b>
              <span className="block text-xs text-gray-500">
                會更新所有已排定但尚未執行的自費預約金額
              </span>
            </span>
          </label>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">取消</button>
          <button type="submit" className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white">確認調整</button>
        </div>
      </form>
    </div>
  );
}
