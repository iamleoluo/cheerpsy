import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'
import { sessionSchema } from 'shared'

export async function GET(req: NextRequest) {
  const session = await getServerSession(authOptions)
  if (!session) return NextResponse.json({ error: '未登入' }, { status: 401 })

  const { searchParams } = new URL(req.url)
  const therapistId = searchParams.get('therapistId')
  const dateFrom = searchParams.get('dateFrom')
  const dateTo = searchParams.get('dateTo')
  const billingType = searchParams.get('billingType')
  const paymentStatus = searchParams.get('paymentStatus')
  const page = parseInt(searchParams.get('page') || '1')
  const limit = parseInt(searchParams.get('limit') || '50')

  const where: any = {}

  // Therapist can only see own sessions
  if (session.user.role === 'therapist' && session.user.therapistId) {
    where.therapistId = session.user.therapistId
  } else if (therapistId) {
    where.therapistId = therapistId
  }

  if (dateFrom || dateTo) {
    where.date = {}
    if (dateFrom) where.date.gte = new Date(dateFrom)
    if (dateTo) where.date.lte = new Date(dateTo + 'T23:59:59')
  }

  if (billingType) where.billingType = billingType
  if (paymentStatus) where.paymentStatus = paymentStatus

  const [sessions, total] = await Promise.all([
    prisma.session.findMany({
      where,
      include: { therapist: true, client: true },
      orderBy: { date: 'desc' },
      skip: (page - 1) * limit,
      take: limit,
    }),
    prisma.session.count({ where }),
  ])

  return NextResponse.json({ sessions, total, page, totalPages: Math.ceil(total / limit) })
}

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions)
  if (!session || session.user.role !== 'admin') {
    return NextResponse.json({ error: '無權限' }, { status: 403 })
  }

  const body = await req.json()
  const parsed = sessionSchema.safeParse(body)
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 })
  }

  const data = parsed.data
  const newSession = await prisma.session.create({
    data: {
      date: new Date(data.date),
      room: data.room,
      therapistId: data.therapistId,
      clientId: data.clientId,
      source: 'manual',
      billingType: data.billingType,
      amountReceivable: data.amountReceivable,
      receivableType: data.receivableType,
      location: data.location,
      paymentStatus: data.paymentStatus,
      amountReceived: data.amountReceived,
      institutionMonth: data.institutionMonth,
      counselingFormat: data.counselingFormat,
      counselingType: data.counselingType,
      hours: data.hours,
      hourlyRate: data.hourlyRate,
      totalFee: data.totalFee,
      commissionRate: data.commissionRate,
      therapistIncome: data.therapistIncome,
      clinicIncome: data.clinicIncome,
      notes: data.notes,
      therapistPaid: data.therapistPaid,
    },
  })

  return NextResponse.json(newSession)
}
