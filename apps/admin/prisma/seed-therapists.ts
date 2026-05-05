import { PrismaClient } from '../src/generated/prisma'
import bcrypt from 'bcryptjs'

const prisma = new PrismaClient()

const therapistNames = [
  '劉彥君', '劉柏宏', '呂孟育', '林容蒂', '林紀宇',
  '楊顯欽', '游子瑩', '潘柔靜', '羅紀萱', '葉邦彥',
  '蔡孟潔', '邱似齡', '邱惟雅', '邱意祺', '鄭幼毅',
  '陳慧苓', '黃慧婷',
]

function nameToPinyin(name: string): string {
  // Simple mapping for demo accounts: use name as email prefix
  const map: Record<string, string> = {
    '劉彥君': 'liuyanjun',
    '劉柏宏': 'liubohong',
    '呂孟育': 'lvmengyu',
    '林容蒂': 'linrongdi',
    '林紀宇': 'linjiyu',
    '楊顯欽': 'yangxianqin',
    '游子瑩': 'youziying',
    '潘柔靜': 'panroujing',
    '羅紀萱': 'luojixuan',
    '葉邦彥': 'yebangyan',
    '蔡孟潔': 'caimengjie',
    '邱似齡': 'qiusiling',
    '邱惟雅': 'qiuweiya',
    '邱意祺': 'qiuyiqi',
    '鄭幼毅': 'zhengyouyi',
    '陳慧苓': 'chenhuiling',
    '黃慧婷': 'huanghuiting',
  }
  return map[name] || name
}

async function main() {
  const passwordHash = await bcrypt.hash('demo1234', 12)

  for (const name of therapistNames) {
    // Upsert therapist
    const therapist = await prisma.therapist.upsert({
      where: { name },
      update: {},
      create: {
        name,
        commissionRate: 0.8,
        isActive: true,
      },
    })

    // Create staff user account
    const email = `${nameToPinyin(name)}@cheerpsy.com`
    await prisma.staffUser.upsert({
      where: { email },
      update: { therapistId: therapist.id },
      create: {
        email,
        passwordHash,
        name,
        role: 'therapist',
        therapistId: therapist.id,
      },
    })

    console.log(`✓ ${name} → ${email}`)
  }

  // Also create a demo accountant
  await prisma.staffUser.upsert({
    where: { email: 'accountant@cheerpsy.com' },
    update: {},
    create: {
      email: 'accountant@cheerpsy.com',
      passwordHash,
      name: '會計人員',
      role: 'accountant',
    },
  })
  console.log(`✓ 會計人員 → accountant@cheerpsy.com`)

  console.log('\n全部完成！密碼皆為 demo1234')
}

main()
  .catch((e) => {
    console.error(e)
    process.exit(1)
  })
  .finally(() => prisma.$disconnect())
