'use client'

import { useEffect } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from './AuthProvider'

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const pathname = usePathname()
  const router = useRouter()
  const publicPage = pathname === '/login'
  useEffect(() => {
    if (!loading && !user && !publicPage) router.replace('/login')
    if (!loading && user && publicPage) router.replace('/pricing-task')
  }, [loading, user, publicPage, router])
  if (loading || (!user && !publicPage)) return <div className="grid min-h-[45vh] place-items-center text-sm text-slate-500">正在验证登录状态…</div>
  return <>{children}</>
}
