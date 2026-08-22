'use client'

import { FormEvent, useEffect, useState } from 'react'
import { useAuth } from '@/components/AuthProvider'

type Provider = { id: string; base_url: string | null }
type Profile = { id: number; name: string; provider: string; base_url: string; model: string; key_hint: string; is_default: boolean }
type Form = { name: string; provider: string; base_url: string; model: string; api_key: string }

const providerNames: Record<string, string> = { deepseek: 'DeepSeek', openai: 'OpenAI', zhipu: '智谱 AI', dashscope: '通义千问', 'openai-compatible': 'OpenAI Compatible' }
const emptyForm: Form = { name: '', provider: 'deepseek', base_url: '', model: '', api_key: '' }
const inputClass = 'w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100'

export default function AccountPage() {
  const { user, logout } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [message, setMessage] = useState('')
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [providers, setProviders] = useState<Provider[]>([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState<Form>(emptyForm)
  const [editing, setEditing] = useState<Profile | null>(null)
  const [saving, setSaving] = useState(false)
  const canManageModels = user?.role === 'admin' || user?.role === 'operator'

  async function loadProfiles() {
    if (!canManageModels) return
    setLoading(true)
    const response = await fetch('/api/model-profiles', { cache: 'no-store' })
    if (response.ok) {
      const data = await response.json()
      setProfiles(data.profiles)
      setProviders(data.providers)
    } else setMessage((await response.json().catch(() => ({}))).detail || '模型配置加载失败')
    setLoading(false)
  }

  useEffect(() => { void loadProfiles() // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canManageModels])

  async function changePassword(event: FormEvent) {
    event.preventDefault()
    const response = await fetch('/api/auth/change-password', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) })
    if (response.ok) { setMessage('密码已更新，请重新登录。'); await logout() } else setMessage((await response.json()).detail || '更新失败')
  }

  function beginEdit(profile?: Profile) {
    setEditing(profile || null)
    setForm(profile ? { name: profile.name, provider: profile.provider, base_url: profile.provider === 'openai-compatible' ? profile.base_url : '', model: profile.model, api_key: '' } : emptyForm)
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault(); setSaving(true)
    const response = await fetch(editing ? `/api/model-profiles/${editing.id}` : '/api/model-profiles', { method: editing ? 'PATCH' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...form, api_key: form.api_key || undefined }) })
    setSaving(false)
    if (!response.ok) return setMessage((await response.json().catch(() => ({}))).detail || '保存失败')
    setMessage('模型配置已保存'); setEditing(null); setForm(emptyForm); await loadProfiles()
  }

  async function action(path: string, success: string, method = 'POST') {
    const response = await fetch(path, { method }); const data = await response.json().catch(() => ({}))
    setMessage(response.ok ? success : data.detail || '操作失败')
    if (response.ok && !path.endsWith('/test')) await loadProfiles()
  }

  return <section className="space-y-7 pb-12">
    <div>
      <p className="text-xs font-semibold tracking-[.18em] text-blue-700">MY ACCOUNT</p>
      <h1 className="mt-2 text-2xl font-bold text-slate-900">我的账号</h1>
      <p className="mt-1 text-sm text-slate-500">管理账号安全与个人模型配置。</p>
    </div>

    {message && <div className="rounded-lg bg-blue-50 px-4 py-3 text-sm text-blue-800">{message}</div>}

    <div className="grid gap-6 lg:grid-cols-3">
      <div className="rounded-xl border bg-white p-5 shadow-sm"><h2 className="font-semibold text-slate-900">账号信息</h2><dl className="mt-5 grid grid-cols-2 gap-4 text-sm"><div><dt className="text-slate-500">姓名</dt><dd className="mt-1 font-medium text-slate-800">{user?.display_name}</dd></div><div><dt className="text-slate-500">角色</dt><dd className="mt-1 font-medium text-slate-800">{{ admin: '管理员', operator: '业务人员', reader: '只读人员' }[user?.role || 'reader']}</dd></div></dl></div>
      <form onSubmit={changePassword} className="space-y-3 rounded-xl border bg-white p-5 shadow-sm lg:col-span-2"><div><h2 className="font-semibold text-slate-900">修改密码</h2><p className="mt-1 text-sm text-slate-500">修改后会退出当前登录。</p></div><div className="grid gap-3 md:grid-cols-3"><input required type="password" placeholder="当前密码" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} className={inputClass} /><input required minLength={8} type="password" placeholder="新密码（至少 8 位）" value={newPassword} onChange={e => setNewPassword(e.target.value)} className={inputClass} /><button className="rounded bg-blue-900 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800">更新密码</button></div></form>
    </div>

    <div id="model-profiles" className="overflow-hidden rounded-xl border bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b bg-slate-50 px-5 py-4"><div><h2 className="font-semibold text-slate-900">模型配置</h2><p className="mt-1 text-sm text-slate-500">每位用户的密钥独立加密保存；组价任务将使用默认配置。</p></div>{canManageModels && <button onClick={() => beginEdit()} className="rounded bg-blue-900 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800">添加模型配置</button>}</div>
      <div className="p-5">{!canManageModels ? <p className="rounded bg-slate-50 p-4 text-sm text-slate-500">只读账号不能配置或调用个人模型。</p> : <>
        {(editing || !profiles.length) && <form onSubmit={saveProfile} className="mb-5 grid gap-3 rounded-lg border border-blue-100 bg-blue-50/60 p-4 md:grid-cols-2"><div><label className="mb-1 block text-xs font-medium text-slate-600">配置名称</label><input required placeholder="例如：生产 DeepSeek" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className={inputClass} /></div><div><label className="mb-1 block text-xs font-medium text-slate-600">供应商</label><select value={form.provider} onChange={e => { const provider = e.target.value; setForm({ ...form, provider, base_url: providers.find(item => item.id === provider)?.base_url || '' }) }} className={inputClass}>{providers.map(provider => <option key={provider.id} value={provider.id}>{providerNames[provider.id] || provider.id}</option>)}</select></div>{form.provider === 'openai-compatible' && <div><label className="mb-1 block text-xs font-medium text-slate-600">Base URL</label><input required type="url" placeholder="https://api.example.com/v1" value={form.base_url} onChange={e => setForm({ ...form, base_url: e.target.value })} className={inputClass} /></div>}<div><label className="mb-1 block text-xs font-medium text-slate-600">模型名称</label><input required placeholder="例如：deepseek-chat" value={form.model} onChange={e => setForm({ ...form, model: e.target.value })} className={inputClass} /></div><div className="md:col-span-2"><label className="mb-1 block text-xs font-medium text-slate-600">API Key</label><input required={!editing} type="password" placeholder={editing ? '留空则保留原 API Key' : '请输入 API Key'} value={form.api_key} onChange={e => setForm({ ...form, api_key: e.target.value })} className={inputClass} /></div><div className="flex gap-3 md:col-span-2"><button disabled={saving} className="rounded bg-blue-900 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-50">{saving ? '保存中…' : editing ? '保存修改' : '保存配置'}</button>{editing && <button type="button" onClick={() => { setEditing(null); setForm(emptyForm) }} className="rounded border bg-white px-4 py-2 text-sm text-slate-700 hover:bg-slate-50">取消</button>}</div></form>}
        {loading ? <p className="py-3 text-sm text-slate-500">正在加载模型配置…</p> : <div className="overflow-x-auto"><table className="w-full min-w-[700px] text-left text-sm"><thead className="border-b text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-3 py-3">配置</th><th className="px-3 py-3">供应商 / 模型</th><th className="px-3 py-3">密钥</th><th className="px-3 py-3">状态</th><th className="px-3 py-3 text-right">操作</th></tr></thead><tbody>{profiles.map(profile => <tr key={profile.id} className="border-b last:border-b-0"><td className="px-3 py-3 font-medium text-slate-800">{profile.name}</td><td className="px-3 py-3"><p className="text-slate-700">{providerNames[profile.provider] || profile.provider}</p><p className="mt-0.5 text-xs text-slate-500">{profile.model}</p></td><td className="px-3 py-3 font-mono text-xs text-slate-500">{profile.key_hint}</td><td className="px-3 py-3">{profile.is_default ? <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">默认使用</span> : <span className="text-slate-400">备用</span>}</td><td className="px-3 py-3 text-right"><div className="inline-flex items-center gap-3"><button onClick={() => void action(`/api/model-profiles/${profile.id}/test`, '连接成功：模型可用于任务执行。')} className="text-blue-700 hover:underline">测试</button>{!profile.is_default && <button onClick={() => void action(`/api/model-profiles/${profile.id}/default`, '已设为默认模型')} className="text-blue-700 hover:underline">设默认</button>}<button onClick={() => beginEdit(profile)} className="text-blue-700 hover:underline">编辑</button><button onClick={() => { if (window.confirm(`删除“${profile.name}”？`)) void action(`/api/model-profiles/${profile.id}`, '模型配置已删除', 'DELETE') }} className="text-rose-600 hover:underline">删除</button></div></td></tr>)}</tbody></table></div>}
      </>}</div>
    </div>
  </section>
}
