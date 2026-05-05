export const EXCEL_COLUMN_MAP = {
  date: 2,
  room: 3,
  therapist: 4,
  billingType: 5,
  amountReceivable: 6,
  receivableType: 7,
  location: 8,
  paymentStatus: 9,
  amountReceived: 10,
  institutionMonth: 11,
  clientName: 12,
  counselingFormat: 13,
  counselingType: 14,
  hours: 15,
  hourlyRate: 16,
  totalFee: 17,
  commissionRate: 18,
  therapistIncome: 19,
  clinicIncome: 20,
  notes: 21,
  therapistPaid: 22,
} as const

export const STAFF_ROLES = ['admin', 'accountant', 'therapist'] as const

export const APPOINTMENT_STATUSES = ['pending', 'confirmed', 'rejected', 'cancelled'] as const

export const TAX_RATE = 0.10
export const HEALTH_INSURANCE_RATE = 0.0211
export const DEFAULT_COMMISSION_RATE = 0.8

export const NAV_ITEMS = {
  admin: [
    { href: '/dashboard', label: '總覽', icon: 'LayoutDashboard' },
    { href: '/bookings', label: '預約管理', icon: 'CalendarCheck' },
    { href: '/schedule', label: '排程表', icon: 'Calendar' },
    { href: '/sessions/new', label: '新增紀錄', icon: 'Plus' },
    { href: '/finance', label: '收款管理', icon: 'DollarSign' },
    { href: '/reports/therapist', label: '薪資核發', icon: 'FileText' },
    { href: '/reports/clinic', label: '治療所收入', icon: 'BarChart3' },
    { href: '/reports/billing', label: '收費分析', icon: 'PieChart' },
    { href: '/therapists', label: '心理師管理', icon: 'Users' },
    { href: '/clients', label: '個案管理', icon: 'UserCheck' },
    { href: '/import', label: 'Excel匯入', icon: 'Upload' },
    { href: '/users', label: '帳號管理', icon: 'Settings' },
  ],
  accountant: [
    { href: '/dashboard', label: '總覽', icon: 'LayoutDashboard' },
    { href: '/schedule', label: '排程表', icon: 'Calendar' },
    { href: '/finance', label: '收款管理', icon: 'DollarSign' },
    { href: '/reports/therapist', label: '薪資核發', icon: 'FileText' },
    { href: '/reports/clinic', label: '治療所收入', icon: 'BarChart3' },
    { href: '/reports/billing', label: '收費分析', icon: 'PieChart' },
  ],
  therapist: [
    { href: '/dashboard', label: '總覽', icon: 'LayoutDashboard' },
    { href: '/bookings', label: '我的預約', icon: 'CalendarCheck' },
    { href: '/schedule', label: '我的排程', icon: 'Calendar' },
  ],
} as const
