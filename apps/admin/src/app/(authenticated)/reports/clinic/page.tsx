'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Download } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from '@/components/charts'

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316']

interface ClinicReport {
  totalRevenue: number
  totalClinicIncome: number
  totalTherapistIncome: number
  totalSessions: number
  byTherapist: { name: string; income: number }[]
  byBillingType: { type: string; amount: number }[]
  trend: { date: string; revenue: number; clinicIncome: number; sessions: number }[]
}

export default function ClinicReportPage() {
  const [report, setReport] = useState<ClinicReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const fetchReport = () => {
    setLoading(true)
    const params = new URLSearchParams()
    if (dateFrom) params.set('dateFrom', dateFrom)
    if (dateTo) params.set('dateTo', dateTo)

    fetch(`/api/reports/clinic?${params}`)
      .then((r) => r.json())
      .then((data) => {
        setReport(data)
        setLoading(false)
      })
  }

  useEffect(() => { fetchReport() }, [])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">治療所收入報表</h1>
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

      {loading ? (
        <p className="text-center text-muted-foreground py-8">載入中...</p>
      ) : report && (
        <>
          {/* KPI cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground">總營收</p>
                <p className="text-2xl font-bold">${report.totalRevenue.toLocaleString()}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground">治療所收入</p>
                <p className="text-2xl font-bold">${report.totalClinicIncome.toLocaleString()}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground">心理師費用</p>
                <p className="text-2xl font-bold">${report.totalTherapistIncome.toLocaleString()}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground">總場次</p>
                <p className="text-2xl font-bold">{report.totalSessions}</p>
              </CardContent>
            </Card>
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader><CardTitle className="text-base">治療所收入（依心理師）</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={report.byTherapist}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" fontSize={12} />
                    <YAxis fontSize={12} />
                    <Tooltip />
                    <Bar dataKey="income" fill="#3b82f6" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-base">營收分佈（依收費形式）</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie data={report.byBillingType} dataKey="amount" nameKey="type" cx="50%" cy="50%" outerRadius={100} label={({ type, percent }) => `${type} ${(percent * 100).toFixed(0)}%`}>
                      {report.byBillingType.map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>

          {/* Trend */}
          <Card>
            <CardHeader><CardTitle className="text-base">每日營收趨勢</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={report.trend}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" fontSize={10} />
                  <YAxis fontSize={12} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="revenue" name="營收" fill="#3b82f6" />
                  <Bar dataKey="clinicIncome" name="治療所收入" fill="#10b981" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
