'use client'

import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ManualComparisonReviewModal from '@/components/pricing-task/ManualComparisonReviewModal'
import {
  BoqItem,
  PricingTaskBatchDetail,
  PricingTaskBatchItemRun,
  PricingTaskEvaluation,
  exportBackgroundPricingTaskBatchDetailReportExcel,
  fetchPricingTaskBatchDetail,
  fetchPricingTaskBatchManualComparisonHistory,
  startBackgroundPricingTaskBatch,
  stopBackgroundPricingTaskBatch,
  streamBackgroundPricingTaskBatchEvents,
  updatePricingTaskBatchManualComparison,
} from '@/lib/api'

const TOOLS = [
  ['code_check', '清单编码校验'], ['feature_check', '项目特征校验'],
  ['chapter_rule_check', '章节规则校验'], ['quota_candidates', '定额候选检索'],
  ['quota_match', '定额匹配'], ['evaluation', '人工结果评测'],
  ['conversion_check', '组合换算'], ['coefficient_check', '系数换算'],
] as const

const ACTIVE_EXECUTIONS = new Set(['queued', 'running', 'stop_requested'])

function itemStatus(run?: PricingTaskBatchItemRun['run']) {
  if (!run || run.status === 'idle') return 'waiting'
  if (run.status === 'queued') return 'waiting'
  if (run.status === 'running' || run.status === 'retrying') return run.status
  if (run.status === 'failed') return 'failed'
  return 'success'
}

function statusLabel(status: string) {
  return ({ waiting: '等待', queued: '等待', running: '处理中', retrying: '重试等待', success: '成功', failed: '失败' } as Record<string, string>)[status] || status
}

function consistency(evaluation?: PricingTaskEvaluation | null) {
  if (!evaluation) return { label: '未评测', cls: 'bg-slate-100 text-slate-500' }
  if (evaluation.missed_count === 0 && evaluation.extra_count === 0) return { label: '完全一致', cls: 'bg-emerald-100 text-emerald-700' }
  if (evaluation.hit_count > 0) return { label: '部分一致', cls: 'bg-amber-100 text-amber-700' }
  return { label: '不一致', cls: 'bg-rose-100 text-rose-700' }
}

function toolData(run: PricingTaskBatchItemRun['run'], id: string): any {
  return (run as any)[id]
}

function toolOutput(run: PricingTaskBatchItemRun['run'], id: string) {
  if (run.current_tool === id && run.current_tool_output) return run.current_tool_output
  const data = toolData(run, id)
  if (!data) return ''
  if (id === 'quota_candidates') return `检索到 ${data.total ?? data.candidates?.length ?? 0} 条候选定额`
  if (id === 'quota_match') return `输出 ${data.matches?.length ?? 0} 条定额`
  if (id === 'evaluation') return `命中 ${data.hit_count ?? 0}，漏项 ${data.missed_count ?? 0}，多项 ${data.extra_count ?? 0}`
  if (id === 'conversion_check' || id === 'coefficient_check') return `完成 ${data.items?.length ?? 0} 条检查`
  if (id === 'code_check') return data.valid === false ? (data.message || '编码需要复核') : (data.message || '编码校验完成')
  if (id === 'feature_check') return data.summary || data.message || '项目特征校验完成'
  if (id === 'chapter_rule_check') return `检查 ${data.rules?.length ?? 0} 条章节规则`
  return '执行完成'
}

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = name
  anchor.click()
  URL.revokeObjectURL(url)
}

export default function BackgroundBatchDetailPage() {
  const batchId = Number(useParams<{ batchId: string }>().batchId)
  const [detail, setDetail] = useState<PricingTaskBatchDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [focusedId, setFocusedId] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<'all' | 'waiting' | 'failed'>('all')
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [reviewOpen, setReviewOpen] = useState(false)
  const lastEventId = useRef(0)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const next = await fetchPricingTaskBatchDetail(batchId)
      setDetail(next)
      setFocusedId(current => current ?? next.items[0]?.id ?? null)
      setError('')
    } catch (err) { setError(err instanceof Error ? err.message : '加载失败') }
    finally { if (!silent) setLoading(false) }
  }, [batchId])

  useEffect(() => { void load() }, [load])

  const active = !!detail?.execution && ACTIVE_EXECUTIONS.has(detail.execution.status)
  useEffect(() => {
    const timer = window.setInterval(() => void load(true), active ? 1800 : 10000)
    return () => window.clearInterval(timer)
  }, [active, load])

  useEffect(() => {
    if (!active) return
    let cancelled = false
    async function connect() {
      while (!cancelled) {
        try {
          await streamBackgroundPricingTaskBatchEvents(batchId, lastEventId.current, event => {
            lastEventId.current = Math.max(lastEventId.current, event.id)
            void load(true)
          })
        } catch { /* polling remains the fallback */ }
        if (!cancelled) await new Promise(resolve => window.setTimeout(resolve, 1200))
      }
    }
    void connect()
    return () => { cancelled = true }
  }, [active, batchId, load])

  const runMap = useMemo(() => new Map((detail?.runs || []).map(row => [row.boq_item_id, row])), [detail?.runs])
  const visibleItems = useMemo(() => (detail?.items || []).filter(item => {
    const text = `${item.item_code} ${item.item_name}`.toLowerCase()
    const status = itemStatus(runMap.get(item.id)?.run)
    return text.includes(query.trim().toLowerCase()) && (filter === 'all' || status === filter)
  }), [detail?.items, filter, query, runMap])
  const focusedItem = detail?.items.find(item => item.id === focusedId) || null
  const focusedRun = focusedId ? runMap.get(focusedId) : undefined
  const reviewable = !!focusedRun?.run.evaluation && (focusedRun.run.evaluation.missed_count > 0 || focusedRun.run.evaluation.extra_count > 0)

  function selectVisible() { setSelected(new Set(visibleItems.map(item => item.id))) }
  function invertVisible() {
    setSelected(current => {
      const next = new Set(current)
      visibleItems.forEach(item => next.has(item.id) ? next.delete(item.id) : next.add(item.id))
      return next
    })
  }

  async function start() {
    if (!selected.size) return alert('请先选择要执行的清单')
    setStarting(true)
    try { await startBackgroundPricingTaskBatch(batchId, Array.from(selected)); await load(true) }
    catch (err) { alert(err instanceof Error ? err.message : '启动失败') }
    finally { setStarting(false) }
  }

  async function stop() {
    if (!detail?.execution || !confirm('停止后不再领取新清单，正在处理的清单会执行完。确认停止？')) return
    setStopping(true)
    try { await stopBackgroundPricingTaskBatch(batchId, detail.execution.id); await load(true) }
    catch (err) { alert(err instanceof Error ? err.message : '停止失败') }
    finally { setStopping(false) }
  }

  async function exportExcel() {
    setExporting(true)
    try { saveBlob(await exportBackgroundPricingTaskBatchDetailReportExcel(batchId), `后台批量组价-${detail?.batch.name || batchId}.xlsx`) }
    catch (err) { alert(err instanceof Error ? err.message : '导出失败') }
    finally { setExporting(false) }
  }

  if (loading) return <div className="min-h-screen bg-slate-100 py-24 text-center text-slate-500">加载后台批次...</div>
  if (!detail) return <div className="min-h-screen bg-slate-100 py-24 text-center text-rose-600">{error || '批次不存在'}</div>

  const execution = detail.execution
  const runningCount = detail.runs.filter(row => row.run.status === 'running').length

  return (
    <main className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b border-slate-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-5">
          <div className="min-w-0"><Link href="/pricing-task/background-batch" className="text-xs font-medium text-blue-600 hover:underline">← 后台批次</Link><div className="mt-1 flex items-center gap-3"><h1 className="truncate text-xl font-bold">{detail.batch.name}</h1><span className="rounded border border-sky-200 bg-sky-50 px-2 py-0.5 text-xs font-semibold text-sky-700">知识库版本 {detail.batch.kb_version_id ?? '-'}</span><span className="rounded border border-slate-200 px-2 py-0.5 text-xs text-slate-600">并发槽 {detail.batch.concurrency_limit ?? 20}</span></div></div>
          <div className="flex shrink-0 items-center gap-2"><button onClick={() => void exportExcel()} disabled={exporting} className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50 disabled:opacity-50">{exporting ? '导出中...' : '导出 Excel'}</button>{active ? <button onClick={() => void stop()} disabled={stopping || execution?.status === 'stop_requested'} className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{execution?.status === 'stop_requested' ? '停止中...' : stopping ? '提交中...' : '停止'}</button> : <button onClick={() => void start()} disabled={starting || selected.size === 0} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">{starting ? '启动中...' : `后台执行 (${selected.size})`}</button>}</div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1600px] grid-cols-[390px_minmax(0,1fr)] gap-5 p-5">
        <aside className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 p-4">
            <div className="grid grid-cols-3 gap-2 text-center text-xs"><div className="rounded-lg bg-slate-50 p-2"><strong className="block text-lg text-slate-900">{execution?.selected_count ?? 0}</strong>已选执行</div><div className="rounded-lg bg-blue-50 p-2 text-blue-700"><strong className="block text-lg">{runningCount}</strong>处理中</div><div className="rounded-lg bg-rose-50 p-2 text-rose-700"><strong className="block text-lg">{execution?.failed_count ?? detail.batch.failed_count}</strong>失败</div></div>
            <input value={query} onChange={e => setQuery(e.target.value)} placeholder="查询清单编码或名称" className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500" />
            <div className="mt-3 flex flex-wrap gap-2 text-xs"><button onClick={selectVisible} className="rounded border border-slate-300 px-2.5 py-1.5">全选</button><button onClick={invertVisible} className="rounded border border-slate-300 px-2.5 py-1.5">反选</button>{(['all', 'waiting', 'failed'] as const).map(value => <button key={value} onClick={() => setFilter(value)} className={`rounded px-2.5 py-1.5 ${filter === value ? 'bg-slate-800 text-white' : 'border border-slate-300'}`}>{value === 'all' ? '全部' : value === 'waiting' ? '等待' : '失败'}</button>)}</div>
          </div>
          <div className="max-h-[calc(100vh-285px)] overflow-y-auto">
            {visibleItems.map(item => {
              const row = runMap.get(item.id)
              const status = itemStatus(row?.run)
              const diff = consistency(row?.run.evaluation)
              return <div key={item.id} onClick={() => setFocusedId(item.id)} className={`flex cursor-pointer gap-3 border-b border-slate-100 px-4 py-3 ${focusedId === item.id ? 'bg-blue-50' : 'hover:bg-slate-50'}`}><input type="checkbox" checked={selected.has(item.id)} onClick={e => e.stopPropagation()} onChange={e => { const next = new Set(selected); e.target.checked ? next.add(item.id) : next.delete(item.id); setSelected(next) }} className="mt-1" /><div className="min-w-0 flex-1"><div className="truncate font-mono text-xs text-slate-500">{item.item_code}</div><div className="mt-0.5 truncate text-sm font-semibold">{item.item_name}</div><div className="mt-2 flex gap-1.5"><span className={`rounded px-2 py-0.5 text-[11px] font-semibold ${status === 'failed' ? 'bg-rose-100 text-rose-700' : status === 'running' || status === 'retrying' ? 'bg-blue-100 text-blue-700' : status === 'success' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>{statusLabel(status)}</span>{row?.run.evaluation && <span className={`rounded px-2 py-0.5 text-[11px] font-semibold ${diff.cls}`}>{diff.label}</span>}{(row?.run.attempt_count || 0) > 1 && <span className="rounded bg-amber-50 px-2 py-0.5 text-[11px] text-amber-700">第 {row?.run.attempt_count} 次</span>}</div></div></div>
            })}
          </div>
        </aside>

        <section className="min-w-0 space-y-5">
          {focusedItem ? <>
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-start justify-between gap-5"><div><div className="font-mono text-xs text-slate-500">{focusedItem.item_code}</div><h2 className="mt-1 text-xl font-bold">{focusedItem.item_name}</h2><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-600">{focusedItem.item_description || '无项目特征'}</p></div>{reviewable && <button onClick={() => setReviewOpen(true)} className="shrink-0 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-800">复核差异并修正人工工程</button>}</div></div>

            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><div className="mb-4 flex items-center justify-between"><h3 className="font-bold">组价过程</h3><span className="text-xs text-slate-400">仅显示工具名称和输出，不展示推理过程</span></div>{!focusedRun ? <div className="rounded-lg border border-dashed border-slate-300 py-12 text-center text-sm text-slate-400">等待执行</div> : <div className="space-y-2">{TOOLS.map(([id, name]) => { const data = toolData(focusedRun.run, id); const current = focusedRun.run.current_tool === id; const state = data ? 'success' : current ? focusedRun.run.current_tool_status || 'running' : 'waiting'; return <div key={id} className="grid grid-cols-[18px_170px_minmax(0,1fr)] items-start gap-3 rounded-lg border border-slate-200 px-3 py-3"><span className={`mt-0.5 h-3.5 w-3.5 rounded-full border-2 ${state === 'success' ? 'border-emerald-500 bg-emerald-500' : state === 'error' ? 'border-rose-500 bg-rose-500' : state === 'running' || state === 'retrying' ? 'animate-pulse border-blue-500 bg-blue-100' : 'border-slate-300 bg-white'}`} /><div><div className="text-sm font-semibold">{name}</div><div className="mt-0.5 font-mono text-[10px] text-slate-400">{id}</div></div><div className={`text-sm ${state === 'waiting' ? 'text-slate-400' : 'text-slate-700'}`}>{state === 'waiting' ? '等待调用' : state === 'running' ? '调用中' : state === 'retrying' ? focusedRun.run.current_tool_output : toolOutput(focusedRun.run, id)}</div></div>})}{focusedRun.run.error_message && <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{focusedRun.run.error_message}</div>}</div>}</div>

            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><div className="mb-4 flex items-center justify-between"><h3 className="font-bold">清单套定额结果</h3>{focusedRun?.run.evaluation && <span className={`rounded-full px-3 py-1 text-xs font-semibold ${consistency(focusedRun.run.evaluation).cls}`}>{consistency(focusedRun.run.evaluation).label}</span>}</div>{!focusedRun?.run.quota_match ? <div className="py-10 text-center text-sm text-slate-400">暂无结果</div> : (focusedRun.run.quota_match.matches || []).length === 0 ? <div className="rounded-lg bg-amber-50 py-10 text-center text-sm text-amber-700">未匹配到定额</div> : <div className="overflow-hidden rounded-lg border border-slate-200"><table className="w-full text-sm"><thead className="bg-slate-50 text-xs text-slate-500"><tr><th className="px-4 py-2.5 text-left">定额编码</th><th className="px-4 py-2.5 text-left">定额名称</th><th className="px-4 py-2.5 text-left">单位</th><th className="px-4 py-2.5 text-right">倍率</th><th className="px-4 py-2.5 text-left">匹配依据</th></tr></thead><tbody className="divide-y divide-slate-100">{focusedRun.run.quota_match.matches?.map((match, index) => <tr key={`${match.dekid}-${match.dezmid}-${index}`}><td className="px-4 py-3 font-mono text-blue-700">{match.zmbh}</td><td className="px-4 py-3 font-medium">{match.zmmc}</td><td className="px-4 py-3 text-slate-500">{match.dw || '-'}</td><td className="px-4 py-3 text-right tabular-nums">{match.qty_factor}</td><td className="max-w-md px-4 py-3 text-xs text-slate-500">{match.match_reason}</td></tr>)}</tbody></table></div>}</div>
          </> : <div className="rounded-xl border border-slate-200 bg-white py-24 text-center text-slate-400">请选择左侧清单</div>}
        </section>
      </div>

      {reviewOpen && focusedItem && focusedRun?.run.id && focusedRun.run.evaluation && reviewable && <ManualComparisonReviewModal open item={focusedItem} evaluation={focusedRun.run.evaluation} matches={focusedRun.run.quota_match?.matches || []} submitReview={input => updatePricingTaskBatchManualComparison(focusedRun.run.id, input)} loadHistory={() => fetchPricingTaskBatchManualComparisonHistory(focusedRun.run.id)} onClose={() => setReviewOpen(false)} onUpdated={evaluation => { setDetail(current => current && ({ ...current, runs: current.runs.map(row => row.boq_item_id === focusedItem.id ? { ...row, run: { ...row.run, evaluation } } : row) })); setReviewOpen(false) }} />}
    </main>
  )
}
