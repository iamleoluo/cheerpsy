import { NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'

export async function GET() {
  const therapists = await prisma.therapistProfile.findMany({
    where: { isAcceptingBookings: true },
    include: { availability: true },
    orderBy: { name: 'asc' },
  })

  return NextResponse.json(therapists)
}
