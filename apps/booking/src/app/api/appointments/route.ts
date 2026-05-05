import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'
import { appointmentSchema } from 'shared'
import { rateLimit } from '@/lib/rate-limit'

export async function GET() {
  const session = await getServerSession(authOptions)
  if (!session) return NextResponse.json({ error: '請先登入' }, { status: 401 })

  const appointments = await prisma.appointment.findMany({
    where: { clientUserId: (session.user as any).id },
    include: { therapistProfile: true },
    orderBy: { createdAt: 'desc' },
  })

  return NextResponse.json(appointments)
}

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions)
  if (!session) return NextResponse.json({ error: '請先登入' }, { status: 401 })

  const userId = (session.user as any).id
  const ip = req.headers.get('x-forwarded-for') || userId
  if (!rateLimit(`booking:${ip}`, 5, 60000)) {
    return NextResponse.json({ error: '請求過於頻繁，請稍後再試' }, { status: 429 })
  }

  const body = await req.json()
  const parsed = appointmentSchema.safeParse(body)
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 })
  }

  const data = parsed.data

  const appointment = await prisma.appointment.create({
    data: {
      clientUserId: userId,
      therapistProfileId: data.therapistProfileId || null,
      requestedDate: new Date(data.requestedDate),
      requestedTimeSlot: data.requestedTimeSlot,
      preferredFormat: data.preferredFormat,
      clientName: data.clientName,
      clientPhone: data.clientPhone,
      clientEmail: data.clientEmail,
      notes: data.notes,
    },
  })

  return NextResponse.json(appointment)
}
