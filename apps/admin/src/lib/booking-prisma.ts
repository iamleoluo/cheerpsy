/**
 * Cross-database access to the Booking DB from the Admin portal.
 *
 * Since both apps share the same server and filesystem, we directly
 * instantiate a second Prisma client pointing to the booking database.
 *
 * We reuse the same Prisma schema types by generating a second client
 * or by using raw SQL. For simplicity, we use raw SQL via the internal
 * Prisma's $queryRawUnsafe with ATTACH DATABASE, or we use a dedicated
 * SQLite library.
 *
 * Approach: Use a lightweight wrapper that reads/writes the booking.db directly.
 */

import Database from 'better-sqlite3'
import path from 'path'

function getBookingDb() {
  const dbPath = path.resolve(process.cwd(), '../booking/prisma/booking.db')
  return new Database(dbPath)
}

export function getPendingAppointments() {
  const db = getBookingDb()
  try {
    const rows = db.prepare(`
      SELECT
        a.id, a.client_user_id, a.therapist_profile_id,
        a.requested_date, a.requested_time_slot, a.preferred_format,
        a.client_name, a.client_phone, a.client_email,
        a.status, a.rejection_reason, a.notes,
        a.created_at, a.updated_at,
        tp.name as therapist_name
      FROM appointments a
      LEFT JOIN therapist_profiles tp ON a.therapist_profile_id = tp.id
      WHERE a.status = 'pending'
      ORDER BY a.created_at DESC
    `).all()
    return rows
  } finally {
    db.close()
  }
}

export function getAllAppointments(status?: string) {
  const db = getBookingDb()
  try {
    let sql = `
      SELECT
        a.id, a.client_user_id, a.therapist_profile_id,
        a.requested_date, a.requested_time_slot, a.preferred_format,
        a.client_name, a.client_phone, a.client_email,
        a.status, a.rejection_reason, a.notes,
        a.created_at, a.updated_at,
        tp.name as therapist_name, tp.internal_therapist_id
      FROM appointments a
      LEFT JOIN therapist_profiles tp ON a.therapist_profile_id = tp.id
    `
    if (status) sql += ` WHERE a.status = ?`
    sql += ` ORDER BY a.created_at DESC`

    const rows = status
      ? db.prepare(sql).all(status)
      : db.prepare(sql).all()
    return rows
  } finally {
    db.close()
  }
}

export function getAppointmentById(id: string) {
  const db = getBookingDb()
  try {
    return db.prepare(`
      SELECT
        a.*, tp.name as therapist_name, tp.internal_therapist_id
      FROM appointments a
      LEFT JOIN therapist_profiles tp ON a.therapist_profile_id = tp.id
      WHERE a.id = ?
    `).get(id)
  } finally {
    db.close()
  }
}

export function updateAppointmentStatus(id: string, status: string, rejectionReason?: string) {
  const db = getBookingDb()
  try {
    db.prepare(`
      UPDATE appointments SET status = ?, rejection_reason = ?, updated_at = datetime('now')
      WHERE id = ?
    `).run(status, rejectionReason || null, id)
  } finally {
    db.close()
  }
}

export function syncTherapistToBookingDb(therapist: {
  id: string
  name: string
  bio: string | null
  specialties: string | null
  isActive: boolean
}) {
  const db = getBookingDb()
  try {
    const existing = db.prepare(
      'SELECT id FROM therapist_profiles WHERE internal_therapist_id = ?'
    ).get(therapist.id) as { id: string } | undefined

    if (existing) {
      db.prepare(`
        UPDATE therapist_profiles
        SET name = ?, bio = ?, specialties = ?, is_accepting_bookings = ?, updated_at = datetime('now')
        WHERE internal_therapist_id = ?
      `).run(therapist.name, therapist.bio, therapist.specialties, therapist.isActive ? 1 : 0, therapist.id)
      return existing.id
    } else {
      const id = generateCuid()
      db.prepare(`
        INSERT INTO therapist_profiles (id, name, bio, specialties, is_accepting_bookings, internal_therapist_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
      `).run(id, therapist.name, therapist.bio, therapist.specialties, therapist.isActive ? 1 : 0, therapist.id)
      return id
    }
  } finally {
    db.close()
  }
}

function generateCuid(): string {
  // Simple unique ID generator
  const timestamp = Date.now().toString(36)
  const random = Math.random().toString(36).substring(2, 10)
  return `c${timestamp}${random}`
}
