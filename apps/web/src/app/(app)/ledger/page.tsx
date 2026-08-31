"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import { SESSION_TYPE, money, shiftDate, todayISO } from "@/lib/format";

interface Row {
  id: number;
  session_date: string;
  case_name: string | null;
  therapist_name: string | null;
  session_type: string;
  amount: number;
  self_pay_amount: number;
  institution_claim_amount: number;
  payment_status: string;
  payment_track: string;
  payment_method: string | null;
  receipt_no: string | null;
  is_no_show: boolean;
  no_show_fee: number;
}

interface Summary {
  closing_date: string;
  status: string;
  locked: boolean;
  cash_total: number;
  transfer_total: number;
  unpaid_total: number;
  receivable_total: number;
  record_count: number;
  rows: Row[];
}

const TRACK_LABEL: Record<string, string> = {
  immediate: "次結",
  monthly: "月結",
  institution: "機構",
};

export default function DailyLedgerPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const role = (session?.user as any)?.role;
  const [day, setDay] = useState(todayISO());
  const [data, setData] = useState<Summary | null>(null);
  const [view, setView] = useState<"all" | "paid" | "unpaid">("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [closing, setClosing] = useState(false);
  const [unlockOpen, setUnlockOpen] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      setData(await clientFetch(`/finance/daily?day=${day}`, token));
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, day]);

  useEffect(() => {
    load();
  }, [load]);

  async function closeDay() {
    if (!confirm(`確定完成 ${day} 的對帳？完成後該日會鎖定，需解鎖才能修改。`)) return;
    setClosing(true);
    try {
      await clientFetch(`/finance/daily/${day}/close`, token, {
        method: "POST",
        body: JSON.stringify({ note: null }),
      });
      load();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setClosing(false);
    }
  }

  if (loading || !data) return <p className="p-6 text-gray-400">載入中...</p>;

  const rows = data.rows.filter((r) =>
    view === "all" ? true : view === "paid" ? r.payment_status === "paid" : r.payment_status !== "paid"
  );

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">日報表 / 對帳</h1>
          <p className="mt-1 text-sm text-gray-500">
            當日結束後的對帳工具。仍未收者按「完成當日對帳」後，隔日自動轉入應收帳冊追蹤。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setDay(shiftDate(day, -1))} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">◀</button>
          <input type="date" value={day} onChange={(e) => setDay(e.target.value)} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm" />
          <button onClick={() => setDay(shiftDate(day, 1))} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">▶</button>
        </div>
      </div>

      {data.locked && (
        <div className="mb-4 flex items-center gap-3 rounded-lg border border-green-200 bg-green-50 px-4 py-2.5 text-sm text-green-900">
          🔒 {day} 已完成對帳並鎖定。
          {["admin", "accountant"].includes(role) && (
            <button onClick={() => setUnlockOpen(true)} className="ml-auto text-xs text-primary-700 underline">
              解鎖修改（會列入主管覆核紀錄）
            </button>
          )}
        </div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
        {[
          ["筆數", String(data.record_count), ""],
          ["現金", money(data.cash_total), "text-primary-700"],
          ["匯款", money(data.transfer_total), "text-primary-700"],
          ["應收合計", money(data.receivable_total), ""],
          ["當日應收未收", money(data.unpaid_total), "text-red-600"],
        ].map(([l, v, cls]) => (
          <div key={l} className="rounded-lg border border-gray-200 bg-white px-3 py-2">
            <div className="text-xs text-gray-500">{l}</div>
            <div className={`text-lg font-semibold ${cls}`}>{v}</div>
          </div>
        ))}
      </div>
      <p className="-mt-2 mb-4 text-xs text-gray-400">
        「當日應收未收」只計本來就該當場收卻沒收到的筆數；月結與機構全額不算。
      </p>

      {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      <div className="mb-3 flex items-center gap-2">
        {([["all", "全部"], ["unpaid", "應收"], ["paid", "已收"]] as const).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setView(k)}
            className={`rounded-lg px-3 py-1.5 text-sm ${
              view === k ? "bg-primary-600 text-white" : "border border-gray-300 hover:bg-gray-50"
            }`}
          >
            {label}
          </button>
        ))}
        <button
          onClick={closeDay}
          disabled={closing || data.locked || data.record_count === 0}
          className="ml-auto rounded-lg bg-green-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-40"
          title={data.locked ? "已完成對帳" : data.record_count === 0 ? "本日沒有紀錄" : undefined}
        >
          {closing ? "處理中..." : "完成當日對帳"}
        </button>
      </div>

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="w-full text-sm">
          <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs text-gray-500">
            <tr>
              <th className="px-3 py-3">姓名</th>
              <th className="px-3 py-3">心理師</th>
              <th className="px-3 py-3">類型</th>
              <th className="px-3 py-3">結帳方式</th>
              <th className="px-3 py-3 text-right">自付額</th>
              <th className="px-3 py-3 text-right">機構請款</th>
              <th className="px-3 py-3">收款狀態</th>
              <th className="px-3 py-3">收據編號</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-10 text-center text-gray-400">本日無符合的紀錄</td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                <td className="px-3 py-2.5 font-medium">
                  {r.case_name}
                  {r.is_no_show && (
                    <span className="ml-1.5 rounded bg-red-100 px-1 py-0.5 text-[10px] text-red-700">
                      失約費 {money(r.no_show_fee)}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2.5">{r.therapist_name}</td>
                <td className="px-3 py-2.5">{SESSION_TYPE[r.session_type] ?? r.session_type}</td>
                <td className="px-3 py-2.5 text-xs">{TRACK_LABEL[r.payment_track] ?? r.payment_track}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{money(r.self_pay_amount)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums text-gray-500">{money(r.institution_claim_amount)}</td>
                <td className="px-3 py-2.5">
                  <span className={`rounded px-1.5 py-0.5 text-xs ${
                    r.payment_status === "paid" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                  }`}>
                    {r.payment_status === "paid" ? `已付款 · ${r.payment_method === "cash" ? "現金" : "匯款"}` : "未付款"}
                  </span>
                </td>
                <td className="px-3 py-2.5 font-mono text-xs text-gray-500">{r.receipt_no ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {unlockOpen && (
        <UnlockModal
          token={token}
          day={day}
          onClose={() => setUnlockOpen(false)}
          onDone={() => {
            setUnlockOpen(false);
            load();
          }}
        />
      )}
    </div>
  );
}

function UnlockModal({
  token,
  day,
  onClose,
  onDone,
}: {
  token: string;
  day: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<string | null>(null);
  async function go(e: React.FormEvent) {
    e.preventDefault();
    try {
      await clientFetch(`/finance/daily/${day}/unlock`, token, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      onDone();
    } catch (e: any) {
      setErr(e.message);
    }
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <form onSubmit={go} className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-1 text-lg font-bold">解鎖 {day} 的對帳</h2>
        <p className="mb-4 text-sm text-gray-500">
          解鎖會寫入<b>主管覆核紀錄</b>，並使該日暫時不計入月報表合計。
          補收款不需要走這裡，它會自動回寫。
        </p>
        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}
        <textarea
          required
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="解鎖原因（必填）"
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">取消</button>
          <button type="submit" className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white">確認解鎖</button>
        </div>
      </form>
    </div>
  );
}
