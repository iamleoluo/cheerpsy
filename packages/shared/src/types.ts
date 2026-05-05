export type StaffRole = 'admin' | 'accountant' | 'therapist'

export type AppointmentStatus = 'pending' | 'confirmed' | 'rejected' | 'cancelled'

export type PreferredFormat = 'online' | 'in_person'

export type SessionSource = 'excel_import' | 'manual' | 'booking'

export type PaymentStatus = '已收' | '未收'

export type TherapistPaidStatus = '已付' | '未付'

export interface ExcelColumnMapping {
  date: number        // B = 2
  room: number        // C = 3
  therapist: number   // D = 4
  billingType: number // E = 5
  amountReceivable: number  // F = 6
  receivableType: number    // G = 7
  location: number          // H = 8
  paymentStatus: number     // I = 9
  amountReceived: number    // J = 10
  institutionMonth: number  // K = 11
  clientName: number        // L = 12
  counselingFormat: number  // M = 13
  counselingType: number    // N = 14
  hours: number             // O = 15
  hourlyRate: number        // P = 16
  totalFee: number          // Q = 17
  commissionRate: number    // R = 18
  therapistIncome: number   // S = 19
  clinicIncome: number      // T = 20
  notes: number             // U = 21
  therapistPaid: number     // V = 22
}
