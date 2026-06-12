'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'

const oldLinks = [
  { href: '/prices', label: '信息价' },
  { href: '/building-standard-2024', label: '建筑消耗量标准2024' },
  { href: '/pricing-kb', label: '组价知识库' },
  { href: '/boq', label: '工程管理' },
]

const links = [
  { href: '/boq-standard-management', label: '国标清单管理' },
  { href: '/quota-management', label: '定额管理' },
  { href: '/pricing-task', label: '单条组价' },
  { href: '/new-boq', label: '新工程管理' },
  { href: '/prompt-templates', label: '提示词模板' },
  { href: '/manual-boq', label: '工程管理（人工）' },
  { href: '/boq/debug', label: '套定额调试' },
  { href: '/compare', label: '定额比较' },
]

function isActive(pathname: string, href: string) {
  if (pathname === href) return true
  // /boq 只匹配 /boq/[数字]（项目详情），不匹配 /boq/debug 等具名子路由
  if (href === '/boq') return /^\/boq\/\d/.test(pathname)
  if (href === '/new-boq') return /^\/new-boq(\/|$)/.test(pathname)
  return pathname.startsWith(href + '/')
}

export default function Navbar() {
  const pathname = usePathname()
  const [oldOpen, setOldOpen] = useState(false)
  const oldMenuRef = useRef<HTMLDivElement>(null)
  const oldActive = oldLinks.some(link => isActive(pathname, link.href))

  useEffect(() => {
    setOldOpen(false)
  }, [pathname])

  useEffect(() => {
    function closeOnOutsideClick(event: MouseEvent) {
      if (!oldMenuRef.current?.contains(event.target as Node)) {
        setOldOpen(false)
      }
    }
    document.addEventListener('mousedown', closeOnOutsideClick)
    return () => document.removeEventListener('mousedown', closeOnOutsideClick)
  }, [])

  return (
    <nav className="bg-blue-900 text-white shadow-lg">
      <div className="max-w-7xl mx-auto px-4 flex items-center h-14 gap-2">
        <span className="font-bold text-lg mr-6 text-blue-100">组价通</span>
        <div ref={oldMenuRef} className="relative">
          <button
            type="button"
            onClick={() => setOldOpen(open => !open)}
            aria-haspopup="menu"
            aria-expanded={oldOpen}
            className={`flex items-center gap-1.5 rounded px-4 py-2 text-sm font-medium transition-colors ${
              oldActive || oldOpen
                ? 'bg-blue-700 text-white'
                : 'text-blue-200 hover:bg-blue-800 hover:text-white'
            }`}
          >
            OLD
            <span className="text-xs" aria-hidden="true">▾</span>
          </button>
          {oldOpen && (
            <div
              role="menu"
              className="absolute left-0 top-full z-50 mt-1 w-60 overflow-hidden rounded border border-gray-200 bg-white py-1 text-gray-800 shadow-xl"
            >
              {oldLinks.map(link => (
                <Link
                  key={link.href}
                  href={link.href}
                  role="menuitem"
                  className={`block px-4 py-2.5 text-sm transition-colors ${
                    isActive(pathname, link.href)
                      ? 'bg-blue-50 font-medium text-blue-700'
                      : 'hover:bg-gray-50'
                  }`}
                >
                  {link.label}
                </Link>
              ))}
            </div>
          )}
        </div>
        {links.map(l => (
          <Link
            key={l.href}
            href={l.href}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              isActive(pathname, l.href)
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
