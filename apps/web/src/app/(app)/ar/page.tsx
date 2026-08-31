"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import { PAYMENT_TRACKS, SESSION_TYPE, money } from "@/lib/format";

interface ArRow {
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
  receipt_no: string | null;
  is_no_show: boolean;
  no_show_fee: number;
  overdue_days: number;
  severity: "none" | "warn" | "urgent";
}

const SEV: Record<string, string> = {
  none: "",
  warn: "bg-amber-100 text-amber-700",
  urgent: "bg-red-100 text-red-700",
};

export default function ArPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [track, setTrack] = useState("immediate");
  const [rows, setRows] = useState<ArRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [payFor, setPayFor] = useState<ArRow | null>(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const p = new URLSearchParams({ track });
      if (start) p.set("start", start);
      if (end) p.set("end", end);
      setRows(await clientFetch(`/finance/ar?${p}`, token));
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, track, start, end]);

  useEffect(() => {
    load();
  }, [load]);

  const total = rows.reduce((s, r) => s + r.self_pay_amount, 0);
  const instTotal = rows.reduce((s, r) => s + r.institution_claim_amount, 0);

  return (
    <div>
      <h1 className="text-2xl font-bold">應收帳冊</h1>
      <p className="mt-1 text-sm text-gray-500">
        三個分頁分的是<b>追款方式</b>，不是付款狀態：未收＝要催、月結＝月底收、機構＝等撥款。
      </p>

      <div className="mb-4 mt-4 flex gap-2 border-b border-gray-200">
        {PAYMENT_TRACKS.map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTrack(k)}
            className={`px-4 py-2 text-sm ${
              track === k
                ? "border-b-2 border-primary-600 font-medium text-primary-700"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-gray-500">區間</span>
        <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="rounded-lg border border-gray-300 px-2 py-1" />
        <span className="text-gray-400">~</span>
        <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="rounded-lg border border-gray-300 px-2 py-1" />
        {(start || end) && (
          <button onClick={() => { setStart(""); setEnd(""); }} className="text-xs text-primary-600 hover:underline">
            清除
          </button>
        )}
        <span className="ml-auto">
          {rows.length} 筆 · 自付合計 <b>{money(total)}</b>
          {track === "institution" && <> · 機構請款 <b>{money(instTotal)}</b></>}
        </span>
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
      {loading && <p className="text-gray-400">載入中...</p>}

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="w-full text-sm">
          <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs text-gray-500">
            <tr>
              <th className="px-3 py-3">日期</th>
              <th className="px-3 py-3">逾期</th>
              <th className="px-3 py-3">姓名</th>
              <th className="px-3 py-3">心理師</th>
              <th className="px-3 py-3">類型</th>
              <th className="px-3 py-3 text-right">個案自付額</th>
              <th className="px-3 py-3 text-right">機構請款額</th>
              <th className="px-3 py-3">狀態</th>
              <th className="px-3 py-3">操作</th>
            </tr>
          </thead>
          <tbody>
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={9} className="px-4 py-10 text-center text-gray-400">
                  此分頁目前沒有應收款項
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                <td className="px-3 py-3">{r.session_date}</td>
                <td className="px-3 py-3">
                  {r.overdue_days > 0 ? (
                    <span className={`rounded px-1.5 py-0.5 text-xs ${SEV[r.severity]}`}>
                      {r.overdue_days} 天
                    </span>
                  ) : (
                    <span className="text-gray-400">—</span>
                  )}
                </td>
                <td className="px-3 py-3 font-medium">
                  {r.case_name}
                  {r.is_no_show && (
                    <span className="ml-1.5 rounded bg-red-100 px-1 py-0.5 text-[10px] text-red-700">
                      失約費 {money(r.no_show_fee)}
                    </span>
                  )}
                </td>
                <td className="px-3 py-3">{r.therapist_name}</td>
                <td className="px-3 py-3">{SESSION_TYPE[r.session_type] ?? r.session_type}</td>
                <td className="px-3 py-3 text-right tabular-nums">{money(r.self_pay_amount)}</td>
                <td className="px-3 py-3 text-right tabular-nums text-gray-500">
                  {money(r.institution_claim_amount)}
                </td>
                <td className="px-3 py-3 text-xs">
                  {r.payment_status === "unpaid" ? "未付款" : r.payment_status}
                </td>
                <td className="px-3 py-3">
                  {track === "institution" ? (
                    <span className="text-xs text-gray-400">與核銷案連動</span>
                  ) : (
                    <button onClick={() => setPayFor(r)} className="text-xs text-primary-600 hover:underline">
                      收款
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {track === "immediate" && (
        <p className="mt-3 text-xs text-gray-400">
          「未收」只收本來就該當場收卻沒收到的款項；月結與機構全額不在此列。
        </p>
      )}

      {payFor && (
        <PayModal
          token={token}
          row={payFor}
          onClose={() => setPayFor(null)}
          onDone={() => {
            setPayFor(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function PayModal({
  token,
  row,
  onClose,
  onDone,
}: {
  token: string;
  row: ArRow;
  onClose: () => void;
  onDone: () => void;
}) {
  const [method, setMethod] = useState("cash");
  const [note, setNote] = useState("");
  const [discount, setDiscount] = useState("0");
  const [issue, setIssue] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function go(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    try {
      await clientFetch(`/finance/ar/${row.id}/pay`, token, {
        method: "POST",
        body: JSON.stringify({
          payment_method: method,
          payment_note: note || null,
          discount_amount: Number(discount) || 0,
          issue_receipt: issue,
        }),
      });
      onDone();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <form onSubmit={go} className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-1 text-lg font-bold">收款 — {row.case_name}</h2>
        <p className="mb-4 text-sm text-gray-500">
          {row.session_date} · 應收 <b className="text-lg">{money(row.self_pay_amount)}</b>
        </p>
        <p className="mb-3 rounded bg-gray-50 px-3 py-2 text-xs text-gray-500">
          若該日已完成對帳，此筆視為<b>補收款</b>：自動回寫月報表該日，不需解鎖、不列主管覆核。
        </p>
        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}
        <div className="space-y-3">
          <div className="flex gap-3">
            {[["cash", "現金"], ["transfer", "匯款"]].map(([k, label]) => (
              <label key={k} className="flex items-center gap-1.5 text-sm">
                <input type="radio" checked={method === k} onChange={() => setMethod(k)} />
                {label}
              </label>
            ))}
          </div>
          {method === "transfer" && (
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="匯款末 5 碼"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
          )}
          <label className="block text-sm">
            <span className="mb-1 block text-gray-600">優待減免</span>
            <input
              type="number"
              min="0"
              value={discount}
              onChange={(e) => setDiscount(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 tabular-nums"
            />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={issue} onChange={(e) => setIssue(e.target.checked)} />
            收款後立即開立收據
          </label>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">
            取消
          </button>
          <button type="submit" disabled={saving} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
            {saving ? "處理中..." : "確認收款"}
          </button>
        </div>
      </form>
    </div>
  );
}
