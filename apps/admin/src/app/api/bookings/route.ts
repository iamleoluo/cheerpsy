import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { getAllAppointments } from '@/lib/booking-client'

export async function GET(req: NextRequest) {
  const session = await getServerSession(authOptions)
  if (!session) return NextResponse.json({ error: '未登入' }, { status: 401 })

  if (!['admin', 'therapist'].includes(session.user.role)) {
    return NextResponse.json({ error: '無權限' }, { status: 403 })
  }

  const { searchParams } = new URL(req.url)
  const status = searchParams.get('status') || undefined

  try {
    const appointments = await getAllAppointments(status)
    return NextResponse.json(appointments)
  } catch (e: any) {
    return NextResponse.json({ error: '無法讀取預約資料：' + e.message }, { status: 500 })
  }
}
