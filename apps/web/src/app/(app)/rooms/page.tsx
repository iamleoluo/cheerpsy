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

interface VenueRental {
  id: number;
  rental_no: string;
  room_id: number;
  room_name: string | null;
  start_time: string | null;
  end_time: string | null;
  purpose: string | null;
  renter_kind: string;
  renter_name: string;
  renter_therapist_name: string | null;
  supervision_fee_mode: string | null;
  amount: number;
  payer: string;
  attendance: string;
  status: string;
}

interface HallBooking {
  id: number;
  title: string;
  setup_start: string | null;
  setup_end: string | null;
  event_start: string | null;
  event_end: string | null;
  lecturer_kind: string;
  lecturer_name: string | null;
  lecturer_fee: number | null;
  fee_to_clinic_account: boolean;
  borrower: string | null;
  attendee_count: number | null;
  status: string;
}

const PAYER_LABEL: Record<string, string> = {
  institution: "機構應收",
  therapist: "心理師酬勞扣回",
  renter: "借用人自付",
};

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
  // 三個分頁對應三種空間佔用（v7 診間日曆定案）：診間、外借的診間、5F 雲燈教室
  const [tab, setTab] = useState<"rooms" | "rentals" | "hall">("rooms");

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

      <div className="mb-3 flex gap-1 border-b border-gray-200">
        {([
          ["rooms", "診間"],
          ["rentals", "場地租借"],
          ["hall", "5F 雲燈教室"],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium ${
              tab === key ? "border-b-2 border-primary-600 text-primary-700" : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "rentals" && <RentalsTab token={token} date={selectedDate} />}
      {tab === "hall" && <HallTab token={token} date={selectedDate} />}

      {tab === "rooms" && (rooms.length === 0 ? (
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
      ))}

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

        {/* 行政流程提醒：整格轉灰的三個條件之一就是這些事項全勾完 */}
        <AdminTasks apptId={appt.id} token={token} onChanged={onChanged} />

        {/* 加時／請假／視訊連結——刻意收合，按了才展開（03 §操作體驗細節） */}
        <ExtraActions appt={appt} token={token} onChanged={onChanged} payable={payable} />
      </div>
    </div>
  );
}

/* ── 行政流程提醒 checklist（02 §1.2、07 §5.3 ⑥）────────────────── */

interface AdminTask {
  id: number;
  title: string;
  side: string;
  is_done: boolean;
  done_at: string | null;
  done_by_name: string | null;
}

function AdminTasks({ apptId, token, onChanged }: { apptId: number; token: string; onChanged: () => void }) {
  const [tasks, setTasks] = useState<AdminTask[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    clientFetch(`/appointments/${apptId}/admin-tasks`, token).then(setTasks).catch(() => setTasks([]));
  }, [apptId, token]);
  useEffect(load, [load]);

  if (tasks.length === 0) return null;
  const open = tasks.filter((t) => !t.is_done).length;

  async function toggle(t: AdminTask) {
    setBusy(true);
    try {
      await clientFetch(`/appointments/admin-tasks/${t.id}`, token, {
        method: "PUT",
        body: JSON.stringify({ is_done: !t.is_done }),
      });
      load();
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-4 rounded-lg border border-gray-200 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-gray-600">
        行政流程提醒
        {open > 0 ? (
          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-700">還有 {open} 項未完成</span>
        ) : (
          <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] text-emerald-700">已全部完成</span>
        )}
      </div>
      <ul className="space-y-1.5">
        {tasks.map((t) => (
          <li key={t.id} className="flex items-start gap-2 text-xs">
            <input type="checkbox" checked={t.is_done} disabled={busy} onChange={() => toggle(t)} className="mt-0.5" />
            <span className={t.is_done ? "text-gray-400 line-through" : "text-gray-700"}>
              {t.title}
              <span className="ml-1 text-[10px] text-gray-400">（{t.side === "admin" ? "行政" : "心理師"}）</span>
              {t.is_done && t.done_at && (
                <span className="ml-1 text-[10px] text-emerald-600">
                  ✓ {t.done_by_name ?? ""} {t.done_at.slice(5, 10)} {t.done_at.slice(11, 16)}
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ── 加時 / 請假 / 視訊連結 / 收據作廢重印 ───────────────────────── */

interface ReceiptRow {
  id: number;
  receipt_no: string;
  amount: number;
  status: string;
  void_reason: string | null;
}

function ExtraActions({
  appt, token, onChanged, payable,
}: { appt: Appointment; token: string; onChanged: () => void; payable: number }) {
  const [open, setOpen] = useState<null | "duration" | "leave" | "video" | "receipts">(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [durMinutes, setDurMinutes] = useState(() => {
    if (!appt.start_time || !appt.end_time) return 60;
    return Math.round((new Date(appt.end_time).getTime() - new Date(appt.start_time).getTime()) / 60000);
  });
  const [durNote, setDurNote] = useState("");
  const [leaveReason, setLeaveReason] = useState("");
  const [videoLink, setVideoLink] = useState("");
  const [receipts, setReceipts] = useState<ReceiptRow[]>([]);
  const [voidReason, setVoidReason] = useState("");

  async function run(fn: () => Promise<any>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onChanged();
      setOpen(null);
    } catch (e: any) {
      setError(e.message ?? "操作失敗");
    } finally {
      setBusy(false);
    }
  }

  async function loadReceipts() {
    setOpen("receipts");
    setReceipts(await clientFetch(`/appointments/${appt.id}/receipts`, token).catch(() => []));
  }

  const canAdjust = appt.check_in_status !== "no_show" && !appt.copay_collected_at;
  const canLeave = appt.check_in_status === "pending" && appt.status === "booked";

  return (
    <div className="mt-3 border-t border-gray-100 pt-3">
      <div className="flex flex-wrap gap-1.5 text-xs">
        {canAdjust && (
          <button onClick={() => setOpen(open === "duration" ? null : "duration")} className="rounded-lg border border-gray-200 px-2 py-1 text-gray-600 hover:bg-gray-50">
            調整實際時數
          </button>
        )}
        {canLeave && (
          <button onClick={() => setOpen(open === "leave" ? null : "leave")} className="rounded-lg border border-gray-200 px-2 py-1 text-gray-600 hover:bg-gray-50">
            個案請假
          </button>
        )}
        {appt.session_type === "online" && (
          <button onClick={() => setOpen(open === "video" ? null : "video")} className="rounded-lg border border-gray-200 px-2 py-1 text-gray-600 hover:bg-gray-50">
            視訊連結
          </button>
        )}
        {appt.receipt_no && (
          <button onClick={loadReceipts} className="rounded-lg border border-gray-200 px-2 py-1 text-gray-600 hover:bg-gray-50">
            收據管理
          </button>
        )}
      </div>

      {error && <div className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{error}</div>}

      {open === "duration" && (
        <div className="mt-2 space-y-2 rounded-lg bg-gray-50 p-3 text-xs">
          <p className="text-gray-400">改變時數會依單價重算金額，並同步回寫預約時間。若新時段撞到下一位，系統會擋下——請聯絡行政協助處理。</p>
          <label className="block">
            <span className="mb-1 block text-gray-500">實際時數（分鐘）</span>
            <input type="number" step={15} value={durMinutes} onChange={(e) => setDurMinutes(Number(e.target.value))} className="w-full rounded-lg border border-gray-200 px-2 py-1.5" />
          </label>
          <label className="block">
            <span className="mb-1 block text-gray-500">原因（選填）</span>
            <input value={durNote} onChange={(e) => setDurNote(e.target.value)} className="w-full rounded-lg border border-gray-200 px-2 py-1.5" />
          </label>
          <button
            disabled={busy}
            onClick={() => run(() => clientFetch(`/appointments/${appt.id}/adjust-duration`, token, {
              method: "PUT",
              body: JSON.stringify({
                actual_start: appt.start_time,
                actual_end: new Date(new Date(appt.start_time!).getTime() + durMinutes * 60000).toISOString(),
                note: durNote || null,
              }),
            }))}
            className="w-full rounded-lg bg-primary-600 py-2 font-medium text-white hover:bg-primary-700 disabled:opacity-50"
          >
            套用並重算金額
          </button>
        </div>
      )}

      {open === "leave" && (
        <div className="mt-2 space-y-2 rounded-lg bg-gray-50 p-3 text-xs">
          <p className="text-gray-400">請假與未到不同：時段會釋出、不產生應收，機構未到補助也不會收。</p>
          <input value={leaveReason} onChange={(e) => setLeaveReason(e.target.value)} placeholder="請假原因（選填）" className="w-full rounded-lg border border-gray-200 px-2 py-1.5" />
          <button
            disabled={busy}
            onClick={() => run(() => clientFetch(`/appointments/${appt.id}/leave`, token, {
              method: "PUT", body: JSON.stringify({ reason: leaveReason || null }),
            }))}
            className="w-full rounded-lg bg-gray-700 py-2 font-medium text-white hover:bg-gray-800 disabled:opacity-50"
          >
            確認請假
          </button>
        </div>
      )}

      {open === "video" && (
        <div className="mt-2 space-y-2 rounded-lg bg-gray-50 p-3 text-xs">
          <p className="text-gray-400">連結由心理師自行貼上，系統不自動產生。貼上後請通知行政轉發給個案。</p>
          <input value={videoLink} onChange={(e) => setVideoLink(e.target.value)} placeholder="https://…" className="w-full rounded-lg border border-gray-200 px-2 py-1.5" />
          <div className="flex gap-2">
            <button
              disabled={busy || !videoLink}
              onClick={() => run(() => clientFetch(`/appointments/${appt.id}/video-link`, token, {
                method: "PUT", body: JSON.stringify({ video_link: videoLink }),
              }))}
              className="flex-1 rounded-lg bg-primary-600 py-2 font-medium text-white hover:bg-primary-700 disabled:opacity-50"
            >
              儲存連結
            </button>
            <button
              disabled={busy}
              onClick={() => run(() => clientFetch(`/appointments/${appt.id}/video-forwarded`, token, { method: "PUT" }))}
              className="flex-1 rounded-lg border border-gray-300 py-2 text-gray-600 hover:bg-gray-50 disabled:opacity-50"
            >
              標記已轉發
            </button>
          </div>
        </div>
      )}

      {open === "receipts" && (
        <div className="mt-2 space-y-2 rounded-lg bg-gray-50 p-3 text-xs">
          {receipts.map((r) => (
            <div key={r.id} className="flex items-center justify-between rounded border border-gray-200 bg-white px-2 py-1.5">
              <div>
                <span className={`font-mono ${r.status === "voided" ? "text-gray-400 line-through" : ""}`}>{r.receipt_no}</span>
                <span className="ml-2 text-gray-500">${r.amount.toLocaleString()}</span>
                {r.status === "voided" && <span className="ml-1 text-[10px] text-rose-500">已作廢{r.void_reason ? `（${r.void_reason}）` : ""}</span>}
              </div>
              {r.status === "issued" && (
                <div className="flex gap-1">
                  <button
                    disabled={busy}
                    onClick={async () => {
                      setBusy(true);
                      setError(null);
                      try {
                        await clientFetch(`/appointments/receipts/${r.id}/reprint`, token, { method: "POST" });
                        setReceipts(await clientFetch(`/appointments/${appt.id}/receipts`, token));
                      } catch (e: any) {
                        setError(e.message ?? "重印失敗");
                      } finally {
                        setBusy(false);
                      }
                    }}
                    className="rounded border border-gray-200 px-1.5 py-0.5 hover:bg-gray-50"
                  >
                    重印
                  </button>
                  <button
                    disabled={busy || !voidReason.trim()}
                    title={voidReason.trim() ? "" : "請先填寫作廢原因"}
                    onClick={async () => {
                      setBusy(true);
                      setError(null);
                      try {
                        setReceipts(await clientFetch(`/appointments/receipts/${r.id}/void`, token, {
                          method: "PUT", body: JSON.stringify({ reason: voidReason, reissue: true }),
                        }));
                        setVoidReason("");
                        onChanged();
                      } catch (e: any) {
                        setError(e.message ?? "作廢失敗");
                      } finally {
                        setBusy(false);
                      }
                    }}
                    className="rounded border border-rose-200 px-1.5 py-0.5 text-rose-600 hover:bg-rose-50 disabled:opacity-40"
                  >
                    作廢重開
                  </button>
                </div>
              )}
            </div>
          ))}
          <input value={voidReason} onChange={(e) => setVoidReason(e.target.value)} placeholder="作廢原因（作廢前必填）" className="w-full rounded-lg border border-gray-200 px-2 py-1.5" />
        </div>
      )}
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

/* ═══════════════════════════════════════════════
   場地租借分頁（06 P6、v7 預約作業 b4）
   佔用實體診間，所以衝突檢查跟一般預約是同一套
   ═══════════════════════════════════════════════ */

function RentalsTab({ token, date }: { token: string; date: Date }) {
  const [rows, setRows] = useState<VenueRental[]>([]);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    const start = new Date(date);
    const end = new Date(date);
    end.setDate(end.getDate() + 30);
    clientFetch(
      `/venues?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`,
      token,
    )
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [token, date, tick]);

  async function setAttendance(id: number, attendance: "arrived" | "no_show") {
    await clientFetch(`/venues/${id}/attendance`, token, {
      method: "PUT",
      body: JSON.stringify({ attendance }),
    });
    setTick((t) => t + 1);
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-xs text-gray-400">自 {toLocalDateString(date)} 起 30 天內的場地租借</p>
        <button onClick={() => setShowCreate(true)} className="rounded-lg bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-700">
          ＋ 新增場地租借
        </button>
      </div>

      {loading && <p className="text-sm text-gray-400">載入中…</p>}
      {!loading && rows.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-200 py-12 text-center text-sm text-gray-400">此期間沒有場地租借</div>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full text-xs">
            <thead className="bg-gray-50 text-left text-gray-500">
              <tr>
                <th className="px-3 py-2">單號</th>
                <th className="px-3 py-2">時間</th>
                <th className="px-3 py-2">診間</th>
                <th className="px-3 py-2">借用人／單位</th>
                <th className="px-3 py-2">用途</th>
                <th className="px-3 py-2">場地費</th>
                <th className="px-3 py-2">付款方</th>
                <th className="px-3 py-2">出席</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((v) => (
                <tr key={v.id} className={`border-t border-gray-100 ${v.status === "cancelled" ? "text-gray-300 line-through" : ""}`}>
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-gray-400">{v.rental_no}</td>
                  <td className="whitespace-nowrap px-3 py-2">
                    {v.start_time?.slice(5, 10)} {v.start_time?.slice(11, 16)}–{v.end_time?.slice(11, 16)}
                  </td>
                  <td className="px-3 py-2">{v.room_name ?? "—"}</td>
                  <td className="px-3 py-2">
                    {v.renter_name}
                    {v.supervision_fee_mode && (
                      <span className="ml-1 rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] text-indigo-600">
                        督導模式 {v.supervision_fee_mode}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-gray-500">{v.purpose ?? "—"}</td>
                  <td className="whitespace-nowrap px-3 py-2">${v.amount.toLocaleString()}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-gray-500">{PAYER_LABEL[v.payer] ?? v.payer}</td>
                  <td className="whitespace-nowrap px-3 py-2">
                    {v.attendance === "pending" ? (
                      <span className="flex gap-1">
                        <button onClick={() => setAttendance(v.id, "arrived")} className="rounded border border-gray-200 px-1.5 py-0.5 hover:bg-gray-50">已到</button>
                        <button onClick={() => setAttendance(v.id, "no_show")} className="rounded border border-gray-200 px-1.5 py-0.5 hover:bg-gray-50">未到</button>
                      </span>
                    ) : v.attendance === "arrived" ? (
                      <span className="text-emerald-600">已到</span>
                    ) : (
                      <span className="text-rose-500">未到 · 改自付</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <CreateRentalModal token={token} date={date} onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); setTick((t) => t + 1); }} />
      )}
    </div>
  );
}

function CreateRentalModal({
  token, date, onClose, onCreated,
}: { token: string; date: Date; onClose: () => void; onCreated: () => void }) {
  const [rooms, setRooms] = useState<Room[]>([]);
  const [institutions, setInstitutions] = useState<{ id: number; name: string }[]>([]);
  const [therapists, setTherapists] = useState<{ id: number; name: string }[]>([]);
  const [roomId, setRoomId] = useState("");
  const [day, setDay] = useState(toLocalDateString(date));
  const [startH, setStartH] = useState("14:00");
  const [endH, setEndH] = useState("16:00");
  const [renterKind, setRenterKind] = useState("institution");
  const [institutionId, setInstitutionId] = useState("");
  const [therapistId, setTherapistId] = useState("");
  const [renterName, setRenterName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [mode, setMode] = useState("");
  const [amount, setAmount] = useState("1200");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    clientFetch("/rooms", token).then(setRooms).catch(() => {});
    clientFetch("/institutions", token).then(setInstitutions).catch(() => {});
    clientFetch("/auth/therapists", token).then(setTherapists).catch(() => {});
  }, [token]);

  // 督導模式 A：櫃台代收督導費並開收據，場地費自動 $0（不跟心理師收兩次）
  const feeDisabled = mode === "A";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await clientFetch("/venues", token, {
        method: "POST",
        body: JSON.stringify({
          room_id: Number(roomId),
          start_time: new Date(`${day}T${startH}:00`).toISOString(),
          end_time: new Date(`${day}T${endH}:00`).toISOString(),
          renter_kind: renterKind,
          renter_name: renterKind === "private"
            ? (therapists.find((t) => String(t.id) === therapistId)?.name ?? renterName)
            : (institutions.find((i) => String(i.id) === institutionId)?.name ?? renterName),
          institution_id: renterKind === "institution" ? Number(institutionId) : null,
          renter_therapist_id: renterKind === "private" ? Number(therapistId) : null,
          supervision_fee_mode: mode || null,
          purpose: purpose || null,
          amount: feeDisabled ? 0 : Number(amount),
        }),
      });
      onCreated();
    } catch (e: any) {
      setError(e.message ?? "建立失敗");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div className="max-h-[88vh] w-[460px] overflow-y-auto rounded-xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 font-semibold">新增場地租借</h3>
        {error && <div className="mb-3 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{error}</div>}
        <form onSubmit={submit} className="space-y-3 text-sm">
          <label className="block">
            <span className="mb-1 block text-xs text-gray-500">診間 <span className="text-rose-500">*</span></span>
            <select required value={roomId} onChange={(e) => setRoomId(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2">
              <option value="">請選擇</option>
              {rooms.map((r) => <option key={r.id} value={r.id}>{r.name}（{r.floor}F）</option>)}
            </select>
          </label>
          <div className="grid grid-cols-3 gap-2">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">日期</span>
              <input type="date" value={day} onChange={(e) => setDay(e.target.value)} className="w-full rounded-lg border border-gray-300 px-2 py-2" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">起</span>
              <input type="time" value={startH} onChange={(e) => setStartH(e.target.value)} className="w-full rounded-lg border border-gray-300 px-2 py-2" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">迄</span>
              <input type="time" value={endH} onChange={(e) => setEndH(e.target.value)} className="w-full rounded-lg border border-gray-300 px-2 py-2" />
            </label>
          </div>
          <label className="block">
            <span className="mb-1 block text-xs text-gray-500">借用類型</span>
            <select value={renterKind} onChange={(e) => setRenterKind(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2">
              <option value="institution">機構借用（場地費進機構應收）</option>
              <option value="private">心理師個人借用（從當月酬勞扣回）</option>
            </select>
          </label>
          {renterKind === "institution" ? (
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">借用單位 <span className="text-rose-500">*</span></span>
              <select required value={institutionId} onChange={(e) => setInstitutionId(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2">
                <option value="">請選擇</option>
                {institutions.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
              </select>
            </label>
          ) : (
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">借用心理師 <span className="text-rose-500">*</span></span>
              <select required value={therapistId} onChange={(e) => setTherapistId(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2">
                <option value="">請選擇</option>
                {therapists.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </label>
          )}
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">用途</span>
              <input value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="督導 / 團體 / 會議" className="w-full rounded-lg border border-gray-300 px-3 py-2" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-gray-500">督導收費模式</span>
              <select value={mode} onChange={(e) => setMode(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2">
                <option value="">非督導場次</option>
                <option value="A">A · 櫃台代收、開收據</option>
                <option value="B">B · 心理師自收、場地費回扣</option>
              </select>
            </label>
          </div>
          <label className="block">
            <span className="mb-1 block text-xs text-gray-500">場地費</span>
            <input
              type="number" value={feeDisabled ? "0" : amount} disabled={feeDisabled}
              onChange={(e) => setAmount(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 disabled:bg-gray-100 disabled:text-gray-400"
            />
            {feeDisabled && (
              <span className="mt-1 block text-[11px] text-gray-400">
                模式 A 由櫃台代收督導費並開立收據，場地費自動為 $0（不重複收）
              </span>
            )}
          </label>
          <div className="flex gap-2 pt-1">
            <button type="submit" disabled={saving} className="flex-1 rounded-lg bg-primary-600 py-2 font-medium text-white hover:bg-primary-700 disabled:opacity-50">
              {saving ? "建立中…" : "建立"}
            </button>
            <button type="button" onClick={onClose} className="rounded-lg border border-gray-200 px-4 py-2 text-gray-500 hover:bg-gray-50">取消</button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════
   5F 雲燈教室分頁（06 P6、v7 預約作業 n4）
   場佈時段與活動時段分開記；不掛在 rooms 底下
   ═══════════════════════════════════════════════ */

function HallTab({ token, date }: { token: string; date: Date }) {
  const [rows, setRows] = useState<HallBooking[]>([]);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    const start = new Date(date);
    const end = new Date(date);
    end.setDate(end.getDate() + 60);
    clientFetch(
      `/venues/hall?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`,
      token,
    )
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [token, date, tick]);

  async function setStatus(id: number, status: string) {
    await clientFetch(`/venues/hall/${id}/status`, token, { method: "PUT", body: JSON.stringify({ status }) });
    setTick((t) => t + 1);
  }

  return (
    <div>
      <p className="mb-3 text-xs text-gray-400">自 {toLocalDateString(date)} 起 60 天內的雲燈教室借用</p>
      {loading && <p className="text-sm text-gray-400">載入中…</p>}
      {!loading && rows.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-200 py-12 text-center text-sm text-gray-400">此期間沒有借用紀錄</div>
      )}
      <div className="space-y-2">
        {rows.map((h) => (
          <div key={h.id} className={`rounded-lg border p-3 ${h.status === "cancelled" ? "border-gray-200 bg-gray-50 text-gray-400" : "border-gray-200 bg-white"}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-medium">{h.title}</span>
                <span className={`rounded px-1.5 py-0.5 text-[10px] ${
                  h.status === "executed" ? "bg-emerald-100 text-emerald-700"
                    : h.status === "cancelled" ? "bg-gray-200 text-gray-500"
                    : "bg-amber-100 text-amber-700"
                }`}>
                  {h.status === "executed" ? "已執行" : h.status === "cancelled" ? "已取消" : "已排定"}
                </span>
              </div>
              {h.status === "scheduled" && (
                <div className="flex gap-1 text-xs">
                  <button onClick={() => setStatus(h.id, "executed")} className="rounded border border-gray-200 px-2 py-0.5 hover:bg-gray-50">標記已執行</button>
                  <button onClick={() => setStatus(h.id, "cancelled")} className="rounded border border-gray-200 px-2 py-0.5 text-gray-500 hover:bg-gray-50">取消</button>
                </div>
              )}
            </div>
            <div className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs text-gray-500 md:grid-cols-4">
              <div>活動：{h.event_start?.slice(5, 10)} {h.event_start?.slice(11, 16)}–{h.event_end?.slice(11, 16)}</div>
              <div>場佈：{h.setup_start ? `${h.setup_start.slice(11, 16)}–${h.setup_end?.slice(11, 16)}` : "—"}</div>
              <div>
                講師：{h.lecturer_name ?? "—"}
                <span className="ml-1 text-gray-400">（{h.lecturer_kind === "internal" ? "所內" : "外聘"}）</span>
              </div>
              <div>借用：{h.borrower ?? "—"}{h.attendee_count ? ` · ${h.attendee_count} 人` : ""}</div>
              <div className="col-span-2">
                講師費：{h.lecturer_fee != null ? `$${h.lecturer_fee.toLocaleString()}` : "—"}
                <span className={`ml-1 rounded px-1.5 py-0.5 text-[10px] ${h.fee_to_clinic_account ? "bg-sky-50 text-sky-600" : "bg-gray-100 text-gray-500"}`}>
                  {h.fee_to_clinic_account ? "入慈恩帳戶" : "主辦方直付講師"}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
