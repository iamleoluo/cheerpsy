'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function NewSessionPage() {
  const router = useRouter()
  const [therapists, setTherapists] = useState<{ id: string; name: string }[]>([])
  const [clients, setClients] = useState<{ id: string; name: string }[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [form, setForm] = useState({
    date: new Date().toISOString().split('T')[0],
    room: '',
    therapistId: '',
    clientId: '',
    billingType: '自費',
    amountReceivable: '',
    receivableType: '',
    location: '治療所',
    paymentStatus: '未收',
    amountReceived: '',
    institutionMonth: '',
    counselingFormat: '實體',
    counselingType: '個別',
    hours: '1',
    hourlyRate: '',
    totalFee: '',
    commissionRate: '0.8',
    therapistIncome: '',
    clinicIncome: '',
    notes: '',
    therapistPaid: '未付',
  })

  useEffect(() => {
    Promise.all([
      fetch('/api/therapists').then((r) => r.json()),
      fetch('/api/clients').then((r) => r.json()),
    ]).then(([t, c]) => {
      setTherapists(t)
      setClients(c)
    })
  }, [])

  // Auto-calculate
  useEffect(() => {
    const hours = parseFloat(form.hours) || 0
    const rate = parseFloat(form.hourlyRate) || 0
    const commission = parseFloat(form.commissionRate) || 0
    const total = hours * rate
    const therapistIncome = total * commission
    const clinicIncome = total - therapistIncome

    setForm((f) => ({
      ...f,
      totalFee: total ? String(total) : '',
      therapistIncome: therapistIncome ? String(therapistIncome) : '',
      clinicIncome: clinicIncome ? String(clinicIncome) : '',
    }))
  }, [form.hours, form.hourlyRate, form.commissionRate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    const res = await fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })

    if (res.ok) {
      router.push('/schedule')
    } else {
      const data = await res.json()
      setError(data.error?.fieldErrors ? '請填寫必要欄位' : data.error || '儲存失敗')
    }
    setLoading(false)
  }

  const update = (key: string, value: string) => setForm((f) => ({ ...f, [key]: value }))

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">新增諮商紀錄</h1>

      <form onSubmit={handleSubmit}>
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-lg">基本資料</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label>日期 *</Label>
              <Input type="date" value={form.date} onChange={(e) => update('date', e.target.value)} required />
            </div>
            <div>
              <Label>空間</Label>
              <Input value={form.room} onChange={(e) => update('room', e.target.value)} placeholder="例：3D" />
            </div>
            <div>
              <Label>心理師 *</Label>
              <select className="w-full border rounded-md px-3 py-2 text-sm" value={form.therapistId} onChange={(e) => update('therapistId', e.target.value)} required>
                <option value="">選擇心理師</option>
                {therapists.map((t) => (<option key={t.id} value={t.id}>{t.name}</option>))}
              </select>
            </div>
            <div>
              <Label>個案 *</Label>
              <select className="w-full border rounded-md px-3 py-2 text-sm" value={form.clientId} onChange={(e) => update('clientId', e.target.value)} required>
                <option value="">選擇個案</option>
                {clients.map((c) => (<option key={c.id} value={c.id}>{c.name}</option>))}
              </select>
            </div>
          </CardContent>
        </Card>

        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-lg">諮商資訊</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <Label>收費形式</Label>
              <Input value={form.billingType} onChange={(e) => update('billingType', e.target.value)} />
            </div>
            <div>
              <Label>諮商地點</Label>
              <select className="w-full border rounded-md px-3 py-2 text-sm" value={form.location} onChange={(e) => update('location', e.target.value)}>
                <option>治療所</option>
                <option>外訪到宅</option>
              </select>
            </div>
            <div>
              <Label>諮商形式</Label>
              <select className="w-full border rounded-md px-3 py-2 text-sm" value={form.counselingFormat} onChange={(e) => update('counselingFormat', e.target.value)}>
                <option>實體</option>
                <option>視訊</option>
              </select>
            </div>
            <div>
              <Label>諮商種類</Label>
              <Input value={form.counselingType} onChange={(e) => update('counselingType', e.target.value)} />
            </div>
            <div>
              <Label>時數</Label>
              <Input type="number" step="0.5" value={form.hours} onChange={(e) => update('hours', e.target.value)} />
            </div>
            <div>
              <Label>鐘點</Label>
              <Input type="number" value={form.hourlyRate} onChange={(e) => update('hourlyRate', e.target.value)} />
            </div>
          </CardContent>
        </Card>

        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-lg">財務資訊</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <Label>應收金額</Label>
              <Input type="number" value={form.amountReceivable} onChange={(e) => update('amountReceivable', e.target.value)} />
            </div>
            <div>
              <Label>應收類型</Label>
              <Input value={form.receivableType} onChange={(e) => update('receivableType', e.target.value)} placeholder="匯款/現金/機構申請" />
            </div>
            <div>
              <Label>收款狀況</Label>
              <select className="w-full border rounded-md px-3 py-2 text-sm" value={form.paymentStatus} onChange={(e) => update('paymentStatus', e.target.value)}>
                <option>未收</option>
                <option>已收</option>
              </select>
            </div>
            <div>
              <Label>當日實收金額</Label>
              <Input type="number" value={form.amountReceived} onChange={(e) => update('amountReceived', e.target.value)} />
            </div>
            <div>
              <Label>機構核銷月份</Label>
              <Input value={form.institutionMonth} onChange={(e) => update('institutionMonth', e.target.value)} />
            </div>
            <div>
              <Label>抽成比率</Label>
              <Input type="number" step="0.1" min="0" max="1" value={form.commissionRate} onChange={(e) => update('commissionRate', e.target.value)} />
            </div>
            <div>
              <Label>應收金額（計算）</Label>
              <Input type="number" value={form.totalFee} readOnly className="bg-muted" />
            </div>
            <div>
              <Label>心理師收入</Label>
              <Input type="number" value={form.therapistIncome} readOnly className="bg-muted" />
            </div>
            <div>
              <Label>治療所收入</Label>
              <Input type="number" value={form.clinicIncome} readOnly className="bg-muted" />
            </div>
            <div>
              <Label>給付治療師</Label>
              <select className="w-full border rounded-md px-3 py-2 text-sm" value={form.therapistPaid} onChange={(e) => update('therapistPaid', e.target.value)}>
                <option>未付</option>
                <option>已付</option>
              </select>
            </div>
            <div className="md:col-span-2">
              <Label>備註</Label>
              <Input value={form.notes} onChange={(e) => update('notes', e.target.value)} />
            </div>
          </CardContent>
        </Card>

        {error && <p className="text-destructive text-sm mb-4">{error}</p>}

        <div className="flex gap-4">
          <Button type="submit" disabled={loading}>
            {loading ? '儲存中...' : '儲存'}
          </Button>
          <Button type="button" variant="outline" onClick={() => router.back()}>
            取消
          </Button>
        </div>
      </form>
    </div>
  )
}
