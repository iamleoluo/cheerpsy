/**
 * Approve Booking Sync Service
 *
 * Called from the admin portal when an appointment is approved.
 * Reads from Booking DB, writes to Internal DB.
 *
 * Since both DBs are on the same server and this runs in the admin portal context,
 * we use direct Prisma client access to both databases.
 */

interface ApproveBookingParams {
  appointmentId: string
  bookingPrisma: any // Booking DB Prisma client
  internalPrisma: any // Internal DB Prisma client
  therapistId: string // Internal DB therapist ID
  approvedBy: string // Staff user ID who approved
}

export async function approveBooking({
  appointmentId,
  bookingPrisma,
  internalPrisma,
  therapistId,
  approvedBy,
}: ApproveBookingParams) {
  // 1. Read appointment from Booking DB
  const appointment = await bookingPrisma.appointment.findUnique({
    where: { id: appointmentId },
    include: { clientUser: true },
  })

  if (!appointment) throw new Error('預約不存在')
  if (appointment.status !== 'pending') throw new Error('此預約已處理')

  // 2. Upsert client in Internal DB
  let client = await internalPrisma.client.findFirst({
    where: { name: appointment.clientName },
  })

  if (!client) {
    client = await internalPrisma.client.create({
      data: {
        name: appointment.clientName,
        phone: appointment.clientPhone,
        email: appointment.clientEmail,
        bookingClientUserId: appointment.clientUserId,
      },
    })
  }

  // 3. Create session in Internal DB
  const session = await internalPrisma.session.create({
    data: {
      date: appointment.requestedDate,
      therapistId,
      clientId: client.id,
      source: 'booking',
      bookingAppointmentId: appointmentId,
      counselingFormat: appointment.preferredFormat === 'online' ? '視訊' : '實體',
      counselingType: '個別',
      location: appointment.preferredFormat === 'online' ? '視訊' : '治療所',
      paymentStatus: '未收',
      therapistPaid: '未付',
    },
  })

  // 4. Update appointment status in Booking DB
  await bookingPrisma.appointment.update({
    where: { id: appointmentId },
    data: { status: 'confirmed' },
  })

  return { session, client }
}
