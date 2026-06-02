'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const links = [
  { href: '/prices', label: '信息价' },
  { href: '/quota', label: '消耗量标准' },
  { href: '/measure', label: '国标清单' },
  { href: '/boq', label: '工程管理' },
  { href: '/manual-boq', label: '工程管理（人工）' },
  { href: '/import', label: '导入管理' },
]

export default function Navbar() {
  const pathname = usePathname()
  return (
    <nav className="bg-blue-900 text-white shadow-lg">
      <div className="max-w-7xl mx-auto px-4 flex items-center h-14 gap-2">
        <span className="font-bold text-lg mr-6 text-blue-100">深圳信息价</span>
        {links.map(l => (
          <Link
            key={l.href}
            href={l.href}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              pathname === l.href || pathname.startsWith(l.href + '/')
                ? 'bg-blue-700 text-white'
                : 'text-blue-200 hover:bg-blue-800 hover:text-white'
            }`}
          >
            {l.label}
          </Link>
        ))}
      </div>
    </nav>
  )
}
