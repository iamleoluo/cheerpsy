'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Plus, Trash2 } from 'lucide-react'

interface StaffUser {
  id: string
  email: string
  name: string
  role: string
  therapistId: string | null
  createdAt: string
}

export default function UsersPage() {
  const [users, setUsers] = useState<StaffUser[]>([])
  const [therapists, setTherapists] = useState<{ id: string; name: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({ email: '', password: '', name: '', role: 'therapist', therapistId: '' })

  const fetchUsers = () => {
    setLoading(true)
    fetch('/api/users').then((r) => r.json()).then((data) => {
      setUsers(data)
      setLoading(false)
    })
  }

  useEffect(() => {
    fetchUsers()
    fetch('/api/therapists').then((r) => r.json()).then(setTherapists)
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)

    const res = await fetch('/api/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })

    if (res.ok) {
      setShowForm(false)
      setForm({ email: '', password: '', name: '', role: 'therapist', therapistId: '' })
      fetchUsers()
    }
    setSaving(false)
  }

  const handleDelete = async (id: string) => {
    if (!confirm('確定刪除此帳號？')) return
    await fetch(`/api/users/${id}`, { method: 'DELETE' })
    fetchUsers()
  }

  const roleLabels: Record<string, string> = { admin: '管理員', accountant: '會計', therapist: '心理師' }
  const roleColors: Record<string, 'default' | 'secondary' | 'outline'> = { admin: 'default', accountant: 'secondary', therapist: 'outline' }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">帳號管理</h1>
        <Button onClick={() => setShowForm(true)}>
          <Plus className="h-4 w-4 mr-2" />
          新增帳號
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader><CardTitle className="text-lg">新增帳號</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div><Label>電子郵件 *</Label><Input type="email" value={form.email} onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))} required /></div>
              <div><Label>密碼 *</Label><Input type="password" value={form.password} onChange={(e) => setForm(f => ({ ...f, password: e.target.value }))} required minLength={6} /></div>
              <div><Label>姓名 *</Label><Input value={form.name} onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))} required /></div>
              <div>
                <Label>角色</Label>
                <select className="w-full border rounded-md px-3 py-2 text-sm" value={form.role} onChange={(e) => setForm(f => ({ ...f, role: e.target.value }))}>
                  <option value="admin">管理員</option>
                  <option value="accountant">會計</option>
                  <option value="therapist">心理師</option>
                </select>
              </div>
              {form.role === 'therapist' && (
                <div>
                  <Label>關聯心理師</Label>
                  <select className="w-full border rounded-md px-3 py-2 text-sm" value={form.therapistId} onChange={(e) => setForm(f => ({ ...f, therapistId: e.target.value }))}>
                    <option value="">無</option>
                    {therapists.map((t) => (<option key={t.id} value={t.id}>{t.name}</option>))}
                  </select>
                </div>
              )}
              <div className="flex gap-2 md:col-span-2">
                <Button type="submit" disabled={saving}>{saving ? '建立中...' : '建立'}</Button>
                <Button type="button" variant="outline" onClick={() => setShowForm(false)}>取消</Button>
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
                  <TableHead>電子郵件</TableHead>
                  <TableHead>角色</TableHead>
                  <TableHead>建立時間</TableHead>
                  <TableHead>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="font-medium">{u.name}</TableCell>
                    <TableCell>{u.email}</TableCell>
                    <TableCell>
                      <Badge variant={roleColors[u.role]}>{roleLabels[u.role]}</Badge>
                    </TableCell>
                    <TableCell>{new Date(u.createdAt).toLocaleDateString('zh-TW')}</TableCell>
                    <TableCell>
                      <Button variant="ghost" size="sm" onClick={() => handleDelete(u.id)} className="text-destructive">
                        <Trash2 className="h-4 w-4" />
                      </Button>
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
