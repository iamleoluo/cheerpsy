'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Input } from '@/components/ui/input'
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend,
} from '@/components/charts'

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316']

interface BillingReport {
  selfPay: { count: number; total: number }
  institution: { count: number; total: number }
  byType: { type: string; count: number; therapistIncome: number; clinicIncome: number; totalFee: number }[]
  byTherapistType: { therapist: string; types: Record<string, number>; total: number }[]
}

export default function BillingReportPage() {
  const [report, setReport] = useState<BillingReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const fetchReport = () => {
    setLoading(true)
    const params = new URLSearchParams()
    if (dateFrom) params.set('dateFrom', dateFrom)
    if (dateTo) params.set('dateTo', dateTo)

    fetch(`/api/reports/billing?${params}`)
      .then((r) => r.json())
      .then((data) => {
        setReport(data)
        setLoading(false)
      })
  }

  useEffect(() => { fetchReport() }, [])

  const pieData = report ? [
    { name: '自費', value: report.selfPay.total },
    { name: '機構', value: report.institution.total },
  ] : []

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">收費分析（自費 vs 機構）</h1>

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

      {loading ? (
        <p className="text-center text-muted-foreground py-8">載入中...</p>
      ) : report && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground">自費</p>
                <p className="text-2xl font-bold">${report.selfPay.total.toLocaleString()}</p>
                <p className="text-sm text-muted-foreground">{report.selfPay.count} 場次</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground">機構</p>
                <p className="text-2xl font-bold">${report.institution.total.toLocaleString()}</p>
                <p className="text-sm text-muted-foreground">{report.institution.count} 場次</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                      <Cell fill="#3b82f6" />
                      <Cell fill="#10b981" />
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>

          {/* By billing type */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">各收費形式明細</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>收費形式</TableHead>
                    <TableHead className="text-right">場次</TableHead>
                    <TableHead className="text-right">總金額</TableHead>
                    <TableHead className="text-right">心理師收入</TableHead>
                    <TableHead className="text-right">治療所收入</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {report.byType.map((bt) => (
                    <TableRow key={bt.type}>
                      <TableCell className="font-medium">{bt.type}</TableCell>
                      <TableCell className="text-right">{bt.count}</TableCell>
                      <TableCell className="text-right">{bt.totalFee.toLocaleString()}</TableCell>
                      <TableCell className="text-right">{bt.therapistIncome.toLocaleString()}</TableCell>
                      <TableCell className="text-right">{bt.clinicIncome.toLocaleString()}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* By therapist */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">各心理師收費形式分佈</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>心理師</TableHead>
                    {report.byType.map((bt) => (
                      <TableHead key={bt.type} className="text-right">{bt.type}</TableHead>
                    ))}
                    <TableHead className="text-right font-bold">合計</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {report.byTherapistType.map((t) => (
                    <TableRow key={t.therapist}>
                      <TableCell className="font-medium">{t.therapist}</TableCell>
                      {report.byType.map((bt) => (
                        <TableCell key={bt.type} className="text-right">
                          {t.types[bt.type]?.toLocaleString() || '-'}
                        </TableCell>
                      ))}
                      <TableCell className="text-right font-bold">{t.total.toLocaleString()}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
