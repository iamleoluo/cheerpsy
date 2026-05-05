'use client'

import { useEffect, useState } from 'react'
import { useSession } from 'next-auth/react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Check, X, RefreshCw } from 'lucide-react'

interface BookingAppointment {
  id: string
  client_name: string
  client_phone: string | null
  client_email: string | null
  therapist_name: string | null
  internal_therapist_id: string | null
  requested_date: string
  requested_time_slot: string
  preferred_format: string
  status: string
  rejection_reason: string | null
  notes: string | null
  created_at: string
}

export default function BookingsPage() {
  const { data: session } = useSession()
  const [appointments, setAppointments] = useState<BookingAppointment[]>([])
  const [therapists, setTherapists] = useState<{ id: string; name: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('pending')
  const [approveModal, setApproveModal] = useState<string | null>(null)
  const [selectedTherapist, setSelectedTherapist] = useState('')
  const [rejectModal, setRejectModal] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [syncing, setSyncing] = useState(false)

  const fetchAppointments = () => {
    setLoading(true)
    fetch(`/api/bookings?status=${filter}`)
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) setAppointments(data)
        else setAppointments([])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }

  useEffect(() => {
    fetchAppointments()
    fetch('/api/therapists').then((r) => r.json()).then(setTherapists)
  }, [filter])

  const handleApprove = async () => {
    if (!approveModal || !selectedTherapist) return
    const res = await fetch(`/api/bookings/${approveModal}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ therapistId: selectedTherapist }),
    })
    if (res.ok) {
      setApproveModal(null)
      setSelectedTherapist('')
      fetchAppointments()
    }
  }

  const handleReject = async () => {
    if (!rejectModal) return
    const res = await fetch(`/api/bookings/${rejectModal}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: rejectReason }),
    })
    if (res.ok) {
      setRejectModal(null)
      setRejectReason('')
      fetchAppointments()
    }
  }

  const handleSyncProfiles = async () => {
    setSyncing(true)
    await fetch('/api/sync/profiles', { method: 'POST' })
    setSyncing(false)
    alert('心理師資料已同步至預約系統')
  }

  const statusLabels: Record<string, string> = {
    pending: '待確認', confirmed: '已確認', rejected: '已拒絕', cancelled: '已取消',
  }
  const statusVariants: Record<string, 'warning' | 'success' | 'destructive' | 'secondary'> = {
    pending: 'warning', confirmed: 'success', rejected: 'destructive', cancelled: 'secondary',
  }
  const formatLabels: Record<string, string> = { in_person: '實體', online: '視訊' }

  const isAdmin = session?.user?.role === 'admin'

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">預約管理</h1>
        {isAdmin && (
          <Button variant="outline" onClick={handleSyncProfiles} disabled={syncing}>
            <RefreshCw className={`h-4 w-4 mr-2 ${syncing ? 'animate-spin' : ''}`} />
            同步心理師至預約系統
          </Button>
        )}
      </div>

      <Card>
        <CardContent className="pt-6">
          <div className="flex gap-2 mb-4">
            {(['pending', 'confirmed', 'rejected', 'cancelled'] as const).map((s) => (
              <Button
                key={s}
                variant={filter === s ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilter(s)}
              >
                {statusLabels[s]}
              </Button>
            ))}
          </div>

          {loading ? (
            <p className="text-center text-muted-foreground py-8">載入中...</p>
          ) : appointments.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">沒有{statusLabels[filter]}的預約</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>個案</TableHead>
                  <TableHead>日期</TableHead>
                  <TableHead>時段</TableHead>
                  <TableHead>形式</TableHead>
                  <TableHead>指定心理師</TableHead>
                  <TableHead>狀態</TableHead>
                  <TableHead>備註</TableHead>
                  {filter === 'pending' && <TableHead>操作</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {appointments.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell>
                      <div>
                        <p className="font-medium">{a.client_name}</p>
                        <p className="text-xs text-muted-foreground">{a.client_phone || a.client_email || ''}</p>
                      </div>
                    </TableCell>
                    <TableCell>{new Date(a.requested_date).toLocaleDateString('zh-TW')}</TableCell>
                    <TableCell>{a.requested_time_slot}</TableCell>
                    <TableCell>{formatLabels[a.preferred_format] || a.preferred_format}</TableCell>
                    <TableCell>{a.therapist_name || '不指定'}</TableCell>
                    <TableCell>
                      <Badge variant={statusVariants[a.status]}>{statusLabels[a.status]}</Badge>
                    </TableCell>
                    <TableCell className="max-w-[150px] truncate">{a.notes || '-'}</TableCell>
                    {filter === 'pending' && (
                      <TableCell>
                        <div className="flex gap-1">
                          <Button size="sm" variant="ghost" onClick={() => { setApproveModal(a.id); setSelectedTherapist(a.internal_therapist_id || '') }}>
                            <Check className="h-4 w-4 text-green-600" />
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setRejectModal(a.id)}>
                            <X className="h-4 w-4 text-red-600" />
                          </Button>
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Approve Modal */}
      {approveModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md">
            <CardHeader><CardTitle>確認預約</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-sm font-medium mb-1 block">選擇心理師 *</label>
                <select
                  className="w-full border rounded-md px-3 py-2 text-sm"
                  value={selectedTherapist}
                  onChange={(e) => setSelectedTherapist(e.target.value)}
                >
                  <option value="">選擇心理師</option>
                  {therapists.map((t) => (<option key={t.id} value={t.id}>{t.name}</option>))}
                </select>
              </div>
              <div className="flex gap-2">
                <Button onClick={handleApprove} disabled={!selectedTherapist}>確認</Button>
                <Button variant="outline" onClick={() => setApproveModal(null)}>取消</Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Reject Modal */}
      {rejectModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md">
            <CardHeader><CardTitle>拒絕預約</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-sm font-medium mb-1 block">拒絕原因</label>
                <textarea
                  className="w-full border rounded-md px-3 py-2 text-sm min-h-[80px]"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="請說明原因（可選）"
                />
              </div>
              <div className="flex gap-2">
                <Button variant="destructive" onClick={handleReject}>拒絕</Button>
                <Button variant="outline" onClick={() => setRejectModal(null)}>取消</Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
