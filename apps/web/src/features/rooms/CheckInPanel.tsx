"use client";

import { useCallback, useEffect, useState } from "react";
import { clientFetch } from "@/lib/client-api";
import { Button } from "@/components/ui";
import type { Appointment, VenueRental, HallBooking, FeeItem, Room } from "./types";
import { NO_SHOW_REASONS, PAYER_LABEL, sessionTypeLabel, toLocalDateString } from "./types";

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
            <p className="text-xs text-ink-3 mt-0.5">
              {appt.is_couple ? `👫 ${appt.couple_name}` : appt.case_name} · {appt.therapist_name} · {sessionTypeLabel[appt.session_type] ?? appt.session_type}
            </p>
          </div>
          <button onClick={onClose} className="text-ink-3 hover:text-ink-2">✕</button>
        </div>

        <dl className="mb-4 space-y-1 rounded-lg bg-surface-2 p-3 text-xs">
          <div className="flex justify-between"><dt className="text-ink-3">時間</dt><dd>{appt.start_time?.slice(11, 16)} ~ {appt.end_time?.slice(11, 16)}</dd></div>
          <div className="flex justify-between"><dt className="text-ink-3">診間</dt><dd>{appt.room_name ?? "—"}</dd></div>
          <div className="flex justify-between"><dt className="text-ink-3">方案</dt><dd>{appt.plan_name ?? (appt.funding_source === "institution" ? "機構（舊路徑）" : "自費")}</dd></div>
          {appt.institution_payable != null && (
            <div className="flex justify-between"><dt className="text-ink-3">機構請款</dt><dd className="text-ink-3">${appt.institution_payable.toLocaleString()}（走機構核銷，與此無關）</dd></div>
          )}
          <div className="flex justify-between font-medium"><dt className="text-ink-2">個案應收</dt><dd>${payable.toLocaleString()}</dd></div>
        </dl>

        {error && <div className="mb-3 rounded-lg bg-st-danger-bg px-3 py-2 text-xs text-st-danger">{error}</div>}

        {/* 步驟指示 */}
        <div className="mb-4 flex items-center gap-1 text-[10px] text-ink-3">
          <StepDot done={appt.check_in_status !== "pending"} active={appt.check_in_status === "pending"} label="報到" />
          <span>→</span>
          <StepDot done={!!appt.copay_collected_at || payable <= 0} active={appt.check_in_status === "arrived" && !appt.copay_collected_at} label="收款" />
          <span>→</span>
          <StepDot done={!!appt.receipt_no} active={appt.check_in_status === "arrived" && !!appt.copay_collected_at && !appt.receipt_no} label="開據" />
        </div>

        {/* ── 步驟 1：報到。初診走另一張表單（11 §5.9）── */}
        {appt.check_in_status === "pending" && appt.first_visit && (
          <FirstVisitStep
            firstVisit={appt.first_visit}
            token={token}
            onChanged={onChanged}
          />
        )}
        {appt.check_in_status === "pending" && !appt.first_visit && !showNoShowForm && (
          <div className="flex gap-2">
            <button disabled={busy} onClick={() => doCheckIn("arrived")} className="flex-1 rounded-lg bg-accent py-2.5 text-sm font-medium text-white hover:bg-st-active disabled:opacity-50">
              ✓ 已到
            </button>
            <button disabled={busy} onClick={() => setShowNoShowForm(true)} className="flex-1 rounded-lg border border-line-2 py-2.5 text-sm text-ink-2 hover:bg-surface-2">
              未到
            </button>
          </div>
        )}
        {appt.check_in_status === "pending" && !appt.first_visit && showNoShowForm && (
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs text-ink-3">未到原因</label>
              <select value={noShowReason} onChange={(e) => setNoShowReason(e.target.value)} className="w-full rounded-lg border border-line px-2 py-1.5 text-sm">
                {NO_SHOW_REASONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-ink-3">備註（選填）</label>
              <input value={noShowNote} onChange={(e) => setNoShowNote(e.target.value)} className="w-full rounded-lg border border-line px-2 py-1.5 text-sm" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-ink-3">催繳方式（選填）</label>
              <input value={noShowFollowup} onChange={(e) => setNoShowFollowup(e.target.value)} className="w-full rounded-lg border border-line px-2 py-1.5 text-sm" />
            </div>
            <div className="flex gap-2">
              <button disabled={busy} onClick={() => doCheckIn("no_show")} className="flex-1 rounded-lg bg-ink py-2 text-sm font-medium text-surface hover:bg-ink-2 disabled:opacity-50">
                確認未到
              </button>
              <button onClick={() => setShowNoShowForm(false)} className="rounded-lg border border-line px-3 py-2 text-sm text-ink-3 hover:bg-surface-2">
                返回
              </button>
            </div>
          </div>
        )}

        {/* 未到後的摘要（唯讀） */}
        {appt.check_in_status === "no_show" && (
          <div className="rounded-lg bg-surface-2 p-3 text-xs text-ink-3">
            <p className="mb-1 font-medium text-ink-2">未到 · {NO_SHOW_REASONS.find((r) => r.value === appt.no_show_reason)?.label ?? appt.no_show_reason}</p>
            {appt.no_show_note && <p>備註：{appt.no_show_note}</p>}
            {appt.no_show_followup && <p>催繳：{appt.no_show_followup}</p>}
          </div>
        )}

        {/* ── 步驟 2：收款 ── */}
        {appt.check_in_status === "arrived" && !appt.copay_collected_at && payable > 0 && (
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs text-ink-3">收款方式</label>
              <div className="flex gap-2">
                {(["cash", "transfer"] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => setPayMethod(m)}
                    className={`flex-1 rounded-lg border py-2 text-sm ${payMethod === m ? "border-accent bg-accent-soft text-accent" : "border-line text-ink-3 hover:bg-surface-2"}`}
                  >
                    {m === "cash" ? "現金" : "匯款"}
                  </button>
                ))}
              </div>
            </div>
            {payMethod === "transfer" && (
              <div>
                <label className="mb-1 block text-xs text-ink-3">匯款資訊（如帳戶末五碼）<span className="text-st-danger">*</span></label>
                <input value={payNote} onChange={(e) => setPayNote(e.target.value)} className="w-full rounded-lg border border-line px-2 py-1.5 text-sm" />
              </div>
            )}
            <button disabled={busy} onClick={doPayment} className="w-full rounded-lg bg-accent py-2.5 text-sm font-medium text-white hover:bg-st-active disabled:opacity-50">
              確認收款 ${payable.toLocaleString()}
            </button>
          </div>
        )}

        {/* 機構全額免收 */}
        {appt.check_in_status === "arrived" && !appt.copay_collected_at && payable <= 0 && (
          <div className="rounded-lg bg-accent-soft text-accent p-3 text-xs">此筆機構全額補助，個案免收款，無需開立收據。</div>
        )}

        {/* ── 步驟 3：開立收據 ── */}
        {appt.check_in_status === "arrived" && appt.copay_collected_at && !appt.receipt_no && (
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs text-ink-3">收款項目</label>
              <select
                value={feeItemId}
                onChange={(e) => setFeeItemId(e.target.value ? Number(e.target.value) : "")}
                className="w-full rounded-lg border border-line px-2 py-1.5 text-sm"
              >
                <option value="">— 選擇項目 —</option>
                {feeItems.map((fi) => <option key={fi.id} value={fi.id}>{fi.name}</option>)}
                <option value="">其他（自行登打）</option>
              </select>
            </div>
            {!feeItemId && (
              <div>
                <label className="mb-1 block text-xs text-ink-3">自訂項目名稱</label>
                <input value={customFeeName} onChange={(e) => setCustomFeeName(e.target.value)} className="w-full rounded-lg border border-line px-2 py-1.5 text-sm" placeholder="未在清單中時填寫" />
              </div>
            )}
            <div>
              <label className="mb-1 block text-xs text-ink-3">備註（選填）</label>
              <input value={receiptNote} onChange={(e) => setReceiptNote(e.target.value)} className="w-full rounded-lg border border-line px-2 py-1.5 text-sm" />
            </div>
            <button disabled={busy} onClick={doReceipt} className="w-full rounded-lg bg-accent py-2.5 text-sm font-medium text-white hover:bg-st-active disabled:opacity-50">
              開立收據
            </button>
          </div>
        )}

        {/* 已完成 */}
        {appt.check_in_status === "arrived" && (appt.receipt_no || (appt.copay_collected_at && payable <= 0)) && (
          <div className="rounded-lg bg-st-done-bg p-3 text-xs text-st-done">
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
    <div className="mt-4 rounded-lg border border-line p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-ink-2">
        行政流程提醒
        {open > 0 ? (
          <span className="rounded bg-st-warn-bg px-1.5 py-0.5 text-[10px] text-st-warn">還有 {open} 項未完成</span>
        ) : (
          <span className="rounded bg-st-done-bg px-1.5 py-0.5 text-[10px] text-st-done">已全部完成</span>
        )}
      </div>
      <ul className="space-y-1.5">
        {tasks.map((t) => (
          <li key={t.id} className="flex items-start gap-2 text-xs">
            <input type="checkbox" checked={t.is_done} disabled={busy} onChange={() => toggle(t)} className="mt-0.5" />
            <span className={t.is_done ? "text-ink-3 line-through" : "text-ink-2"}>
              {t.title}
              <span className="ml-1 text-[10px] text-ink-3">（{t.side === "admin" ? "行政" : "心理師"}）</span>
              {t.is_done && t.done_at && (
                <span className="ml-1 text-[10px] text-st-done">
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
    <div className="mt-3 border-t border-line pt-3">
      <div className="flex flex-wrap gap-1.5 text-xs">
        {canAdjust && (
          <button onClick={() => setOpen(open === "duration" ? null : "duration")} className="rounded-lg border border-line px-2 py-1 text-ink-2 hover:bg-surface-2">
            調整實際時數
          </button>
        )}
        {canLeave && (
          <button onClick={() => setOpen(open === "leave" ? null : "leave")} className="rounded-lg border border-line px-2 py-1 text-ink-2 hover:bg-surface-2">
            個案請假
          </button>
        )}
        {appt.session_type === "online" && (
          <button onClick={() => setOpen(open === "video" ? null : "video")} className="rounded-lg border border-line px-2 py-1 text-ink-2 hover:bg-surface-2">
            視訊連結
          </button>
        )}
        {appt.receipt_no && (
          <button onClick={loadReceipts} className="rounded-lg border border-line px-2 py-1 text-ink-2 hover:bg-surface-2">
            收據管理
          </button>
        )}
      </div>

      {error && <div className="mt-2 rounded-lg bg-st-danger-bg px-3 py-2 text-xs text-st-danger">{error}</div>}

      {open === "duration" && (
        <div className="mt-2 space-y-2 rounded-lg bg-surface-2 p-3 text-xs">
          <p className="text-ink-3">改變時數會依單價重算金額，並同步回寫預約時間。若新時段撞到下一位，系統會擋下——請聯絡行政協助處理。</p>
          <label className="block">
            <span className="mb-1 block text-ink-3">實際時數（分鐘）</span>
            <input type="number" step={15} value={durMinutes} onChange={(e) => setDurMinutes(Number(e.target.value))} className="w-full rounded-lg border border-line px-2 py-1.5" />
          </label>
          <label className="block">
            <span className="mb-1 block text-ink-3">原因（選填）</span>
            <input value={durNote} onChange={(e) => setDurNote(e.target.value)} className="w-full rounded-lg border border-line px-2 py-1.5" />
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
            className="w-full rounded-lg bg-accent py-2 font-medium text-white hover:bg-st-active disabled:opacity-50"
          >
            套用並重算金額
          </button>
        </div>
      )}

      {open === "leave" && (
        <div className="mt-2 space-y-2 rounded-lg bg-surface-2 p-3 text-xs">
          <p className="text-ink-3">請假與未到不同：時段會釋出、不產生應收，機構未到補助也不會收。</p>
          <input value={leaveReason} onChange={(e) => setLeaveReason(e.target.value)} placeholder="請假原因（選填）" className="w-full rounded-lg border border-line px-2 py-1.5" />
          <button
            disabled={busy}
            onClick={() => run(() => clientFetch(`/appointments/${appt.id}/leave`, token, {
              method: "PUT", body: JSON.stringify({ reason: leaveReason || null }),
            }))}
            className="w-full rounded-lg bg-ink py-2 font-medium text-surface hover:bg-ink-2 disabled:opacity-50"
          >
            確認請假
          </button>
        </div>
      )}

      {open === "video" && (
        <div className="mt-2 space-y-2 rounded-lg bg-surface-2 p-3 text-xs">
          <p className="text-ink-3">連結由心理師自行貼上，系統不自動產生。貼上後請通知行政轉發給個案。</p>
          <input value={videoLink} onChange={(e) => setVideoLink(e.target.value)} placeholder="https://…" className="w-full rounded-lg border border-line px-2 py-1.5" />
          <div className="flex gap-2">
            <button
              disabled={busy || !videoLink}
              onClick={() => run(() => clientFetch(`/appointments/${appt.id}/video-link`, token, {
                method: "PUT", body: JSON.stringify({ video_link: videoLink }),
              }))}
              className="flex-1 rounded-lg bg-accent py-2 font-medium text-white hover:bg-st-active disabled:opacity-50"
            >
              儲存連結
            </button>
            <button
              disabled={busy}
              onClick={() => run(() => clientFetch(`/appointments/${appt.id}/video-forwarded`, token, { method: "PUT" }))}
              className="flex-1 rounded-lg border border-line-2 py-2 text-ink-2 hover:bg-surface-2 disabled:opacity-50"
            >
              標記已轉發
            </button>
          </div>
        </div>
      )}

      {open === "receipts" && (
        <div className="mt-2 space-y-2 rounded-lg bg-surface-2 p-3 text-xs">
          {receipts.map((r) => (
            <div key={r.id} className="flex items-center justify-between rounded border border-line bg-white px-2 py-1.5">
              <div>
                <span className={`font-mono ${r.status === "voided" ? "text-ink-3 line-through" : ""}`}>{r.receipt_no}</span>
                <span className="ml-2 text-ink-3">${r.amount.toLocaleString()}</span>
                {r.status === "voided" && <span className="ml-1 text-[10px] text-st-danger">已作廢{r.void_reason ? `（${r.void_reason}）` : ""}</span>}
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
                    className="rounded border border-line px-1.5 py-0.5 hover:bg-surface-2"
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
                    className="rounded border border-st-danger/30 px-1.5 py-0.5 text-st-danger hover:bg-st-danger-bg disabled:opacity-40"
                  >
                    作廢重開
                  </button>
                </div>
              )}
            </div>
          ))}
          <input value={voidReason} onChange={(e) => setVoidReason(e.target.value)} placeholder="作廢原因（作廢前必填）" className="w-full rounded-lg border border-line px-2 py-1.5" />
        </div>
      )}
    </div>
  );
}


/** 報到三步驟的進度指示。三步各自的狀態：已完成 / 進行中 / 還沒輪到。 */
function StepDot({ done, active, label }: { done: boolean; active: boolean; label: string }) {
  return (
    <span className={`flex items-center gap-1 rounded px-1.5 py-0.5 ${done ? "bg-st-done-bg text-st-done" : active ? "bg-st-warn-bg text-st-warn" : "bg-surface-3 text-ink-3"}`}>
      {done ? "✓" : "·"} {label}
    </span>
  );
}

/**
 * 初診報到 — V2升級計畫 11 §5.9。
 *
 * 這一步本來長在媒合管理裡：行政要記得回到 /match、找到那一列、點開報到彈窗。
 * 但人在櫃檯、日曆開著，自然會直接在格子上按「已到」——而那條路會把資料走壞：
 * 預約變已到、場次照常建立，媒合案卻永遠卡在 booked，個案永遠停在 initial，
 * 也就永遠拿不到病歷號。所以把表單搬到這裡，讓自然的那條路變成對的那條路。
 *
 * 後端仍是既有的 `PUT /referrals/{id}/arrived` 與 `/no-show`，**一行沒改**——
 * 媒合狀態機只有那一份實作。這裡只是換了入口。
 *
 * 未到這半邊不能省：初診未到帶著「轉預約／派案／結案」的分流，是普通 no_show
 * 不會做的事。少了它，媒合案一樣會斷在半路。
 */
const FIELD_LABEL: Record<string, string> = {
  national_id: "身分證字號",
  birth_date: "出生日期",
  phone: "電話",
};

function FirstVisitStep({
  firstVisit,
  token,
  onChanged,
}: {
  firstVisit: NonNullable<Appointment["first_visit"]>;
  token: string;
  onChanged: () => void;
}) {
  const [mode, setMode] = useState<null | "arrived" | "no_show">(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [nationalId, setNationalId] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [phone, setPhone] = useState("");

  const [reason, setReason] = useState("case_leave");
  const [nextAction, setNextAction] = useState<"rebook" | "reassign" | "close">("rebook");

  // 後端算好的「還缺哪幾個」。表單只問這幾個，也只擋這幾個——問的東西與
  // activate_case 要的東西是同一份清單，不會再出現「填完才被打回」。
  const need = firstVisit.missing_fields ?? [];
  const value = { national_id: nationalId, birth_date: birthDate, phone };
  const incomplete = need.filter((f) => !value[f].trim());

  async function submit(path: string, body: unknown) {
    setBusy(true);
    setError(null);
    try {
      await clientFetch(`/referrals/${firstVisit.referral_id}/${path}`, token, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      onChanged();
    } catch (e: any) {
      setError(e.message ?? "操作失敗");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="rounded-lg bg-accent-soft px-3 py-2 text-xs text-accent">
        <b>初診</b> · 派案碼 <span className="ident">{firstVisit.referral_code}</span>
        <div className="mt-0.5">
          {need.length > 0
            ? `報到時一併登記${need.map((f) => FIELD_LABEL[f]).join("、")}，系統會產生病歷號並轉為正式個案。`
            : "個資已登記齊全，按「已到」即完成報到並轉為正式個案。"}
        </div>
      </div>

      {error && <div className="rounded-lg bg-st-danger-bg px-3 py-2 text-xs text-st-danger">{error}</div>}

      {mode === null && (
        <div className="flex gap-2">
          <button
            onClick={() => setMode("arrived")}
            className="flex-1 rounded-lg bg-accent py-2.5 text-sm font-medium text-white hover:bg-st-active"
          >
            ✓ 已到
          </button>
          <button
            onClick={() => setMode("no_show")}
            className="flex-1 rounded-lg border border-line-2 py-2.5 text-sm text-ink-2 hover:bg-surface-2"
          >
            未到
          </button>
        </div>
      )}

      {mode === "arrived" && (
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-ink-3">
              身分證字號{need.includes("national_id") && <span className="text-st-danger"> *</span>}
            </label>
            <input
              value={nationalId}
              onChange={(e) => setNationalId(e.target.value.toUpperCase())}
              placeholder="A123456789"
              className="w-full rounded-lg border border-line-2 px-2 py-1.5 font-mono text-sm"
            />
            <p className="mt-1 text-[10px] text-ink-3">病歷號會取用身分證末兩碼，之後不可更改</p>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs text-ink-3">
                出生日期{need.includes("birth_date") && <span className="text-st-danger"> *</span>}
              </label>
              <input type="date" value={birthDate} onChange={(e) => setBirthDate(e.target.value)}
                className="w-full rounded-lg border border-line-2 px-2 py-1.5 text-sm" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-ink-3">
                電話{need.includes("phone") && <span className="text-st-danger"> *</span>}
              </label>
              <input value={phone} onChange={(e) => setPhone(e.target.value)}
                className="w-full rounded-lg border border-line-2 px-2 py-1.5 text-sm" />
            </div>
          </div>
          <div className="flex gap-2">
            <button
              disabled={busy || incomplete.length > 0}
              onClick={() => submit("arrived", {
                national_id: nationalId.trim() || null,
                birth_date: birthDate || null,
                phone: phone || null,
              })}
              className="flex-1 rounded-lg bg-accent py-2 text-sm font-medium text-white hover:bg-st-active disabled:opacity-50"
            >
              {busy ? "處理中…" : "產生病歷號並完成報到"}
            </button>
            <button onClick={() => setMode(null)}
              className="rounded-lg border border-line px-3 py-2 text-sm text-ink-3 hover:bg-surface-2">返回</button>
          </div>
        </div>
      )}

      {mode === "no_show" && (
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-ink-3">未到原因</label>
            <select value={reason} onChange={(e) => setReason(e.target.value)}
              className="w-full rounded-lg border border-line px-2 py-1.5 text-sm">
              {NO_SHOW_REASONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </div>
          <div>
            {/* 這一欄是初診未到才有的：媒合案要知道接下來往哪走 */}
            <label className="mb-1 block text-xs text-ink-3">後續處理</label>
            <select value={nextAction} onChange={(e) => setNextAction(e.target.value as any)}
              className="w-full rounded-lg border border-line px-2 py-1.5 text-sm">
              <option value="rebook">轉預約（同一心理師重排時間）</option>
              <option value="reassign">派案（改派其他心理師）</option>
              <option value="close">轉媒合結案</option>
            </select>
          </div>
          <div className="flex gap-2">
            <button disabled={busy} onClick={() => submit("no-show", { reason, next_action: nextAction })}
              className="flex-1 rounded-lg bg-ink py-2 text-sm font-medium text-surface hover:bg-ink-2 disabled:opacity-50">
              {busy ? "處理中…" : "確認未到"}
            </button>
            <button onClick={() => setMode(null)}
              className="rounded-lg border border-line px-3 py-2 text-sm text-ink-3 hover:bg-surface-2">返回</button>
          </div>
        </div>
      )}
    </div>
  );
}
