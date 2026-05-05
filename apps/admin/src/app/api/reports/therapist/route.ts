import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'
import { TAX_RATE, HEALTH_INSURANCE_RATE } from 'shared'

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
    orderBy: [{ therapist: { name: 'asc' } }, { billingType: 'asc' }],
  })

  // Group by therapist, then by billing type
  const therapistMap = new Map<string, {
    therapistName: string
    byBillingType: Map<string, number>
    totalIncome: number
  }>()

  for (const s of sessions) {
    const name = s.therapist.name
    if (!therapistMap.has(name)) {
      therapistMap.set(name, { therapistName: name, byBillingType: new Map(), totalIncome: 0 })
    }
    const entry = therapistMap.get(name)!
    const bt = s.billingType || '其他'
    entry.byBillingType.set(bt, (entry.byBillingType.get(bt) || 0) + (s.therapistIncome || 0))
    entry.totalIncome += s.therapistIncome || 0
  }

  const report = Array.from(therapistMap.values()).map((entry) => {
    const tax = entry.totalIncome * TAX_RATE
    const healthInsurance = entry.totalIncome > 20000 ? entry.totalIncome * HEALTH_INSURANCE_RATE : 0
    const netIncome = entry.totalIncome - tax - healthInsurance

    return {
      therapistName: entry.therapistName,
      byBillingType: Object.fromEntries(entry.byBillingType),
      totalIncome: entry.totalIncome,
      tax,
      healthInsurance,
      netIncome,
    }
  })

  return NextResponse.json(report)
}
