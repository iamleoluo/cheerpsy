import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'
import { sessionSchema } from 'shared'

export async function GET(req: NextRequest, { params }: { params: { id: string } }) {
  const session = await getServerSession(authOptions)
  if (!session) return NextResponse.json({ error: '未登入' }, { status: 401 })

  const record = await prisma.session.findUnique({
    where: { id: params.id },
    include: { therapist: true, client: true },
  })

  if (!record) return NextResponse.json({ error: '找不到紀錄' }, { status: 404 })

  // Therapist can only see own sessions
  if (session.user.role === 'therapist' && record.therapistId !== session.user.therapistId) {
    return NextResponse.json({ error: '無權限' }, { status: 403 })
  }

  return NextResponse.json(record)
}

export async function PUT(req: NextRequest, { params }: { params: { id: string } }) {
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
  const updated = await prisma.session.update({
    where: { id: params.id },
    data: {
      date: new Date(data.date),
      room: data.room,
      therapistId: data.therapistId,
      clientId: data.clientId,
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

  return NextResponse.json(updated)
}

export async function DELETE(req: NextRequest, { params }: { params: { id: string } }) {
  const session = await getServerSession(authOptions)
  if (!session || session.user.role !== 'admin') {
    return NextResponse.json({ error: '無權限' }, { status: 403 })
  }

  await prisma.session.delete({ where: { id: params.id } })
  return NextResponse.json({ success: true })
}
