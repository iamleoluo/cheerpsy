import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export const dynamic = 'force-dynamic'

export default async function DashboardPage() {
  const session = await getServerSession(authOptions)

  const [sessionCount, therapistCount, clientCount] = await Promise.all([
    prisma.session.count(),
    prisma.therapist.count(),
    prisma.client.count(),
  ])

  const roleLabel: Record<string, string> = {
    admin: '管理員',
    accountant: '會計',
    therapist: '心理師',
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">
        歡迎，{session?.user?.name}（{roleLabel[session?.user?.role || 'admin']}）
      </h1>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-muted-foreground">諮商紀錄</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{sessionCount}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-muted-foreground">心理師</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{therapistCount}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-muted-foreground">個案</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{clientCount}</p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
