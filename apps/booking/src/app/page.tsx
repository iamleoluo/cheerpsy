import Link from 'next/link'
import { prisma } from '@/lib/prisma'

export const dynamic = 'force-dynamic'

export default async function Home() {
  const therapists = await prisma.therapistProfile.findMany({
    where: { isAcceptingBookings: true },
    take: 6,
  })

  return (
    <main>
      {/* Hero */}
      <section className="bg-gradient-to-b from-primary/5 to-background py-20">
        <div className="max-w-5xl mx-auto px-4 text-center">
          <h1 className="text-4xl md:text-5xl font-bold mb-4">慈恩心理治療所</h1>
          <p className="text-lg text-muted-foreground mb-8 max-w-xl mx-auto">
            專業心理諮商服務，陪伴您走過生命中的每個階段
          </p>
          <div className="flex gap-4 justify-center">
            <Link
              href="/booking"
              className="px-6 py-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition font-medium"
            >
              立即預約
            </Link>
            <Link
              href="/therapists"
              className="px-6 py-3 border border-primary text-primary rounded-lg hover:bg-primary/5 transition font-medium"
            >
              瀏覽心理師
            </Link>
          </div>
        </div>
      </section>

      {/* Therapists preview */}
      {therapists.length > 0 && (
        <section className="max-w-5xl mx-auto px-4 py-16">
          <h2 className="text-2xl font-bold mb-8 text-center">我們的心理師</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {therapists.map((t) => (
              <div key={t.id} className="border rounded-lg p-6 text-center">
                <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center text-2xl font-bold text-primary mx-auto mb-4">
                  {t.name[0]}
                </div>
                <h3 className="font-semibold text-lg mb-2">{t.name}</h3>
                {t.specialties && (
                  <p className="text-sm text-muted-foreground">{t.specialties}</p>
                )}
              </div>
            ))}
          </div>
          <div className="text-center mt-8">
            <Link href="/therapists" className="text-primary hover:underline">
              查看全部心理師 →
            </Link>
          </div>
        </section>
      )}

      {/* Footer */}
      <footer className="border-t py-8 text-center text-sm text-muted-foreground">
        <p>慈恩心理治療所 &copy; {new Date().getFullYear()}</p>
      </footer>
    </main>
  )
}
