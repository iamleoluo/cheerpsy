import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'
import { getAppointmentById, updateAppointmentStatus } from '@/lib/booking-prisma'

export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const session = await getServerSession(authOptions)
  if (!session || !['admin', 'therapist'].includes(session.user.role)) {
    return NextResponse.json({ error: '無權限' }, { status: 403 })
  }

  const { therapistId } = await req.json()
  if (!therapistId) {
    return NextResponse.json({ error: '請選擇心理師' }, { status: 400 })
  }

  try {
    // 1. Read appointment from Booking DB
    const appointment = getAppointmentById(params.id) as any
    if (!appointment) {
      return NextResponse.json({ error: '預約不存在' }, { status: 404 })
    }
    if (appointment.status !== 'pending') {
      return NextResponse.json({ error: '此預約已處理' }, { status: 400 })
    }

    // 2. Upsert client in Internal DB
    let client = await prisma.client.findFirst({
      where: { name: appointment.client_name },
    })
    if (!client) {
      client = await prisma.client.create({
        data: {
          name: appointment.client_name,
          phone: appointment.client_phone,
          email: appointment.client_email,
          bookingClientUserId: appointment.client_user_id,
        },
      })
    }

    // 3. Create session in Internal DB
    const newSession = await prisma.session.create({
      data: {
        date: new Date(appointment.requested_date),
        therapistId,
        clientId: client.id,
        source: 'booking',
        bookingAppointmentId: params.id,
        counselingFormat: appointment.preferred_format === 'online' ? '視訊' : '實體',
        counselingType: '個別',
        location: appointment.preferred_format === 'online' ? '視訊' : '治療所',
        paymentStatus: '未收',
        therapistPaid: '未付',
      },
    })

    // 4. Update appointment status in Booking DB
    updateAppointmentStatus(params.id, 'confirmed')

    return NextResponse.json({ success: true, sessionId: newSession.id })
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
