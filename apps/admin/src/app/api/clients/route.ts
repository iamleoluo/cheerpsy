import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'
import { clientSchema } from 'shared'

export async function GET(req: NextRequest) {
  const session = await getServerSession(authOptions)
  if (!session) return NextResponse.json({ error: '未登入' }, { status: 401 })

  const { searchParams } = new URL(req.url)
  const search = searchParams.get('search')

  const where: any = {}
  if (search) {
    where.name = { contains: search }
  }

  // Therapist can only see their own clients
  if (session.user.role === 'therapist' && session.user.therapistId) {
    const clientIds = await prisma.session.findMany({
      where: { therapistId: session.user.therapistId },
      select: { clientId: true },
      distinct: ['clientId'],
    })
    where.id = { in: clientIds.map((c) => c.clientId) }
  }

  const clients = await prisma.client.findMany({
    where,
    orderBy: { name: 'asc' },
  })

  return NextResponse.json(clients)
}

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions)
  if (!session || session.user.role !== 'admin') {
    return NextResponse.json({ error: '無權限' }, { status: 403 })
  }

  const body = await req.json()
  const parsed = clientSchema.safeParse(body)
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 })
  }

  const client = await prisma.client.create({ data: parsed.data })
  return NextResponse.json(client)
}
