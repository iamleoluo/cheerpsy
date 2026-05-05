import { z } from 'zod'

export const loginSchema = z.object({
  email: z.string().email('請輸入有效的電子郵件'),
  password: z.string().min(6, '密碼至少6個字元'),
})

export const registerSchema = z.object({
  email: z.string().email('請輸入有效的電子郵件'),
  password: z.string().min(6, '密碼至少6個字元'),
  name: z.string().min(1, '請輸入姓名'),
  phone: z.string().optional(),
})

export const appointmentSchema = z.object({
  therapistProfileId: z.string().optional(),
  requestedDate: z.string().min(1, '請選擇日期'),
  requestedTimeSlot: z.string().min(1, '請選擇時段'),
  preferredFormat: z.enum(['online', 'in_person']),
  clientName: z.string().min(1, '請輸入姓名'),
  clientPhone: z.string().optional(),
  clientEmail: z.string().email('請輸入有效的電子郵件').optional().or(z.literal('')),
  notes: z.string().optional(),
})

export const sessionSchema = z.object({
  date: z.string().min(1, '請選擇日期'),
  room: z.string().optional(),
  therapistId: z.string().min(1, '請選擇心理師'),
  clientId: z.string().min(1, '請選擇個案'),
  billingType: z.string().optional(),
  amountReceivable: z.coerce.number().optional(),
  receivableType: z.string().optional(),
  location: z.string().optional(),
  paymentStatus: z.string().optional(),
  amountReceived: z.coerce.number().optional(),
  institutionMonth: z.string().optional(),
  counselingFormat: z.string().optional(),
  counselingType: z.string().optional(),
  hours: z.coerce.number().optional(),
  hourlyRate: z.coerce.number().optional(),
  totalFee: z.coerce.number().optional(),
  commissionRate: z.coerce.number().optional(),
  therapistIncome: z.coerce.number().optional(),
  clinicIncome: z.coerce.number().optional(),
  notes: z.string().optional(),
  therapistPaid: z.string().optional(),
})

export const therapistSchema = z.object({
  name: z.string().min(1, '請輸入心理師姓名'),
  commissionRate: z.coerce.number().min(0).max(1).default(0.8),
  isActive: z.boolean().default(true),
  bio: z.string().optional(),
  specialties: z.string().optional(),
})

export const staffUserSchema = z.object({
  email: z.string().email('請輸入有效的電子郵件'),
  password: z.string().min(6, '密碼至少6個字元'),
  name: z.string().min(1, '請輸入姓名'),
  role: z.enum(['admin', 'accountant', 'therapist']),
  therapistId: z.string().optional(),
})

export const clientSchema = z.object({
  name: z.string().min(1, '請輸入個案姓名'),
  phone: z.string().optional(),
  email: z.string().email().optional().or(z.literal('')),
  notes: z.string().optional(),
})

export type LoginInput = z.infer<typeof loginSchema>
export type RegisterInput = z.infer<typeof registerSchema>
export type AppointmentInput = z.infer<typeof appointmentSchema>
export type SessionInput = z.infer<typeof sessionSchema>
export type TherapistInput = z.infer<typeof therapistSchema>
export type StaffUserInput = z.infer<typeof staffUserSchema>
export type ClientInput = z.infer<typeof clientSchema>
