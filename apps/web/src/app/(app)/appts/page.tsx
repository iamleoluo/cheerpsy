"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import { BillingDetailModal, BillingLine } from "@/components/billing-summary";
import { AmountField, parseAmount, useCanEditAmount } from "@/components/amount-field";
import { NO_SHOW_TYPES, SESSION_TYPE, hhmm, shiftDate, todayISO } from "@/lib/format";

interface Appt {
  id: number;
  case_id: number;
  case_name: string | null;
  therapist_name: string | null;
  room_name: string | null;
  room_id: number | null;
  session_type: string;
  start_time: string | null;
  end_time: string | null;
  status: string;
  checkin_status: string;
  is_intake: boolean;
  amount?: number;
  self_pay_amount?: number | null;
  plan_name?: string | null;
  rate_item_label?: string | null;
  institution_name?: string | null;
  institution_subsidy?: number | null;
  transport_fee?: number;
  transport_fee_label?: string | null;
  funding_source?: string | null;
  quota_used?: number | null;
  quota_total?: number | null;
  quota_remaining?: number | null;
  quota_is_last_session?: boolean;
}

const STATUS: Record<string, { label: string; cls: string }> = {
  booked: { label: "已預約", cls: "bg-blue-100 text-blue-700" },
  executed: { label: "已執行", cls: "bg-green-100 text-green-700" },
  cancelled: { label: "已取消", cls: "bg-gray-200 text-gray-600" },
  no_show: { label: "未到", cls: "bg-red-100 text-red-700" },
};

export default function ApptsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const role = (session?.user as any)?.role;
  const canAdjust = role === "admin" || role === "staff";
  const [start, setStart] = useState(todayISO());
  const [end, setEnd] = useState(shiftDate(todayISO(), 3));
  const [rows, setRows] = useState<Appt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [fStatus, setFStatus] = useState("");
  const [fType, setFType] = useState("");
  const [absentFor, setAbsentFor] = useState<Appt | null>(null);
  const [adjustFor, setAdjustFor] = useState<Appt | null>(null);
  const [detail, setDetail] = useState<Appt | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      setRows(
        await clientFetch(
          `/appointments?start=${start}T00:00:00%2B08:00&end=${shiftDate(end, 1)}T00:00:00%2B08:00`,
          token
        )
      );
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, start, end]);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(
    () =>
      rows.filter((r) => {
        if (fStatus && r.status !== fStatus) return false;
        if (fType && r.session_type !== fType) return false;
        if (q) {
          const n = q.toLowerCase();
          if (
            !(r.case_name ?? "").toLowerCase().includes(n) &&
            !(r.therapist_name ?? "").toLowerCase().includes(n)
          )
            return false;
        }
        return true;
      }),
    [rows, q, fStatus, fType]
  );

  async function arrive(a: Appt) {
    try {
      await clientFetch(`/appointments/${a.id}/arrive`, token, { method: "PUT" });
      load();
    } catch (e: any) {
      alert(e.message);
    }
  }

  function exportCsv() {
    const head = ["心理師", "個案", "空間", "類型", "日期", "時段", "狀態", "報到"];
    const lines = filtered.map((r) => [
      r.therapist_name ?? "",
      r.case_name ?? "",
      r.room_name ?? "",
      SESSION_TYPE[r.session_type] ?? r.session_type,
      r.start_time?.slice(0, 10) ?? "",
      `${hhmm(r.start_time)}-${hhmm(r.end_time)}`,
      STATUS[r.status]?.label ?? r.status,
      r.checkin_status,
    ]);
    const csv = [head, ...lines].map((c) => c.map((x) => `"${x}"`).join(",")).join("\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `預約總表_${start}_${end}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">預約總表</h1>
          <p className="mt-1 text-sm text-gray-500">
            跨日期區間的查詢與稽核總表。每日現場作業請用診間日曆——兩處是同一份資料。
          </p>
        </div>
        <button onClick={exportCsv} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">
          匯出 CSV
        </button>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="rounded-lg border border-gray-300 px-2 py-1.5" />
        <span className="text-gray-400">~</span>
        <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="rounded-lg border border-gray-300 px-2 py-1.5" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜尋 個案／心理師" className="w-52 rounded-lg border border-gray-300 px-3 py-1.5" />
        <select value={fStatus} onChange={(e) => setFStatus(e.target.value)} className="rounded-lg border border-gray-300 px-2 py-1.5">
          <option value="">全部狀態</option>
          {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <select value={fType} onChange={(e) => setFType(e.target.value)} className="rounded-lg border border-gray-300 px-2 py-1.5">
          <option value="">全部類型</option>
          {Object.entries(SESSION_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <span className="ml-auto text-gray-500">{filtered.length} 筆</span>
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
      {loading && <p className="text-gray-400">載入中...</p>}

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="w-full text-sm">
          <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs text-gray-500">
            <tr>
              <th className="px-3 py-3">預約日期</th>
              <th className="px-3 py-3">姓名</th>
              <th className="px-3 py-3">心理師</th>
              <th className="px-3 py-3">時間</th>
              <th className="px-3 py-3">類型</th>
              <th className="px-3 py-3">診間</th>
              <th className="px-3 py-3">狀態</th>
              <th className="px-3 py-3">行政確認</th>
              {canAdjust && <th className="px-3 py-3">調整</th>}
            </tr>
          </thead>
          <tbody>
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={canAdjust ? 9 : 8} className="px-4 py-10 text-center text-gray-400">此區間沒有符合的預約</td></tr>
            )}
            {filtered.map((r) => {
              const st = STATUS[r.status] ?? { label: r.status, cls: "bg-gray-100" };
              const offsite = !r.room_id;
              return (
                <tr key={r.id} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                  <td className="px-3 py-2.5">{r.start_time?.slice(0, 10)}</td>
                  <td className="px-3 py-2.5 font-medium">
                    {r.is_intake && <span className="mr-1 text-amber-600" title="媒合初診">⭐</span>}
                    {r.case_name}
                    <button type="button" onClick={() => setDetail(r)} className="mt-0.5 block text-left text-[11px] font-normal hover:underline" title="金額與經費來源">
                      <BillingLine a={r} />
                    </button>
                  </td>
                  <td className="px-3 py-2.5">{r.therapist_name}</td>
                  <td className="px-3 py-2.5 tabular-nums">{hhmm(r.start_time)}–{hhmm(r.end_time)}</td>
                  <td className="px-3 py-2.5">{SESSION_TYPE[r.session_type] ?? r.session_type}</td>
                  <td className="px-3 py-2.5">{r.room_name ?? "—"}</td>
                  <td className="px-3 py-2.5">
                    <span className={`rounded px-1.5 py-0.5 text-xs ${st.cls}`}>{st.label}</span>
                  </td>
                  <td className="px-3 py-2.5">
                    {offsite ? (
                      <span className="text-xs text-gray-400">心理師端確認</span>
                    ) : r.checkin_status === "pending" && r.status === "booked" ? (
                      <div className="flex gap-2 text-xs">
                        <button onClick={() => arrive(r)} className="text-primary-600 hover:underline">
                          {r.is_intake ? "初診有到" : "已到"}
                        </button>
                        <button onClick={() => setAbsentFor(r)} className="text-red-500 hover:underline">未到</button>
                      </div>
                    ) : (
                      <span className="text-xs text-gray-500">
                        {r.checkin_status === "arrived" ? "已到" : r.checkin_status === "absent" ? "未到" : "—"}
                      </span>
                    )}
                  </td>
                  {canAdjust && (
                    <td className="px-3 py-2.5">
                      {r.status === "booked" ? (
                        <button onClick={() => setAdjustFor(r)} className="text-xs text-primary-600 hover:underline">
                          改期／改房
                        </button>
                      ) : (
                        <span className="text-xs text-gray-300">—</span>
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {detail && <BillingDetailModal appt={detail} onClose={() => setDetail(null)} />}

      {adjustFor && (
        <AdjustModal
          token={token}
          appt={adjustFor}
          onClose={() => setAdjustFor(null)}
          onDone={() => {
            setAdjustFor(null);
            load();
          }}
        />
      )}

      {absentFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-bold">未到原因 — {absentFor.case_name}</h2>
            <div className="space-y-2">
              {NO_SHOW_TYPES.map(([k, label]) => (
                <button
                  key={k}
                  onClick={async () => {
                    try {
                      await clientFetch(`/appointments/${absentFor.id}/absent`, token, {
                        method: "PUT",
                        body: JSON.stringify({ no_show_type: k }),
                      });
                      setAbsentFor(null);
                      load();
                    } catch (e: any) {
                      alert(e.message);
                    }
                  }}
                  className="flex w-full items-center justify-between rounded-lg border border-gray-300 px-3 py-2 text-sm hover:bg-gray-50"
                >
                  <span>{label}</span>
                </button>
              ))}
            </div>
            <div className="mt-6 flex justify-end">
              <button onClick={() => setAbsentFor(null)} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">取消</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface FreeRoom {
  id: number;
  room_code: string;
  room_type: string;
}

/** 行政調整已預約場次的日期、時段與診間。診間只列「該時段空著」的（伺服器算，排除自己）。 */
function AdjustModal({
  token,
  appt,
  onClose,
  onDone,
}: {
  token: string;
  appt: Appt;
  onClose: () => void;
  onDone: () => void;
}) {
  const inPerson = appt.session_type === "in_person";
  const [date, setDate] = useState(appt.start_time?.slice(0, 10) ?? "");
  const [st, setSt] = useState(hhmm(appt.start_time));
  const [et, setEt] = useState(hhmm(appt.end_time));
  const [roomId, setRoomId] = useState(appt.room_id ? String(appt.room_id) : "");
  const [free, setFree] = useState<FreeRoom[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const canAmount = useCanEditAmount();
  const selfPay = (appt.funding_source ?? "self_pay") !== "institution";
  const [amount, setAmount] = useState(String(appt.amount ?? 0));

  useEffect(() => {
    if (!inPerson || !date || !st || !et || st >= et) {
      setFree(null);
      return;
    }
    let stale = false;
    const q = `start=${encodeURIComponent(`${date}T${st}:00+08:00`)}&end=${encodeURIComponent(`${date}T${et}:00+08:00`)}&exclude_appointment_id=${appt.id}`;
    clientFetch(`/rooms/availability?${q}`, token)
      .then((r: FreeRoom[]) => {
        if (stale) return;
        setFree(r);
        // 目前選的診間不在空房清單裡就清掉，避免送出一定衝突的組合
        setRoomId((cur) => (cur && !r.some((x) => String(x.id) === cur) ? "" : cur));
      })
      .catch(() => { if (!stale) setFree(null); });
    return () => { stale = true; };
  }, [token, inPerson, date, st, et, appt.id]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    try {
      const body: Record<string, unknown> = {
        start_time: `${date}T${st}:00+08:00`,
        end_time: `${date}T${et}:00+08:00`,
      };
      if (inPerson) body.room_id = Number(roomId);
      // 改期不動機構案的金額（由方案帶出）；自費案只在金額有改時才送，且不可清空
      if (canAmount && selfPay && amount !== String(appt.amount ?? "")) {
        const amt = parseAmount(amount);
        if (amt === undefined || amt <= 0) { setErr("自費預約請填金額（須大於 0）"); setSaving(false); return; }
        body.amount = amt;
      }
      await clientFetch(`/appointments/${appt.id}`, token, { method: "PUT", body: JSON.stringify(body) });
      onDone();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <form onSubmit={save} className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-1 text-lg font-bold">改期／改房 — {appt.case_name}</h2>
        <p className="mb-4 text-xs text-gray-500">
          原本：{appt.start_time?.slice(0, 10)} {hhmm(appt.start_time)}–{hhmm(appt.end_time)} · {appt.room_name ?? "—"}
        </p>
        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}
        <div className="grid grid-cols-3 gap-2 text-sm">
          <label className="col-span-3 block">
            <span className="mb-1 block text-xs text-gray-500">日期</span>
            <input required type="date" value={date} onChange={(e) => setDate(e.target.value)} className="w-full rounded-lg border border-gray-300 px-2 py-1.5" />
          </label>
          <label className="col-span-1 block">
            <span className="mb-1 block text-xs text-gray-500">開始</span>
            <input required type="time" step={900} value={st} onChange={(e) => setSt(e.target.value)} className="w-full rounded-lg border border-gray-300 px-2 py-1.5" />
          </label>
          <label className="col-span-1 block">
            <span className="mb-1 block text-xs text-gray-500">結束</span>
            <input required type="time" step={900} value={et} onChange={(e) => setEt(e.target.value)} className="w-full rounded-lg border border-gray-300 px-2 py-1.5" />
          </label>
          {inPerson && (
            <label className="col-span-3 block">
              <span className="mb-1 block text-xs text-gray-500">診間（只列此時段空著的）</span>
              <select required value={roomId} onChange={(e) => setRoomId(e.target.value)} className="w-full rounded-lg border border-gray-300 px-2 py-1.5">
                <option value="">請選擇</option>
                {(free ?? []).map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.room_code}{r.room_type === "play" ? "（遊戲室）" : ""}
                  </option>
                ))}
              </select>
              {free && free.length === 0 && <span className="mt-1 block text-xs text-red-600">此時段沒有空房</span>}
            </label>
          )}
        </div>
        {selfPay && <AmountField required value={amount} onChange={setAmount} className="mt-3" />}
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">取消</button>
          <button type="submit" disabled={saving || (inPerson && !roomId)} className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
            {saving ? "儲存中..." : "儲存"}
          </button>
        </div>
      </form>
    </div>
  );
}
