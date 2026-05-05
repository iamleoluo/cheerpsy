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
  const type = searchParams.get('type') || 'sessions'
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
    include: { therapist: true, client: true },
    orderBy: { date: 'asc' },
  })

  // Generate CSV
  const headers = [
    '日期', '空間', '心理師', '收費形式', '應收金額', '應收類型',
    '諮商地點', '收款狀況', '當日實收金額', '機構核銷月份',
    '個案姓名', '諮商形式', '諮商種類', '時數', '鐘點',
    '應收金額（計算）', '抽成', '心理師收入', '治療所收入', '備註', '給付治療師',
  ]

  const rows = sessions.map((s) => [
    new Date(s.date).toLocaleDateString('zh-TW'),
    s.room || '',
    s.therapist.name,
    s.billingType || '',
    s.amountReceivable?.toString() || '',
    s.receivableType || '',
    s.location || '',
    s.paymentStatus || '',
    s.amountReceived?.toString() || '',
    s.institutionMonth || '',
    s.client.name,
    s.counselingFormat || '',
    s.counselingType || '',
    s.hours?.toString() || '',
    s.hourlyRate?.toString() || '',
    s.totalFee?.toString() || '',
    s.commissionRate?.toString() || '',
    s.therapistIncome?.toString() || '',
    s.clinicIncome?.toString() || '',
    s.notes || '',
    s.therapistPaid || '',
  ])

  const BOM = '\uFEFF'
  const csv = BOM + [headers, ...rows].map((r) => r.map((c) => `"${c}"`).join(',')).join('\n')

  return new NextResponse(csv, {
    headers: {
      'Content-Type': 'text/csv; charset=utf-8',
      'Content-Disposition': `attachment; filename="sessions_export_${new Date().toISOString().split('T')[0]}.csv"`,
    },
  })
}
