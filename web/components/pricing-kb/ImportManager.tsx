'use client'

import { useEffect, useState } from 'react'
import {
  cancelPricingKbImportJob,
  createPricingKbImportJob,
  fetchPricingKbImportJob,
  fetchPricingKbImportProfiles,
  fetchPricingKbVersions,
  PricingKbImportJob,
  PricingKbImportProfile,
  PricingKbSourceTableInspection,
  PricingKbUploadResult,
  PricingKbVersion,
  publishPricingKbVersion,
  savePricingKbImportProfile,
  uploadPricingKb,
} from '@/lib/api'

const TOKEN_KEY = 'qmind_pricing_kb_admin_token'
const terminal = new Set(['validated', 'failed', 'cancelled'])

function Badge({ value }: { value: string }) {
  const tone = value === 'active' || value === 'validated'
    ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300'
    : value === 'failed' ? 'border-rose-400/30 bg-rose-400/10 text-rose-300'
      : 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  return <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[.18em] ${tone}`}>{value}</span>
}

export default function ImportManager({ onRefresh }: { onRefresh?: () => void }) {
  const [token, setToken] = useState('')
  const [profiles, setProfiles] = useState<PricingKbImportProfile[]>([])
  const [versions, setVersions] = useState<PricingKbVersion[]>([])
  const [upload, setUpload] = useState<PricingKbUploadResult | null>(null)
  const [profileId, setProfileId] = useState('full-pricing')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [raw, setRaw] = useState<Set<string>>(new Set())
  const [job, setJob] = useState<PricingKbImportJob | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const reloadVersions = () => fetchPricingKbVersions().then(setVersions).catch(() => undefined)
  useEffect(() => {
    setToken(sessionStorage.getItem(TOKEN_KEY) || '')
    fetchPricingKbImportProfiles().then(items => {
      setProfiles(items)
      const profile = items.find(item => item.profile_id === 'full-pricing')
      if (profile) setSelected(new Set(profile.selected_tables))
    }).catch(reason => setError(reason instanceof Error ? reason.message : '加载导入模板失败'))
    reloadVersions()
  }, [])

  useEffect(() => {
    if (!job || terminal.has(job.status) || !token) return
    const timer = window.setInterval(() => {
      fetchPricingKbImportJob(job.id, token).then(next => {
        setJob(next)
        if (terminal.has(next.status)) {
          reloadVersions()
          onRefresh?.()
        }
      }).catch(reason => setError(reason instanceof Error ? reason.message : '刷新任务失败'))
    }, 1800)
    return () => window.clearInterval(timer)
  }, [job, onRefresh, token])

  const tables = upload?.inspection.tables ?? []
  const available = new Set(tables.map(table => table.name))
  const currentProfile = profiles.find(item => item.profile_id === profileId)

  function saveToken(value: string) {
    setToken(value)
    sessionStorage.setItem(TOKEN_KEY, value)
  }

  function applyProfile(id: string) {
    setProfileId(id)
    const profile = profiles.find(item => item.profile_id === id)
    if (profile) setSelected(new Set(profile.selected_tables.filter(table => !tables.length || available.has(table))))
  }

  function toggleTable(table: PricingKbSourceTableInspection) {
    if (!table.known) {
      setRaw(previous => {
        const next = new Set(previous)
        next.has(table.name) ? next.delete(table.name) : next.add(table.name)
        return next
      })
      return
    }
    if (currentProfile?.required_tables.includes(table.name)) return
    setSelected(previous => {
      const next = new Set(previous)
      if (next.has(table.name)) next.delete(table.name)
      else {
        next.add(table.name)
        table.dependencies.forEach(item => available.has(item) && next.add(item))
      }
      return next
    })
  }

  async function handleUpload(file: File) {
    if (!token) return setError('请先输入管理员令牌')
    setBusy(true); setError(''); setJob(null)
    try {
      const result = await uploadPricingKb(file, token)
      setUpload(result)
      const profile = profiles.find(item => item.profile_id === profileId)
      const names = new Set(result.inspection.tables.map(table => table.name))
      setSelected(new Set((profile?.selected_tables ?? []).filter(name => names.has(name))))
      setRaw(new Set(result.inspection.tables.filter(table => !table.known).map(table => table.name)))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '上传失败')
    } finally { setBusy(false) }
  }

  async function queueImport() {
    if (!upload || !token) return
    setBusy(true); setError('')
    try {
      const created = await createPricingKbImportJob({
        upload_id: upload.id,
        profile_id: profileId,
        selected_tables: Array.from(selected),
        unknown_tables: Object.fromEntries(Array.from(raw).map(name => [name, 'raw'])),
      }, token)
      setJob(await fetchPricingKbImportJob(created.id, token))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '创建导入任务失败')
    } finally { setBusy(false) }
  }

  async function saveProfile() {
    if (!token) return setError('请先输入管理员令牌')
    const name = window.prompt('自定义模板名称')?.trim()
    if (!name) return
    const profile_id = `custom-${Date.now()}`
    try {
      await savePricingKbImportProfile({ profile_id, name, selected_tables: Array.from(selected), required_tables: [] }, token)
      const items = await fetchPricingKbImportProfiles(); setProfiles(items); setProfileId(profile_id)
    } catch (reason) { setError(reason instanceof Error ? reason.message : '保存模板失败') }
  }

  async function publish(version: PricingKbVersion) {
    if (!token || !window.confirm(`发布知识库版本 #${version.id}？新任务将使用该版本。`)) return
    setBusy(true); setError('')
    try { await publishPricingKbVersion(version.id, token); await reloadVersions(); onRefresh?.() }
    catch (reason) { setError(reason instanceof Error ? reason.message : '发布失败') }
    finally { setBusy(false) }
  }

  const progress = job?.total_tables ? Math.round(job.completed_tables / job.total_tables * 100) : 0

  return (
    <section className="overflow-hidden border border-slate-800 bg-[#07131b] text-slate-100 shadow-[0_20px_60px_rgba(15,23,42,.16)]">
      <div className="relative overflow-hidden border-b border-cyan-400/15 px-5 py-5">
        <div className="absolute inset-0 opacity-20 [background-image:linear-gradient(rgba(34,211,238,.12)_1px,transparent_1px),linear-gradient(90deg,rgba(34,211,238,.12)_1px,transparent_1px)] [background-size:24px_24px]" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[.35em] text-cyan-300">Knowledge Intake Console</div>
            <h2 className="mt-2 font-serif text-2xl font-semibold text-white">知识库导入控制台</h2>
            <p className="mt-1 text-xs text-slate-400">扫描、编排、校验、发布。未知表只进入隔离原始区。</p>
          </div>
          <label className="w-full max-w-xs">
            <span className="text-[10px] uppercase tracking-widest text-slate-500">管理员令牌 / Session only</span>
            <input type="password" value={token} onChange={event => saveToken(event.target.value)} placeholder="PRICING_KB_ADMIN_TOKEN"
              className="mt-1 w-full border border-slate-700 bg-slate-950/70 px-3 py-2 font-mono text-xs text-cyan-100 outline-none focus:border-cyan-500" />
          </label>
        </div>
      </div>

      {error && <div className="border-b border-rose-400/20 bg-rose-500/10 px-5 py-3 text-xs text-rose-200">{error}</div>}

      <div className="grid lg:grid-cols-[1.25fr_.75fr]">
        <div className="border-b border-slate-800 p-5 lg:border-b-0 lg:border-r">
          <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto]">
            <select value={profileId} onChange={event => applyProfile(event.target.value)} className="border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-cyan-500">
              {profiles.map(profile => <option key={profile.profile_id} value={profile.profile_id}>{profile.name}</option>)}
            </select>
            <label className="cursor-pointer border border-cyan-400/40 bg-cyan-400/10 px-4 py-2 text-center text-xs font-semibold uppercase tracking-widest text-cyan-200 hover:bg-cyan-400/20">
              {busy ? '处理中' : '上传 .DB'}
              <input type="file" accept=".db" disabled={busy} className="hidden" onChange={event => event.target.files?.[0] && handleUpload(event.target.files[0])} />
            </label>
            <button onClick={saveProfile} disabled={!selected.size} className="border border-slate-700 px-3 py-2 text-[10px] uppercase tracking-widest text-slate-400 hover:border-slate-500 disabled:opacity-30">保存模板</button>
          </div>
          <p className="mt-2 text-xs text-slate-500">{currentProfile?.description || '选择一个导入模板'}</p>

          <div className="mt-5 border border-slate-800">
            <div className="grid grid-cols-[minmax(0,1fr)_80px_76px] border-b border-slate-800 bg-slate-900/70 px-3 py-2 text-[10px] uppercase tracking-widest text-slate-500">
              <span>源表 / 处理策略</span><span className="text-right">行数</span><span className="text-right">选择</span>
            </div>
            <div className="max-h-[360px] overflow-y-auto">
              {!tables.length && <div className="px-4 py-12 text-center text-xs text-slate-600">上传 SQLite `.DB` 后显示结构扫描结果</div>}
              {tables.map(table => {
                const checked = table.known ? selected.has(table.name) : raw.has(table.name)
                const locked = table.known && currentProfile?.required_tables.includes(table.name)
                return <button key={table.name} onClick={() => toggleTable(table)} className="grid w-full grid-cols-[minmax(0,1fr)_80px_76px] items-center border-b border-slate-800/80 px-3 py-2.5 text-left hover:bg-slate-800/40">
                  <span className="min-w-0"><span className="font-mono text-xs text-slate-200">{table.name}</span>
                    <span className={`ml-2 text-[9px] font-semibold uppercase tracking-widest ${table.known ? 'text-cyan-400' : 'text-amber-300'}`}>{locked ? 'required' : table.known ? 'typed' : 'raw'}</span>
                    {!!table.dependencies.length && <span className="mt-0.5 block truncate text-[10px] text-slate-600">依赖 {table.dependencies.join(' · ')}</span>}
                  </span>
                  <span className="text-right font-mono text-xs text-slate-500">{table.row_count.toLocaleString()}</span>
                  <span className="flex justify-end"><span className={`h-4 w-8 border p-0.5 ${checked ? 'border-cyan-400 bg-cyan-400/20' : 'border-slate-600'}`}><span className={`block h-full w-3 bg-cyan-300 transition ${checked ? 'translate-x-3' : ''}`} /></span></span>
                </button>
              })}
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <div className="font-mono text-[10px] text-slate-500">TYPED {selected.size} / RAW {raw.size} / SHA {upload ? upload.inspection.schema_signature.slice(0, 12) : '—'}</div>
            <button disabled={!upload || busy || (!selected.size && !raw.size)} onClick={queueImport} className="bg-cyan-300 px-5 py-2 text-xs font-bold uppercase tracking-widest text-slate-950 disabled:cursor-not-allowed disabled:opacity-30">进入后台队列</button>
          </div>

          {job && <div className="mt-5 border border-slate-700 bg-slate-900/60 p-4">
            <div className="flex items-center justify-between"><div className="font-mono text-xs">JOB #{job.id} · {job.current_table || 'WAITING'}</div><Badge value={job.status} /></div>
            <div className="mt-3 h-1.5 overflow-hidden bg-slate-800"><div className="h-full bg-gradient-to-r from-cyan-400 to-emerald-300 transition-all" style={{ width: `${progress}%` }} /></div>
            <div className="mt-2 flex justify-between font-mono text-[10px] text-slate-500"><span>{job.completed_tables}/{job.total_tables} TABLES</span><span>{job.processed_rows.toLocaleString()} ROWS · {progress}%</span></div>
            {!terminal.has(job.status) && <button onClick={() => cancelPricingKbImportJob(job.id, token).then(() => fetchPricingKbImportJob(job.id, token).then(setJob))} className="mt-3 text-[10px] uppercase tracking-widest text-rose-300">取消任务</button>}
            {job.error_message && <div className="mt-3 text-xs text-rose-300">{job.error_message}</div>}
          </div>}
        </div>

        <aside className="p-5">
          <div className="flex items-center justify-between"><h3 className="text-xs font-semibold uppercase tracking-[.2em] text-slate-300">版本轨道</h3><button onClick={reloadVersions} className="font-mono text-[10px] text-cyan-400">REFRESH</button></div>
          <div className="mt-4 space-y-2">
            {versions.slice(0, 10).map(version => <div key={version.id} className={`border p-3 ${version.is_active ? 'border-emerald-400/40 bg-emerald-400/5' : 'border-slate-800 bg-slate-900/40'}`}>
              <div className="flex items-center justify-between gap-2"><span className="font-mono text-sm font-semibold">V{version.id.toString().padStart(3, '0')}</span><Badge value={version.status} /></div>
              <div className="mt-2 truncate font-mono text-[10px] text-slate-600">{version.source_file_sha256.slice(0, 20)}</div>
              <div className="mt-2 text-[10px] text-slate-500">{new Date(version.imported_at).toLocaleString('zh-CN')}</div>
              {!version.is_active && ['validated', 'retired'].includes(version.status) && <button disabled={busy || !token} onClick={() => publish(version)} className="mt-3 w-full border border-emerald-400/30 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-emerald-300 hover:bg-emerald-400/10 disabled:opacity-30">{version.status === 'retired' ? '重新激活' : '发布版本'}</button>}
            </div>)}
          </div>
          <div className="mt-5 border-l-2 border-amber-300/50 pl-3 text-[10px] leading-relaxed text-slate-500">Worker 需单独运行：<code className="text-amber-200">python pricing_kb_import_worker.py</code></div>
        </aside>
      </div>
    </section>
  )
}
