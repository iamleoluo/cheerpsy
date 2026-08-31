"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";
import {
  DAY_END_MIN,
  DAY_START_MIN,
  NO_SHOW_TYPES,
  SESSION_TYPE,
  SLOT_MIN,
  hhmm,
  minutesOfDay,
  money,
  shiftDate,
  slotLabels,
  todayISO,
} from "@/lib/format";

interface Room {
  id: number;
  name: string;
  room_code: string;
  room_type: string;
}

interface Appt {
  id: number;
  case_id: number;
  case_name: string | null;
  therapist_name: string | null;
  room_id: number | null;
  session_type: string;
  start_time: string | null;
  end_time: string | null;
  amount: number;
  funding_source: string;
  status: string;
  checkin_status: string;
  no_show_fee: number;
  is_intake: boolean;
  quota_is_last_session: boolean;
  quota_used: number | null;
  quota_total: number | null;
}

interface DailyRow {
  id: number;
  case_name: string | null;
  self_pay_amount: number;
  payment_status: string;
  receipt_no: string | null;
}

const BADGE: Record<string, { label: string; cls: string }> = {
  pending: { label: "待報到", cls: "bg-gray-200 text-gray-600" },
  arrived: { label: "已到", cls: "bg-green-100 text-green-700" },
  absent: { label: "未到", cls: "bg-red-100 text-red-700" },
};

export default function CalendarPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [day, setDay] = useState(todayISO());
  const [rooms, setRooms] = useState<Room[]>([]);
  const [appts, setAppts] = useState<Appt[]>([]);
  const [ledger, setLedger] = useState<DailyRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [absentFor, setAbsentFor] = useState<Appt | null>(null);
  const [payFor, setPayFor] = useState<{ appt: Appt; row: DailyRow } | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [rs, as, dl] = await Promise.all([
        clientFetch("/rooms", token),
        clientFetch(
          `/appointments?start=${day}T00:00:00%2B08:00&end=${shiftDate(day, 1)}T00:00:00%2B08:00`,
          token
        ),
        clientFetch(`/finance/daily?day=${day}`, token).catch(() => null),
      ]);
      setRooms(rs);
      setAppts(as);
      setLedger(dl?.rows ?? []);
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

  const inRoom = useMemo(() => appts.filter((a) => a.room_id), [appts]);
  const offsite = useMemo(() => appts.filter((a) => !a.room_id), [appts]);
  const labels = slotLabels();

  const stats = useMemo(() => {
    const active = appts.filter((a) => a.status !== "cancelled");
    const arrived = active.filter((a) => a.checkin_status === "arrived");
    const absent = active.filter((a) => a.checkin_status === "absent");
    const paid = ledger.filter((r) => r.payment_status === "paid");
    return {
      due: active.length,
      arrived: arrived.length,
      absent: absent.length,
      pending: active.length - arrived.length - absent.length,
      collected: paid.reduce((s, r) => s + r.self_pay_amount, 0),
      outstanding: ledger
        .filter((r) => r.payment_status !== "paid")
        .reduce((s, r) => s + r.self_pay_amount, 0),
    };
  }, [appts, ledger]);

  async function arrive(a: Appt) {
    try {
      await clientFetch(`/appointments/${a.id}/arrive`, token, { method: "PUT" });
      load();
    } catch (e: any) {
      alert(e.message);
    }
  }

  function rowFor(a: Appt): DailyRow | undefined {
    return ledger.find((r) => r.case_name === a.case_name);
  }

  if (loading) return <p className="p-6 text-gray-400">載入中...</p>;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">診間日曆 — 櫃檯主控台</h1>
          <p className="mt-1 text-sm text-gray-500">報到 → 收款 → 開收據，一頁完成</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setDay(shiftDate(day, -1))} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">
            ◀ 前一天
          </button>
          <input
            type="date"
            value={day}
            onChange={(e) => setDay(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
          />
          <button onClick={() => setDay(shiftDate(day, 1))} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">
            後一天 ▶
          </button>
          <button onClick={() => setDay(todayISO())} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">
            今天
          </button>
        </div>
      </div>

      <div className="mb-4 grid grid-cols-3 gap-3 md:grid-cols-6">
        {[
          ["應到", stats.due, ""],
          ["已報到", stats.arrived, "text-green-600"],
          ["未到", stats.absent, "text-red-600"],
          ["待報到", stats.pending, "text-amber-600"],
          ["今日已收", money(stats.collected), "text-primary-700"],
          ["尚待收款", money(stats.outstanding), "text-red-600"],
        ].map(([label, val, cls]) => (
          <div key={label as string} className="rounded-lg border border-gray-200 bg-white px-3 py-2">
            <div className="text-xs text-gray-500">{label}</div>
            <div className={`text-lg font-semibold ${cls}`}>{val}</div>
          </div>
        ))}
      </div>

      {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="w-full border-collapse text-xs">
          <thead className="sticky top-0 bg-gray-50">
            <tr>
              <th className="w-14 border-b border-r border-gray-200 px-1 py-2 text-gray-500">時間</th>
              {rooms.map((r) => (
                <th key={r.id} className="border-b border-r border-gray-200 px-1 py-2 last:border-r-0">
                  <div className="font-medium">{r.room_code}</div>
                  <div className="text-[10px] font-normal text-gray-400">
                    {r.room_type === "play" ? "兒童遊戲室" : "晤談"}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {labels.map((label, i) => {
              const slotStart = DAY_START_MIN + i * SLOT_MIN;
              return (
                <tr key={label}>
                  <td className="border-b border-r border-gray-100 px-1 py-1 text-right align-top text-[10px] text-gray-400">
                    {slotStart % 60 === 0 ? label : ""}
                  </td>
                  {rooms.map((room) => {
                    const a = inRoom.find(
                      (x) =>
                        x.room_id === room.id &&
                        x.start_time &&
                        minutesOfDay(x.start_time) <= slotStart &&
                        (x.end_time ? minutesOfDay(x.end_time) : slotStart + SLOT_MIN) > slotStart
                    );
                    if (!a) {
                      return (
                        <td key={room.id} className="h-8 border-b border-r border-gray-100 last:border-r-0" />
                      );
                    }
                    const isStart = a.start_time && minutesOfDay(a.start_time) === slotStart;
                    if (!isStart) {
                      return (
                        <td
                          key={room.id}
                          className={`border-r border-gray-100 last:border-r-0 ${cellBg(a)}`}
                        />
                      );
                    }
                    return (
                      <td
                        key={room.id}
                        className={`border-b border-r border-gray-100 p-1 align-top last:border-r-0 ${cellBg(a)}`}
                      >
                        <ApptCell
                          a={a}
                          row={rowFor(a)}
                          onArrive={() => arrive(a)}
                          onAbsent={() => setAbsentFor(a)}
                          onPay={(row) => setPayFor({ appt: a, row })}
                        />
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {offsite.length > 0 && (
        <div className="mt-4 rounded-xl border border-gray-200 bg-white p-4">
          <h2 className="mb-2 text-sm font-medium">視訊 / 外展（不佔診間）</h2>
          <div className="grid gap-2 md:grid-cols-3">
            {offsite.map((a) => (
              <div key={a.id} className={`rounded-lg border p-2 ${cellBg(a)}`}>
                <ApptCell
                  a={a}
                  row={rowFor(a)}
                  onArrive={() => arrive(a)}
                  onAbsent={() => setAbsentFor(a)}
                  onPay={(row) => setPayFor({ appt: a, row })}
                />
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-gray-400">
            這兩類個案不會到櫃檯報到，由心理師在「我的班表」處理；超過起始時間後系統自動視為已到。
          </p>
        </div>
      )}

      {absentFor && (
        <AbsentModal
          token={token}
          appt={absentFor}
          onClose={() => setAbsentFor(null)}
          onDone={() => {
            setAbsentFor(null);
            load();
          }}
        />
      )}
      {payFor && (
        <PayModal
          token={token}
          appt={payFor.appt}
          row={payFor.row}
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

function cellBg(a: Appt): string {
  if (a.status === "cancelled") return "bg-gray-100 opacity-50";
  if (a.checkin_status === "absent") return "bg-red-50";
  if (a.checkin_status === "arrived") return "bg-gray-100";
  if (a.is_intake) return "bg-amber-50 ring-1 ring-inset ring-amber-300";
  return a.funding_source === "institution" ? "bg-violet-50" : "bg-blue-50";
}

function ApptCell({
  a,
  row,
  onArrive,
  onAbsent,
  onPay,
}: {
  a: Appt;
  row: DailyRow | undefined;
  onArrive: () => void;
  onAbsent: () => void;
  onPay: (row: DailyRow) => void;
}) {
  const badge = BADGE[a.checkin_status] ?? BADGE.pending;
  const offsite = !a.room_id;
  return (
    <div className={a.quota_is_last_session ? "rounded ring-1 ring-red-400" : ""}>
      <div className="flex items-start justify-between gap-1">
        <span className="truncate font-medium">{a.case_name}</span>
        <span className={`shrink-0 rounded px-1 text-[9px] ${badge.cls}`}>{badge.label}</span>
      </div>
      <div className="truncate text-[10px] text-gray-500">
        {hhmm(a.start_time)}–{hhmm(a.end_time)} · {a.therapist_name}
      </div>
      <div className="truncate text-[10px] text-gray-500">
        {SESSION_TYPE[a.session_type]} ·{" "}
        {a.funding_source === "institution"
          ? `機構 ${a.quota_used ?? "?"}/${a.quota_total ?? "?"}`
          : "自費"}
      </div>
      {a.quota_is_last_session && (
        <div className="text-[10px] font-medium text-red-600">最後一次 · 下次轉自費</div>
      )}
      {a.is_intake && <div className="text-[10px] font-medium text-amber-700">⭐ 媒合初診</div>}

      {a.status !== "cancelled" && a.checkin_status === "pending" && !offsite && (
        <div className="mt-1 flex gap-1">
          <button onClick={onArrive} className="flex-1 rounded border border-gray-400 bg-white px-1 py-0.5 text-[10px] hover:bg-gray-50">
            {a.is_intake ? "初診有到" : "已到"}
          </button>
          <button onClick={onAbsent} className="flex-1 rounded border border-gray-400 bg-white px-1 py-0.5 text-[10px] hover:bg-gray-50">
            未到
          </button>
        </div>
      )}
      {a.checkin_status === "absent" && a.no_show_fee > 0 && (
        <div className="mt-1 text-[10px] text-red-600">失約費 {money(a.no_show_fee)}</div>
      )}
      {a.checkin_status === "arrived" && row && (
        <div className="mt-1">
          {row.payment_status === "paid" ? (
            <span className="text-[10px] text-primary-700">
              已收 {money(row.self_pay_amount)}
              {row.receipt_no && <span className="block font-mono text-[9px] text-gray-400">{row.receipt_no}</span>}
            </span>
          ) : (
            <button
              onClick={() => onPay(row)}
              className="w-full rounded bg-primary-600 px-1 py-0.5 text-[10px] text-white hover:bg-primary-700"
            >
              收款 {money(row.self_pay_amount)}
            </button>
          )}
        </div>
      )}
      {a.checkin_status === "pending" && offsite && (
        <div className="mt-1 text-[10px] text-gray-400">心理師端確認</div>
      )}
    </div>
  );
}

function AbsentModal({
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
  const [type, setType] = useState("late_cancel");
  const [err, setErr] = useState<string | null>(null);
  async function go() {
    try {
      await clientFetch(`/appointments/${appt.id}/absent`, token, {
        method: "PUT",
        body: JSON.stringify({ no_show_type: type }),
      });
      onDone();
    } catch (e: any) {
      setErr(e.message);
    }
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-1 text-lg font-bold">未到原因 — {appt.case_name}</h2>
        <p className="mb-4 text-sm text-gray-500">
          不產生應收諮商費，機構額度釋回為可用；失約費另計。
        </p>
        {err && <div className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}
        <div className="space-y-2">
          {NO_SHOW_TYPES.map(([k, label, fee]) => (
            <label key={k} className="flex items-center gap-2 text-sm">
              <input type="radio" checked={type === k} onChange={() => setType(k)} />
              {label}
              <span className="ml-auto tabular-nums text-gray-500">失約費 {money(fee)}</span>
            </label>
          ))}
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm">
            取消
          </button>
          <button onClick={go} className="rounded-lg bg-gray-700 px-4 py-2 text-sm font-medium text-white">
            確認未到
          </button>
        </div>
      </div>
    </div>
  );
}

function PayModal({
  token,
  appt,
  row,
  onClose,
  onDone,
}: {
  token: string;
  appt: Appt;
  row: DailyRow;
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
        <h2 className="mb-1 text-lg font-bold">收款 — {appt.case_name}</h2>
        <p className="mb-4 text-sm text-gray-500">
          應收 <b className="text-lg">{money(row.self_pay_amount)}</b>
          {appt.funding_source === "institution" && (
            <span className="ml-2 text-xs">（機構案只收自付額，差額轉核銷）</span>
          )}
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
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {saving ? "處理中..." : "確認收款"}
          </button>
        </div>
      </form>
    </div>
  );
}
