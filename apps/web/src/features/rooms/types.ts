/**
 * 診間日曆的資料形狀與顯示字串 — 從 rooms/page.tsx 搬出（V2升級計畫 11 §4.2）。
 *
 * 三種佔用診間的實體共用同一張時間軸：一般預約、場地租借、5F 雲燈教室
 * （P4 §4 的三者共用 _check_room_conflict 與 excl_room_time_overlap）。
 *
 * 時間軸 08:00–22:00、半小時一格，對應定稿 A3／v7 原型 TICKS。
 */

export interface Room {
  id: number;
  name: string;
  floor: number;
  room_code: string;
  use_type?: string | null; // 晤談 / 兒童遊戲室
  size?: string | null;
}

export interface Appointment {
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
  /** 初診（11 §5.9）。非 null 代表這筆屬於還沒報到的媒合案，報到要走初診流程。 */
  first_visit?: {
    referral_id: number;
    referral_code: string;
    missing_fields: ("national_id" | "birth_date" | "phone")[];
  } | null;
}

export interface VenueRental {
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

export interface HallBooking {
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

export const PAYER_LABEL: Record<string, string> = {
  institution: "機構應收",
  therapist: "心理師酬勞扣回",
  renter: "借用人自付",
};

export interface FeeItem {
  id: number;
  name: string;
  is_default: boolean;
}

export const sessionTypeLabel: Record<string, string> = { in_person: "現場", online: "視訊", outdoor: "外展" };

export const NO_SHOW_REASONS: { value: string; label: string }[] = [
  { value: "case_leave", label: "個案來電請假" },
  { value: "last_minute_cancel", label: "臨時取消" },
  { value: "unreachable", label: "未聯繫上" },
  { value: "other", label: "其他" },
];

export function toLocalDateString(d: Date): string {
  const y = d.getFullYear();
  const m = (d.getMonth() + 1).toString().padStart(2, "0");
  const day = d.getDate().toString().padStart(2, "0");
  return `${y}-${m}-${day}`;
}

