import ExcelJS from 'exceljs'
import { EXCEL_COLUMN_MAP } from 'shared'

export interface ParsedRow {
  date: Date | null
  room: string | null
  therapistName: string | null
  billingType: string | null
  amountReceivable: number | null
  receivableType: string | null
  location: string | null
  paymentStatus: string | null
  amountReceived: number | null
  institutionMonth: string | null
  clientName: string | null
  counselingFormat: string | null
  counselingType: string | null
  hours: number | null
  hourlyRate: number | null
  totalFee: number | null
  commissionRate: number | null
  therapistIncome: number | null
  clinicIncome: number | null
  notes: string | null
  therapistPaid: string | null
  rowNumber: number
}

function getCellValue(row: ExcelJS.Row, col: number): any {
  const cell = row.getCell(col)
  if (cell.value === null || cell.value === undefined) return null
  // Handle formula results
  if (typeof cell.value === 'object' && 'result' in cell.value) {
    return cell.value.result
  }
  return cell.value
}

function toNumber(val: any): number | null {
  if (val === null || val === undefined || val === '') return null
  const n = Number(val)
  return isNaN(n) ? null : n
}

function toStr(val: any): string | null {
  if (val === null || val === undefined) return null
  return String(val).trim() || null
}

function toDate(val: any): Date | null {
  if (val === null || val === undefined) return null
  if (val instanceof Date) return val
  if (typeof val === 'number') {
    // Excel serial date number
    const epoch = new Date(1899, 11, 30)
    const date = new Date(epoch.getTime() + val * 86400000)
    return date
  }
  const d = new Date(val)
  return isNaN(d.getTime()) ? null : d
}

export async function parseExcel(buffer: Buffer): Promise<{
  rows: ParsedRow[]
  sheetName: string
}> {
  const workbook = new ExcelJS.Workbook()
  await workbook.xlsx.load(buffer as any)

  const sheet = workbook.getWorksheet('raw')
  if (!sheet) {
    throw new Error('找不到 "raw" 工作表')
  }

  const rows: ParsedRow[] = []
  const m = EXCEL_COLUMN_MAP

  sheet.eachRow((row, rowNumber) => {
    if (rowNumber <= 1) return // skip header

    const therapistName = toStr(getCellValue(row, m.therapist))
    const clientName = toStr(getCellValue(row, m.clientName))

    // Skip empty rows
    if (!therapistName && !clientName) return

    const date = toDate(getCellValue(row, m.date))

    rows.push({
      date,
      room: toStr(getCellValue(row, m.room)),
      therapistName,
      billingType: toStr(getCellValue(row, m.billingType)),
      amountReceivable: toNumber(getCellValue(row, m.amountReceivable)),
      receivableType: toStr(getCellValue(row, m.receivableType)),
      location: toStr(getCellValue(row, m.location)),
      paymentStatus: toStr(getCellValue(row, m.paymentStatus)),
      amountReceived: toNumber(getCellValue(row, m.amountReceived)),
      institutionMonth: toStr(getCellValue(row, m.institutionMonth)),
      clientName,
      counselingFormat: toStr(getCellValue(row, m.counselingFormat)),
      counselingType: toStr(getCellValue(row, m.counselingType)),
      hours: toNumber(getCellValue(row, m.hours)),
      hourlyRate: toNumber(getCellValue(row, m.hourlyRate)),
      totalFee: toNumber(getCellValue(row, m.totalFee)),
      commissionRate: toNumber(getCellValue(row, m.commissionRate)),
      therapistIncome: toNumber(getCellValue(row, m.therapistIncome)),
      clinicIncome: toNumber(getCellValue(row, m.clinicIncome)),
      notes: toStr(getCellValue(row, m.notes)),
      therapistPaid: toStr(getCellValue(row, m.therapistPaid)),
      rowNumber,
    })
  })

  return { rows, sheetName: sheet.name }
}
