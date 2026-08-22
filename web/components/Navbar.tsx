'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { useAuth } from './AuthProvider'

const oldLinks = [
  { href: '/prices', label: '信息价' },
  { href: '/building-standard-2024', label: '建筑消耗量标准2024' },
  { href: '/boq-standard-management', label: '国标清单管理' },
  { href: '/quota-management', label: '定额管理' },
  { href: '/pricing-kb', label: '组价知识库' },
  { href: '/boq', label: '工程管理（旧）' },
  { href: '/prompt-templates', label: '提示词模板' },
  { href: '/boq/debug', label: '套定额调试' },
  { href: '/compare', label: '定额比较' },
  { href: '/pricing-task/batch', label: '批量组价（旧）' },
  { href: '/pricing-task/demo', label: '组价演示' },
]

const links = [
  { href: '/new-boq', label: '工程管理' },
  { href: '/manual-boq', label: '工程管理（人工）' },
  { href: '/pricing-task', label: '单条组价' },
  { href: '/pricing-task/new-batch', label: '批量组价' },
  { href: '/pricing-task/background-batch', label: '后台批量组价' },
]

function isActive(pathname: string, href: string) {
  if (pathname === href) return true
  // /boq 只匹配 /boq/[数字]（项目详情），不匹配 /boq/debug 等具名子路由
  if (href === '/boq') return /^\/boq\/\d/.test(pathname)
  if (href === '/new-boq') return /^\/new-boq(\/|$)/.test(pathname)
  if (href === '/pricing-task') return /^\/pricing-task(\/\d+)?$/.test(pathname)
  if (href === '/pricing-task/batch') return pathname.startsWith('/pricing-task/batch')
  if (href === '/pricing-task/new-batch') return pathname.startsWith('/pricing-task/new-batch')
  if (href === '/pricing-task/background-batch') return pathname.startsWith('/pricing-task/background-batch')
  if (href === '/pricing-task/demo') return pathname.startsWith('/pricing-task/demo')
  if (href === '/quota-management') return pathname.startsWith('/quota-management') || pathname.startsWith('/quota-input-prompts')
  return pathname.startsWith(href + '/')
}

export default function Navbar() {
  const pathname = usePathname()
  const [oldOpen, setOldOpen] = useState(false)
  const oldMenuRef = useRef<HTMLDivElement>(null)
  const oldActive = oldLinks.some(link => isActive(pathname, link.href))
  const { user, loading, logout } = useAuth()

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
        {!loading && !user && <span className="ml-auto text-sm text-blue-200">安全工作台</span>}
        {user && <>
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
        <div className="ml-auto flex items-center gap-3 text-sm">
          <div ref={oldMenuRef} className="relative">
            <button
              type="button"
              onClick={() => setOldOpen(open => !open)}
              aria-haspopup="menu"
              aria-expanded={oldOpen}
              className={`flex items-center gap-1.5 rounded px-3 py-2 text-sm font-medium transition-colors ${
                oldActive || oldOpen
                  ? 'bg-blue-700 text-white'
                  : 'text-blue-200 hover:bg-blue-800 hover:text-white'
              }`}
            >
              后台管理
              <span className="text-xs" aria-hidden="true">▾</span>
            </button>
            {oldOpen && (
              <div
                role="menu"
                className="absolute right-0 top-full z-50 mt-1 w-60 overflow-hidden rounded border border-gray-200 bg-white py-1 text-gray-800 shadow-xl"
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
          {user.role === 'admin' && <Link href="/admin/users" className={`rounded px-3 py-2 ${pathname.startsWith('/admin') ? 'bg-blue-700' : 'text-blue-200 hover:bg-blue-800'}`}>账号管理</Link>}
          <Link href="/account" className="text-blue-100 hover:text-white">{user.display_name}</Link>
          <button onClick={() => void logout()} className="rounded border border-blue-500 px-2.5 py-1 text-xs text-blue-100 hover:bg-blue-800">退出</button>
        </div>
        </>}
      </div>
    </nav>
  )
}
