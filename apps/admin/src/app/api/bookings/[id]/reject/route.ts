import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { getAppointmentById, updateAppointmentStatus } from '@/lib/booking-client'

export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const session = await getServerSession(authOptions)
  if (!session || !['admin', 'therapist'].includes(session.user.role)) {
    return NextResponse.json({ error: '無權限' }, { status: 403 })
  }

  const { reason } = await req.json()

  try {
    const appointment = await getAppointmentById(params.id)
    if (!appointment) {
      return NextResponse.json({ error: '預約不存在' }, { status: 404 })
    }
    if (appointment.status !== 'pending') {
      return NextResponse.json({ error: '此預約已處理' }, { status: 400 })
    }

    await updateAppointmentStatus(params.id, 'rejected', reason)

    return NextResponse.json({ success: true })
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
