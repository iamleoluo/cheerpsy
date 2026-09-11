"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { clientFetch } from "@/lib/client-api";

/**
 * 預約作業（行政端）— 第一版把「機構方案報價」這條真正缺的線接上：
 * 選機構方案 → GET /institution/eligible-plans 抓清單 → 選定後
 * POST /institution/quote-preview 試算金額 → 建立時帶 plan_id，
 * 金額由後端依費率規則決定（不用手動填）。
 *
 * ─────────────────────────────────────────────────────────────────────────
 * ⚠️ 這頁與 features/booking/AppointmentForm 是**兩個世代**，不是兩份重複
 *
 * V2升級計畫 11 §4.2 原本把它們列為「兩套表單並行」，預期 P3 拆檔時合併成
 * 一份。實際查證後發現不是重複，而是走**互斥的兩條金流路徑**——
 * schemas/appointment.py:20 寫得很明白：
 *
 *     quota_id: int | None = None  # 舊路徑：case_institution_quotas。與 plan_id 互斥
 *
 *   · AppointmentForm（原 /cases）→ 舊的 quota_id 路徑。有診間小日曆、
 *     伴侶案付款方選擇、完整 UX，但金流模型是舊的。
 *   · 這一頁                      → 新的 plan_id 報價路徑（07 §4.2 的報價
 *     快照），金流模型正確，但 UX 只有最小可用版本。
 *
 * 所以「合併」不是搬程式碼，而是**決定退役 quota_id**——那會動到後端契約與
 * 既有資料，屬於 P4 機構那條線（09 §1.4 的同一類收斂問題）。P3 只做結構拆分，
 * 不在重構裡偷偷改金流語意。
 * ─────────────────────────────────────────────────────────────────────────
 */

interface CaseOption {
  id: number;
  name: string;
  therapist_id: number;
  case_type?: string;
  funding_source?: string;
}
interface RoomOption {
  id: number;
  name: string;
  floor: number;
  room_code: string;
  use_type?: string | null;
}
interface PlanOption {
  plan_id: number;
  plan_name: string;
  institution_name: string | null;
  quota_summary: string | null;
  is_last: boolean;
  disabled: boolean;
  disabled_reason: string | null;
}
interface Quote {
  quote_id: string;
  plan_name: string;
  institution_name: string | null;
  pricing: { unit_price: string; case_payable: string; institution_payable: string };
  quota: { is_last: boolean; blocking: string | null };
}

const sessionTypeOptions = [
  { value: "in_person", label: "現場" },
  { value: "online", label: "視訊" },
  { value: "outdoor", label: "外展" },
];

function toLocalDateString(d: Date): string {
  const y = d.getFullYear();
  const m = (d.getMonth() + 1).toString().padStart(2, "0");
  const day = d.getDate().toString().padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function BookingPage() {
  const { data: session } = useSession();
  const token = (session?.user as any)?.accessToken;

  const [cases, setCases] = useState<CaseOption[]>([]);
  const [rooms, setRooms] = useState<RoomOption[]>([]);
  const [caseId, setCaseId] = useState("");
  const [caseQuery, setCaseQuery] = useState("");
  const [sessionType, setSessionType] = useState("in_person");
  const [roomId, setRoomId] = useState("");
  const [date, setDate] = useState(toLocalDateString(new Date()));
  const [startTime, setStartTime] = useState("10:00");
  const [durationMin, setDurationMin] = useState(60);

  const [payWith, setPayWith] = useState<"self_pay" | "plan">("self_pay");
  const [selfPayAmount, setSelfPayAmount] = useState("2000");
  const [plans, setPlans] = useState<PlanOption[]>([]);
  const [planId, setPlanId] = useState("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [quoteError, setQuoteError] = useState<string | null>(null);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    clientFetch("/cases", token).then(setCases).catch(() => {});
    clientFetch("/rooms", token).then(setRooms).catch(() => {});
  }, [token]);

  const selectedCase = cases.find((c) => String(c.id) === caseId);
  const endTime = (() => {
    const [h, m] = startTime.split(":").map(Number);
    const total = h * 60 + m + durationMin;
    return `${String(Math.floor(total / 60) % 24).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
  })();

  // 個案選定 → 抓可用機構方案
  useEffect(() => {
    if (!token || !caseId || payWith !== "plan") {
      setPlans([]);
      return;
    }
    clientFetch(`/institution/eligible-plans?case_id=${caseId}&on_date=${date}&session_type=${sessionType}`, token)
      .then(setPlans)
      .catch(() => setPlans([]));
  }, [token, caseId, payWith, date, sessionType]);

  // 選定方案 → 報價試算
  const runQuote = useCallback(async () => {
    if (!token || !planId || !selectedCase) {
      setQuote(null);
      return;
    }
    setQuoteError(null);
    try {
      const q = await clientFetch("/institution/quote-preview", token, {
        method: "POST",
        body: JSON.stringify({
          case_id: Number(caseId),
          plan_id: Number(planId),
          therapist_id: selectedCase.therapist_id,
          session_type: sessionType,
          duration_min: durationMin,
          appt_date: date,
        }),
      });
      setQuote(q);
    } catch (e: any) {
      setQuote(null);
      setQuoteError(e.message ?? "報價失敗");
    }
  }, [token, planId, selectedCase, caseId, sessionType, durationMin, date]);

  useEffect(() => {
    runQuote();
  }, [runQuote]);

  const filteredCases = caseQuery
    ? cases.filter((c) => c.name.toLowerCase().includes(caseQuery.toLowerCase()))
    : cases;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedCase) return;
    setSaving(true);
    setError("");
    setSuccess(null);
    try {
      const body: Record<string, unknown> = {
        case_id: selectedCase.id,
        room_id: sessionType === "in_person" && roomId ? Number(roomId) : null,
        session_type: sessionType,
        start_time: `${date}T${startTime}:00+08:00`,
        end_time: `${date}T${endTime}:00+08:00`,
        funding_source: payWith === "plan" ? "institution" : "self_pay",
      };
      if (payWith === "plan") {
        if (!planId) throw new Error("請選擇機構方案");
        if (quote?.quota.blocking) throw new Error(quote.quota.blocking);
        body.plan_id = Number(planId);
      } else {
        body.amount = parseFloat(selfPayAmount);
      }
      const appt = await clientFetch("/appointments", token, { method: "POST", body: JSON.stringify(body) });
      setSuccess(`已建立預約 ${appt.appointment_number}`);
      setPlanId("");
      setQuote(null);
    } catch (e: any) {
      setError(e.message ?? "建立失敗");
    } finally {
      setSaving(false);
    }
  }

  if (!token) return <p>Loading...</p>;

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-6 text-2xl font-bold">預約作業</h1>

      {success && <div className="mb-4 rounded-lg bg-st-done-bg px-4 py-3 text-sm text-st-done">{success}</div>}
      {error && <div className="mb-4 rounded-lg bg-st-danger-bg px-4 py-3 text-sm text-st-danger">{error}</div>}

      <form onSubmit={handleSubmit} className="space-y-4 rounded-xl border border-line bg-white p-6">
        <label className="block">
          <span className="mb-1 block text-xs text-ink-3">個案 <span className="text-st-danger">*</span></span>
          <input
            value={caseQuery}
            onChange={(e) => setCaseQuery(e.target.value)}
            placeholder="輸入姓名搜尋"
            className="mb-1 w-full rounded-lg border border-line-2 px-3 py-2 text-sm"
          />
          <select required value={caseId} onChange={(e) => { setCaseId(e.target.value); setPlanId(""); }} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
            <option value="">請選擇</option>
            {filteredCases.map((c) => (
              <option key={c.id} value={c.id}>{c.case_type === "couple" ? "👫 " : ""}{c.name}</option>
            ))}
          </select>
          {selectedCase?.case_type === "couple" && (
            <p className="mt-1 text-xs text-st-warn">伴侶案付款方選擇請至「個案管理」既有的新增預約入口，這裡先支援一般個案。</p>
          )}
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">諮商類型</span>
            <select value={sessionType} onChange={(e) => setSessionType(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
              {sessionTypeOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
          {sessionType === "in_person" && (
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">診間</span>
              <select value={roomId} onChange={(e) => setRoomId(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
                <option value="">請選擇</option>
                {rooms.map((r) => <option key={r.id} value={r.id}>{r.name}（{r.floor}F）</option>)}
              </select>
            </label>
          )}
        </div>

        <div className="grid grid-cols-3 gap-3">
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">日期</span>
            <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">開始時間</span>
            <input type="time" required value={startTime} onChange={(e) => setStartTime(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-ink-3">時長</span>
            <select value={durationMin} onChange={(e) => setDurationMin(Number(e.target.value))} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
              <option value={60}>60 分</option>
              <option value={90}>90 分（伴侶）</option>
              <option value={30}>30 分</option>
            </select>
          </label>
        </div>
        <p className="text-xs text-ink-3">{date} {startTime} ~ {endTime}</p>

        <div className="border-t border-line pt-4">
          <span className="mb-2 block text-xs text-ink-3">付款方式</span>
          <div className="mb-3 flex gap-2">
            <button type="button" onClick={() => setPayWith("self_pay")} className={`flex-1 rounded-lg border py-2 text-sm ${payWith === "self_pay" ? "border-accent bg-accent-soft text-accent" : "border-line text-ink-3"}`}>自費</button>
            <button type="button" onClick={() => setPayWith("plan")} className={`flex-1 rounded-lg border py-2 text-sm ${payWith === "plan" ? "border-accent bg-accent-soft text-accent" : "border-line text-ink-3"}`}>機構方案</button>
          </div>

          {payWith === "self_pay" && (
            <label className="block">
              <span className="mb-1 block text-xs text-ink-3">金額</span>
              <input type="number" required value={selfPayAmount} onChange={(e) => setSelfPayAmount(e.target.value)} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm" />
            </label>
          )}

          {payWith === "plan" && (
            <div className="space-y-3">
              <label className="block">
                <span className="mb-1 block text-xs text-ink-3">機構方案 <span className="text-st-danger">*</span></span>
                <select required={payWith === "plan"} value={planId} onChange={(e) => setPlanId(e.target.value)} disabled={!caseId} className="w-full rounded-lg border border-line-2 px-3 py-2 text-sm">
                  <option value="">{caseId ? "請選擇" : "請先選個案"}</option>
                  {plans.map((p) => (
                    <option key={p.plan_id} value={p.plan_id} disabled={p.disabled}>
                      {p.plan_name}{p.institution_name ? `（${p.institution_name}）` : ""}{p.quota_summary ? ` · ${p.quota_summary}` : ""}{p.is_last ? " · 最後一次" : ""}{p.disabled ? ` · ${p.disabled_reason}` : ""}
                    </option>
                  ))}
                </select>
                {caseId && plans.length === 0 && <p className="mt-1 text-xs text-ink-3">此個案目前沒有可用的機構方案</p>}
              </label>

              {quoteError && <div className="rounded-lg bg-st-danger-bg px-3 py-2 text-xs text-st-danger">{quoteError}</div>}
              {quote && (
                <div className={`rounded-lg p-3 text-xs ${quote.quota.blocking ? "bg-st-danger-bg text-st-danger" : "bg-accent-soft text-accent"}`}>
                  <div className="flex justify-between"><span>總鐘點費</span><span>${Number(quote.pricing.unit_price).toLocaleString()}</span></div>
                  <div className="flex justify-between"><span>個案自付</span><span>${Number(quote.pricing.case_payable).toLocaleString()}</span></div>
                  <div className="flex justify-between"><span>機構請款</span><span>${Number(quote.pricing.institution_payable).toLocaleString()}</span></div>
                  {quote.quota.blocking && <div className="mt-1 font-medium">⚠️ {quote.quota.blocking}</div>}
                  {quote.quota.is_last && !quote.quota.blocking && <div className="mt-1 font-medium text-st-warn">⚠️ 最後一次額度</div>}
                </div>
              )}
            </div>
          )}
        </div>

        <button type="submit" disabled={saving} className="w-full rounded-lg bg-accent py-2.5 text-sm font-medium text-white hover:bg-st-active disabled:opacity-50">
          {saving ? "建立中…" : "建立預約"}
        </button>
      </form>
    </div>
  );
}
