'use client'

import { createContext, useContext, useEffect, useState } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || ''
export type AuthUser = { id: number; username: string; display_name: string; role: 'admin' | 'operator' | 'reader' }
type AuthState = { user: AuthUser | null; loading: boolean; refresh: () => Promise<void>; logout: () => Promise<void> }
const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!API_BASE) return
    const originalFetch = window.fetch.bind(window)
    window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      const target = url.startsWith('/api/') ? `${API_BASE}${url}` : url
      const directApi = target.startsWith(`${API_BASE}/api/`)
      return originalFetch(target, directApi ? { ...init, credentials: 'include' } : init)
    }) as typeof window.fetch
    return () => { window.fetch = originalFetch }
  }, [])

  const refresh = async () => {
    try {
      const response = await fetch('/api/auth/me', { cache: 'no-store' })
      setUser(response.ok ? await response.json() : null)
    } finally {
      setLoading(false)
    }
  }
  const logout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' })
    setUser(null)
  }
  useEffect(() => { void refresh() }, [])
  return <AuthContext.Provider value={{ user, loading, refresh, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth 必须在 AuthProvider 内使用')
  return value
}
