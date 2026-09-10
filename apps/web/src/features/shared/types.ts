/**
 * 跨 feature 共用的資料形狀 — V2升級計畫 11 §4.2。
 *
 * 這些型別原本全部擠在 cases/page.tsx 的檔頭。拆檔後 booking 與 institution
 * 兩個 feature 都會用到，所以放在中立的位置，而不是掛在其中一邊底下。
 *
 * 長期方向見 11 §5：應該改成從 FastAPI 的 OpenAPI schema 生成，而不是手抄。
 * 目前是手抄的，後端改欄位不會有任何東西擋下來。
 */

export interface CaseItem {
  id: number;
  temp_seq: number | null;
  case_number: string | null;
  name: string;
  age: number | null;
  birth_date: string | null;
  gender: string | null;
  phone: string | null;
  phone_home: string | null;
  address: string | null;
  emergency_contact: string | null;
  emergency_phone: string | null;
  emergency_phone2: string | null;
  referral_source: string | null;
  session_location: string | null;
  has_national_id: boolean;
  initial_visit_date: string | null;
  funding_source: string;
  institution_id: number | null;
  institution_name: string | null;
  therapist_id: number;
  therapist_name: string | null;
  status: string;
  billing_cycle: string | null;
  is_designated: boolean;
  case_type: string;
  members: { case_id: number; name: string; role: string | null }[] | null;
  notes: string | null;
  closed_at: string | null;
  closure_reason: string | null;
}

export interface Appointment {
  id: number;
  appointment_number: string;
  case_id: number;
  case_name: string | null;
  therapist_id: number;
  therapist_name: string | null;
  room_id: number | null;
  room_name: string | null;
  session_type: string;
  start_time: string | null;
  end_time: string | null;
  amount: number;
  funding_source: string;
  quota_id: number | null;
  quota_institution_name: string | null;
  therapist_share: number | null;
  clinic_share: number | null;
  visit_seq: number | null;
  status: string;
  batch_id: string | null;
  created_at: string | null;
}

export interface SessionRecord {
  id: number;
  session_date: string;
  appointment_number: string;
  case_name: string;
  therapist_name: string;
  amount: number;
  therapist_share: number;
  clinic_share: number;
  commission_rate_used: number | null;
  payment_status: string;
  claim_batch_id: number | null;
  therapist_doc_submitted_at: string | null;
}

export interface Therapist { id: number; name: string; email: string; role: string; base_price?: number | null; }
export interface InstitutionItem { id: number; name: string; is_active: boolean; }
export interface RoomOption { id: number; name: string; floor: number; room_code: string; }

/* ───── constants ───── */


/** 舊的 case_institution_quotas 路徑。booking（建約時挑額度）與 institution
 *  （額度管理）都要用。 */
export interface QuotaRow {
  id: number;
  case_id: number;
  case_name: string | null;
  institution_id: number;
  institution_name: string | null;
  total_count: number;
  used_count: number;
  reserved_count: number;
  remaining: number;
  valid_from: string | null;
  valid_until: string | null;
  note: string | null;
}

export interface QuotaTemplate {
  id: number;
  institution_id: number;
  institution_name: string | null;
  name: string;
  total_count: number;
  notes: string | null;
  default_valid_from: string | null;
  default_valid_until: string | null;
  created_by: number | null;
  created_at: string;
}

