'use client'

import Link from 'next/link'
import { useSession, signOut } from 'next-auth/react'
import { Button } from './ui/button'

export function Navbar() {
  const { data: session } = useSession()

  return (
    <nav className="border-b bg-card">
      <div className="max-w-5xl mx-auto px-4 h-16 flex items-center justify-between">
        <Link href="/" className="text-lg font-bold text-primary">
          慈恩心理治療所
        </Link>
        <div className="flex items-center gap-4">
          <Link href="/therapists" className="text-sm hover:text-primary transition-colors">
            心理師介紹
          </Link>
          {session ? (
            <>
              <Link href="/booking" className="text-sm hover:text-primary transition-colors">
                預約諮商
              </Link>
              <Link href="/my-appointments" className="text-sm hover:text-primary transition-colors">
                我的預約
              </Link>
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">{session.user.name}</span>
                <Button variant="ghost" size="sm" onClick={() => signOut({ callbackUrl: '/' })}>
                  登出
                </Button>
              </div>
            </>
          ) : (
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" asChild>
                <Link href="/login">登入</Link>
              </Button>
              <Button size="sm" asChild>
                <Link href="/register">註冊</Link>
              </Button>
            </div>
          )}
        </div>
      </div>
    </nav>
  )
}
