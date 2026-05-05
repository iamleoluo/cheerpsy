import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { parseExcel } from '@/lib/excel-parser'

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions)
  if (!session || session.user.role !== 'admin') {
    return NextResponse.json({ error: '無權限' }, { status: 403 })
  }

  const formData = await req.formData()
  const file = formData.get('file') as File | null

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

  const { rows, sheetName } = parsed

  const uniqueTherapists = [...new Set(rows.map((r) => r.therapistName).filter(Boolean))]
  const uniqueClients = [...new Set(rows.map((r) => r.clientName).filter(Boolean))]

  // Return preview with first 20 rows
  return NextResponse.json({
    sheetName,
    totalRows: rows.length,
    therapistCount: uniqueTherapists.length,
    clientCount: uniqueClients.length,
    therapists: uniqueTherapists,
    preview: rows.slice(0, 20).map((r) => ({
      rowNumber: r.rowNumber,
      date: r.date?.toISOString().split('T')[0] || '',
      therapist: r.therapistName || '',
      client: r.clientName || '',
      billingType: r.billingType || '',
      hours: r.hours,
      totalFee: r.totalFee,
      paymentStatus: r.paymentStatus || '',
    })),
  })
}
