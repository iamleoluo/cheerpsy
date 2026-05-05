'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Input } from '@/components/ui/input'
import { Download } from 'lucide-react'

interface TherapistReport {
  therapistName: string
  byBillingType: Record<string, number>
  totalIncome: number
  tax: number
  healthInsurance: number
  netIncome: number
}

export default function TherapistReportPage() {
  const [report, setReport] = useState<TherapistReport[]>([])
  const [loading, setLoading] = useState(true)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const fetchReport = () => {
    setLoading(true)
    const params = new URLSearchParams()
    if (dateFrom) params.set('dateFrom', dateFrom)
    if (dateTo) params.set('dateTo', dateTo)

    fetch(`/api/reports/therapist?${params}`)
      .then((r) => r.json())
      .then((data) => {
        setReport(data)
        setLoading(false)
      })
  }

  useEffect(() => { fetchReport() }, [])

  // Get all unique billing types
  const allBillingTypes = [...new Set(report.flatMap((r) => Object.keys(r.byBillingType)))].sort()

  const grandTotal = report.reduce((sum, r) => sum + r.totalIncome, 0)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">薪資核發報表</h1>
        <Button variant="outline" asChild>
          <a href={`/api/export?type=sessions${dateFrom ? `&dateFrom=${dateFrom}` : ''}${dateTo ? `&dateTo=${dateTo}` : ''}`} download>
            <Download className="h-4 w-4 mr-2" />
            匯出 CSV
          </a>
        </Button>
      </div>

      <Card>
        <CardContent className="pt-6 flex gap-4 items-end">
          <div>
            <label className="text-sm font-medium mb-1 block">起始日期</label>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">結束日期</label>
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <Button onClick={fetchReport}>查詢</Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>心理師收入彙總</CardTitle>
          <CardDescription>稅率 10%，二代健保 2.11%（收入超過 $20,000 時扣除）</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-center text-muted-foreground py-8">載入中...</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>心理師</TableHead>
                    {allBillingTypes.map((bt) => (
                      <TableHead key={bt} className="text-right">{bt}</TableHead>
                    ))}
                    <TableHead className="text-right">合計</TableHead>
                    <TableHead className="text-right">稅 (10%)</TableHead>
                    <TableHead className="text-right">二代健保</TableHead>
                    <TableHead className="text-right font-bold">實發</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {report.map((r) => (
                    <TableRow key={r.therapistName}>
                      <TableCell className="font-medium">{r.therapistName}</TableCell>
                      {allBillingTypes.map((bt) => (
                        <TableCell key={bt} className="text-right">
                          {r.byBillingType[bt]?.toLocaleString() || '-'}
                        </TableCell>
                      ))}
                      <TableCell className="text-right font-medium">{r.totalIncome.toLocaleString()}</TableCell>
                      <TableCell className="text-right text-destructive">{r.tax.toLocaleString()}</TableCell>
                      <TableCell className="text-right text-destructive">
                        {r.healthInsurance > 0 ? r.healthInsurance.toLocaleString() : '-'}
                      </TableCell>
                      <TableCell className="text-right font-bold">{Math.round(r.netIncome).toLocaleString()}</TableCell>
                    </TableRow>
                  ))}
                  <TableRow className="bg-muted/50 font-bold">
                    <TableCell>總計</TableCell>
                    {allBillingTypes.map((bt) => (
                      <TableCell key={bt} className="text-right">
                        {report.reduce((sum, r) => sum + (r.byBillingType[bt] || 0), 0).toLocaleString()}
                      </TableCell>
                    ))}
                    <TableCell className="text-right">{grandTotal.toLocaleString()}</TableCell>
                    <TableCell className="text-right">{report.reduce((s, r) => s + r.tax, 0).toLocaleString()}</TableCell>
                    <TableCell className="text-right">{report.reduce((s, r) => s + r.healthInsurance, 0).toLocaleString()}</TableCell>
                    <TableCell className="text-right">{Math.round(report.reduce((s, r) => s + r.netIncome, 0)).toLocaleString()}</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
