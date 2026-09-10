"use client";

import { useCallback, useEffect, useState } from "react";
import { clientFetch } from "@/lib/client-api";
import { Button } from "@/components/ui";
import type { Appointment, VenueRental, HallBooking, FeeItem, Room } from "./types";
import { NO_SHOW_REASONS, PAYER_LABEL, sessionTypeLabel, toLocalDateString } from "./types";

/* @token-guard legacy — P3 從舊路由原樣搬入，尚未換語意 token（11 §2.2） */
/**
 * 報到三步驟：已到/未到 → 收款 → 開立收據 —— 從 rooms/page.tsx 搬出（11 §4.2）。
 *
 * 一次只出現一步（V2升級計畫 03 §操作體驗細節）。P2 把「已到」改成在日曆格
 * 就地執行，剩下三步仍走這個面板，因為它們都要填欄位（未到原因／付款方式／
 * 收費名目）——不把同一份 API 邏輯抄成兩份。
 */

export function CheckInPanel({
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


/** 報到三步驟的進度指示。三步各自的狀態：已完成 / 進行中 / 還沒輪到。 */
function StepDot({ done, active, label }: { done: boolean; active: boolean; label: string }) {
  return (
    <span className={`flex items-center gap-1 rounded px-1.5 py-0.5 ${done ? "bg-emerald-100 text-emerald-700" : active ? "bg-amber-100 text-amber-700" : "bg-gray-100 text-gray-400"}`}>
      {done ? "✓" : "·"} {label}
    </span>
  );
}
