import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'
import bcrypt from 'bcryptjs'

export async function DELETE(req: NextRequest, { params }: { params: { id: string } }) {
  const session = await getServerSession(authOptions)
  if (!session || session.user.role !== 'admin') {
    return NextResponse.json({ error: '無權限' }, { status: 403 })
  }

  if (params.id === session.user.id) {
    return NextResponse.json({ error: '無法刪除自己的帳號' }, { status: 400 })
  }

  await prisma.staffUser.delete({ where: { id: params.id } })
  return NextResponse.json({ success: true })
}

export async function PATCH(req: NextRequest, { params }: { params: { id: string } }) {
  const session = await getServerSession(authOptions)
  if (!session || session.user.role !== 'admin') {
    return NextResponse.json({ error: '無權限' }, { status: 403 })
  }

  const body = await req.json()
  const data: any = {}

  if (body.name) data.name = body.name
  if (body.role) data.role = body.role
  if (body.therapistId !== undefined) data.therapistId = body.therapistId || null
  if (body.password) data.passwordHash = await bcrypt.hash(body.password, 12)

  const updated = await prisma.staffUser.update({
    where: { id: params.id },
    data,
    select: { id: true, email: true, name: true, role: true },
  })

  return NextResponse.json(updated)
}
