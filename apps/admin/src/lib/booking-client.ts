/**
 * Client for calling the Booking app's internal API.
 *
 * Tries BOOKING_INTERNAL_URL first (private network on Railway),
 * falls back to BOOKING_PUBLIC_URL if private network fails.
 * In development, uses localhost:3000.
 */

const PRIVATE_URL = process.env.BOOKING_INTERNAL_URL || ''
const PUBLIC_URL = process.env.BOOKING_PUBLIC_URL || ''
const DEV_URL = 'http://localhost:3000'

function getBaseUrls(): string[] {
  if (process.env.NODE_ENV !== 'production') return [DEV_URL]
  const urls: string[] = []
  if (PRIVATE_URL) urls.push(PRIVATE_URL)
  if (PUBLIC_URL) urls.push(PUBLIC_URL)
  return urls.length > 0 ? urls : [DEV_URL]
}

async function call<T>(action: string, data?: unknown): Promise<T> {
  const urls = getBaseUrls()
  let lastError: Error | null = null

  for (const base of urls) {
    try {
      const res = await fetch(`${base}/api/internal`, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'x-internal-secret': process.env.INTERNAL_API_SECRET || '',
        },
        body: JSON.stringify({ action, data }),
        cache: 'no-store',
        signal: AbortSignal.timeout(5000),
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(`Booking API ${action} failed (${res.status}): ${text}`)
      }
      return res.json() as Promise<T>
    } catch (e: any) {
      lastError = e
      // If private URL failed, try next (public) URL
      continue
    }
  }

  throw lastError || new Error(`Booking API ${action} failed: no URLs configured`)
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
