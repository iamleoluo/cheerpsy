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
  const filter = searchParams.get('filter') // 'unpaid_clients' | 'unpaid_therapists' | 'all'
  const therapistId = searchParams.get('therapistId')

  const where: any = {}
  if (filter === 'unpaid_clients') where.paymentStatus = '未收'
  if (filter === 'unpaid_therapists') where.therapistPaid = '未付'
  if (therapistId) where.therapistId = therapistId

  const sessions = await prisma.session.findMany({
    where,
    include: { therapist: true, client: true },
    orderBy: { date: 'desc' },
  })

  // Summary
  const totalReceivable = sessions.reduce((sum, s) => sum + (s.amountReceivable || 0), 0)
  const totalReceived = sessions.reduce((sum, s) => sum + (s.amountReceived || 0), 0)
  const totalTherapistIncome = sessions.reduce((sum, s) => sum + (s.therapistIncome || 0), 0)
  const totalClinicIncome = sessions.reduce((sum, s) => sum + (s.clinicIncome || 0), 0)
  const unpaidToClient = sessions.filter((s) => s.paymentStatus === '未收').length
  const unpaidToTherapist = sessions.filter((s) => s.therapistPaid === '未付').length

  return NextResponse.json({
    sessions,
    summary: {
      totalReceivable,
      totalReceived,
      totalTherapistIncome,
      totalClinicIncome,
      unpaidToClient,
      unpaidToTherapist,
      totalSessions: sessions.length,
    },
  })
}

export async function PATCH(req: NextRequest) {
  const session = await getServerSession(authOptions)
  if (!session || !['admin', 'accountant'].includes(session.user.role)) {
    return NextResponse.json({ error: '無權限' }, { status: 403 })
  }

  const { sessionIds, field, value } = await req.json()

  if (!Array.isArray(sessionIds) || !field || !value) {
    return NextResponse.json({ error: '參數錯誤' }, { status: 400 })
  }

  if (field === 'paymentStatus') {
    await prisma.session.updateMany({
      where: { id: { in: sessionIds } },
      data: { paymentStatus: value },
    })
  } else if (field === 'therapistPaid') {
    await prisma.session.updateMany({
      where: { id: { in: sessionIds } },
      data: { therapistPaid: value },
    })
  }

  return NextResponse.json({ success: true })
}
