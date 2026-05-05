'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import Link from 'next/link'

interface SessionRecord {
  id: string
  date: string
  therapist: { name: string }
  client: { name: string }
  counselingFormat: string | null
  hours: number | null
}

export default function CalendarPage() {
  const [year, setYear] = useState(new Date().getFullYear())
  const [month, setMonth] = useState(new Date().getMonth() + 1)
  const [sessions, setSessions] = useState<SessionRecord[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const dateFrom = `${year}-${String(month).padStart(2, '0')}-01`
    const lastDay = new Date(year, month, 0).getDate()
    const dateTo = `${year}-${String(month).padStart(2, '0')}-${lastDay}`

    fetch(`/api/sessions?dateFrom=${dateFrom}&dateTo=${dateTo}&limit=1000`)
      .then((r) => r.json())
      .then((data) => {
        setSessions(data.sessions)
        setLoading(false)
      })
  }, [year, month])

  const prevMonth = () => {
    if (month === 1) { setMonth(12); setYear(y => y - 1) }
    else setMonth(m => m - 1)
  }

  const nextMonth = () => {
    if (month === 12) { setMonth(1); setYear(y => y + 1) }
    else setMonth(m => m + 1)
  }

  // Build calendar grid
  const firstDayOfMonth = new Date(year, month - 1, 1).getDay()
  const daysInMonth = new Date(year, month, 0).getDate()

  const sessionsByDay: Record<number, SessionRecord[]> = {}
  for (const s of sessions) {
    const day = new Date(s.date).getDate()
    if (!sessionsByDay[day]) sessionsByDay[day] = []
    sessionsByDay[day].push(s)
  }

  const weeks: (number | null)[][] = []
  let currentWeek: (number | null)[] = Array(firstDayOfMonth).fill(null)

  for (let d = 1; d <= daysInMonth; d++) {
    currentWeek.push(d)
    if (currentWeek.length === 7) {
      weeks.push(currentWeek)
      currentWeek = []
    }
  }
  if (currentWeek.length > 0) {
    while (currentWeek.length < 7) currentWeek.push(null)
    weeks.push(currentWeek)
  }

  const weekDays = ['日', '一', '二', '三', '四', '五', '六']

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">月曆檢視</h1>
        <Button variant="outline" asChild>
          <Link href="/schedule">列表檢視</Link>
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <Button variant="ghost" onClick={prevMonth}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <CardTitle>{year} 年 {month} 月</CardTitle>
            <Button variant="ghost" onClick={nextMonth}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-center text-muted-foreground py-12">載入中...</p>
          ) : (
            <div className="grid grid-cols-7 gap-px bg-muted">
              {weekDays.map((d) => (
                <div key={d} className="bg-background p-2 text-center text-sm font-medium text-muted-foreground">
                  {d}
                </div>
              ))}
              {weeks.flat().map((day, i) => (
                <div
                  key={i}
                  className={`bg-background min-h-[100px] p-2 ${day ? '' : 'bg-muted/30'}`}
                >
                  {day && (
                    <>
                      <p className="text-sm font-medium mb-1">{day}</p>
                      <div className="space-y-1">
                        {(sessionsByDay[day] || []).slice(0, 3).map((s) => (
                          <div
                            key={s.id}
                            className="text-xs bg-primary/10 text-primary rounded px-1 py-0.5 truncate"
                            title={`${s.therapist.name} - ${s.client.name}`}
                          >
                            {s.therapist.name} · {s.client.name}
                          </div>
                        ))}
                        {(sessionsByDay[day]?.length || 0) > 3 && (
                          <p className="text-xs text-muted-foreground">
                            +{sessionsByDay[day].length - 3} 筆
                          </p>
                        )}
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
