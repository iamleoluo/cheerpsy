import Link from 'next/link'
import { prisma } from '@/lib/prisma'
import { Navbar } from '@/components/navbar'

export default async function TherapistsPage() {
  const therapists = await prisma.therapistProfile.findMany({
    where: { isAcceptingBookings: true },
    include: { availability: true },
    orderBy: { name: 'asc' },
  })

  const dayNames = ['日', '一', '二', '三', '四', '五', '六']

  return (
    <>
      <Navbar />
      <main className="max-w-5xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-8">心理師介紹</h1>

        {therapists.length === 0 ? (
          <p className="text-muted-foreground text-center py-12">目前沒有可預約的心理師</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {therapists.map((t) => (
              <div key={t.id} className="border rounded-lg p-6">
                <div className="flex items-start gap-4">
                  <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center text-2xl font-bold text-primary flex-shrink-0">
                    {t.name[0]}
                  </div>
                  <div className="flex-1">
                    <h2 className="text-xl font-semibold">{t.name}</h2>
                    {t.specialties && (
                      <p className="text-sm text-muted-foreground mt-1">{t.specialties}</p>
                    )}
                    {t.bio && <p className="text-sm mt-2">{t.bio}</p>}
                  </div>
                </div>

                {t.availability.length > 0 && (
                  <div className="mt-4 pt-4 border-t">
                    <p className="text-sm font-medium mb-2">可預約時段</p>
                    <div className="flex flex-wrap gap-2">
                      {t.availability.map((a) => (
                        <span
                          key={a.id}
                          className="text-xs bg-primary/10 text-primary px-2 py-1 rounded"
                        >
                          週{dayNames[a.dayOfWeek]} {a.startTime}-{a.endTime}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="mt-4">
                  <Link
                    href={`/booking?therapist=${t.id}`}
                    className="inline-block px-4 py-2 bg-primary text-primary-foreground text-sm rounded-md hover:bg-primary/90 transition"
                  >
                    預約此心理師
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </>
  )
}
