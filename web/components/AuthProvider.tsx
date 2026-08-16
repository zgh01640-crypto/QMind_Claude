'use client'

import { createContext, useContext, useEffect, useState } from 'react'

export type AuthUser = { id: number; username: string; display_name: string; role: 'admin' | 'operator' | 'reader' }
type AuthState = { user: AuthUser | null; loading: boolean; refresh: () => Promise<void>; logout: () => Promise<void> }
const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
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
