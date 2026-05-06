/**
 * Client for calling the Booking app's internal API.
 *
 * In production (Railway), uses private network: booking.railway.internal
 * In development, uses localhost:3000
 */

const BASE =
  process.env.BOOKING_INTERNAL_URL ||
  (process.env.NODE_ENV === 'production'
    ? 'http://booking.railway.internal:8080'
    : 'http://localhost:3000')

async function call<T>(action: string, data?: unknown): Promise<T> {
  const res = await fetch(`${BASE}/api/internal`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-internal-secret': process.env.INTERNAL_API_SECRET || '',
    },
    body: JSON.stringify({ action, data }),
    cache: 'no-store',
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Booking API ${action} failed (${res.status}): ${text}`)
  }
  return res.json() as Promise<T>
}

export function getAllAppointments(status?: string) {
  return call<any[]>('appointments.list', { status })
}

export function getAppointmentById(id: string) {
  return call<any | null>('appointments.get', { id })
}

export function updateAppointmentStatus(
  id: string,
  status: string,
  rejectionReason?: string
) {
  return call<{ success: boolean }>('appointments.updateStatus', {
    id,
    status,
    rejectionReason,
  })
}

export function syncTherapistToBookingDb(therapist: {
  id: string
  name: string
  bio: string | null
  specialties: string | null
  isActive: boolean
}) {
  return call<{ id: string }>('therapists.sync', {
    internalId: therapist.id,
    name: therapist.name,
    bio: therapist.bio,
    specialties: therapist.specialties,
    isActive: therapist.isActive,
  })
}
