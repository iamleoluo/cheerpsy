import { PrismaClient } from '../src/generated/prisma'
import bcrypt from 'bcryptjs'

const prisma = new PrismaClient()

async function main() {
  const passwordHash = await bcrypt.hash('admin123', 12)

  await prisma.staffUser.upsert({
    where: { email: 'admin@cheerpsy.com' },
    update: {},
    create: {
      email: 'admin@cheerpsy.com',
      passwordHash,
      name: '系統管理員',
      role: 'admin',
    },
  })

  console.log('Seed complete: admin user created (admin@cheerpsy.com / admin123)')
}

main()
  .catch((e) => {
    console.error(e)
    process.exit(1)
  })
  .finally(async () => {
    await prisma.$disconnect()
  })
