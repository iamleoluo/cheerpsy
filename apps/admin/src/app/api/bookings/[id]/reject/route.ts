import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { getAppointmentById, updateAppointmentStatus } from '@/lib/booking-prisma'

export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const session = await getServerSession(authOptions)
  if (!session || !['admin', 'therapist'].includes(session.user.role)) {
    return NextResponse.json({ error: '無權限' }, { status: 403 })
  }

  const { reason } = await req.json()

  try {
    const appointment = getAppointmentById(params.id) as any
    if (!appointment) {
      return NextResponse.json({ error: '預約不存在' }, { status: 404 })
    }
    if (appointment.status !== 'pending') {
      return NextResponse.json({ error: '此預約已處理' }, { status: 400 })
    }

    updateAppointmentStatus(params.id, 'rejected', reason)

    return NextResponse.json({ success: true })
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
