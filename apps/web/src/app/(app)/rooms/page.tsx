"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

/**
 * 診間日曆（櫃檯主控台）— V2升級計畫 09 §0.1 標記的「照樣本」page，
 * 後端報到三步驟（已到/未到 → 收款 → 開立收據）與房間衝突 DB 層防護
 * 已在 08 §5.3–§5.5 全部完成並測試覆蓋，這裡是第一個把整條後端流程接上
 * 畫面的頁面。
 *
 * 時間軸 08:00–22:00、半小時一格，對應定稿 A3／v7 原型 TICKS。
 */

interface Room {
  id: number;
  name: string;
  floor: number;
  room_code: string;
  use_type?: string | null; // 晤談 / 兒童遊戲室
  size?: string | null;
}

interface Appointment {
  id: number;
  appointment_number: string;
  case_id: number;
  case_name: string | null;
  is_couple?: boolean;
  couple_name?: string | null;
  therapist_id: number;
  therapist_name: string | null;
  room_id: number | null;
  room_name: string | null;
  session_type: string;
  start_time: string | null;
  end_time: string | null;
  amount: number;
  funding_source: string;
  status: string;
  plan_name: string | null;
  case_payable: number | null;
  institution_payable: number | null;
  check_in_status: "pending" | "arrived" | "no_show";
  checked_in_at: string | null;
  no_show_reason: string | null;
  no_show_note: string | null;
  no_show_followup: string | null;
  copay_collected_at: string | null;
  copay_payment_method: string | null;
  receipt_no: string | null;
}

interface FeeItem {
  id: number;
  name: string;
  is_default: boolean;
}

const SLOT_HOURS = Array.from({ length: 28 }, (_, i) => {
  const totalMin = 8 * 60 + i * 30;
  const h = Math.floor(totalMin / 60).toString().padStart(2, "0");
  const m = (totalMin % 60).toString().padStart(2, "0");
  return `${h}:${m}`;
}); // 08:00 ~ 21:30

const sessionTypeLabel: Record<string, string> = { in_person: "現場", online: "視訊", outdoor: "外展" };

const NO_SHOW_REASONS: { value: string; label: string }[] = [
  { value: "case_leave", label: "個案來電請假" },
  { value: "last_minute_cancel", label: "臨時取消" },
  { value: "unreachable", label: "未聯繫上" },
  { value: "other", label: "其他" },
];

function toLocalDateString(d: Date): string {
  const y = d.getFullYear();
  const m = (d.getMonth() + 1).toString().padStart(2, "0");
  const day = d.getDate().toString().padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function cellStyle(a: Appointment): string {
  if (a.check_in_status === "no_show") return "bg-gray-100 text-gray-400 line-through decoration-gray-300";
  if (a.check_in_status === "arrived") {
    if (a.receipt_no) return "bg-emerald-50 text-emerald-800 border-emerald-200";
    if (a.copay_collected_at) return "bg-sky-50 text-sky-800 border-sky-200";
    return "bg-amber-50 text-amber-800 border-amber-200";
  }
  return "bg-primary-50 text-primary-700 border-primary-100";
}

function cellBadge(a: Appointment): string {
  if (a.check_in_status === "no_show") return "✕";
  if (a.check_in_status === "arrived") {
    if (a.receipt_no) return "✓";
    if (a.copay_collected_at) return "💰";
    return "●";
  }
  return "";
}

export default function RoomsPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;
  const [selectedDate, setSelectedDate] = useState<Date>(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  });
  const [rooms, setRooms] = useState<Room[]>([]);
  const [appts, setAppts] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Appointment | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    if (!token) return;
    clientFetch("/rooms", token).then(setRooms).catch(() => {});
  }, [token]);

  const fetchAppts = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const start = new Date(selectedDate);
      const end = new Date(selectedDate);
      end.setDate(end.getDate() + 1);
      const data = await clientFetch(
        `/appointments?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`,
        token,
      );
      setAppts(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token, selectedDate]);

  useEffect(() => {
    fetchAppts();
  }, [fetchAppts, refreshTick]);

  // 選取的預約若剛被更新（例如報到後），從最新的 appts 清單同步內容
  useEffect(() => {
    if (!selected) return;
    const fresh = appts.find((a) => a.id === selected.id);
    if (fresh) setSelected(fresh);
  }, [appts]); // eslint-disable-line react-hooks/exhaustive-deps

  type Matrix = Record<string, Record<number, Appointment>>;
  const matrix: Matrix = useMemo(() => {
    const m: Matrix = {};
    for (const slot of SLOT_HOURS) m[slot] = {};
    for (const a of appts) {
      if (a.status === "cancelled") continue;
      if (!a.start_time || !a.end_time || !a.room_id) continue;
      const start = new Date(a.start_time);
      const end = new Date(a.end_time);
      const cur = new Date(start);
      while (cur < end) {
        const key = `${cur.getHours().toString().padStart(2, "0")}:${cur.getMinutes() < 30 ? "00" : "30"}`;
        if (m[key]) m[key][a.room_id!] = a;
        cur.setMinutes(cur.getMinutes() + 30);
      }
    }
    return m;
  }, [appts]);

  const prevDay = () => setSelectedDate((d) => { const n = new Date(d); n.setDate(n.getDate() - 1); return n; });
  const nextDay = () => setSelectedDate((d) => { const n = new Date(d); n.setDate(n.getDate() + 1); return n; });
  const goToday = () => { const d = new Date(); d.setHours(0, 0, 0, 0); setSelectedDate(d); };
  const dateLabel = selectedDate.toLocaleDateString("zh-TW", { year: "numeric", month: "long", day: "numeric", weekday: "short" });

  if (!token) return <p>Loading...</p>;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">診間日曆</h1>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-1"><i className="inline-block h-2.5 w-2.5 rounded-sm bg-primary-100" />已預約</span>
          <span className="flex items-center gap-1"><i className="inline-block h-2.5 w-2.5 rounded-sm bg-amber-100" />已到·待收款</span>
          <span className="flex items-center gap-1"><i className="inline-block h-2.5 w-2.5 rounded-sm bg-sky-100" />已收款·待開據</span>
          <span className="flex items-center gap-1"><i className="inline-block h-2.5 w-2.5 rounded-sm bg-emerald-100" />已完成</span>
          <span className="flex items-center gap-1"><i className="inline-block h-2.5 w-2.5 rounded-sm bg-gray-200" />未到</span>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <button onClick={prevDay} className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm hover:bg-gray-50">← 前一天</button>
        <button onClick={goToday} className="rounded-lg border border-primary-300 px-3 py-1.5 text-sm text-primary-600 hover:bg-primary-50">今天</button>
        <button onClick={nextDay} className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm hover:bg-gray-50">後一天 →</button>
        <span className="text-sm font-medium text-gray-700">{dateLabel}</span>
        <input
          type="date"
          value={toLocalDateString(selectedDate)}
          onChange={(e) => {
            if (!e.target.value) return;
            const [y, m, d] = e.target.value.split("-").map(Number);
            const nd = new Date(y, m - 1, d);
            nd.setHours(0, 0, 0, 0);
            setSelectedDate(nd);
          }}
          className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm focus:border-primary-400 focus:outline-none"
        />
        {loading && <span className="text-xs text-gray-400">載入中...</span>}
      </div>

      {rooms.length === 0 ? (
        <div className="py-12 text-center text-sm text-gray-400">載入診間中…</div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="bg-gray-50">
                <th className="w-14 border-b border-r border-gray-200 px-2 py-2 text-left text-gray-500">時段</th>
                {rooms.map((r) => (
                  <th key={r.id} className="min-w-[86px] border-b border-r border-gray-200 px-2 py-2 text-center font-medium">
                    <div className="leading-tight">{r.name}</div>
                    <div className="text-[10px] font-normal text-gray-400">
                      {r.floor}F · {r.use_type === "兒童遊戲室" ? "👶 遊戲室" : "晤談"}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {SLOT_HOURS.map((slot) => {
                const rowHasAny = rooms.some((r) => matrix[slot]?.[r.id]);
                return (
                  <tr key={slot} className={rowHasAny ? "bg-white" : "bg-gray-50/30"}>
                    <td className="whitespace-nowrap border-b border-r border-gray-200 px-2 py-1 font-mono text-gray-400">{slot}</td>
                    {rooms.map((r) => {
                      const appt = matrix[slot]?.[r.id];
                      return (
                        <td key={r.id} className={`border-b border-r border-gray-200 px-1 py-1 align-middle ${appt ? cellStyle(appt) : ""}`}>
                          {appt && (
                            <button
                              onClick={() => setSelected(appt)}
                              title={`${appt.therapist_name ?? ""} ${appt.start_time?.slice(11, 16)}~${appt.end_time?.slice(11, 16)}`}
                              className="block w-full truncate rounded px-1 py-0.5 text-left leading-tight hover:opacity-70"
                            >
                              <span className="mr-1">{cellBadge(appt)}</span>
                              {appt.is_couple ? `👫 ${appt.couple_name?.slice(0, 6) ?? ""}` : appt.case_name?.slice(0, 5) ?? appt.therapist_name?.slice(0, 4) ?? "—"}
                            </button>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <CheckInPanel
          key={selected.id}
          appt={selected}
          token={token}
          onClose={() => setSelected(null)}
          onChanged={() => setRefreshTick((t) => t + 1)}
        />
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════
   報到三步驟：已到/未到 → 收款 → 開立收據
   一次只出現一步（見 V2升級計畫 03 §操作體驗細節）
   ═══════════════════════════════════════════════ */

function CheckInPanel({
  appt,
  token,
  onClose,
  onChanged,
}: {
  appt: Appointment;
  token: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feeItems, setFeeItems] = useState<FeeItem[]>([]);

  // 未到表單
  const [noShowReason, setNoShowReason] = useState("case_leave");
  const [noShowNote, setNoShowNote] = useState("");
  const [noShowFollowup, setNoShowFollowup] = useState("");
  const [showNoShowForm, setShowNoShowForm] = useState(false);

  // 收款表單
  const [payMethod, setPayMethod] = useState<"cash" | "transfer">("cash");
  const [payNote, setPayNote] = useState("");

  // 收據表單
  const [feeItemId, setFeeItemId] = useState<number | "">("");
  const [customFeeName, setCustomFeeName] = useState("");
  const [receiptNote, setReceiptNote] = useState("");

  useEffect(() => {
    if (appt.check_in_status === "arrived" && appt.copay_collected_at && !appt.receipt_no) {
      clientFetch("/fee-items", token).then(setFeeItems).catch(() => {});
    }
  }, [appt.check_in_status, appt.copay_collected_at, appt.receipt_no, token]);

  const payable = appt.case_payable ?? appt.amount;

  async function doCheckIn(status: "arrived" | "no_show") {
    setBusy(true);
    setError(null);
    try {
      await clientFetch(`/appointments/${appt.id}/check-in`, token, {
        method: "PUT",
        body: JSON.stringify(
          status === "arrived"
            ? { status }
            : { status, no_show_reason: noShowReason, no_show_note: noShowNote || null, no_show_followup: noShowFollowup || null },
        ),
      });
      onChanged();
    } catch (e: any) {
      setError(e.message ?? "操作失敗");
    } finally {
      setBusy(false);
    }
  }

  async function doPayment() {
    setBusy(true);
    setError(null);
    try {
      await clientFetch(`/appointments/${appt.id}/payment-step`, token, {
        method: "POST",
        body: JSON.stringify({ payment_method: payMethod, payment_note: payNote || null }),
      });
      onChanged();
    } catch (e: any) {
      setError(e.message ?? "收款失敗");
    } finally {
      setBusy(false);
    }
  }

  async function doReceipt() {
    setBusy(true);
    setError(null);
    try {
      await clientFetch(`/appointments/${appt.id}/receipt`, token, {
        method: "POST",
        body: JSON.stringify({
          fee_item_id: feeItemId || null,
          fee_item_custom_name: feeItemId ? null : customFeeName || null,
          note: receiptNote || null,
        }),
      });
      onChanged();
    } catch (e: any) {
      setError(e.message ?? "開立收據失敗");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div className="max-h-[90vh] w-[420px] overflow-y-auto rounded-xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-start justify-between">
          <div>
            <h3 className="font-semibold">{appt.appointment_number}</h3>
            <p className="text-xs text-gray-400 mt-0.5">
              {appt.is_couple ? `👫 ${appt.couple_name}` : appt.case_name} · {appt.therapist_name} · {sessionTypeLabel[appt.session_type] ?? appt.session_type}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">✕</button>
        </div>

        <dl className="mb-4 space-y-1 rounded-lg bg-gray-50 p-3 text-xs">
          <div className="flex justify-between"><dt className="text-gray-500">時間</dt><dd>{appt.start_time?.slice(11, 16)} ~ {appt.end_time?.slice(11, 16)}</dd></div>
          <div className="flex justify-between"><dt className="text-gray-500">診間</dt><dd>{appt.room_name ?? "—"}</dd></div>
          <div className="flex justify-between"><dt className="text-gray-500">方案</dt><dd>{appt.plan_name ?? (appt.funding_source === "institution" ? "機構（舊路徑）" : "自費")}</dd></div>
          {appt.institution_payable != null && (
            <div className="flex justify-between"><dt className="text-gray-500">機構請款</dt><dd className="text-gray-400">${appt.institution_payable.toLocaleString()}（走機構核銷，與此無關）</dd></div>
          )}
          <div className="flex justify-between font-medium"><dt className="text-gray-600">個案應收</dt><dd>${payable.toLocaleString()}</dd></div>
        </dl>

        {error && <div className="mb-3 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{error}</div>}

        {/* 步驟指示 */}
        <div className="mb-4 flex items-center gap-1 text-[10px] text-gray-400">
          <StepDot done={appt.check_in_status !== "pending"} active={appt.check_in_status === "pending"} label="報到" />
          <span>→</span>
          <StepDot done={!!appt.copay_collected_at || payable <= 0} active={appt.check_in_status === "arrived" && !appt.copay_collected_at} label="收款" />
          <span>→</span>
          <StepDot done={!!appt.receipt_no} active={appt.check_in_status === "arrived" && !!appt.copay_collected_at && !appt.receipt_no} label="開據" />
        </div>

        {/* ── 步驟 1：報到 ── */}
        {appt.check_in_status === "pending" && !showNoShowForm && (
          <div className="flex gap-2">
            <button disabled={busy} onClick={() => doCheckIn("arrived")} className="flex-1 rounded-lg bg-primary-600 py-2.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">
              ✓ 已到
            </button>
            <button disabled={busy} onClick={() => setShowNoShowForm(true)} className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm text-gray-600 hover:bg-gray-50">
              未到
            </button>
          </div>
        )}
        {appt.check_in_status === "pending" && showNoShowForm && (
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs text-gray-500">未到原因</label>
              <select value={noShowReason} onChange={(e) => setNoShowReason(e.target.value)} className="w-full rounded-lg border border-gray-200 px-2 py-1.5 text-sm">
                {NO_SHOW_REASONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-gray-500">備註（選填）</label>
              <input value={noShowNote} onChange={(e) => setNoShowNote(e.target.value)} className="w-full rounded-lg border border-gray-200 px-2 py-1.5 text-sm" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-gray-500">催繳方式（選填）</label>
              <input value={noShowFollowup} onChange={(e) => setNoShowFollowup(e.target.value)} className="w-full rounded-lg border border-gray-200 px-2 py-1.5 text-sm" />
            </div>
            <div className="flex gap-2">
              <button disabled={busy} onClick={() => doCheckIn("no_show")} className="flex-1 rounded-lg bg-gray-700 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50">
                確認未到
              </button>
              <button onClick={() => setShowNoShowForm(false)} className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-500 hover:bg-gray-50">
                返回
              </button>
            </div>
          </div>
        )}

        {/* 未到後的摘要（唯讀） */}
        {appt.check_in_status === "no_show" && (
          <div className="rounded-lg bg-gray-50 p-3 text-xs text-gray-500">
            <p className="mb-1 font-medium text-gray-600">未到 · {NO_SHOW_REASONS.find((r) => r.value === appt.no_show_reason)?.label ?? appt.no_show_reason}</p>
            {appt.no_show_note && <p>備註：{appt.no_show_note}</p>}
            {appt.no_show_followup && <p>催繳：{appt.no_show_followup}</p>}
          </div>
        )}

        {/* ── 步驟 2：收款 ── */}
        {appt.check_in_status === "arrived" && !appt.copay_collected_at && payable > 0 && (
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs text-gray-500">收款方式</label>
              <div className="flex gap-2">
                {(["cash", "transfer"] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => setPayMethod(m)}
                    className={`flex-1 rounded-lg border py-2 text-sm ${payMethod === m ? "border-primary-500 bg-primary-50 text-primary-700" : "border-gray-200 text-gray-500 hover:bg-gray-50"}`}
                  >
                    {m === "cash" ? "現金" : "匯款"}
                  </button>
                ))}
              </div>
            </div>
            {payMethod === "transfer" && (
              <div>
                <label className="mb-1 block text-xs text-gray-500">匯款資訊（如帳戶末五碼）<span className="text-rose-500">*</span></label>
                <input value={payNote} onChange={(e) => setPayNote(e.target.value)} className="w-full rounded-lg border border-gray-200 px-2 py-1.5 text-sm" />
              </div>
            )}
            <button disabled={busy} onClick={doPayment} className="w-full rounded-lg bg-primary-600 py-2.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">
              確認收款 ${payable.toLocaleString()}
            </button>
          </div>
        )}

        {/* 機構全額免收 */}
        {appt.check_in_status === "arrived" && !appt.copay_collected_at && payable <= 0 && (
          <div className="rounded-lg bg-sky-50 p-3 text-xs text-sky-700">此筆機構全額補助，個案免收款，無需開立收據。</div>
        )}

        {/* ── 步驟 3：開立收據 ── */}
        {appt.check_in_status === "arrived" && appt.copay_collected_at && !appt.receipt_no && (
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs text-gray-500">收款項目</label>
              <select
                value={feeItemId}
                onChange={(e) => setFeeItemId(e.target.value ? Number(e.target.value) : "")}
                className="w-full rounded-lg border border-gray-200 px-2 py-1.5 text-sm"
              >
                <option value="">— 選擇項目 —</option>
                {feeItems.map((fi) => <option key={fi.id} value={fi.id}>{fi.name}</option>)}
                <option value="">其他（自行登打）</option>
              </select>
            </div>
            {!feeItemId && (
              <div>
                <label className="mb-1 block text-xs text-gray-500">自訂項目名稱</label>
                <input value={customFeeName} onChange={(e) => setCustomFeeName(e.target.value)} className="w-full rounded-lg border border-gray-200 px-2 py-1.5 text-sm" placeholder="未在清單中時填寫" />
              </div>
            )}
            <div>
              <label className="mb-1 block text-xs text-gray-500">備註（選填）</label>
              <input value={receiptNote} onChange={(e) => setReceiptNote(e.target.value)} className="w-full rounded-lg border border-gray-200 px-2 py-1.5 text-sm" />
            </div>
            <button disabled={busy} onClick={doReceipt} className="w-full rounded-lg bg-primary-600 py-2.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">
              開立收據
            </button>
          </div>
        )}

        {/* 已完成 */}
        {appt.check_in_status === "arrived" && (appt.receipt_no || (appt.copay_collected_at && payable <= 0)) && (
          <div className="rounded-lg bg-emerald-50 p-3 text-xs text-emerald-700">
            ✓ 報到→收款→開據已完成{appt.receipt_no ? `（收據 ${appt.receipt_no}）` : ""}
          </div>
        )}
      </div>
    </div>
  );
}

function StepDot({ done, active, label }: { done: boolean; active: boolean; label: string }) {
  return (
    <span className={`flex items-center gap-1 rounded px-1.5 py-0.5 ${done ? "bg-emerald-100 text-emerald-700" : active ? "bg-amber-100 text-amber-700" : "bg-gray-100 text-gray-400"}`}>
      {done ? "✓" : "·"} {label}
    </span>
  );
}
