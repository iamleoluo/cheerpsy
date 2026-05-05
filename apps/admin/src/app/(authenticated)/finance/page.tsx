'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { DollarSign, Download } from 'lucide-react'

interface FinanceSession {
  id: string
  date: string
  therapist: { name: string }
  client: { name: string }
  billingType: string | null
  amountReceivable: number | null
  amountReceived: number | null
  paymentStatus: string | null
  therapistIncome: number | null
  therapistPaid: string | null
}

export default function FinancePage() {
  const [sessions, setSessions] = useState<FinanceSession[]>([])
  const [summary, setSummary] = useState<any>(null)
  const [filter, setFilter] = useState('all')
  const [therapists, setTherapists] = useState<{ id: string; name: string }[]>([])
  const [therapistFilter, setTherapistFilter] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/therapists').then((r) => r.json()).then(setTherapists)
  }, [])

  useEffect(() => {
    setLoading(true)
    const params = new URLSearchParams({ filter })
    if (therapistFilter) params.set('therapistId', therapistFilter)

    fetch(`/api/finance?${params}`)
      .then((r) => r.json())
      .then((data) => {
        setSessions(data.sessions)
        setSummary(data.summary)
        setSelected(new Set())
        setLoading(false)
      })
  }, [filter, therapistFilter])

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const selectAll = () => {
    if (selected.size === sessions.length) setSelected(new Set())
    else setSelected(new Set(sessions.map((s) => s.id)))
  }

  const batchUpdate = async (field: string, value: string) => {
    if (selected.size === 0) return
    await fetch('/api/finance', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionIds: [...selected], field, value }),
    })
    // Refresh
    const params = new URLSearchParams({ filter })
    if (therapistFilter) params.set('therapistId', therapistFilter)
    const data = await fetch(`/api/finance?${params}`).then((r) => r.json())
    setSessions(data.sessions)
    setSummary(data.summary)
    setSelected(new Set())
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">收款管理</h1>
        <Button variant="outline" asChild>
          <a href="/api/export?type=sessions" download>
            <Download className="h-4 w-4 mr-2" />
            匯出 CSV
          </a>
        </Button>
      </div>

      {/* Summary */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">總應收</p>
              <p className="text-2xl font-bold">${summary.totalReceivable?.toLocaleString()}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">總實收</p>
              <p className="text-2xl font-bold">${summary.totalReceived?.toLocaleString()}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">未收款</p>
              <p className="text-2xl font-bold text-yellow-600">{summary.unpaidToClient} 筆</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">未付心理師</p>
              <p className="text-2xl font-bold text-yellow-600">{summary.unpaidToTherapist} 筆</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <Card>
        <CardContent className="pt-6 flex flex-wrap gap-4 items-end">
          <div>
            <label className="text-sm font-medium mb-1 block">篩選</label>
            <select className="border rounded-md px-3 py-2 text-sm" value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="all">全部</option>
              <option value="unpaid_clients">未收款</option>
              <option value="unpaid_therapists">未付心理師</option>
            </select>
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">心理師</label>
            <select className="border rounded-md px-3 py-2 text-sm" value={therapistFilter} onChange={(e) => setTherapistFilter(e.target.value)}>
              <option value="">全部</option>
              {therapists.map((t) => (<option key={t.id} value={t.id}>{t.name}</option>))}
            </select>
          </div>
          {selected.size > 0 && (
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => batchUpdate('paymentStatus', '已收')}>
                標記已收 ({selected.size})
              </Button>
              <Button size="sm" variant="outline" onClick={() => batchUpdate('therapistPaid', '已付')}>
                標記已付 ({selected.size})
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardContent className="pt-6">
          {loading ? (
            <p className="text-center text-muted-foreground py-8">載入中...</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>
                    <input type="checkbox" checked={selected.size === sessions.length && sessions.length > 0} onChange={selectAll} />
                  </TableHead>
                  <TableHead>日期</TableHead>
                  <TableHead>心理師</TableHead>
                  <TableHead>個案</TableHead>
                  <TableHead>收費形式</TableHead>
                  <TableHead>應收</TableHead>
                  <TableHead>實收</TableHead>
                  <TableHead>收款</TableHead>
                  <TableHead>心理師收入</TableHead>
                  <TableHead>給付</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sessions.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell>
                      <input type="checkbox" checked={selected.has(s.id)} onChange={() => toggleSelect(s.id)} />
                    </TableCell>
                    <TableCell>{new Date(s.date).toLocaleDateString('zh-TW')}</TableCell>
                    <TableCell>{s.therapist.name}</TableCell>
                    <TableCell>{s.client.name}</TableCell>
                    <TableCell>{s.billingType || '-'}</TableCell>
                    <TableCell>{s.amountReceivable?.toLocaleString() || '-'}</TableCell>
                    <TableCell>{s.amountReceived?.toLocaleString() || '-'}</TableCell>
                    <TableCell>
                      <Badge variant={s.paymentStatus === '已收' ? 'success' : 'warning'}>
                        {s.paymentStatus || '-'}
                      </Badge>
                    </TableCell>
                    <TableCell>{s.therapistIncome?.toLocaleString() || '-'}</TableCell>
                    <TableCell>
                      <Badge variant={s.therapistPaid === '已付' ? 'success' : 'warning'}>
                        {s.therapistPaid || '-'}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
