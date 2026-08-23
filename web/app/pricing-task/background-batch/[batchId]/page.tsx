'use client'

import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import ManualComparisonReviewModal from '@/components/pricing-task/ManualComparisonReviewModal'
import BatchPricingResultDetailModal from '@/components/pricing-task/BatchPricingResultDetailModal'
import {
  BackgroundBatchConsistencyStatus,
  BackgroundBatchExecutionStatus,
  BackgroundBatchItemDetail,
  BackgroundBatchWorkspace,
  BackgroundBatchWorkspaceItem,
  PricingTaskRun,
  exportBackgroundPricingTaskBatchDetailReportExcel,
  fetchBackgroundPricingTaskItemDetail,
  fetchBackgroundPricingTaskWorkspace,
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
const ACTIVE = new Set(['queued', 'running', 'stop_requested'])
const EXECUTION: Record<BackgroundBatchExecutionStatus, [string, string]> = {
  waiting: ['等待', 'border-slate-200 bg-slate-50 text-slate-600'],
  processing: ['处理中', 'border-sky-200 bg-sky-50 text-sky-700'],
  retrying: ['重试中', 'border-amber-200 bg-amber-50 text-amber-700'],
  completed: ['已完成', 'border-emerald-200 bg-emerald-50 text-emerald-700'],
  failed: ['失败', 'border-rose-200 bg-rose-50 text-rose-700'],
}
const CONSISTENCY: Record<BackgroundBatchConsistencyStatus, [string, string]> = {
  exact: ['完全一致', 'border-emerald-200 bg-emerald-50 text-emerald-700'],
  partial: ['部分一致', 'border-amber-200 bg-amber-50 text-amber-700'],
  inconsistent: ['不一致', 'border-rose-200 bg-rose-50 text-rose-700'],
  no_comparable: ['无可比数据', 'border-violet-200 bg-violet-50 text-violet-700'],
  unassessed: ['未评测', 'border-slate-200 bg-slate-50 text-slate-500'],
}
type StatusFilter = 'all' | BackgroundBatchExecutionStatus | 'review'
type Stage = 'item' | 'candidates' | 'quota' | 'conversion'

function Badge({ value, meta }: { value: string; meta: [string, string] }) {
  return <span className={`inline-flex rounded border px-2 py-0.5 text-[10px] font-semibold ${meta[1]}`}>{value || meta[0]}</span>
}
function duration(ms?: number | null) {
  if (ms == null) return '—'
  const seconds = Math.round(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}
function percent(value?: number | null) { return value == null ? '—' : `${(value * 100).toFixed(1)}%` }
function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-dashed border-slate-300 py-12 text-center text-xs text-slate-400">{children}</div>
}
function Metric({ label, value, note, tone = '' }: { label: string; value: ReactNode; note?: string; tone?: string }) {
  return <div className={`min-w-0 rounded-lg border border-slate-200 px-3 py-2 ${tone || 'bg-white'}`}>
    <div className="truncate text-[10px] text-slate-500">{label}</div>
    <div className="truncate text-lg font-bold tabular-nums">{value}</div>
    {note && <div className="truncate text-[9px] text-slate-400">{note}</div>}
  </div>
}
function ResourceObservation({ label, value, detail, status = 'idle' }: { label: string; value: ReactNode; detail: string; status?: 'idle' | 'active' | 'warning' }) {
  const dot = status === 'warning' ? 'bg-amber-400' : status === 'active' ? 'bg-sky-400' : 'bg-slate-300'
  return <div className="flex min-w-0 items-center gap-1.5 whitespace-nowrap">
    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
    <span className="text-slate-400">{label}</span>
    <span className="font-semibold tabular-nums text-slate-600">{value}</span>
    <span className="text-slate-400">{detail}</span>
  </div>
}
function ResultAssessment({ summary }: { summary: BackgroundBatchWorkspace['summary'] }) {
  const quotaRate = summary.hit_rate == null ? null : Math.max(0, Math.min(1, summary.hit_rate))
  const itemConsistencyRate = summary.selected_count > 0
    ? Math.max(0, Math.min(1, summary.exact_count / summary.selected_count))
    : null
  return <section className="overflow-hidden rounded-2xl border border-emerald-200 bg-white shadow-sm">
    <div className="grid lg:grid-cols-[390px_minmax(0,1fr)]">
      <div className="relative overflow-hidden bg-emerald-950 px-5 py-3 text-white">
        <div className="absolute -right-8 -top-12 h-28 w-28 rounded-full border-[20px] border-emerald-800/60" />
        <div className="relative">
          <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-emerald-300">结果评估</div>
          <div className="mt-2 grid grid-cols-2 gap-4">
            <div>
              <div className="text-2xl font-bold tabular-nums tracking-tight">{percent(itemConsistencyRate)}</div>
              <div className="mt-0.5 text-[11px] font-semibold text-cyan-200">清单一致率</div>
              <div className="mt-1 h-1 overflow-hidden rounded-full bg-emerald-900"><div className="h-full rounded-full bg-cyan-300 transition-all duration-700" style={{ width: `${(itemConsistencyRate ?? 0) * 100}%` }} /></div>
              <div className="mt-1 text-[9px] leading-3 text-emerald-400">完全一致清单数 ÷ 套取清单总数</div>
            </div>
            <div className="border-l border-emerald-800 pl-4">
              <div className="text-2xl font-bold tabular-nums tracking-tight">{percent(quotaRate)}</div>
              <div className="mt-0.5 text-[11px] font-semibold text-emerald-200">定额命中率</div>
              <div className="mt-1 h-1 overflow-hidden rounded-full bg-emerald-900"><div className="h-full rounded-full bg-emerald-300 transition-all duration-700" style={{ width: `${(quotaRate ?? 0) * 100}%` }} /></div>
              <div className="mt-1 text-[9px] leading-3 text-emerald-400">命中定额数 ÷ 人工定额数</div>
            </div>
          </div>
          <div className="mt-2 text-[9px] text-emerald-300">已评测 {summary.evaluated_count} / {summary.selected_count} 条套取清单</div>
        </div>
      </div>
      <div className="px-4 py-3">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          <Metric label="命中定额" value={summary.hit_count} tone="border-emerald-100 bg-emerald-50/70 text-emerald-800" />
          <Metric label="漏项定额" value={summary.missed_count} tone="border-amber-100 bg-amber-50/70 text-amber-800" />
          <Metric label="多项定额" value={summary.extra_count} tone="border-rose-100 bg-rose-50/70 text-rose-800" />
          <Metric label="人工定额" value={summary.manual_count} />
          <Metric label="AI 定额" value={summary.ai_count} />
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-slate-100 pt-2 text-[11px]">
          <span className="mr-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">清单一致性</span>
          <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 font-semibold text-emerald-700">完全一致 {summary.exact_count}</span>
          <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 font-semibold text-amber-700">部分一致 {summary.partial_count}</span>
          <span className="rounded-full border border-rose-200 bg-rose-50 px-2.5 py-1 font-semibold text-rose-700">不一致 {summary.inconsistent_count}</span>
          {summary.failed_count > 0 && <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 font-semibold text-slate-600">执行失败 {summary.failed_count}</span>}
        </div>
      </div>
    </div>
  </section>
}
function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = name; anchor.click(); URL.revokeObjectURL(url)
}
function toolData(run: PricingTaskRun, id: string): any { return (run as any)[id] }
function toolOutput(run: PricingTaskRun, id: string) {
  if (run.current_tool === id && run.current_tool_output) return run.current_tool_output
  const data = toolData(run, id)
  if (!data) return ''
  if (id === 'quota_candidates') return `检索到 ${data.total ?? data.candidates?.length ?? 0} 条候选定额`
  if (id === 'quota_match') return `输出 ${data.matches?.length ?? 0} 条定额`
  if (id === 'evaluation') return `命中 ${data.hit_count ?? 0}，漏项 ${data.missed_count ?? 0}，多项 ${data.extra_count ?? 0}`
  if (id === 'conversion_check' || id === 'coefficient_check') return `完成 ${data.items?.length ?? 0} 条检查`
  if (id === 'chapter_rule_check') return `检查 ${data.rules?.length ?? 0} 条章节规则`
  return data.summary || data.message || '执行完成'
}

function ToolFeed({ run }: { run: PricingTaskRun | null }) {
  if (!run) return <Empty>该清单尚未执行</Empty>
  return <div className="grid gap-3 md:grid-cols-2">{TOOLS.map(([id, name], index) => {
    const data = toolData(run, id)
    const current = run.current_tool === id
    const state = data ? 'success' : current ? run.current_tool_status || 'running' : 'waiting'
    const timing = run.step_timings?.[String(index + 1)]
    return <div key={id} className={`rounded-xl border px-4 py-3 ${current ? 'border-sky-300 bg-sky-50/70 shadow-sm' : 'border-slate-200 bg-white'}`}>
      <div className="flex items-start justify-between gap-3"><div className="flex items-center gap-2"><span className={`h-2.5 w-2.5 rounded-full border-2 ${state === 'success' ? 'border-emerald-500 bg-emerald-500' : state === 'error' ? 'border-rose-500 bg-rose-500' : state === 'running' || state === 'retrying' ? 'animate-pulse border-sky-500 bg-sky-100' : 'border-slate-300 bg-white'}`} /><div><div className="text-xs font-semibold">{name}</div><div className="font-mono text-[10px] text-slate-400">{id}</div></div></div><div className="shrink-0 text-xs tabular-nums text-slate-400">{timing ? duration(timing.duration_ms) : '—'}</div></div>
      <div className={`mt-2 line-clamp-2 min-h-9 text-xs leading-5 ${state === 'waiting' ? 'text-slate-400' : state === 'error' ? 'text-rose-700' : 'text-slate-600'}`}>{state === 'waiting' ? '等待调用' : state === 'running' ? '调用中…' : toolOutput(run, id)}</div>
    </div>
  })}{run.error_message && <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">{run.error_message}</div>}</div>
}

function StageResult({ stage, detail }: { stage: Stage; detail: BackgroundBatchItemDetail | null }) {
  if (!detail) return <Empty>加载清单详情…</Empty>
  const { item, run } = detail
  if (stage === 'item') {
    const feature = run?.feature_check as any
    return <div className="grid gap-2 md:grid-cols-2">
      <Info label="清单编码" value={item.item_code} /><Info label="清单名称" value={item.item_name} />
      <Info label="单位 / 工程量" value={`${item.unit || '—'} / ${item.quantity ?? '—'}`} /><Info label="特征完整性" value={feature?.completeness_status || feature?.status || '—'} />
      <div className="md:col-span-2"><Info label="项目特征" value={item.item_description || '无项目特征'} /></div>
      {feature?.effective_description && <div className="md:col-span-2"><Info label="校验后项目特征" value={feature.effective_description} /></div>}
    </div>
  }
  if (stage === 'candidates') {
    const candidates = run?.quota_candidates?.candidates || []
    return candidates.length ? <DataTable heads={['定额编码', '定额名称', '单位', '定额库 / 章节']} rows={candidates.map(row => [row.zmbh, row.zmmc, row.dw || '—', row.library_name || row.chapter_name || '—'])} /> : <Empty>{run ? '没有检索到候选定额' : '尚未执行候选检索'}</Empty>
  }
  if (stage === 'quota') {
    const evaluation = run?.evaluation
    const matches = run?.quota_match?.matches || []
    return <div className="space-y-3">
      {evaluation && <div className="grid grid-cols-3 gap-2 md:grid-cols-6"><Metric label="AI 定额" value={evaluation.ai_count} /><Metric label="人工定额" value={evaluation.manual_count} /><Metric label="命中" value={evaluation.hit_count} tone="bg-emerald-50" /><Metric label="漏项" value={evaluation.missed_count} tone="bg-amber-50" /><Metric label="多项" value={evaluation.extra_count} tone="bg-rose-50" /><Metric label="命中率" value={evaluation.manual_count ? percent(evaluation.hit_count / evaluation.manual_count) : '—'} /></div>}
      {matches.length ? <DataTable heads={['定额编码', '定额名称', '单位', '倍率', '匹配依据']} rows={matches.map(row => [row.zmbh, row.zmmc, row.dw || '—', row.qty_factor, row.match_reason || '—'])} /> : <Empty>{run?.quota_match ? '未匹配到定额' : '尚未生成定额结果'}</Empty>}
      {evaluation && <div className="grid gap-2 md:grid-cols-3"><Codes title="一致定额" values={evaluation.hit_codes} cls="text-emerald-700" /><Codes title="仅人工存在" values={evaluation.missed_codes} cls="text-amber-700" /><Codes title="仅 AI 存在" values={evaluation.extra_codes} cls="text-rose-700" /></div>}
    </div>
  }
  const conversion = run?.conversion_check?.items || []
  const coefficient = run?.coefficient_check?.items || []
  return <div className="space-y-4"><CompactResults title="组合换算" items={conversion.map(row => ({ code: row.quota_code, name: row.quota_name, note: `${row.needs_conversion ? '需要换算' : '无需换算'} · ${row.reason || '无说明'} · 资源 ${row.resources?.length || 0}` }))} /><CompactResults title="系数换算" items={coefficient.map(row => ({ code: row.quota_code, name: row.quota_name, note: `命中规则 ${row.coefficient_rules?.filter(rule => rule.matched).length || 0}/${row.coefficient_rules?.length || 0} · 资源 ${row.resources?.length || 0}` }))} /></div>
}

function Info({ label, value }: { label: string; value: ReactNode }) { return <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3"><div className="text-[10px] text-slate-400">{label}</div><div className="mt-1 whitespace-pre-wrap text-xs leading-5 text-slate-700">{value}</div></div> }
function Codes({ title, values, cls }: { title: string; values: string[]; cls: string }) { return <div className="rounded-lg border border-slate-200 p-3"><div className="text-[11px] font-semibold">{title} · {values.length}</div><div className={`mt-2 flex flex-wrap gap-1 font-mono text-[10px] ${cls}`}>{values.length ? values.map(value => <span key={value} className="rounded bg-slate-50 px-1.5 py-1">{value}</span>) : <span className="text-slate-400">无</span>}</div></div> }
function DataTable({ heads, rows }: { heads: string[]; rows: Array<Array<ReactNode>> }) { return <div className="max-h-[440px] overflow-auto rounded-lg border border-slate-200"><table className="w-full text-xs"><thead className="sticky top-0 bg-slate-50 text-slate-500"><tr>{heads.map(head => <th key={head} className="px-3 py-2 text-left">{head}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex} className={`px-3 py-2.5 ${cellIndex === 0 ? 'font-mono text-sky-700' : cellIndex === 1 ? 'font-medium' : 'text-slate-500'}`}>{cell}</td>)}</tr>)}</tbody></table></div> }
function CompactResults({ title, items }: { title: string; items: Array<{ code: string; name: string; note: string }> }) { return <div><div className="mb-2 text-xs font-bold">{title} · {items.length}</div>{items.length ? <div className="grid gap-2 md:grid-cols-2">{items.map((item, index) => <div key={`${item.code}-${index}`} className="rounded-lg border border-slate-200 p-3"><div className="font-mono text-[10px] text-sky-700">{item.code}</div><div className="text-xs font-semibold">{item.name}</div><div className="mt-1 text-[10px] text-slate-500">{item.note}</div></div>)}</div> : <Empty>暂无结果</Empty>}</div> }

export default function BackgroundBatchDetailPage() {
  const batchId = Number(useParams<{ batchId: string }>().batchId)
  const [workspace, setWorkspace] = useState<BackgroundBatchWorkspace | null>(null)
  const [detail, setDetail] = useState<BackgroundBatchItemDetail | null>(null)
  const [focusedId, setFocusedId] = useState<number | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [differenceFilter, setDifferenceFilter] = useState<'all' | BackgroundBatchConsistencyStatus>('all')
  const [view, setView] = useState<'process' | 'results'>('process')
  const [stage, setStage] = useState<Stage>('quota')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [resultDetailOpen, setResultDetailOpen] = useState(false)
  const lastEventId = useRef(0)
  const refreshTimer = useRef<number | null>(null)
  const selectionReady = useRef(false)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const next = await fetchBackgroundPricingTaskWorkspace(batchId)
      setWorkspace(next); setFocusedId(current => current ?? next.items[0]?.id ?? null); setError('')
      if (!selectionReady.current) { setSelected(new Set(next.items.filter(item => item.execution_status === 'waiting').map(item => item.id))); selectionReady.current = true }
    } catch (err) { setError(err instanceof Error ? err.message : '加载失败') }
    finally { if (!silent) setLoading(false) }
  }, [batchId])
  useEffect(() => { void load() }, [load])
  const active = !!workspace?.execution && ACTIVE.has(workspace.execution.status)
  const finished = !!workspace?.execution && ['completed', 'stopped'].includes(workspace.execution.status)
  useEffect(() => { if (finished) setView('results') }, [finished, workspace?.execution?.id])
  useEffect(() => { const timer = window.setInterval(() => void load(true), active ? 4000 : 15000); return () => window.clearInterval(timer) }, [active, load])

  const scheduleRefresh = useCallback(() => {
    if (refreshTimer.current != null) return
    refreshTimer.current = window.setTimeout(() => { refreshTimer.current = null; void load(true) }, 750)
  }, [load])
  useEffect(() => {
    if (!active) return
    let cancelled = false
    const controller = new AbortController()
    async function connect() {
      while (!cancelled) {
        try {
          await streamBackgroundPricingTaskBatchEvents(batchId, lastEventId.current, event => {
            if (event.event_type === 'database_busy') return
            lastEventId.current = Math.max(lastEventId.current, event.id)
            scheduleRefresh()
          }, controller.signal)
        } catch {
          if (controller.signal.aborted) return
          // Keep polling and reconnect after a transient stream failure.
        }
        if (!cancelled) await new Promise(resolve => window.setTimeout(resolve, 1500))
      }
    }
    void connect(); return () => { cancelled = true; controller.abort() }
  }, [active, batchId, scheduleRefresh])
  useEffect(() => () => { if (refreshTimer.current != null) window.clearTimeout(refreshTimer.current) }, [])

  const focused = workspace?.items.find(item => item.id === focusedId)
  useEffect(() => {
    if (!focusedId) return setDetail(null)
    let cancelled = false
    fetchBackgroundPricingTaskItemDetail(batchId, focusedId).then(next => { if (!cancelled) setDetail(next) }).catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : '详情加载失败') })
    return () => { cancelled = true }
  }, [batchId, focusedId, focused?.updated_at])

  const visible = useMemo(() => (workspace?.items || []).filter(item => {
    const search = `${item.item_code} ${item.item_name}`.toLowerCase().includes(query.trim().toLowerCase())
    const status = statusFilter === 'all' || (statusFilter === 'review' ? ['partial', 'inconsistent'].includes(item.consistency_status) : item.execution_status === statusFilter)
    return search && status && (differenceFilter === 'all' || item.consistency_status === differenceFilter)
  }), [differenceFilter, query, statusFilter, workspace?.items])
  const reviewable = !!detail?.run?.evaluation && (detail.run.evaluation.missed_count > 0 || detail.run.evaluation.extra_count > 0)

  function selectWhere(test: (item: BackgroundBatchWorkspaceItem) => boolean) { if (!active && workspace) setSelected(new Set(workspace.items.filter(test).map(item => item.id))) }
  function invert() { if (!active) setSelected(current => { const next = new Set(current); visible.forEach(item => next.has(item.id) ? next.delete(item.id) : next.add(item.id)); return next }) }
  async function start() { if (!selected.size) return alert('请先选择要执行的清单'); setStarting(true); try { await startBackgroundPricingTaskBatch(batchId, Array.from(selected)); await load(true) } catch (err) { alert(err instanceof Error ? err.message : '启动失败') } finally { setStarting(false) } }
  async function stop() { if (!workspace?.execution || !confirm('停止后不再领取新清单，正在处理的清单会执行完。确认停止？')) return; setStopping(true); try { await stopBackgroundPricingTaskBatch(batchId, workspace.execution.id); await load(true) } catch (err) { alert(err instanceof Error ? err.message : '停止失败') } finally { setStopping(false) } }
  async function exportExcel() { setExporting(true); try { saveBlob(await exportBackgroundPricingTaskBatchDetailReportExcel(batchId), `后台批量组价-${workspace?.batch.name || batchId}.xlsx`) } catch (err) { alert(err instanceof Error ? err.message : '导出失败') } finally { setExporting(false) } }

  if (loading) return <div className="min-h-screen bg-slate-100 py-24 text-center text-sm text-slate-500">加载后台批次工作台…</div>
  if (!workspace) return <div className="min-h-screen bg-slate-100 py-24 text-center text-rose-600">{error || '批次不存在'}</div>
  const { batch, execution, summary, runtime_metrics } = workspace
  return <main className="min-h-screen bg-[#f6f7f8] text-slate-900">
    <header className="border-b border-slate-200 bg-white"><div className="mx-auto max-w-[1560px] px-6 py-4">
      <div className="flex items-center justify-between gap-6"><div className="min-w-0"><div className="text-xs text-slate-500"><Link href="/pricing-task/background-batch" className="font-semibold text-sky-700 hover:underline">← 后台批次</Link><span className="mx-2 text-slate-300">/</span>{batch.project_name}</div><div className="mt-2 flex flex-wrap items-center gap-2"><h1 className="mr-2 truncate text-2xl font-semibold tracking-tight">{batch.name}</h1><Badge value={`知识库版本 ${batch.kb_version_id ?? '—'}`} meta={['', 'border-sky-200 bg-sky-50 text-sky-700']} /><Badge value={`人工：${batch.manual_project_name || batch.manual_project_id || '—'}`} meta={['', 'border-slate-200 bg-slate-50 text-slate-600']} /></div></div>
        <div className="flex shrink-0 gap-2"><button onClick={() => void exportExcel()} disabled={exporting} className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium hover:bg-slate-50 disabled:opacity-40">{exporting ? '导出中…' : '导出 Excel'}</button>{active ? <button onClick={() => void stop()} disabled={stopping || execution?.status === 'stop_requested'} className="rounded-lg bg-rose-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40">{execution?.status === 'stop_requested' ? '停止中…' : '停止领取'}</button> : <button onClick={() => void start()} disabled={starting || !selected.size} className="rounded-lg bg-sky-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-sky-800 disabled:opacity-40">{starting ? '启动中…' : `后台执行 ${selected.size} 条`}</button>}</div></div>
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 border-t border-slate-100 pt-2.5 text-[10px]">
        <span className="font-semibold tracking-[0.12em] text-slate-300">资源观测</span>
        <ResourceObservation label="进度" value={`${summary.completed_count}/${summary.total_count}`} detail={`待 ${summary.waiting_count} · 运行 ${summary.running_count} · 失败 ${summary.failed_count}`} status={summary.failed_count > 0 ? 'warning' : summary.running_count > 0 ? 'active' : 'idle'} />
        <ResourceObservation label="模型" value={`${runtime_metrics.model.running}/${runtime_metrics.model.limit}`} detail={`等待 ${runtime_metrics.model.waiting} · 限流 ${runtime_metrics.model_rate_limited_failed_count}`} status={runtime_metrics.model_rate_limited_failed_count > 0 ? 'warning' : runtime_metrics.model.running > 0 ? 'active' : 'idle'} />
        <ResourceObservation label="连接池" value={`${runtime_metrics.database.in_use}/${runtime_metrics.database.max}`} detail={`等待 ${runtime_metrics.database.waiting} · 长租约 ${runtime_metrics.database.long_lease_count} · ${runtime_metrics.database.longest_lease_seconds.toFixed(1)}秒`} status={runtime_metrics.database.waiting > 0 || runtime_metrics.database.long_lease_count > 0 ? 'warning' : runtime_metrics.database.in_use > 0 ? 'active' : 'idle'} />
        <ResourceObservation label="耗时" value={duration(summary.elapsed_seconds * 1000)} detail={`${summary.throughput_per_minute}/分钟 · 剩余 ${duration(summary.eta_seconds == null ? null : summary.eta_seconds * 1000)}`} />
      </div>
    </div></header>

    {finished && summary.evaluated_count > 0 && <div className="mx-auto max-w-[1560px] px-6 pt-4"><ResultAssessment summary={summary} /></div>}

    <div className="mx-auto grid max-w-[1560px] grid-cols-[340px_minmax(0,1fr)] gap-6 px-6 py-6">
      <aside className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="border-b border-slate-200 p-4">
        <div className="mb-3 flex items-center justify-between"><h2 className="text-sm font-semibold">清单范围</h2><span className="text-xs text-slate-400">显示 {visible.length} 条</span></div>
        <div className="flex gap-2"><div className="relative flex-1"><input value={query} onChange={event => setQuery(event.target.value)} placeholder="查询编码或名称" className="w-full rounded-lg border border-slate-300 px-3 py-2.5 pr-10 text-xs outline-none focus:border-sky-500" />{query && <button onClick={() => setQuery('')} className="absolute right-2 top-2.5 text-[11px] text-slate-400">清除</button>}</div><select value={differenceFilter} onChange={event => setDifferenceFilter(event.target.value as typeof differenceFilter)} className="w-28 rounded-lg border border-slate-300 px-2 text-xs"><option value="all">全部差异</option><option value="exact">完全一致</option><option value="partial">部分一致</option><option value="inconsistent">不一致</option><option value="no_comparable">无可比</option><option value="unassessed">未评测</option></select></div>
        <div className="mt-3 flex flex-wrap gap-1.5">{(['all', 'waiting', 'processing', 'retrying', 'completed', 'failed', 'review'] as StatusFilter[]).map(value => <button key={value} onClick={() => setStatusFilter(value)} className={`rounded-full border px-2.5 py-1 text-[11px] ${statusFilter === value ? 'border-slate-800 bg-slate-800 text-white' : 'border-slate-200 text-slate-600 hover:bg-slate-50'}`}>{value === 'all' ? '全部' : value === 'review' ? '待复核' : EXECUTION[value][0]}</button>)}</div>
        <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1.5 border-t border-slate-100 pt-3 text-[11px]"><span className="mr-1 text-slate-400">选择</span>{[['全部', () => selectWhere(() => true)], ['清空', () => setSelected(new Set())], ['反选', invert], ['等待', () => selectWhere(item => item.execution_status === 'waiting')], ['失败', () => selectWhere(item => item.execution_status === 'failed')], ['待复核', () => selectWhere(item => ['partial', 'inconsistent'].includes(item.consistency_status))]].map(([label, action]) => <button key={label as string} disabled={active} onClick={action as () => void} className="font-medium text-sky-700 disabled:text-slate-300">{label as string}</button>)}</div>
      </div><div className="max-h-[calc(100vh-350px)] overflow-y-auto">{visible.map(item => <ItemCard key={item.id} item={item} focused={item.id === focusedId} selected={selected.has(item.id)} disabled={active} onFocus={() => { setFocusedId(item.id); setView('process') }} onCheck={checked => setSelected(current => { const next = new Set(current); checked ? next.add(item.id) : next.delete(item.id); return next })} />)}{!visible.length && <div className="py-16 text-center text-xs text-slate-400">没有符合条件的清单</div>}</div></aside>

      <section className="min-w-0"><div className="mb-4 flex items-center justify-between rounded-xl border border-slate-200 bg-white p-2 shadow-sm"><div className="flex gap-1"><button onClick={() => setView('process')} className={`rounded-lg px-4 py-2.5 text-sm font-semibold ${view === 'process' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'}`}>过程监控</button><button onClick={() => setView('results')} className={`rounded-lg px-4 py-2.5 text-sm font-semibold ${view === 'results' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'}`}>结果汇总</button></div>{error && <span className="max-w-xl truncate px-3 text-xs text-rose-600">{error}</span>}</div>
        {view === 'results' ? <Results items={workspace.items} onOpen={id => { setFocusedId(id); setResultDetailOpen(true) }} /> : !focused ? <Empty>请选择左侧清单</Empty> : <div className="space-y-5"><div className="rounded-2xl border border-slate-200 bg-white px-6 py-5 shadow-sm"><div className="flex items-start justify-between gap-6"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs text-sky-700">{focused.item_code}</span><Badge value="" meta={EXECUTION[focused.execution_status]} /><Badge value="" meta={CONSISTENCY[focused.consistency_status]} /></div><h2 className="mt-2 truncate text-xl font-semibold tracking-tight">{focused.item_name}</h2><div className="mt-2 text-sm text-slate-500">单位 {focused.unit || '—'} <span className="mx-2 text-slate-300">·</span> 工程量 {focused.quantity ?? '—'} <span className="mx-2 text-slate-300">·</span> 候选 {focused.candidate_count} <span className="mx-2 text-slate-300">·</span> 定额结果 {focused.match_count} <span className="mx-2 text-slate-300">·</span> 耗时 {duration(focused.duration_ms)}</div></div>{reviewable && <button onClick={() => setReviewOpen(true)} className="shrink-0 rounded-lg border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm font-semibold text-amber-800 hover:bg-amber-100">复核差异并修正人工工程</button>}</div></div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div className="mb-4 flex items-center justify-between"><h3 className="text-sm font-semibold">工具调用</h3><span className="text-xs text-slate-400">仅显示工具、状态、耗时和输出</span></div><ToolFeed run={detail?.run || null} /></div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div className="mb-5 flex flex-wrap gap-2 border-b border-slate-100 pb-4">{([['item', '清单与特征'], ['candidates', '章节与候选'], ['quota', '定额与人工对比'], ['conversion', '换算与系数']] as Array<[Stage, string]>).map(([value, label]) => <button key={value} onClick={() => setStage(value)} className={`rounded-lg px-3.5 py-2 text-xs font-semibold ${stage === value ? 'bg-sky-700 text-white shadow-sm' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>{label}</button>)}</div><StageResult stage={stage} detail={detail} /></div></div>}
      </section>
    </div>
    {resultDetailOpen && (!detail || detail.item.id !== focusedId) && <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/40"><div className="rounded-lg bg-white px-6 py-4 text-sm text-gray-500 shadow-xl">加载组价详细结果…</div></div>}
    {resultDetailOpen && detail && detail.item.id === focusedId && <BatchPricingResultDetailModal item={detail.item} result={{ quotaMatch: detail.run?.quota_match, evaluation: detail.run?.evaluation, conversionCheck: detail.run?.conversion_check, coefficientCheck: detail.run?.coefficient_check }} onClose={() => setResultDetailOpen(false)} onReview={reviewable ? () => { setResultDetailOpen(false); setReviewOpen(true) } : undefined} />}
    {reviewOpen && detail?.run?.id && detail.run.evaluation && reviewable && <ManualComparisonReviewModal open item={detail.item} evaluation={detail.run.evaluation} matches={detail.run.quota_match?.matches || []} submitReview={input => updatePricingTaskBatchManualComparison(detail.run!.id, input)} loadHistory={() => fetchPricingTaskBatchManualComparisonHistory(detail.run!.id)} onClose={() => setReviewOpen(false)} onUpdated={() => { setReviewOpen(false); void load(true); void fetchBackgroundPricingTaskItemDetail(batchId, detail.item.id).then(setDetail) }} />}
  </main>
}

function ItemCard({ item, focused, selected, disabled, onFocus, onCheck }: { item: BackgroundBatchWorkspaceItem; focused: boolean; selected: boolean; disabled: boolean; onFocus: () => void; onCheck: (checked: boolean) => void }) {
  return <div onClick={onFocus} className={`flex cursor-pointer gap-3 border-b border-slate-100 px-4 py-4 transition-colors ${focused ? 'bg-sky-50/80' : 'hover:bg-slate-50'}`}><input type="checkbox" disabled={disabled} checked={selected} onClick={event => event.stopPropagation()} onChange={event => onCheck(event.target.checked)} className="mt-1 h-4 w-4 disabled:opacity-30" /><div className="min-w-0 flex-1"><div className="flex justify-between gap-2"><span className="truncate font-mono text-[11px] text-slate-500">{item.item_code}</span><span className="text-[11px] text-slate-400">{duration(item.duration_ms)}</span></div><div className="mt-0.5 truncate text-sm font-medium">{item.item_name}</div><div className="mt-2 flex flex-wrap gap-1"><Badge value="" meta={EXECUTION[item.execution_status]} /><Badge value="" meta={CONSISTENCY[item.consistency_status]} />{item.attempt_count > 1 && <Badge value={`第 ${item.attempt_count} 次`} meta={['', 'border-amber-200 bg-amber-50 text-amber-700']} />}</div><div className="mt-2 flex justify-between gap-3 text-[10px] text-slate-400"><span className="truncate">{item.current_tool ? TOOLS.find(([id]) => id === item.current_tool)?.[1] || item.current_tool : '尚未调用工具'}</span><span className="shrink-0">候选 {item.candidate_count} · 结果 {item.match_count}</span></div>{item.error_message && <div className="mt-1.5 truncate text-[10px] text-rose-600">{item.error_message}</div>}</div></div>
}

function Results({ items, onOpen }: { items: BackgroundBatchWorkspaceItem[]; onOpen: (id: number) => void }) {
  return <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><div className="border-b border-slate-200 px-4 py-3"><h3 className="text-sm font-bold">清单套定额结果</h3><p className="text-[10px] text-slate-400">执行状态与差异状态分列展示，共 {items.length} 条</p></div><div className="max-h-[calc(100vh-260px)] overflow-auto"><table className="w-full text-xs"><thead className="sticky top-0 bg-slate-50 text-slate-500"><tr>{['清单编码 / 名称', '执行状态', '差异状态', '候选', '定额', '命中', '漏项', '多项', '耗时', '尝试', '操作'].map((head, index) => <th key={head} className={`px-3 py-2.5 ${index === 0 || index < 3 ? 'text-left' : 'text-right'}`}>{head}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{items.map(item => <tr key={item.id} className="hover:bg-slate-50"><td className="max-w-sm px-3 py-2.5"><div className="truncate font-mono text-[9px] text-slate-500">{item.item_code}</div><div className="truncate font-semibold">{item.item_name}</div></td><td className="px-3 py-2.5"><Badge value="" meta={EXECUTION[item.execution_status]} /></td><td className="px-3 py-2.5"><Badge value="" meta={CONSISTENCY[item.consistency_status]} /></td>{[item.candidate_count, item.match_count, item.hit_count, item.missed_count, item.extra_count].map((value, index) => <td key={index} className={`px-3 py-2.5 text-right tabular-nums ${index === 2 ? 'text-emerald-700' : index === 3 ? 'text-amber-700' : index === 4 ? 'text-rose-700' : ''}`}>{value}</td>)}<td className="px-3 py-2.5 text-right text-slate-500">{duration(item.duration_ms)}</td><td className="px-3 py-2.5 text-right">{item.attempt_count || '—'}</td><td className="px-3 py-2.5 text-right"><button onClick={() => onOpen(item.id)} className="font-semibold text-sky-700">查看详情</button></td></tr>)}</tbody></table></div></div>
}
