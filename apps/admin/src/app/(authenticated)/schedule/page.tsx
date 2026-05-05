'use client'

import { useEffect, useState } from 'react'
import { useSession } from 'next-auth/react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Calendar, Plus, ChevronLeft, ChevronRight } from 'lucide-react'

interface SessionRecord {
  id: string
  date: string
  room: string | null
  therapist: { id: string; name: string }
  client: { id: string; name: string }
  billingType: string | null
  counselingFormat: string | null
  hours: number | null
  totalFee: number | null
  paymentStatus: string | null
  therapistPaid: string | null
}

export default function SchedulePage() {
  const { data: session } = useSession()
  const [records, setRecords] = useState<SessionRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [therapistFilter, setTherapistFilter] = useState('')
  const [therapists, setTherapists] = useState<{ id: string; name: string }[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  useEffect(() => {
    fetch('/api/therapists')
      .then((r) => r.json())
      .then(setTherapists)
  }, [])

  useEffect(() => {
    setLoading(true)
    const params = new URLSearchParams({ page: String(page), limit: '50' })
    if (therapistFilter) params.set('therapistId', therapistFilter)
    if (dateFrom) params.set('dateFrom', dateFrom)
    if (dateTo) params.set('dateTo', dateTo)

    fetch(`/api/sessions?${params}`)
      .then((r) => r.json())
      .then((data) => {
        setRecords(data.sessions)
        setTotal(data.total)
        setLoading(false)
      })
  }, [page, therapistFilter, dateFrom, dateTo])

  const isAdmin = session?.user?.role === 'admin'
  const totalPages = Math.ceil(total / 50)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">排程表</h1>
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link href="/schedule/calendar">
              <Calendar className="h-4 w-4 mr-2" />
              月曆檢視
            </Link>
          </Button>
          {isAdmin && (
            <Button asChild>
              <Link href="/sessions/new">
                <Plus className="h-4 w-4 mr-2" />
                新增紀錄
              </Link>
            </Button>
          )}
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap gap-4">
            <div>
              <label className="text-sm font-medium mb-1 block">心理師</label>
              <select
                value={therapistFilter}
                onChange={(e) => { setTherapistFilter(e.target.value); setPage(1) }}
                className="border rounded-md px-3 py-2 text-sm min-w-[150px]"
              >
                <option value="">全部</option>
                {therapists.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">起始日期</label>
              <Input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1) }} />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">結束日期</label>
              <Input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1) }} />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">共 {total} 筆紀錄</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-muted-foreground py-8 text-center">載入中...</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>日期</TableHead>
                      <TableHead>空間</TableHead>
                      <TableHead>心理師</TableHead>
                      <TableHead>個案</TableHead>
                      <TableHead>收費形式</TableHead>
                      <TableHead>形式</TableHead>
                      <TableHead>時數</TableHead>
                      <TableHead>金額</TableHead>
                      <TableHead>收款</TableHead>
                      <TableHead>給付</TableHead>
                      {isAdmin && <TableHead>操作</TableHead>}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {records.map((r) => (
                      <TableRow key={r.id}>
                        <TableCell>{new Date(r.date).toLocaleDateString('zh-TW')}</TableCell>
                        <TableCell>{r.room || '-'}</TableCell>
                        <TableCell>{r.therapist.name}</TableCell>
                        <TableCell>{r.client.name}</TableCell>
                        <TableCell>{r.billingType || '-'}</TableCell>
                        <TableCell>{r.counselingFormat || '-'}</TableCell>
                        <TableCell>{r.hours || '-'}</TableCell>
                        <TableCell>{r.totalFee?.toLocaleString() || '-'}</TableCell>
                        <TableCell>
                          {r.paymentStatus && (
                            <Badge variant={r.paymentStatus === '已收' ? 'success' : 'warning'}>
                              {r.paymentStatus}
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell>
                          {r.therapistPaid && (
                            <Badge variant={r.therapistPaid === '已付' ? 'success' : 'warning'}>
                              {r.therapistPaid}
                            </Badge>
                          )}
                        </TableCell>
                        {isAdmin && (
                          <TableCell>
                            <Button variant="ghost" size="sm" asChild>
                              <Link href={`/sessions/${r.id}`}>編輯</Link>
                            </Button>
                          </TableCell>
                        )}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {totalPages > 1 && (
                <div className="flex items-center justify-center gap-2 mt-4">
                  <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}>
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <span className="text-sm">第 {page} / {totalPages} 頁</span>
                  <Button variant="outline" size="sm" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}>
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
