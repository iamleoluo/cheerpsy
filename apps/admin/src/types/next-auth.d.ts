import 'next-auth'

declare module 'next-auth' {
  interface Session {
    user: {
      id: string
      email: string
      name: string
      role: 'admin' | 'accountant' | 'therapist'
      therapistId: string | null
    }
  }
}

declare module 'next-auth/jwt' {
  interface JWT {
    role: 'admin' | 'accountant' | 'therapist'
    therapistId: string | null
  }
}
