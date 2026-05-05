import { NextRequest, NextResponse } from 'next/server'
import { timingSafeEqual } from 'crypto'
import { prisma } from '@/lib/prisma'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function verifySecret(req: NextRequest): boolean {
  const expected = process.env.INTERNAL_API_SECRET
  if (!expected) return false
  const got = req.headers.get('x-internal-secret') ?? ''
  if (got.length !== expected.length) return false
  try {
    return timingSafeEqual(Buffer.from(got), Buffer.from(expected))
  } catch {
    return false
  }
}

export async function POST(req: NextRequest) {
  if (!verifySecret(req)) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
  }

  const { action, data } = await req.json()

  switch (action) {
    case 'appointments.list': {
      const where: any = {}
      if (data?.status) where.status = data.status
      const appointments = await prisma.appointment.findMany({
        where,
        include: {
          therapistProfile: { select: { name: true, internalTherapistId: true } },
        },
        orderBy: { createdAt: 'desc' },
      })
      return NextResponse.json(
        appointments.map((a) => ({
          id: a.id,
          client_user_id: a.clientUserId,
          therapist_profile_id: a.therapistProfileId,
          requested_date: a.requestedDate,
          requested_time_slot: a.requestedTimeSlot,
          preferred_format: a.preferredFormat,
          client_name: a.clientName,
          client_phone: a.clientPhone,
          client_email: a.clientEmail,
          status: a.status,
          rejection_reason: a.rejectionReason,
          notes: a.notes,
          created_at: a.createdAt,
          updated_at: a.updatedAt,
          therapist_name: a.therapistProfile?.name ?? null,
          internal_therapist_id: a.therapistProfile?.internalTherapistId ?? null,
        }))
      )
    }

    case 'appointments.get': {
      const appointment = await prisma.appointment.findUnique({
        where: { id: data.id },
        include: {
          therapistProfile: { select: { name: true, internalTherapistId: true } },
        },
      })
      if (!appointment) return NextResponse.json(null)
      return NextResponse.json({
        id: appointment.id,
        client_user_id: appointment.clientUserId,
        therapist_profile_id: appointment.therapistProfileId,
        requested_date: appointment.requestedDate,
        requested_time_slot: appointment.requestedTimeSlot,
        preferred_format: appointment.preferredFormat,
        client_name: appointment.clientName,
        client_phone: appointment.clientPhone,
        client_email: appointment.clientEmail,
        status: appointment.status,
        rejection_reason: appointment.rejectionReason,
        notes: appointment.notes,
        created_at: appointment.createdAt,
        updated_at: appointment.updatedAt,
        therapist_name: appointment.therapistProfile?.name ?? null,
        internal_therapist_id: appointment.therapistProfile?.internalTherapistId ?? null,
      })
    }

    case 'appointments.updateStatus': {
      await prisma.appointment.update({
        where: { id: data.id },
        data: {
          status: data.status,
          rejectionReason: data.rejectionReason ?? null,
        },
      })
      return NextResponse.json({ success: true })
    }

    case 'therapists.sync': {
      const { internalId, name, bio, specialties, isActive } = data
      const result = await prisma.therapistProfile.upsert({
        where: { internalTherapistId: internalId },
        update: {
          name,
          bio,
          specialties,
          isAcceptingBookings: isActive,
        },
        create: {
          name,
          bio,
          specialties,
          isAcceptingBookings: isActive,
          internalTherapistId: internalId,
        },
      })
      return NextResponse.json({ id: result.id })
    }

    default:
      return NextResponse.json({ error: 'unknown action' }, { status: 404 })
  }
}
