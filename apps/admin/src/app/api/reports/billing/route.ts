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
  })

  // Categorize: 自費 vs 機構
  const selfPay = sessions.filter((s) => s.billingType === '自費')
  const institution = sessions.filter((s) => s.billingType !== '自費')

  const selfPayTotal = selfPay.reduce((sum, s) => sum + (s.therapistIncome || 0), 0)
  const institutionTotal = institution.reduce((sum, s) => sum + (s.therapistIncome || 0), 0)

  // By billing type detail
  const byType: Record<string, { count: number; therapistIncome: number; clinicIncome: number; totalFee: number }> = {}
  for (const s of sessions) {
    const bt = s.billingType || '其他'
    if (!byType[bt]) byType[bt] = { count: 0, therapistIncome: 0, clinicIncome: 0, totalFee: 0 }
    byType[bt].count++
    byType[bt].therapistIncome += s.therapistIncome || 0
    byType[bt].clinicIncome += s.clinicIncome || 0
    byType[bt].totalFee += s.totalFee || 0
  }

  // By therapist and billing type
  const byTherapistType: Record<string, Record<string, number>> = {}
  for (const s of sessions) {
    const name = s.therapist.name
    const bt = s.billingType || '其他'
    if (!byTherapistType[name]) byTherapistType[name] = {}
    byTherapistType[name][bt] = (byTherapistType[name][bt] || 0) + (s.therapistIncome || 0)
  }

  return NextResponse.json({
    selfPay: { count: selfPay.length, total: selfPayTotal },
    institution: { count: institution.length, total: institutionTotal },
    byType: Object.entries(byType).map(([type, data]) => ({ type, ...data })),
    byTherapistType: Object.entries(byTherapistType).map(([therapist, types]) => ({
      therapist,
      types,
      total: Object.values(types).reduce((a, b) => a + b, 0),
    })),
  })
}
