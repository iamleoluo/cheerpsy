"use client";

import { cn } from "@/lib/cn";
import { Badge, type BadgeTone } from "./badge";
import { Button } from "./button";
import { MoneySplit } from "./domain";

/**
 * 診間格 — V2升級計畫 11 §2.3。**整個系統最重要的一個元件。**
 *
 * 櫃檯一整天只開這一頁，一天要處理 38 格。三條規則來自 v7 診間日曆定案：
 *   ③ 操作鍵一律中性黑白，狀態改由**右上角徽章**標色
 *   ④ 已完成（報到＋收款＋開據）**整格轉灰** —— 意思是「這格今天不用再碰了」
 *   ⑤ 機構額度剩最後一次**整格標黃**，因為收錯金額是這個畫面最貴的錯誤
 *
 * 每格四行固定：個案 · 心理師｜地點 · 方案／金額 · 操作列。位置固定，眼睛
 * 才能沿著同一條線往下掃。
 *
 * 已知後端缺口：AppointmentResponse 目前沒有 gender 與 case_number，所以
 * v7 樣本裡的「個案｜性別」與病歷號還印不出來。欄位補上後這裡直接接。
 */

export interface RoomCellAppointment {
  id: number;
  case_name: string | null;
  couple_name?: string | null;
  is_couple?: boolean;
  therapist_name: string | null;
  room_name: string | null;
  session_type: string;
  start_time: string | null;
  end_time: string | null;
  amount: number;
  plan_name: string | null;
  case_payable: number | null;
  institution_payable: number | null;
  check_in_status: "pending" | "arrived" | "no_show";
  copay_collected_at: string | null;
  receipt_no: string | null;
  no_show_reason?: string | null;
  /** 機構額度剩最後一次。目前需由呼叫端算出來（後端尚未直接提供）。 */
  is_last_quota?: boolean;
}

type Phase = "pending" | "arrived" | "collected" | "done" | "no_show";

/** 報到三步驟走到哪一步了。順序：待報到 → 已到 → 已收款 → 已開據。 */
export function cellPhase(a: RoomCellAppointment): Phase {
  if (a.check_in_status === "no_show") return "no_show";
  if (a.check_in_status !== "arrived") return "pending";
  if (a.receipt_no) return "done";
  if (a.copay_collected_at) return "collected";
  return "arrived";
}

const PHASE: Record<Phase, { label: string; tone: BadgeTone }> = {
  pending: { label: "待報到", tone: "pending" },
  arrived: { label: "已到", tone: "active" },
  collected: { label: "已收款", tone: "active" },
  done: { label: "已完成", tone: "muted" },
  no_show: { label: "未到", tone: "danger" },
};

const SESSION_LABEL: Record<string, string> = {
  in_person: "現場",
  online: "視訊",
  outdoor: "外展",
};

const hhmm = (iso: string | null) => (iso ? iso.slice(11, 16) : "");

export function RoomCell({
  appt,
  onOpen,
  onCheckIn,
  onNoShow,
  onCollect,
  onReceipt,
  className,
}: {
  appt: RoomCellAppointment;
  /** 點方塊本體 → 開啟完整明細。 */
  onOpen: (a: RoomCellAppointment) => void;
  onCheckIn?: (a: RoomCellAppointment) => void;
  onNoShow?: (a: RoomCellAppointment) => void;
  onCollect?: (a: RoomCellAppointment) => void;
  onReceipt?: (a: RoomCellAppointment) => void;
  className?: string;
}) {
  const phase = cellPhase(appt);
  const { label, tone } = PHASE[phase];
  const name = appt.is_couple ? (appt.couple_name ?? appt.case_name) : appt.case_name;
  const due = appt.case_payable ?? appt.amount;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onOpen(appt)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(appt);
        }
      }}
      className={cn(
        "relative h-full cursor-pointer rounded-control border border-l-[3px] px-2 py-1.5 text-left",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        // 底色與左緣是唯一帶顏色的地方；操作鍵永遠中性。
        phase === "done" && "border-line border-l-st-muted bg-st-muted-bg",
        phase === "no_show" && "border-st-danger/30 border-l-st-danger bg-st-danger-bg",
        phase === "collected" && "border-line border-l-st-done bg-surface",
        phase === "arrived" && "border-line border-l-st-active bg-surface",
        phase === "pending" &&
          (appt.is_last_quota
            ? "border-st-warn/40 border-l-st-warn bg-st-warn-bg"
            : "border-line border-l-st-pending bg-surface"),
        className,
      )}
    >
      <Badge tone={appt.is_last_quota && phase === "pending" ? "warn" : tone} size="mini" className="absolute right-1.5 top-1.5">
        {appt.is_last_quota && phase === "pending" ? "最後一次" : label}
      </Badge>

      {/* 1 · 個案 */}
      <div
        className={cn(
          "truncate pr-14 text-[11.5px] font-bold",
          phase === "done" ? "text-st-muted" : "text-ink",
        )}
      >
        {appt.is_couple && "👫 "}
        {name ?? "—"}
      </div>

      {/* 2 · 心理師｜地點 */}
      <div className={cn("truncate text-[10px]", phase === "done" ? "text-st-muted" : "text-ink-2")}>
        {appt.therapist_name ?? "—"}
        <span className="mx-1 text-st-muted">·</span>
        {SESSION_LABEL[appt.session_type] ?? appt.session_type}
        {appt.room_name ? ` ${appt.room_name}` : ""}
      </div>

      {/* 3 · 方案／金額 */}
      <div className={cn("truncate text-[10px]", phase === "done" ? "text-st-muted" : "text-ink-3")}>
        {phase === "no_show" ? (
          <>未到{appt.no_show_reason ? ` · ${appt.no_show_reason}` : ""}</>
        ) : phase === "done" ? (
          <span className="ident">{appt.receipt_no}</span>
        ) : appt.institution_payable ? (
          <MoneySplit casePayable={appt.case_payable} institutionPayable={appt.institution_payable} />
        ) : (
          <>
            {appt.plan_name ?? "自費"}
            <span className="mx-1">·</span>
            {hhmm(appt.start_time)}–{hhmm(appt.end_time)}
          </>
        )}
      </div>

      {/* 4 · 操作列。就地執行，不必離開日曆（v7 定案）。 */}
      <div className="mt-1 flex flex-wrap gap-1" onClick={(e) => e.stopPropagation()}>
        {phase === "pending" && (
          <>
            {onCheckIn && (
              <Button size="mini" variant="solid" onClick={() => onCheckIn(appt)}>
                已到
              </Button>
            )}
            {onNoShow && (
              <Button size="mini" onClick={() => onNoShow(appt)}>
                未到
              </Button>
            )}
          </>
        )}
        {phase === "arrived" &&
          onCollect &&
          (due > 0 ? (
            <Button size="mini" variant="solid" onClick={() => onCollect(appt)}>
              收款 ${due.toLocaleString("en-US")}
            </Button>
          ) : (
            // 機構全額補助：不產生應收，直接開據。
            <span className="text-[10px] text-ink-3">機構請款 · 免收</span>
          ))}
        {phase === "collected" && onReceipt && (
          <Button size="mini" variant="solid" onClick={() => onReceipt(appt)}>
            開立收據
          </Button>
        )}
        {phase === "done" && onReceipt && (
          <Button size="mini" onClick={() => onReceipt(appt)}>
            查看收據
          </Button>
        )}
      </div>
    </div>
  );
}
