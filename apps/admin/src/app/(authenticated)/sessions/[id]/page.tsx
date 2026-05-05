'use client'

import { useEffect, useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function EditSessionPage() {
  const router = useRouter()
  const params = useParams()
  const id = params.id as string
  const [therapists, setTherapists] = useState<{ id: string; name: string }[]>([])
  const [clients, setClients] = useState<{ id: string; name: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const [form, setForm] = useState({
    date: '', room: '', therapistId: '', clientId: '',
    billingType: '', amountReceivable: '', receivableType: '',
    location: '', paymentStatus: '', amountReceived: '',
    institutionMonth: '', counselingFormat: '', counselingType: '',
    hours: '', hourlyRate: '', totalFee: '', commissionRate: '',
    therapistIncome: '', clinicIncome: '', notes: '', therapistPaid: '',
  })

  useEffect(() => {
    Promise.all([
      fetch('/api/therapists').then((r) => r.json()),
      fetch('/api/clients').then((r) => r.json()),
      fetch(`/api/sessions/${id}`).then((r) => r.json()),
    ]).then(([t, c, s]) => {
      setTherapists(t)
      setClients(c)
      setForm({
        date: s.date ? new Date(s.date).toISOString().split('T')[0] : '',
        room: s.room || '',
        therapistId: s.therapistId || '',
        clientId: s.clientId || '',
        billingType: s.billingType || '',
        amountReceivable: s.amountReceivable?.toString() || '',
        receivableType: s.receivableType || '',
        location: s.location || '',
        paymentStatus: s.paymentStatus || '',
        amountReceived: s.amountReceived?.toString() || '',
        institutionMonth: s.institutionMonth || '',
        counselingFormat: s.counselingFormat || '',
        counselingType: s.counselingType || '',
        hours: s.hours?.toString() || '',
        hourlyRate: s.hourlyRate?.toString() || '',
        totalFee: s.totalFee?.toString() || '',
        commissionRate: s.commissionRate?.toString() || '',
        therapistIncome: s.therapistIncome?.toString() || '',
        clinicIncome: s.clinicIncome?.toString() || '',
        notes: s.notes || '',
        therapistPaid: s.therapistPaid || '',
      })
      setLoading(false)
    })
  }, [id])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')

    const res = await fetch(`/api/sessions/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })

    if (res.ok) {
      router.push('/schedule')
    } else {
      const data = await res.json()
      setError(data.error || '儲存失敗')
    }
    setSaving(false)
  }

  const handleDelete = async () => {
    if (!confirm('確定刪除此紀錄？')) return
    const res = await fetch(`/api/sessions/${id}`, { method: 'DELETE' })
    if (res.ok) router.push('/schedule')
  }

  const update = (key: string, value: string) => setForm((f) => ({ ...f, [key]: value }))

  if (loading) return <p className="text-muted-foreground">載入中...</p>

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">編輯諮商紀錄</h1>

      <form onSubmit={handleSubmit}>
        <Card className="mb-6">
          <CardHeader><CardTitle className="text-lg">基本資料</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label>日期</Label>
              <Input type="date" value={form.date} onChange={(e) => update('date', e.target.value)} required />
            </div>
            <div>
              <Label>空間</Label>
              <Input value={form.room} onChange={(e) => update('room', e.target.value)} />
            </div>
            <div>
              <Label>心理師</Label>
              <select className="w-full border rounded-md px-3 py-2 text-sm" value={form.therapistId} onChange={(e) => update('therapistId', e.target.value)} required>
                <option value="">選擇心理師</option>
                {therapists.map((t) => (<option key={t.id} value={t.id}>{t.name}</option>))}
              </select>
            </div>
            <div>
              <Label>個案</Label>
              <select className="w-full border rounded-md px-3 py-2 text-sm" value={form.clientId} onChange={(e) => update('clientId', e.target.value)} required>
                <option value="">選擇個案</option>
                {clients.map((c) => (<option key={c.id} value={c.id}>{c.name}</option>))}
              </select>
            </div>
          </CardContent>
        </Card>

        <Card className="mb-6">
          <CardHeader><CardTitle className="text-lg">諮商 & 財務</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div><Label>收費形式</Label><Input value={form.billingType} onChange={(e) => update('billingType', e.target.value)} /></div>
            <div><Label>諮商地點</Label><Input value={form.location} onChange={(e) => update('location', e.target.value)} /></div>
            <div><Label>諮商形式</Label><Input value={form.counselingFormat} onChange={(e) => update('counselingFormat', e.target.value)} /></div>
            <div><Label>諮商種類</Label><Input value={form.counselingType} onChange={(e) => update('counselingType', e.target.value)} /></div>
            <div><Label>時數</Label><Input type="number" step="0.5" value={form.hours} onChange={(e) => update('hours', e.target.value)} /></div>
            <div><Label>鐘點</Label><Input type="number" value={form.hourlyRate} onChange={(e) => update('hourlyRate', e.target.value)} /></div>
            <div><Label>應收金額</Label><Input type="number" value={form.amountReceivable} onChange={(e) => update('amountReceivable', e.target.value)} /></div>
            <div><Label>應收類型</Label><Input value={form.receivableType} onChange={(e) => update('receivableType', e.target.value)} /></div>
            <div><Label>收款狀況</Label><Input value={form.paymentStatus} onChange={(e) => update('paymentStatus', e.target.value)} /></div>
            <div><Label>當日實收</Label><Input type="number" value={form.amountReceived} onChange={(e) => update('amountReceived', e.target.value)} /></div>
            <div><Label>機構核銷月份</Label><Input value={form.institutionMonth} onChange={(e) => update('institutionMonth', e.target.value)} /></div>
            <div><Label>抽成</Label><Input type="number" step="0.1" value={form.commissionRate} onChange={(e) => update('commissionRate', e.target.value)} /></div>
            <div><Label>應收（計算）</Label><Input type="number" value={form.totalFee} onChange={(e) => update('totalFee', e.target.value)} /></div>
            <div><Label>心理師收入</Label><Input type="number" value={form.therapistIncome} onChange={(e) => update('therapistIncome', e.target.value)} /></div>
            <div><Label>治療所收入</Label><Input type="number" value={form.clinicIncome} onChange={(e) => update('clinicIncome', e.target.value)} /></div>
            <div><Label>給付治療師</Label><Input value={form.therapistPaid} onChange={(e) => update('therapistPaid', e.target.value)} /></div>
            <div className="md:col-span-2"><Label>備註</Label><Input value={form.notes} onChange={(e) => update('notes', e.target.value)} /></div>
          </CardContent>
        </Card>

        {error && <p className="text-destructive text-sm mb-4">{error}</p>}

        <div className="flex gap-4">
          <Button type="submit" disabled={saving}>{saving ? '儲存中...' : '更新'}</Button>
          <Button type="button" variant="outline" onClick={() => router.back()}>取消</Button>
          <Button type="button" variant="destructive" onClick={handleDelete}>刪除</Button>
        </div>
      </form>
    </div>
  )
}
