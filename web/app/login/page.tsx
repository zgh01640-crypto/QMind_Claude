'use client'

import { FormEvent, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/components/AuthProvider'

export default function LoginPage() {
  const router = useRouter()
  const { refresh } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault(); setSubmitting(true); setError('')
    try {
      const response = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) })
      if (!response.ok) setError((await response.json().catch(() => ({}))).detail || '登录失败，请重试')
      else { await refresh(); router.replace('/pricing-task') }
    } catch {
      setError('无法连接登录服务，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }
  return <div className="mx-auto mt-16 w-full max-w-md overflow-hidden rounded-2xl border border-blue-100 bg-white shadow-2xl shadow-blue-950/10">
    <div className="bg-blue-950 px-8 py-9 text-white"><p className="text-xs font-semibold tracking-[.24em] text-blue-300">QMIND · SECURE WORKSPACE</p><h1 className="mt-3 text-3xl font-semibold">欢迎回来</h1><p className="mt-2 text-sm text-blue-200">登录后查看仅属于你的工程与组价结果。</p></div>
    <form onSubmit={submit} className="space-y-5 p-8">
      <label className="block text-sm font-medium text-slate-700">账号<input autoFocus value={username} onChange={e => setUsername(e.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-blue-700 focus:ring-2 focus:ring-blue-100" /></label>
      <label className="block text-sm font-medium text-slate-700">密码<input type="password" value={password} onChange={e => setPassword(e.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-blue-700 focus:ring-2 focus:ring-blue-100" /></label>
      {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
      <button disabled={submitting} className="w-full rounded-lg bg-amber-400 py-2.5 text-sm font-bold text-blue-950 transition hover:bg-amber-300 disabled:opacity-60">{submitting ? '正在登录…' : '登录工作台'}</button>
    </form>
  </div>
}
