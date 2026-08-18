'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  BoqProject,
  ManualBoqProject,
  PricingKbLibrary,
  PricingTaskBatch,
  createBackgroundPricingTaskBatch,
  deletePricingTaskBatch,
  fetchBackgroundPricingTaskBatches,
  fetchBoqProjects,
  fetchManualBoqProjects,
  fetchPricingKbLibraries,
} from '@/lib/api'

const STATUS_LABEL: Record<string, string> = {
  active: '待执行', queued: '排队中', running: '执行中', stop_requested: '停止中',
  stopped: '已停止', completed: '已完成', failed: '失败',
}

export default function BackgroundBatchListPage() {
  const router = useRouter()
  const [batches, setBatches] = useState<PricingTaskBatch[]>([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [modalLoading, setModalLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [projects, setProjects] = useState<BoqProject[]>([])
  const [libraries, setLibraries] = useState<PricingKbLibrary[]>([])
  const [manualProjects, setManualProjects] = useState<ManualBoqProject[]>([])
  const [name, setName] = useState('')
  const [projectId, setProjectId] = useState<number | null>(null)
  const [manualProjectId, setManualProjectId] = useState<number | null>(null)
  const [libraryIds, setLibraryIds] = useState<Set<number>>(new Set())

  async function load() {
    setLoading(true)
    try { setBatches(await fetchBackgroundPricingTaskBatches()) }
    finally { setLoading(false) }
  }

  useEffect(() => { void load() }, [])

  async function showCreate() {
    setOpen(true)
    setModalLoading(true)
    if (!name) setName(`后台批量组价 ${new Date().toLocaleString()}`)
    try {
      const [boq, libs, manual] = await Promise.all([
        fetchBoqProjects(), fetchPricingKbLibraries(), fetchManualBoqProjects(),
      ])
      setProjects(boq)
      setLibraries(libs)
      setManualProjects(manual)
    } finally { setModalLoading(false) }
  }

  async function create() {
    if (!name.trim() || !projectId || !manualProjectId) return
    setSaving(true)
    try {
      const result = await createBackgroundPricingTaskBatch({
        name: name.trim(), boq_project_id: projectId,
        quota_library_ids: Array.from(libraryIds), manual_project_id: manualProjectId,
      })
      router.push(`/pricing-task/background-batch/${result.id}`)
    } catch (err) {
      alert(err instanceof Error ? err.message : '后台批次创建失败')
    } finally { setSaving(false) }
  }

  async function remove(id: number) {
    if (!confirm('确定删除这个后台批次？运行记录也会一并删除。')) return
    await deletePricingTaskBatch(id)
    await load()
  }

  return (
    <main className="min-h-screen bg-slate-100 text-slate-900">
      <div className="mx-auto max-w-7xl px-6 py-8">
        <header className="mb-7 flex items-end justify-between">
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-[.22em] text-blue-600">Server Queue</div>
            <h1 className="text-3xl font-bold tracking-tight">后台批量组价</h1>
            <p className="mt-2 text-sm text-slate-500">任务由服务器持续执行，关闭页面不影响进度；业务逻辑与单条组价共用。</p>
          </div>
          <button onClick={() => void showCreate()} className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700">新建后台批次</button>
        </header>

        <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          {loading ? <div className="py-20 text-center text-sm text-slate-400">加载批次...</div> : batches.length === 0 ? (
            <div className="py-20 text-center">
              <div className="text-base font-semibold">尚无后台批次</div>
              <p className="mt-2 text-sm text-slate-500">新建后选择清单，服务器会按批次并发槽调度。</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr><th className="px-5 py-3 text-left">批次</th><th className="px-5 py-3 text-left">工程 / 对比工程</th><th className="px-5 py-3 text-left">状态</th><th className="px-5 py-3 text-left">进度</th><th className="px-5 py-3 text-left">配置</th><th className="px-5 py-3 text-right">操作</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {batches.map(batch => (
                  <tr key={batch.id} className="hover:bg-slate-50/80">
                    <td className="px-5 py-4"><Link href={`/pricing-task/background-batch/${batch.id}`} className="font-semibold text-slate-900 hover:text-blue-600">{batch.name}</Link><div className="mt-1 text-xs text-slate-400">{new Date(batch.created_at).toLocaleString()}</div></td>
                    <td className="px-5 py-4"><div>{batch.project_name}</div><div className="mt-1 text-xs text-slate-500">人工：{batch.manual_project_name || `#${batch.manual_project_id}`}</div></td>
                    <td className="px-5 py-4"><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${batch.status === 'running' ? 'bg-blue-100 text-blue-700' : batch.status === 'completed' ? 'bg-emerald-100 text-emerald-700' : batch.status === 'stopped' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'}`}>{STATUS_LABEL[batch.status] || batch.status}</span></td>
                    <td className="px-5 py-4 tabular-nums"><span className="font-semibold">{batch.completed_count}</span> / {batch.selected_count}{batch.failed_count > 0 && <span className="ml-2 text-rose-600">失败 {batch.failed_count}</span>}</td>
                    <td className="px-5 py-4 text-xs text-slate-600"><div>并发 {batch.concurrency_limit ?? 20}</div><div className="mt-1">知识库版本 {batch.kb_version_id ?? '-'}</div></td>
                    <td className="px-5 py-4 text-right"><Link href={`/pricing-task/background-batch/${batch.id}`} className="mr-4 font-medium text-blue-600 hover:text-blue-700">进入</Link><button onClick={() => void remove(batch.id)} className="text-slate-400 hover:text-rose-600">删除</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>

      {open && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 p-4">
        <div className="w-full max-w-xl rounded-xl bg-white p-6 shadow-2xl">
          <div className="mb-5"><h2 className="text-xl font-bold">新建后台批次</h2><p className="mt-1 text-sm text-slate-500">并发数和知识库版本会在创建时固定。</p></div>
          {modalLoading ? <div className="py-16 text-center text-sm text-slate-400">加载基础数据...</div> : <div className="space-y-4">
            <label className="block text-sm font-medium">批次名称<input value={name} onChange={e => setName(e.target.value)} className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-blue-500" /></label>
            <label className="block text-sm font-medium">清单工程<select value={projectId ?? ''} onChange={e => setProjectId(e.target.value ? Number(e.target.value) : null)} className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2"><option value="">请选择</option>{projects.map(row => <option key={row.id} value={row.id}>{row.project_name}</option>)}</select></label>
            <label className="block text-sm font-medium">人工对比工程<select value={manualProjectId ?? ''} onChange={e => setManualProjectId(e.target.value ? Number(e.target.value) : null)} className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2"><option value="">请选择</option>{manualProjects.map(row => <option key={row.id} value={row.id}>{row.project_name}</option>)}</select></label>
            <div><div className="mb-1.5 text-sm font-medium">定额库 <span className="font-normal text-slate-400">（不选表示全部）</span></div><div className="max-h-40 space-y-2 overflow-auto rounded-lg border border-slate-200 p-3">{libraries.map(lib => <label key={lib.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={libraryIds.has(lib.id)} onChange={e => { const next = new Set(libraryIds); e.target.checked ? next.add(lib.id) : next.delete(lib.id); setLibraryIds(next) }} />{lib.name}<span className="text-xs text-slate-400">{lib.quota_count} 条</span></label>)}</div></div>
          </div>}
          <div className="mt-6 flex justify-end gap-3"><button onClick={() => setOpen(false)} className="rounded-lg border border-slate-300 px-4 py-2 text-sm">取消</button><button disabled={saving || modalLoading || !name.trim() || !projectId || !manualProjectId} onClick={() => void create()} className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white disabled:opacity-40">{saving ? '创建中...' : '创建并进入'}</button></div>
        </div>
      </div>}
    </main>
  )
}
