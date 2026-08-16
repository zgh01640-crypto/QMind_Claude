'use client'

import { FormEvent, useState } from 'react'
import { useAuth } from '@/components/AuthProvider'

export default function AccountPage() {
  const { user, logout } = useAuth(); const [currentPassword, setCurrent] = useState(''); const [newPassword, setNew] = useState(''); const [message, setMessage] = useState('')
  async function submit(e: FormEvent) { e.preventDefault(); const r = await fetch('/api/auth/change-password', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) }); if (r.ok) { setMessage('密码已更新，请重新登录。'); await logout() } else setMessage((await r.json()).detail || '更新失败') }
  return <section className="mx-auto max-w-xl space-y-6"><div><p className="text-xs font-semibold tracking-widest text-blue-700">MY ACCOUNT</p><h1 className="mt-2 text-2xl font-bold text-slate-900">我的账号</h1></div><div className="rounded-xl border bg-white p-6 shadow-sm"><dl className="grid grid-cols-2 gap-4 text-sm"><div><dt className="text-slate-500">姓名</dt><dd className="mt-1 font-medium">{user?.display_name}</dd></div><div><dt className="text-slate-500">角色</dt><dd className="mt-1 font-medium">{{ admin: '管理员', operator: '业务人员', reader: '只读人员' }[user?.role || 'reader']}</dd></div></dl></div><form onSubmit={submit} className="space-y-4 rounded-xl border bg-white p-6 shadow-sm"><h2 className="font-semibold text-slate-900">修改密码</h2><input required type="password" placeholder="当前密码" value={currentPassword} onChange={e => setCurrent(e.target.value)} className="w-full rounded border px-3 py-2" /><input required minLength={8} type="password" placeholder="新密码（至少 8 位）" value={newPassword} onChange={e => setNew(e.target.value)} className="w-full rounded border px-3 py-2" />{message && <p className="text-sm text-blue-700">{message}</p>}<button className="rounded bg-blue-900 px-4 py-2 text-sm font-medium text-white">更新密码</button></form></section>
}
