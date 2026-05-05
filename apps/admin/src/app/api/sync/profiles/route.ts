import { NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'
import { syncTherapistToBookingDb } from '@/lib/booking-prisma'

export async function POST() {
  const session = await getServerSession(authOptions)
  if (!session || session.user.role !== 'admin') {
    return NextResponse.json({ error: '無權限' }, { status: 403 })
  }

  try {
    const therapists = await prisma.therapist.findMany({
      where: { isActive: true },
    })

    let synced = 0
    for (const t of therapists) {
      syncTherapistToBookingDb({
        id: t.id,
        name: t.name,
        bio: t.bio,
        specialties: t.specialties,
        isActive: t.isActive,
      })
      synced++
    }

    return NextResponse.json({ success: true, synced })
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
