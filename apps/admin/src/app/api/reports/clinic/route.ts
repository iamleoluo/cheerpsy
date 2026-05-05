import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'

export async function GET(req: NextRequest) {
  const session = await getServerSession(authOptions)
  if (!session || !['admin', 'accountant'].includes(session.user.role)) {
    return NextResponse.json({ error: '無權限' }, { status: 403 })
  }

  const { searchParams } = new URL(req.url)
  const dateFrom = searchParams.get('dateFrom')
  const dateTo = searchParams.get('dateTo')

  const where: any = {}
  if (dateFrom || dateTo) {
    where.date = {}
    if (dateFrom) where.date.gte = new Date(dateFrom)
    if (dateTo) where.date.lte = new Date(dateTo + 'T23:59:59')
  }

  const sessions = await prisma.session.findMany({
    where,
    include: { therapist: true },
    orderBy: { date: 'asc' },
  })

  const totalClinicIncome = sessions.reduce((sum, s) => sum + (s.clinicIncome || 0), 0)
  const totalTherapistIncome = sessions.reduce((sum, s) => sum + (s.therapistIncome || 0), 0)
  const totalRevenue = sessions.reduce((sum, s) => sum + (s.totalFee || 0), 0)
  const totalSessions = sessions.length

  // Income by therapist
  const byTherapist: Record<string, number> = {}
  for (const s of sessions) {
    const name = s.therapist.name
    byTherapist[name] = (byTherapist[name] || 0) + (s.clinicIncome || 0)
  }

  // Income by billing type
  const byBillingType: Record<string, number> = {}
  for (const s of sessions) {
    const bt = s.billingType || '其他'
    byBillingType[bt] = (byBillingType[bt] || 0) + (s.totalFee || 0)
  }

  // Monthly trend (group by date)
  const byDate: Record<string, { revenue: number; clinicIncome: number; sessions: number }> = {}
  for (const s of sessions) {
    const dateKey = new Date(s.date).toISOString().split('T')[0]
    if (!byDate[dateKey]) byDate[dateKey] = { revenue: 0, clinicIncome: 0, sessions: 0 }
    byDate[dateKey].revenue += s.totalFee || 0
    byDate[dateKey].clinicIncome += s.clinicIncome || 0
    byDate[dateKey].sessions += 1
  }

  return NextResponse.json({
    totalRevenue,
    totalClinicIncome,
    totalTherapistIncome,
    totalSessions,
    byTherapist: Object.entries(byTherapist).map(([name, income]) => ({ name, income })),
    byBillingType: Object.entries(byBillingType).map(([type, amount]) => ({ type, amount })),
    trend: Object.entries(byDate)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, data]) => ({ date, ...data })),
  })
}
