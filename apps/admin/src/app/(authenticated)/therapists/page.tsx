'use client'

import { useEffect, useState } from 'react'
import { useSession } from 'next-auth/react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Plus, Pencil } from 'lucide-react'

interface Therapist {
  id: string
  name: string
  commissionRate: number
  isActive: boolean
  bio: string | null
  specialties: string | null
}

export default function TherapistsPage() {
  const { data: session } = useSession()
  const [therapists, setTherapists] = useState<Therapist[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<Therapist | null>(null)
  const [form, setForm] = useState({ name: '', commissionRate: '0.8', bio: '', specialties: '', isActive: true })
  const [saving, setSaving] = useState(false)

  const fetchTherapists = () => {
    setLoading(true)
    fetch('/api/therapists').then((r) => r.json()).then((data) => {
      setTherapists(data)
      setLoading(false)
    })
  }

  useEffect(() => { fetchTherapists() }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)

    const url = editing ? `/api/therapists/${editing.id}` : '/api/therapists'
    const method = editing ? 'PUT' : 'POST'

    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: form.name,
        commissionRate: parseFloat(form.commissionRate),
        bio: form.bio || undefined,
        specialties: form.specialties || undefined,
        isActive: form.isActive,
      }),
    })

    if (res.ok) {
      setShowForm(false)
      setEditing(null)
      setForm({ name: '', commissionRate: '0.8', bio: '', specialties: '', isActive: true })
      fetchTherapists()
    }
    setSaving(false)
  }

  const startEdit = (t: Therapist) => {
    setEditing(t)
    setForm({
      name: t.name,
      commissionRate: t.commissionRate.toString(),
      bio: t.bio || '',
      specialties: t.specialties || '',
      isActive: t.isActive,
    })
    setShowForm(true)
  }

  const isAdmin = session?.user?.role === 'admin'

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">心理師管理</h1>
        {isAdmin && (
          <Button onClick={() => { setShowForm(true); setEditing(null); setForm({ name: '', commissionRate: '0.8', bio: '', specialties: '', isActive: true }) }}>
            <Plus className="h-4 w-4 mr-2" />
            新增心理師
          </Button>
        )}
      </div>

      {showForm && isAdmin && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{editing ? '編輯心理師' : '新增心理師'}</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div><Label>姓名 *</Label><Input value={form.name} onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))} required /></div>
              <div><Label>抽成比率</Label><Input type="number" step="0.1" min="0" max="1" value={form.commissionRate} onChange={(e) => setForm(f => ({ ...f, commissionRate: e.target.value }))} /></div>
              <div><Label>簡介</Label><Input value={form.bio} onChange={(e) => setForm(f => ({ ...f, bio: e.target.value }))} /></div>
              <div><Label>專長</Label><Input value={form.specialties} onChange={(e) => setForm(f => ({ ...f, specialties: e.target.value }))} /></div>
              <div className="flex items-center gap-2">
                <input type="checkbox" checked={form.isActive} onChange={(e) => setForm(f => ({ ...f, isActive: e.target.checked }))} />
                <Label>啟用</Label>
              </div>
              <div className="flex gap-2 md:col-span-2">
                <Button type="submit" disabled={saving}>{saving ? '儲存中...' : '儲存'}</Button>
                <Button type="button" variant="outline" onClick={() => { setShowForm(false); setEditing(null) }}>取消</Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="pt-6">
          {loading ? (
            <p className="text-center text-muted-foreground py-8">載入中...</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>姓名</TableHead>
                  <TableHead>抽成</TableHead>
                  <TableHead>專長</TableHead>
                  <TableHead>狀態</TableHead>
                  {isAdmin && <TableHead>操作</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {therapists.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell className="font-medium">{t.name}</TableCell>
                    <TableCell>{(t.commissionRate * 100).toFixed(0)}%</TableCell>
                    <TableCell>{t.specialties || '-'}</TableCell>
                    <TableCell>
                      <Badge variant={t.isActive ? 'success' : 'secondary'}>
                        {t.isActive ? '啟用' : '停用'}
                      </Badge>
                    </TableCell>
                    {isAdmin && (
                      <TableCell>
                        <Button variant="ghost" size="sm" onClick={() => startEdit(t)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    )}
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
