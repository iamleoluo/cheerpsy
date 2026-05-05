/**
 * Sync Therapist Profiles from Internal DB to Booking DB
 *
 * Copies public-safe therapist data to the booking portal.
 */

interface SyncProfilesParams {
  internalPrisma: any
  bookingPrisma: any
}

export async function syncTherapistProfiles({
  internalPrisma,
  bookingPrisma,
}: SyncProfilesParams) {
  // Get all active therapists from Internal DB
  const therapists = await internalPrisma.therapist.findMany({
    where: { isActive: true },
    include: { availability: true },
  })

  let synced = 0

  for (const therapist of therapists) {
    // Upsert therapist profile in Booking DB
    const profile = await bookingPrisma.therapistProfile.upsert({
      where: { internalTherapistId: therapist.id },
      update: {
        name: therapist.name,
        bio: therapist.bio,
        specialties: therapist.specialties,
        isAcceptingBookings: therapist.isActive,
      },
      create: {
        name: therapist.name,
        bio: therapist.bio,
        specialties: therapist.specialties,
        isAcceptingBookings: therapist.isActive,
        internalTherapistId: therapist.id,
      },
    })

    // Sync availability - delete old and recreate
    await bookingPrisma.therapistAvailability.deleteMany({
      where: { therapistProfileId: profile.id },
    })

    for (const avail of therapist.availability) {
      await bookingPrisma.therapistAvailability.create({
        data: {
          therapistProfileId: profile.id,
          dayOfWeek: avail.dayOfWeek,
          startTime: avail.startTime,
          endTime: avail.endTime,
          isRecurring: avail.isRecurring,
          effectiveFrom: avail.effectiveFrom,
          effectiveUntil: avail.effectiveUntil,
        },
      })
    }

    synced++
  }

  // Deactivate profiles for inactive/deleted therapists
  const activeIds = therapists.map((t: any) => t.id)
  await bookingPrisma.therapistProfile.updateMany({
    where: {
      internalTherapistId: { notIn: activeIds },
      isAcceptingBookings: true,
    },
    data: { isAcceptingBookings: false },
  })

  return { synced }
}
