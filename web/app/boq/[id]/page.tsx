'use client'
import { useState, useEffect, useRef, Fragment } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  fetchBoqProjects, fetchAllBoqItems, fetchBoqRuns, startMatchBoqProject,
  streamMatchBoqProject,
  fetchQuotaStandards, BoqProject, BoqItem, BoqMatchRun, StreamMatch,
} from '@/lib/api'
import type { QuotaStandard } from '@/lib/api'

// ── 流式面板 ──────────────────────────────────────────────────────────────────

interface CompletedItem {
  boq_item_id: number
  item_name: string
  matches: StreamMatch[]
  elapsed: number  // 毫秒
}

interface StreamPanelState {
  runId: number | null
  total: number
  currentIndex: number
  currentItemName: string
  reasoningBuffer: string
  completedItems: CompletedItem[]
  done: boolean
}

function StreamPanel({ state, onScrollRef }: { state: StreamPanelState; onScrollRef: React.RefObject<HTMLDivElement | null> }) {
  const confColor = (c: string) =>
    c === 'high' ? 'text-green-700 bg-green-100' :
    c === 'medium' ? 'text-yellow-700 bg-yellow-100' :
    'text-red-700 bg-red-100'

  return (
    <div className="border border-indigo-200 rounded-lg bg-white shadow-sm overflow-hidden">
      {/* 标题栏 */}
      <div className="px-4 py-2.5 bg-indigo-50 border-b border-indigo-100 flex items-center gap-2">
        {!state.done
          ? <span className="animate-spin inline-block w-3.5 h-3.5 border-2 border-indigo-500 border-t-transparent rounded-full shrink-0" />
          : <span className="text-green-600 shrink-0">✓</span>}
        <span className="text-sm font-medium text-indigo-800">
          {state.done
            ? `套定额完成（${state.completedItems.filter(i => i.matches.length > 0).length}/${state.total} 项命中）`
            : `正在处理第 ${state.currentIndex} / ${state.total} 条：${state.currentItemName}`}
        </span>
      </div>

      {/* 当前推理区（流式文字） */}
      {!state.done && state.reasoningBuffer && (
        <div className="px-4 py-3 border-b border-indigo-100 bg-indigo-50/40 max-h-64 overflow-y-auto" ref={onScrollRef}>
          <div className="text-xs font-medium text-indigo-600 mb-1.5">🧠 AI 推理中…</div>
          <div className="text-xs text-gray-700 leading-relaxed whitespace-pre-wrap font-mono">
            {state.reasoningBuffer}
            <span className="inline-block w-1.5 h-3.5 bg-indigo-400 ml-0.5 animate-pulse align-middle" />
          </div>
        </div>
      )}

      {/* 已完成条目列表 */}
      <div className="divide-y divide-gray-100 max-h-80 overflow-y-auto">
        {[...state.completedItems].reverse().map(item => (
          <div key={item.boq_item_id} className="flex items-start gap-3 px-4 py-2 text-xs hover:bg-gray-50">
            <span className="text-green-500 shrink-0 mt-0.5">✓</span>
            <span className="text-gray-600 w-32 shrink-0 truncate">{item.item_name}</span>
            <span className="text-gray-300 shrink-0">{(item.elapsed / 1000).toFixed(1)}s</span>
            {item.matches.length === 0
              ? <span className="text-gray-400">— 无匹配</span>
              : <div className="flex flex-wrap gap-1.5">
                  {item.matches.map((m, i) => (
                    <span key={i} className="flex items-center gap-1">
                      <span className="font-mono text-blue-600 font-medium">{m.quota_item_code}</span>
                      <span className="text-gray-700 truncate max-w-[160px]">{m.quota_item_name}{m.quota_variant_desc ? `（${m.quota_variant_desc}）` : ''}</span>
                      <span className={`px-1 py-0.5 rounded text-xs ${confColor(m.confidence)}`}>{m.confidence === 'high' ? '高' : m.confidence === 'medium' ? '中' : '低'}</span>
                    </span>
                  ))}
                </div>
            }
          </div>
        ))}
      </div>
    </div>
  )
}

// ── 分部树（只读）────────────────────────────────────────────────────────────

function SectionTree({ items }: { items: BoqItem[] }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [expandedItem, setExpandedItem] = useState<number | null>(null)
  const map = new Map<string, BoqItem[]>()
  for (const it of items) {
    const k = it.section_name ?? '未分类'
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(it)
  }
  const sections = Array.from(map.entries())

  const toggle = (k: string) =>
    setExpanded(prev => { const n = new Set(prev); n.has(k) ? n.delete(k) : n.add(k); return n })

  return (
    <div className="divide-y divide-gray-100">
      {sections.map(([name, its]) => (
        <div key={name}>
          <button
            className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-gray-50 group"
            onClick={() => toggle(name)}
          >
            <span className={`w-4 h-4 flex items-center justify-center rounded border text-xs font-bold shrink-0 ${expanded.has(name) ? 'border-blue-400 text-blue-600 bg-blue-50' : 'border-gray-300 text-gray-500'}`}>
              {expanded.has(name) ? '−' : '+'}
            </span>
            <span className="font-medium text-gray-700 text-sm">{name}</span>
            <span className="ml-auto text-xs text-gray-400">{its.length} 项</span>
          </button>
          {expanded.has(name) && (
            <div className="bg-gray-50/50">
              {its.map(it => (
                <div key={it.id}>
                  <div
                    className={`flex items-center gap-2 pl-8 pr-3 py-2 text-xs border-b border-gray-100 cursor-pointer hover:bg-gray-100/60 ${expandedItem === it.id ? 'bg-blue-50/50' : ''}`}
                    onClick={() => setExpandedItem(expandedItem === it.id ? null : it.id)}
                  >
                    <span className="font-mono text-blue-600 shrink-0 w-32 truncate">{it.item_code}</span>
                    <span className="text-gray-700 flex-1 truncate">{it.item_name}</span>
                    <span className="text-gray-400 shrink-0">{it.unit}</span>
                    <span className="text-gray-600 tabular-nums shrink-0 w-20 text-right">
                      {it.quantity?.toLocaleString('zh-CN', { maximumFractionDigits: 4 }) ?? '—'}
                    </span>
                    {it.item_description && (
                      <span className="text-gray-400 select-none shrink-0">{expandedItem === it.id ? '▲' : '▼'}</span>
                    )}
                  </div>
                  {expandedItem === it.id && it.item_description && (
                    <div className="pl-10 pr-3 py-2 bg-white border-b border-gray-100">
                      <div className="text-xs text-gray-400 mb-1 font-medium">项目特征描述</div>
                      <div className="text-xs text-gray-500 leading-relaxed space-y-0.5">
                        {it.item_description.split('\n').filter(Boolean).map((l, i) => (
                          <div key={i}>{l}</div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ── run 状态标签 ─────────────────────────────────────────────────────────────

function RunStatus({ status }: { status: string }) {
  const map: Record<string, string> = {
    running: 'bg-yellow-100 text-yellow-700',
    done: 'bg-green-100 text-green-700',
    error: 'bg-red-100 text-red-600',
  }
  const label: Record<string, string> = { running: '进行中', done: '已完成', error: '出错' }
  return <span className={`text-xs px-1.5 py-0.5 rounded ${map[status] ?? 'bg-gray-100 text-gray-500'}`}>{label[status] ?? status}</span>
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

export default function BoqDetailPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = Number(params.id)

  const [project, setProject] = useState<BoqProject | null>(null)
  const [items, setItems] = useState<BoqItem[]>([])
  const [runs, setRuns] = useState<BoqMatchRun[]>([])
  const [standards, setStandards] = useState<QuotaStandard[]>([])
  const [standardId, setStandardId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [matching, setMatching] = useState(false)

  // 流式推理状态
  const [streamState, setStreamState] = useState<StreamPanelState | null>(null)
  const reasoningScrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    Promise.all([
      fetchBoqProjects(),
      fetchAllBoqItems(projectId),
      fetchBoqRuns(projectId),
      fetchQuotaStandards(),
    ]).then(([projs, its, rs, stds]) => {
      setProject(projs.find(p => p.id === projectId) ?? null)
      setItems(its)
      setRuns(rs)
      setStandards(stds)
      if (stds.length) setStandardId(stds[0].id)
    }).catch(e => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false))
  }, [projectId])

  // 推理文字滚动到底
  useEffect(() => {
    if (reasoningScrollRef.current) {
      reasoningScrollRef.current.scrollTop = reasoningScrollRef.current.scrollHeight
    }
  }, [streamState?.reasoningBuffer])

  const handleNewRun = async () => {
    if (!standardId) return
    setMatching(true)
    setStreamState({
      runId: null, total: items.length, currentIndex: 0,
      currentItemName: '准备中…', reasoningBuffer: '',
      completedItems: [], done: false,
    })

    try {
      let finalRunId: number | null = null
    let itemStartTime = 0

    await streamMatchBoqProject(projectId, standardId, (evt) => {
        if (evt.type === 'run_start') {
          finalRunId = evt.run_id
          setStreamState(s => s ? { ...s, runId: evt.run_id, total: evt.total } : s)
        }
        else if (evt.type === 'item_start') {
          itemStartTime = Date.now()
          setStreamState(s => s ? {
            ...s,
            currentIndex: evt.index,
            currentItemName: evt.item_name,
            reasoningBuffer: '',
          } : s)
        }
        else if (evt.type === 'reasoning_token') {
          setStreamState(s => s ? {
            ...s,
            reasoningBuffer: s.reasoningBuffer + evt.token,
          } : s)
        }
        else if (evt.type === 'item_done') {
          const elapsed = Date.now() - itemStartTime
          setStreamState(s => {
            if (!s) return s
            return {
              ...s,
              reasoningBuffer: '',
              completedItems: [...s.completedItems, {
                boq_item_id: evt.boq_item_id,
                item_name: s.currentItemName,
                matches: evt.matches,
                elapsed,
              }],
            }
          })
        }
        else if (evt.type === 'run_done') {
          setStreamState(s => s ? { ...s, done: true, reasoningBuffer: '' } : s)
        }
      })

      // 刷新 runs 列表
      const rs = await fetchBoqRuns(projectId)
      setRuns(rs)

      // 完成后跳到结果页
      if (finalRunId) {
        setTimeout(() => router.push(`/boq/${projectId}/run/${finalRunId}`), 1500)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '套定额失败')
      setStreamState(s => s ? { ...s, done: true } : s)
    } finally {
      setMatching(false)
    }
  }

  if (loading) return <div className="text-center text-gray-400 py-20 animate-pulse">加载中…</div>
  if (!project) return <div className="text-center text-gray-400 py-20">工程不存在</div>

  return (
    <div>
      {/* 面包屑 */}
      <div className="flex items-center gap-1.5 text-sm text-gray-500 mb-4">
        <Link href="/boq" className="hover:text-blue-600">工程管理</Link>
        <span>/</span>
        <span className="text-gray-800 font-medium">{project.project_name}</span>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4 text-sm">{error}</div>}

      {/* 第一行：定额选择 + 套定额按钮 */}
      <div className="bg-white rounded-lg shadow p-4 mb-4 flex flex-wrap gap-3 items-center">
        <label className="text-sm text-gray-600 shrink-0">定额标准</label>
        <select
          value={standardId ?? ''}
          onChange={e => setStandardId(Number(e.target.value))}
          disabled={matching}
          className="flex-1 min-w-[200px] border rounded px-2 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400 disabled:opacity-50"
        >
          {standards.map(s => (
            <option key={s.id} value={s.id}>{s.region ? `[${s.region}] ` : ''}{s.name}（{s.standard_code}）</option>
          ))}
        </select>
        <button
          onClick={handleNewRun}
          disabled={matching || !standardId}
          className="px-5 py-1.5 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2 shrink-0"
        >
          {matching
            ? <><span className="animate-spin inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full" />运行中</>
            : '🤖 开始套定额'}
        </button>

        {/* 历史记录摘要（不在运行时显示） */}
        {!matching && runs.length > 0 && (
          <div className="ml-auto flex items-center gap-3 text-xs text-gray-400">
            <span>历史 {runs.length} 次</span>
            {runs[0] && (
              <Link href={`/boq/${projectId}/run/${runs[0].id}`} className="text-blue-600 hover:underline">
                最近记录 →
              </Link>
            )}
          </div>
        )}
      </div>

      {/* 第二行：清单概览 */}
      <div className="bg-white rounded-lg shadow mb-4">
        <div className="px-4 py-3 border-b flex items-center justify-between">
          <span className="font-medium text-gray-700">清单概览</span>
          <span className="text-xs text-gray-400">{items.length} 个清单项</span>
        </div>
        {items.length === 0
          ? <div className="text-center text-gray-400 py-10 text-sm">暂无清单项</div>
          : <SectionTree items={items} />}
      </div>

      {/* 第三行：流式推理面板（全宽） */}
      {streamState && (
        <StreamPanel state={streamState} onScrollRef={reasoningScrollRef} />
      )}

      {/* 历史批次列表（无流式时显示） */}
      {!streamState && runs.length > 0 && (
        <div className="bg-white rounded-lg shadow">
          <div className="px-4 py-3 border-b font-medium text-gray-700">套定额记录</div>
          <div className="divide-y divide-gray-100">
            {runs.map(run => (
              <div key={run.id} className="px-4 py-3 hover:bg-gray-50 flex items-center gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-sm font-medium text-gray-700">{run.standard_code ?? `标准 #${run.standard_id}`}</span>
                    <RunStatus status={run.status} />
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-400">
                    <span>{new Date(run.created_at).toLocaleString('zh-CN')}</span>
                    <span>{run.matched_items} / {run.total_items} 项已匹配</span>
                  </div>
                </div>
                <Link
                  href={`/boq/${projectId}/run/${run.id}`}
                  className="text-xs text-blue-600 hover:underline shrink-0"
                >查看结果 →</Link>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
