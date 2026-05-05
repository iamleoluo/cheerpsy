'use client'

import { useEffect, useState } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Navbar } from '@/components/navbar'

interface Appointment {
  id: string
  requestedDate: string
  requestedTimeSlot: string
  preferredFormat: string
  status: string
  therapistProfile: { name: string } | null
  clientName: string
  notes: string | null
  rejectionReason: string | null
  createdAt: string
}

export default function MyAppointmentsPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (status === 'authenticated') {
      fetch('/api/appointments')
        .then((r) => r.json())
        .then((data) => {
          setAppointments(data)
          setLoading(false)
        })
    }
  }, [status])

  if (status === 'loading') return null
  if (!session) {
    router.push('/login')
    return null
  }

  const handleCancel = async (id: string) => {
    if (!confirm('確定取消此預約？')) return
    const res = await fetch(`/api/appointments/${id}`, { method: 'PATCH' })
    if (res.ok) {
      setAppointments((prev) => prev.map((a) => (a.id === id ? { ...a, status: 'cancelled' } : a)))
    }
  }

  const statusLabels: Record<string, string> = {
    pending: '待確認',
    confirmed: '已確認',
    rejected: '已拒絕',
    cancelled: '已取消',
  }

  const statusVariants: Record<string, 'warning' | 'success' | 'destructive' | 'secondary'> = {
    pending: 'warning',
    confirmed: 'success',
    rejected: 'destructive',
    cancelled: 'secondary',
  }

  const formatLabels: Record<string, string> = {
    in_person: '實體',
    online: '視訊',
  }

  return (
    <>
      <Navbar />
      <main className="max-w-3xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold">我的預約</h1>
          <Button asChild>
            <Link href="/booking">新增預約</Link>
          </Button>
        </div>

        {loading ? (
          <p className="text-center text-muted-foreground py-12">載入中...</p>
        ) : appointments.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-muted-foreground mb-4">您還沒有任何預約</p>
            <Button asChild>
              <Link href="/booking">立即預約</Link>
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            {appointments.map((a) => (
              <Card key={a.id}>
                <CardContent className="pt-6">
                  <div className="flex items-start justify-between">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <Badge variant={statusVariants[a.status]}>
                          {statusLabels[a.status]}
                        </Badge>
                        <span className="text-sm text-muted-foreground">
                          {formatLabels[a.preferredFormat]}
                        </span>
                      </div>
                      <p className="font-medium">
                        {new Date(a.requestedDate).toLocaleDateString('zh-TW')} {a.requestedTimeSlot}
                      </p>
                      {a.therapistProfile && (
                        <p className="text-sm text-muted-foreground">
                          心理師：{a.therapistProfile.name}
                        </p>
                      )}
                      {a.rejectionReason && (
                        <p className="text-sm text-destructive">原因：{a.rejectionReason}</p>
                      )}
                      {a.notes && (
                        <p className="text-sm text-muted-foreground">備註：{a.notes}</p>
                      )}
                    </div>
                    {a.status === 'pending' && (
                      <Button variant="outline" size="sm" onClick={() => handleCancel(a.id)}>
                        取消
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>
    </>
  )
}
