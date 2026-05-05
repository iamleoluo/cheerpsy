import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'

export async function GET(req: NextRequest, { params }: { params: { id: string } }) {
  const session = await getServerSession(authOptions)
  if (!session) return NextResponse.json({ error: '請先登入' }, { status: 401 })

  const appointment = await prisma.appointment.findUnique({
    where: { id: params.id },
    include: { therapistProfile: true },
  })

  if (!appointment || appointment.clientUserId !== (session.user as any).id) {
    return NextResponse.json({ error: '找不到預約' }, { status: 404 })
  }

  return NextResponse.json(appointment)
}

export async function PATCH(req: NextRequest, { params }: { params: { id: string } }) {
  const session = await getServerSession(authOptions)
  if (!session) return NextResponse.json({ error: '請先登入' }, { status: 401 })

  const appointment = await prisma.appointment.findUnique({ where: { id: params.id } })
  if (!appointment || appointment.clientUserId !== (session.user as any).id) {
    return NextResponse.json({ error: '找不到預約' }, { status: 404 })
  }

  if (appointment.status !== 'pending') {
    return NextResponse.json({ error: '只能取消待確認的預約' }, { status: 400 })
  }

  const updated = await prisma.appointment.update({
    where: { id: params.id },
    data: { status: 'cancelled' },
  })

  return NextResponse.json(updated)
}
