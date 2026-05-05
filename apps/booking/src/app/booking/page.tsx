'use client'

import { Suspense, useEffect, useState } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Navbar } from '@/components/navbar'

interface TherapistProfile {
  id: string
  name: string
  specialties: string | null
  availability: { id: string; dayOfWeek: number; startTime: string; endTime: string }[]
}

export default function BookingPageWrapper() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">載入中...</div>}>
      <BookingPage />
    </Suspense>
  )
}

function BookingPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const searchParams = useSearchParams()
  const preselectedTherapist = searchParams.get('therapist')

  const [therapists, setTherapists] = useState<TherapistProfile[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  const [form, setForm] = useState({
    therapistProfileId: preselectedTherapist || '',
    requestedDate: '',
    requestedTimeSlot: '',
    preferredFormat: 'in_person',
    clientName: '',
    clientPhone: '',
    clientEmail: '',
    notes: '',
  })

  useEffect(() => {
    fetch('/api/therapists').then((r) => r.json()).then(setTherapists)
  }, [])

  useEffect(() => {
    if (session?.user) {
      setForm((f) => ({
        ...f,
        clientName: f.clientName || session.user.name || '',
        clientEmail: f.clientEmail || session.user.email || '',
      }))
    }
  }, [session])

  if (status === 'loading') return null
  if (!session) {
    router.push('/login')
    return null
  }

  const selectedTherapist = therapists.find((t) => t.id === form.therapistProfileId)
  const dayNames = ['日', '一', '二', '三', '四', '五', '六']

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    const res = await fetch('/api/appointments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })

    if (res.ok) {
      setSuccess(true)
    } else {
      const data = await res.json()
      setError(typeof data.error === 'string' ? data.error : '預約失敗，請稍後再試')
    }
    setLoading(false)
  }

  if (success) {
    return (
      <>
        <Navbar />
        <div className="max-w-lg mx-auto px-4 py-16 text-center">
          <div className="h-16 w-16 rounded-full bg-green-100 flex items-center justify-center text-green-600 text-3xl mx-auto mb-6">
            ✓
          </div>
          <h1 className="text-2xl font-bold mb-2">預約已送出</h1>
          <p className="text-muted-foreground mb-8">
            我們將盡快確認您的預約，您可以在「我的預約」頁面查看狀態。
          </p>
          <div className="flex gap-4 justify-center">
            <Button asChild>
              <a href="/my-appointments">查看我的預約</a>
            </Button>
            <Button variant="outline" onClick={() => { setSuccess(false); setForm(f => ({ ...f, requestedDate: '', requestedTimeSlot: '', notes: '' })) }}>
              繼續預約
            </Button>
          </div>
        </div>
      </>
    )
  }

  return (
    <>
      <Navbar />
      <main className="max-w-2xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-2">預約諮商</h1>
        <p className="text-muted-foreground mb-8">填寫以下資訊，我們將為您安排諮商時段</p>

        <form onSubmit={handleSubmit} className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">選擇心理師</CardTitle>
              <CardDescription>可以留空，由治療所為您安排</CardDescription>
            </CardHeader>
            <CardContent>
              <select
                className="w-full border rounded-md px-3 py-2 text-sm"
                value={form.therapistProfileId}
                onChange={(e) => setForm((f) => ({ ...f, therapistProfileId: e.target.value }))}
              >
                <option value="">不指定心理師</option>
                {therapists.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}{t.specialties ? ` - ${t.specialties}` : ''}
                  </option>
                ))}
              </select>

              {selectedTherapist && selectedTherapist.availability.length > 0 && (
                <div className="mt-4">
                  <p className="text-sm font-medium mb-2">可預約時段：</p>
                  <div className="flex flex-wrap gap-2">
                    {selectedTherapist.availability.map((a) => (
                      <span key={a.id} className="text-xs bg-primary/10 text-primary px-2 py-1 rounded">
                        週{dayNames[a.dayOfWeek]} {a.startTime}-{a.endTime}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">預約資訊</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium">希望日期 *</label>
                  <Input
                    type="date"
                    value={form.requestedDate}
                    onChange={(e) => setForm((f) => ({ ...f, requestedDate: e.target.value }))}
                    min={new Date().toISOString().split('T')[0]}
                    required
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">希望時段 *</label>
                  <select
                    className="w-full border rounded-md px-3 py-2 text-sm"
                    value={form.requestedTimeSlot}
                    onChange={(e) => setForm((f) => ({ ...f, requestedTimeSlot: e.target.value }))}
                    required
                  >
                    <option value="">選擇時段</option>
                    <option value="09:00">09:00</option>
                    <option value="10:00">10:00</option>
                    <option value="11:00">11:00</option>
                    <option value="13:00">13:00</option>
                    <option value="14:00">14:00</option>
                    <option value="15:00">15:00</option>
                    <option value="16:00">16:00</option>
                    <option value="17:00">17:00</option>
                    <option value="18:00">18:00</option>
                    <option value="19:00">19:00</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="text-sm font-medium">諮商形式 *</label>
                <select
                  className="w-full border rounded-md px-3 py-2 text-sm"
                  value={form.preferredFormat}
                  onChange={(e) => setForm((f) => ({ ...f, preferredFormat: e.target.value }))}
                >
                  <option value="in_person">實體諮商</option>
                  <option value="online">視訊諮商</option>
                </select>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">聯絡資訊</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-sm font-medium">姓名 *</label>
                <Input value={form.clientName} onChange={(e) => setForm((f) => ({ ...f, clientName: e.target.value }))} required />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium">電話</label>
                  <Input value={form.clientPhone} onChange={(e) => setForm((f) => ({ ...f, clientPhone: e.target.value }))} />
                </div>
                <div>
                  <label className="text-sm font-medium">電子郵件</label>
                  <Input type="email" value={form.clientEmail} onChange={(e) => setForm((f) => ({ ...f, clientEmail: e.target.value }))} />
                </div>
              </div>
              <div>
                <label className="text-sm font-medium">備註</label>
                <textarea
                  className="w-full border rounded-md px-3 py-2 text-sm min-h-[80px]"
                  value={form.notes}
                  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                  placeholder="有任何需要讓我們知道的事項"
                />
              </div>
            </CardContent>
          </Card>

          {error && <p className="text-destructive text-sm">{error}</p>}

          <Button type="submit" className="w-full" size="lg" disabled={loading}>
            {loading ? '送出中...' : '送出預約'}
          </Button>
        </form>
      </main>
    </>
  )
}
