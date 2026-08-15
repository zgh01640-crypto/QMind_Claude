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
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : value === 'running' ? 'border-blue-200 bg-blue-50 text-blue-700'
      : value === 'failed' ? 'border-red-200 bg-red-50 text-red-700'
        : value === 'queued' ? 'border-amber-200 bg-amber-50 text-amber-700'
          : 'border-gray-200 bg-gray-50 text-gray-600'
  return <span className={`inline-flex rounded border px-2 py-0.5 text-xs font-medium ${tone}`}>{value}</span>
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
    if (!token) {
      setError('请先在页面右上角输入管理员令牌，再发布知识库版本')
      return
    }
    if (!window.confirm(`发布知识库版本 #${version.id}？新任务将使用该版本。`)) return
    setBusy(true); setError('')
    try { await publishPricingKbVersion(version.id, token); await reloadVersions(); onRefresh?.() }
    catch (reason) { setError(reason instanceof Error ? reason.message : '发布失败') }
    finally { setBusy(false) }
  }

  const progress = job?.total_tables ? Math.round(job.completed_tables / job.total_tables * 100) : 0
  const jobStage = job?.current_table || (job?.status === 'validated' ? 'COMPLETED'
    : job?.status === 'failed' ? 'FAILED'
      : job?.status === 'cancelled' ? 'CANCELLED'
        : job?.status === 'running' ? 'PREPARING' : 'WAITING')

  return (
    <section className="overflow-hidden border border-gray-200 bg-white">
      <div className="border-b border-gray-200 px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">知识库导入控制台</h2>
            <p className="mt-1 text-sm text-gray-500">上传、扫描、校验并发布知识库版本，未知表将进入隔离原始区。</p>
          </div>
          <label className="w-full max-w-xs">
            <span className="mb-1 block text-xs font-medium text-gray-600">管理员令牌</span>
            <input
              type="password"
              value={token}
              onChange={event => saveToken(event.target.value)}
              placeholder="PRICING_KB_ADMIN_TOKEN"
              className="w-full rounded border border-gray-300 bg-white px-3 py-2 text-xs text-gray-900 shadow-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            />
          </label>
        </div>
      </div>

      {error && <div className="border-b border-red-200 bg-red-50 px-5 py-3 text-sm text-red-700">{error}</div>}

      <div className="grid lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,.65fr)]">
        <div className="border-b border-gray-200 p-5 lg:border-b-0 lg:border-r">
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
            <select
              value={profileId}
              onChange={event => applyProfile(event.target.value)}
              className="min-w-0 rounded border border-gray-300 bg-white px-3 py-2 text-sm text-gray-800 shadow-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            >
              {profiles.map(profile => <option key={profile.profile_id} value={profile.profile_id}>{profile.name}</option>)}
            </select>
            <label className="cursor-pointer rounded bg-blue-600 px-4 py-2 text-center text-sm font-medium text-white transition hover:bg-blue-700">
              {busy ? '处理中...' : '上传 .DB'}
              <input type="file" accept=".db" disabled={busy} className="hidden" onChange={event => event.target.files?.[0] && handleUpload(event.target.files[0])} />
            </label>
            <button
              type="button"
              onClick={saveProfile}
              disabled={!selected.size}
              className="rounded border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              保存模板
            </button>
          </div>
          <p className="mt-2 text-xs text-gray-500">{currentProfile?.description || '选择一个导入模板'}</p>

          <div className="mt-5 overflow-hidden rounded border border-gray-200">
            <div className="grid grid-cols-[minmax(0,1fr)_90px_72px] border-b border-gray-200 bg-gray-50 px-3 py-2.5 text-xs font-medium text-gray-600">
              <span>来源表 / 处理策略</span>
              <span className="text-right">行数</span>
              <span className="text-right">启用</span>
            </div>
            <div className="max-h-[360px] overflow-y-auto">
              {!tables.length && <div className="px-4 py-12 text-center text-sm text-gray-400">上传 SQLite `.DB` 后显示结构扫描结果</div>}
              {tables.map(table => {
                const checked = table.known ? selected.has(table.name) : raw.has(table.name)
                const locked = table.known && currentProfile?.required_tables.includes(table.name)
                return (
                  <button
                    key={table.name}
                    type="button"
                    onClick={() => toggleTable(table)}
                    className="grid w-full grid-cols-[minmax(0,1fr)_90px_72px] items-center border-b border-gray-100 px-3 py-2.5 text-left transition last:border-b-0 hover:bg-blue-50/50"
                  >
                    <span className="min-w-0">
                      <span className="font-mono text-xs font-medium text-gray-900">{table.name}</span>
                      <span className={`ml-2 text-[10px] font-semibold ${table.known ? 'text-blue-600' : 'text-amber-600'}`}>
                        {locked ? '必需' : table.known ? '结构化' : '原始表'}
                      </span>
                      {!!table.dependencies.length && <span className="mt-0.5 block truncate text-xs text-gray-400">依赖 {table.dependencies.join(' · ')}</span>}
                    </span>
                    <span className="text-right text-xs tabular-nums text-gray-500">{table.row_count.toLocaleString()}</span>
                    <span className="flex justify-end">
                      <span className={`h-5 w-9 rounded-full border p-0.5 transition ${checked ? 'border-blue-600 bg-blue-600' : 'border-gray-300 bg-gray-100'}`}>
                        <span className={`block h-3.5 w-3.5 rounded-full transition ${checked ? 'translate-x-4 bg-white' : 'bg-gray-400'}`} />
                      </span>
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <div className="text-xs text-gray-500">
              已选结构化表 <span className="font-medium text-gray-800">{selected.size}</span>
              <span className="mx-2 text-gray-300">|</span>
              原始表 <span className="font-medium text-gray-800">{raw.size}</span>
              <span className="mx-2 text-gray-300">|</span>
              <span className="font-mono">SHA {upload ? upload.inspection.schema_signature.slice(0, 12) : '—'}</span>
            </div>
            <button
              type="button"
              disabled={!upload || busy || (!selected.size && !raw.size)}
              onClick={queueImport}
              className="rounded bg-blue-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              开始导入
            </button>
          </div>

          {job && (
            <div className="mt-5 rounded border border-gray-200 bg-gray-50 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-gray-900">导入任务 #{job.id}</div>
                  <div className="mt-0.5 font-mono text-xs text-gray-500">{jobStage}</div>
                </div>
                <Badge value={job.status} />
              </div>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-gray-200">
                <div className="h-full rounded-full bg-blue-600 transition-all" style={{ width: `${progress}%` }} />
              </div>
              <div className="mt-2 flex justify-between text-xs text-gray-500">
                <span>{job.completed_tables}/{job.total_tables} 张表</span>
                <span>{job.processed_rows.toLocaleString()} 行 · {progress}%</span>
              </div>
              {!terminal.has(job.status) && (
                <button type="button" onClick={() => cancelPricingKbImportJob(job.id, token).then(() => fetchPricingKbImportJob(job.id, token).then(setJob))} className="mt-3 text-xs font-medium text-red-600 hover:text-red-700">
                  取消任务
                </button>
              )}
              {job.error_message && <div className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{job.error_message}</div>}
            </div>
          )}
        </div>

        <aside className="bg-gray-50/60 p-5">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">知识库版本</h3>
              <p className="mt-0.5 text-xs text-gray-500">校验后发布，组价任务才会使用新版本。</p>
            </div>
            <button type="button" onClick={reloadVersions} className="text-xs font-medium text-blue-600 hover:text-blue-700">刷新</button>
          </div>
          <div className="mt-4 space-y-2">
            {versions.slice(0, 10).map(version => (
              <div key={version.id} className={`rounded border p-3 ${version.is_active ? 'border-emerald-200 bg-emerald-50/70' : 'border-gray-200 bg-white'}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-sm font-semibold text-gray-900">V{version.id.toString().padStart(3, '0')}</span>
                  <Badge value={version.status} />
                </div>
                <div className="mt-2 truncate font-mono text-xs text-gray-400">{version.source_file_sha256.slice(0, 20)}</div>
                <div className="mt-1 text-xs text-gray-500">{new Date(version.imported_at).toLocaleString('zh-CN')}</div>
                {!version.is_active && ['validated', 'retired'].includes(version.status) && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => publish(version)}
                    title={!token ? '请先输入管理员令牌' : undefined}
                    className="mt-3 w-full rounded border border-blue-200 bg-blue-50 py-1.5 text-xs font-medium text-blue-700 transition hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {version.status === 'retired'
                      ? (token ? '重新激活' : '输入令牌后重新激活')
                      : (token ? '发布版本' : '输入令牌后发布')}
                  </button>
                )}
              </div>
            ))}
          </div>
          <div className="mt-5 border-l-2 border-blue-200 pl-3 text-xs leading-relaxed text-gray-500">
            导入任务由后台 Worker 自动执行，排队后通常会在数秒内开始。
          </div>
        </aside>
      </div>
    </section>
  )
}
