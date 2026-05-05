'use client'

import { useSession } from 'next-auth/react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function SettingsPage() {
  const { data: session } = useSession()
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [message, setMessage] = useState('')
  const [saving, setSaving] = useState(false)

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault()
    if (password !== confirmPassword) {
      setMessage('密碼不一致')
      return
    }
    if (password.length < 6) {
      setMessage('密碼至少6個字元')
      return
    }

    setSaving(true)
    const res = await fetch(`/api/users/${session?.user?.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    })

    if (res.ok) {
      setMessage('密碼已更新')
      setPassword('')
      setConfirmPassword('')
    } else {
      setMessage('更新失敗')
    }
    setSaving(false)
  }

  const roleLabels: Record<string, string> = { admin: '管理員', accountant: '會計', therapist: '心理師' }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <h1 className="text-2xl font-bold">帳號設定</h1>

      <Card>
        <CardHeader><CardTitle className="text-lg">個人資訊</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div>
            <Label className="text-muted-foreground">姓名</Label>
            <p className="font-medium">{session?.user?.name}</p>
          </div>
          <div>
            <Label className="text-muted-foreground">電子郵件</Label>
            <p className="font-medium">{session?.user?.email}</p>
          </div>
          <div>
            <Label className="text-muted-foreground">角色</Label>
            <p className="font-medium">{roleLabels[session?.user?.role || '']}</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-lg">變更密碼</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={handlePasswordChange} className="space-y-4">
            <div>
              <Label>新密碼</Label>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength={6} required />
            </div>
            <div>
              <Label>確認密碼</Label>
              <Input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required />
            </div>
            {message && <p className="text-sm text-muted-foreground">{message}</p>}
            <Button type="submit" disabled={saving}>{saving ? '更新中...' : '更新密碼'}</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
