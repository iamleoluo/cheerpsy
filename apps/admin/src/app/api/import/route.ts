import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'
import { parseExcel } from '@/lib/excel-parser'

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions)
  if (!session || session.user.role !== 'admin') {
    return NextResponse.json({ error: '無權限' }, { status: 403 })
  }

  const formData = await req.formData()
  const file = formData.get('file') as File | null
  const mode = formData.get('mode') as string || 'append' // 'replace' | 'append'

  if (!file) {
    return NextResponse.json({ error: '請上傳檔案' }, { status: 400 })
  }

  const buffer = Buffer.from(await file.arrayBuffer())

  let parsed
  try {
    parsed = await parseExcel(buffer)
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 400 })
  }

  const { rows } = parsed

  if (rows.length === 0) {
    return NextResponse.json({ error: '沒有可匯入的資料' }, { status: 400 })
  }

  // If replace mode, delete all existing imported sessions
  if (mode === 'replace') {
    await prisma.session.deleteMany({
      where: { source: 'excel_import' },
    })
  }

  // Upsert therapists
  const therapistMap = new Map<string, string>()
  const uniqueTherapists = [...new Set(rows.map((r) => r.therapistName).filter(Boolean))] as string[]

  for (const name of uniqueTherapists) {
    const therapist = await prisma.therapist.upsert({
      where: { name },
      update: {},
      create: {
        name,
        commissionRate: 0.8,
      },
    })
    therapistMap.set(name, therapist.id)
  }

  // Upsert clients
  const clientMap = new Map<string, string>()
  const uniqueClients = [...new Set(rows.map((r) => r.clientName).filter(Boolean))] as string[]

  for (const name of uniqueClients) {
    // Find or create by name
    let client = await prisma.client.findFirst({ where: { name } })
    if (!client) {
      client = await prisma.client.create({ data: { name } })
    }
    clientMap.set(name, client.id)
  }

  // Batch insert sessions
  let imported = 0
  let skipped = 0

  for (const row of rows) {
    if (!row.therapistName || !row.clientName) {
      skipped++
      continue
    }

    const therapistId = therapistMap.get(row.therapistName)
    const clientId = clientMap.get(row.clientName)

    if (!therapistId || !clientId) {
      skipped++
      continue
    }

    await prisma.session.create({
      data: {
        date: row.date || new Date(),
        room: row.room,
        therapistId,
        clientId,
        source: 'excel_import',
        billingType: row.billingType,
        amountReceivable: row.amountReceivable,
        receivableType: row.receivableType,
        location: row.location,
        paymentStatus: row.paymentStatus,
        amountReceived: row.amountReceived,
        institutionMonth: row.institutionMonth,
        counselingFormat: row.counselingFormat,
        counselingType: row.counselingType,
        hours: row.hours,
        hourlyRate: row.hourlyRate,
        totalFee: row.totalFee,
        commissionRate: row.commissionRate,
        therapistIncome: row.therapistIncome,
        clinicIncome: row.clinicIncome,
        notes: row.notes,
        therapistPaid: row.therapistPaid,
      },
    })
    imported++
  }

  // Log import
  await prisma.importLog.create({
    data: {
      filename: file.name,
      rowsImported: imported,
      importedBy: session.user.id,
    },
  })

  return NextResponse.json({
    success: true,
    imported,
    skipped,
    therapists: uniqueTherapists.length,
    clients: uniqueClients.length,
  })
}
