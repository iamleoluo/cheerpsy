"use client";

import React, { useCallback, useEffect, useState } from "react";
import { clientFetch } from "@/lib/client-api";
import type {
  Appointment,
  CaseItem,
  InstitutionItem,
  RoomOption,
  SessionRecord,
  Therapist,
} from "@/features/shared/types";
import {
  apptStatusColors,
  apptStatusLabels,
  billingLabels,
  sessionTypeLabels,
  statusColors,
  statusLabels,
} from "@/features/shared/labels";
import { caseDisplayId, fmtDate, fmtTime, visitId } from "@/features/shared/format";

import {
  AppointmentEditModal,
  AppointmentForm,
  AppointmentPaymentModal,
  BatchForm,
} from "@/features/booking";

/* @token-guard legacy — P3 從舊路由原樣搬入，尚未換語意 token（11 §2.2） */
/** 個案詳情四分頁 — 從 cases/page.tsx 搬出（11 §4.2）。 */

export function CaseDetailPanel({
  token, userRole, caseItem, onClose, onCaseUpdated,
}: {
  token: string; userRole: string; caseItem: CaseItem; onClose: () => void; onCaseUpdated: () => void;
}) {
  const [subTab, setSubTab] = useState<"appointments" | "ledger">("appointments");
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [records, setRecords] = useState<SessionRecord[]>([]);
  const [loadingAppts, setLoadingAppts] = useState(true);
  const [loadingRecords, setLoadingRecords] = useState(false);
  const [showApptForm, setShowApptForm] = useState(false);
  const [showBatchForm, setShowBatchForm] = useState(false);

  const fetchAppts = useCallback(async () => {
    setLoadingAppts(true);
    try {
      setAppointments(await clientFetch(`/appointments?case_id=${caseItem.id}`, token));
    } catch { /* ignore */ } finally { setLoadingAppts(false); }
  }, [token, caseItem.id]);

  const fetchRecords = useCallback(async () => {
    setLoadingRecords(true);
    try {
      const all = await clientFetch("/ledger", token);
      setRecords(all.filter((r: any) => r.case_name === caseItem.name));
    } catch { /* ignore */ } finally { setLoadingRecords(false); }
  }, [token, caseItem.name]);

  useEffect(() => { fetchAppts(); }, [fetchAppts]);
  useEffect(() => { if (subTab === "ledger") fetchRecords(); }, [subTab, fetchRecords]);

  const handleCancelAppt = async (id: number) => {
    if (!confirm("確定要取消此預約？")) return;
    try {
      await clientFetch(`/appointments/${id}/cancel`, token, { method: "PUT" });
      fetchAppts();
    } catch (e: any) { alert(e.message); }
  };

  const [paymentModal, setPaymentModal] = useState<Appointment | null>(null);
  const [editApptPanel, setEditApptPanel] = useState<Appointment | null>(null);

  const c = caseItem;
  const displayId = caseDisplayId(c);

  return (
    <div className="mt-4 rounded-lg border border-primary-200 bg-white p-5 shadow-sm">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-bold">
            {c.name}
            <span className="ml-2 font-mono text-sm font-normal text-gray-500">{displayId}</span>
          </h3>
          <p className="mt-1 text-sm text-gray-500">
            心理師：{c.therapist_name} ・
            {billingLabels[c.billing_cycle ?? "once"]} ・
            <span className={`${statusColors[c.status]} rounded-full px-1.5 py-0.5 text-xs`}>
              {statusLabels[c.status]}
            </span>
          </p>
        </div>
        <button onClick={onClose} className="rounded px-2 py-1 text-sm text-gray-400 hover:bg-gray-100 hover:text-gray-600">✕ 收合</button>
      </div>

      {/* Sub-tabs */}
      <div className="mb-4 flex gap-1 border-b border-gray-200">
        <button
          onClick={() => setSubTab("appointments")}
          className={`px-3 py-2 text-sm font-medium ${subTab === "appointments" ? "border-b-2 border-primary-600 text-primary-700" : "text-gray-500 hover:text-gray-700"}`}
        >
          預約紀錄 ({appointments.length})
        </button>
        <button
          onClick={() => setSubTab("ledger")}
          className={`px-3 py-2 text-sm font-medium ${subTab === "ledger" ? "border-b-2 border-primary-600 text-primary-700" : "text-gray-500 hover:text-gray-700"}`}
        >
          帳冊紀錄 ({records.length})
        </button>
      </div>

      {/* Sub-tab content */}
      {subTab === "appointments" && (
        <>
          <div className="mb-3 flex justify-end gap-2">
            <button onClick={() => setShowBatchForm(true)} className="rounded-lg border border-primary-600 px-3 py-1.5 text-xs font-medium text-primary-600 hover:bg-primary-50">批次預約</button>
            <button onClick={() => setShowApptForm(true)} className="rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-700">+ 新增預約</button>
          </div>
          {loadingAppts ? (
            <p className="py-4 text-center text-sm text-gray-400">載入中...</p>
          ) : appointments.length === 0 ? (
            <p className="py-4 text-center text-sm text-gray-400">尚無預約</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                  <tr>
                    <th className="px-3 py-2">到訪序號</th>
                    <th className="px-3 py-2">日期</th>
                    <th className="px-3 py-2">時間</th>
                    <th className="px-3 py-2">診間</th>
                    <th className="px-3 py-2">金額</th>
                    <th className="px-3 py-2">酬勞</th>
                    <th className="px-3 py-2">狀態</th>
                    <th className="px-3 py-2">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {appointments.map((a) => (
                    <tr key={a.id} className="hover:bg-gray-50">
                      <td className="px-3 py-2 font-mono text-xs text-gray-600">
                        {visitId(c, a)}
                      </td>
                      <td className="px-3 py-2 text-xs">{fmtDate(a.start_time)}</td>
                      <td className="px-3 py-2 text-xs">{fmtTime(a.start_time)}~{fmtTime(a.end_time)}</td>
                      <td className="px-3 py-2 text-xs">{a.room_name ?? "—"}</td>
                      <td className="px-3 py-2">${a.amount.toLocaleString()}</td>
                      <td className="px-3 py-2 text-xs text-gray-500">
                        ${a.therapist_share?.toLocaleString()}
                      </td>
                      <td className="px-3 py-2">
                        <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${apptStatusColors[a.status] ?? "bg-gray-100"}`}>
                          {apptStatusLabels[a.status] ?? a.status}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        {a.status === "booked" && (
                          <div className="flex gap-2">
                            <button onClick={() => setEditApptPanel(a)} className="text-xs text-blue-600 hover:underline">編輯</button>
                            <button
                              onClick={() => setPaymentModal(a)}
                              className="text-xs text-primary-600 hover:underline"
                              title={a.funding_source === "institution"
                                ? `機構：${a.quota_institution_name ?? "—"}`
                                : "自費"}
                            >
                              付款（{a.funding_source === "institution" ? "機構" : "自費"}）
                            </button>
                            <button onClick={() => handleCancelAppt(a.id)} className="text-xs text-red-500 hover:underline">取消</button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {paymentModal && (
            <AppointmentPaymentModal
              token={token}
              appointment={paymentModal}
              onClose={() => setPaymentModal(null)}
              onSaved={() => { setPaymentModal(null); fetchAppts(); }}
            />
          )}
          {editApptPanel && (
            <AppointmentEditModal
              token={token}
              appt={editApptPanel}
              onClose={() => setEditApptPanel(null)}
              onDone={() => { setEditApptPanel(null); fetchAppts(); }}
            />
          )}
        </>
      )}

      {subTab === "ledger" && (
        <>
          {loadingRecords ? (
            <p className="py-4 text-center text-sm text-gray-400">載入中...</p>
          ) : records.length === 0 ? (
            <p className="py-4 text-center text-sm text-gray-400">尚無帳冊紀錄（需先日結）</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                  <tr>
                    <th className="px-3 py-2">日期</th>
                    <th className="px-3 py-2">金額</th>
                    <th className="px-3 py-2">抽成</th>
                    <th className="px-3 py-2">收款狀態</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {records.map((r) => (
                    <tr key={r.id} className="hover:bg-gray-50">
                      <td className="px-3 py-2 text-xs">{r.session_date}</td>
                      <td className="px-3 py-2">${r.amount.toLocaleString()}</td>
                      <td className="px-3 py-2 text-xs text-gray-500">
                        {r.commission_rate_used ? `${Math.round(r.commission_rate_used * 100)}%` : "—"}
                      </td>
                      <td className="px-3 py-2">
                        <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${
                          r.payment_status === "paid" ? "bg-green-100 text-green-700" : "bg-yellow-100 text-yellow-700"
                        }`}>
                          {r.payment_status === "paid" ? "已收" : "未收"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Appointment forms */}
      {showApptForm && (
        <AppointmentForm
          token={token}
          fixedCaseId={caseItem.id}
          fixedCaseName={caseItem.name}
          onClose={() => setShowApptForm(false)}
          onSaved={() => { setShowApptForm(false); fetchAppts(); }}
        />
      )}
      {showBatchForm && (
        <BatchForm
          token={token}
          fixedCaseId={caseItem.id}
          fixedCaseName={caseItem.name}
          onClose={() => setShowBatchForm(false)}
          onSaved={() => { setShowBatchForm(false); fetchAppts(); }}
        />
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   Tab 2: 預約總表
   ═══════════════════════════════════════════════════ */

