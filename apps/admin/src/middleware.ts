import { withAuth } from 'next-auth/middleware'
import { NextResponse } from 'next/server'

export default withAuth(
  function middleware(req) {
    const token = req.nextauth.token
    const path = req.nextUrl.pathname

    if (!token) {
      return NextResponse.redirect(new URL('/login', req.url))
    }

    const role = token.role as string

    // Admin has full access
    if (role === 'admin') return NextResponse.next()

    // Accountant restrictions
    if (role === 'accountant') {
      const allowed = ['/dashboard', '/schedule', '/finance', '/reports', '/settings']
      if (!allowed.some((p) => path.startsWith(p))) {
        return NextResponse.redirect(new URL('/dashboard', req.url))
      }
    }

    // Therapist restrictions
    if (role === 'therapist') {
      const allowed = ['/dashboard', '/bookings', '/schedule', '/settings']
      if (!allowed.some((p) => path.startsWith(p))) {
        return NextResponse.redirect(new URL('/dashboard', req.url))
      }
    }

    return NextResponse.next()
  },
  {
    callbacks: {
      authorized: ({ token }) => !!token,
    },
  }
)

export const config = {
  matcher: [
    '/dashboard/:path*',
    '/bookings/:path*',
    '/schedule/:path*',
    '/sessions/:path*',
    '/finance/:path*',
    '/reports/:path*',
    '/therapists/:path*',
    '/clients/:path*',
    '/import/:path*',
    '/users/:path*',
    '/settings/:path*',
  ],
}
