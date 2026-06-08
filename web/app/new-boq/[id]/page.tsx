'use client'
import { useState, useEffect, useRef } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { fetchBoqProjects, fetchAllBoqItems, BoqProject, BoqItem } from '@/lib/api'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface Chapter {
  id: number
  chapter_no: number
  title: string
  subitem_count: number
}

interface MatchRun {
  id: number
  chapter_id: number
  chapter_name: string
  run_name: string | null
  status: string
  total_items: number
  matched_items: number
  created_at: string
  finished_at: string | null
}

interface StreamMatchItem {
  subitem_id: number
  subitem_code: string
  work_procedure: string
  confidence: string
  qty_factor: number
}

interface CompletedItem {
  boq_item_id: number
  item_name: string
  matches: StreamMatchItem[]
}

interface StreamState {
  runId: number | null
  total: number
  currentIndex: number
  currentItemName: string
  reasoningBuffer: string
  completedItems: CompletedItem[]
  done: boolean
  chapterName: string
}

// ── 流式面板 ──────────────────────────────────────────────────────────────────

function StreamPanel({ state, scrollRef, projectId }: {
  state: StreamState
  scrollRef: React.Ref<HTMLDivElement>
  projectId: number
}) {
  const confColor = (c: string) =>
    c === 'high' ? 'text-green-700 bg-green-50' :
    c === 'medium' ? 'text-yellow-700 bg-yellow-50' :
    'text-red-700 bg-red-50'
  const confLabel = (c: string) => c === 'high' ? '高' : c === 'medium' ? '中' : '低'

  return (
    <div className="border border-indigo-200 rounded-lg bg-white shadow-sm overflow-hidden flex flex-col">
      <div className="px-4 py-2.5 bg-indigo-50 border-b border-indigo-100 flex items-center gap-2 shrink-0">
        {!state.done
          ? <span className="animate-spin inline-block w-3.5 h-3.5 border-2 border-indigo-500 border-t-transparent rounded-full shrink-0" />
          : <span className="text-green-600 shrink-0">✓</span>}
        <span className="text-sm font-medium text-indigo-800">
          {state.done
            ? `套定额完成（${state.completedItems.filter(i => i.matches.length > 0).length}/${state.total} 项命中）`
            : `[${state.currentIndex}/${state.total}] ${state.currentItemName}`}
        </span>
        {state.runId && (
          <Link
            href={`/new-boq/${projectId}/run/${state.runId}`}
            className="ml-auto text-xs text-indigo-600 hover:underline shrink-0"
          >
            查看结果 →
          </Link>
        )}
      </div>

      {!state.done && state.reasoningBuffer && (
        <div className="px-4 py-3 border-b border-indigo-100 bg-indigo-50/40 max-h-96 overflow-y-auto shrink-0" ref={scrollRef}>
          <div className="text-xs font-medium text-indigo-600 mb-1">🧠 AI 推理中…</div>
          <div className="text-xs text-gray-600 leading-relaxed whitespace-pre-wrap font-mono">
            {state.reasoningBuffer}
            <span className="inline-block w-1.5 h-3.5 bg-indigo-400 ml-0.5 animate-pulse align-middle" />
          </div>
        </div>
      )}

      <div className="divide-y divide-gray-100 overflow-y-auto flex-1" style={{ maxHeight: 480 }}>
        {[...state.completedItems].reverse().map(item => (
          <div key={item.boq_item_id} className="px-4 py-2 text-xs hover:bg-gray-50">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-green-500 shrink-0">✓</span>
              <span className="text-gray-700 font-medium truncate flex-1">{item.item_name}</span>
              {item.matches.length === 0 && <span className="text-gray-400">— 无匹配</span>}
            </div>
            {item.matches.length > 0 && (
              <div className="pl-4 space-y-0.5">
                {item.matches.map((m, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className="font-mono text-blue-600 shrink-0">{m.subitem_code}</span>
                    <span className="text-gray-500 truncate flex-1">{m.work_procedure}</span>
                    <span className={`px-1.5 py-0.5 rounded text-xs shrink-0 ${confColor(m.confidence)}`}>
                      {confLabel(m.confidence)}
                    </span>
                    <span className="text-gray-400 shrink-0">×{m.qty_factor}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── 清单项列表（含多选）──────────────────────────────────────────────────────

function ItemList({
  items, selected, onToggle, onToggleAll,
}: {
  items: BoqItem[]
  selected: Set<number>
  onToggle: (id: number) => void
  onToggleAll: (ids: number[], checked: boolean) => void
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [expandedItem, setExpandedItem] = useState<Set<number>>(new Set())
  const map = new Map<string, BoqItem[]>()
  for (const it of items) {
    const k = it.section_name ?? '未分类'
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(it)
  }

  const toggle = (k: string) =>
    setExpanded(prev => { const n = new Set(prev); n.has(k) ? n.delete(k) : n.add(k); return n })

  return (
    <div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
      <div className="px-3 py-2 bg-gray-50 border-b border-gray-200 flex items-center gap-2 text-xs text-gray-500">
        <input
          type="checkbox"
          checked={items.length > 0 && items.every(it => selected.has(it.id))}
          onChange={e => onToggleAll(items.map(it => it.id), e.target.checked)}
          className="rounded"
        />
        <span>全选 ({selected.size}/{items.length})</span>
      </div>
      <div className="divide-y divide-gray-100 max-h-[480px] overflow-y-auto">
        {Array.from(map.entries()).map(([name, its]) => (
          <div key={name}>
            <button
              className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-gray-50"
              onClick={() => toggle(name)}
            >
              <input
                type="checkbox"
                checked={its.every(it => selected.has(it.id))}
                onChange={e => { e.stopPropagation(); onToggleAll(its.map(it => it.id), e.target.checked) }}
                onClick={e => e.stopPropagation()}
                className="rounded shrink-0"
              />
              <span className={`w-3.5 h-3.5 flex items-center justify-center rounded border text-xs shrink-0 ${expanded.has(name) ? 'border-blue-400 text-blue-600' : 'border-gray-300 text-gray-500'}`}>
                {expanded.has(name) ? '−' : '+'}
              </span>
              <span className="font-medium text-gray-700 text-sm">{name}</span>
              <span className="ml-auto text-xs text-gray-400">{its.length} 项</span>
            </button>
            {expanded.has(name) && (
              <div className="bg-gray-50/50">
                {its.map(it => (
                  <div key={it.id} className="border-b border-gray-100">
                    <div
                      className="flex items-center gap-2 pl-8 pr-3 py-1.5 text-xs cursor-pointer hover:bg-gray-100/60"
                      onClick={() => setExpandedItem(prev => {
                        const n = new Set(prev); n.has(it.id) ? n.delete(it.id) : n.add(it.id); return n
                      })}
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(it.id)}
                        onChange={() => onToggle(it.id)}
                        onClick={e => e.stopPropagation()}
                        className="rounded shrink-0"
                      />
                      <span className="font-mono text-blue-600 shrink-0 w-24 truncate">{it.item_code}</span>
                      <span className="text-gray-700 flex-1 truncate">{it.item_name}</span>
                      <span className="text-gray-400 shrink-0">{it.unit}</span>
                      <span className="text-gray-500 tabular-nums shrink-0 w-16 text-right">
                        {it.quantity?.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) ?? '—'}
                      </span>
                      {it.item_description && (
                        <span className="text-gray-300 shrink-0 ml-1">{expandedItem.has(it.id) ? '▲' : '▼'}</span>
                      )}
                    </div>
                    {expandedItem.has(it.id) && it.item_description && (
                      <div className="pl-12 pr-3 py-2 bg-white">
                        <div className="text-xs text-gray-400 mb-1 font-medium">项目特征</div>
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
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

export default function NewBoqDetailPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = Number(params.id)

  const [project, setProject] = useState<BoqProject | null>(null)
  const [allItems, setAllItems] = useState<BoqItem[]>([])
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [runs, setRuns] = useState<MatchRun[]>([])
  const [loading, setLoading] = useState(true)

  const [chapterIds, setChapterIds] = useState<Set<number>>(new Set())
  const [runName, setRunName] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())

  const [streaming, setStreaming] = useState(false)
  const [streamState, setStreamState] = useState<StreamState | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const readerRef = useRef<ReadableStreamDefaultReader | null>(null)

  const [promptPreview, setPromptPreview] = useState<string | null>(null)
  const [showPrompt, setShowPrompt] = useState(false)
  const [loadingPrompt, setLoadingPrompt] = useState(false)

  const fetchPromptPreview = async () => {
    if (chapterIds.size === 0) return
    setLoadingPrompt(true)
    try {
      const ids = Array.from(chapterIds).join(',')
      const r = await fetch(`${API}/api/bs2024-match/prompt-preview?chapter_ids=${ids}`)
      const d = await r.json()
      setPromptPreview(d.system_prompt || null)
      setShowPrompt(true)
    } finally {
      setLoadingPrompt(false)
    }
  }

  useEffect(() => {
    Promise.all([
      fetchBoqProjects(),
      fetchAllBoqItems(projectId),
      fetch(`${API}/api/bs2024-match/chapters`).then(r => r.json()),
      fetch(`${API}/api/bs2024-match/runs?project_id=${projectId}`).then(r => r.json()),
    ]).then(([projects, items, chs, rs]) => {
      setProject(Array.isArray(projects) ? (projects.find((p: BoqProject) => p.id === projectId) || null) : null)
      setAllItems(Array.isArray(items) ? items : [])
      const chsArr = Array.isArray(chs) ? chs : []
      setChapters(chsArr)
      setRuns(Array.isArray(rs) ? rs : [])
      if (chsArr.length > 0) setChapterIds(new Set([chsArr[0].id]))
      // 默认全选
      const itemsArr = Array.isArray(items) ? items : []
      setSelected(new Set(itemsArr.map((it: BoqItem) => it.id)))
    }).finally(() => setLoading(false))
  }, [projectId])

  const refreshRuns = () => {
    fetch(`${API}/api/bs2024-match/runs?project_id=${projectId}`)
      .then(r => r.json()).then(setRuns)
  }

  const toggleItem = (id: number) =>
    setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })

  const toggleAll = (ids: number[], checked: boolean) =>
    setSelected(prev => {
      const n = new Set(prev)
      ids.forEach(id => checked ? n.add(id) : n.delete(id))
      return n
    })

  const startMatch = async () => {
    if (chapterIds.size === 0 || selected.size === 0) return
    setStreaming(true)
    setStreamState({
      runId: null, total: 0, currentIndex: 0,
      currentItemName: '', reasoningBuffer: '',
      completedItems: [], done: false, chapterName: '',
    })

    const res = await fetch(`${API}/api/bs2024-match/runs/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId,
        chapter_ids: Array.from(chapterIds),
        item_ids: Array.from(selected),
        run_name: runName.trim() || null,
      }),
    })

    if (!res.body) { setStreaming(false); return }
    const reader = res.body.getReader()
    readerRef.current = reader
    const decoder = new TextDecoder()
    let buf = ''

    const process = async () => {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const ev = JSON.parse(line.slice(6))
            setStreamState(prev => {
              if (!prev) return prev
              switch (ev.type) {
                case 'run_start':
                  return { ...prev, runId: ev.run_id, total: ev.total, chapterName: ev.chapter_name || '' }
                case 'item_start':
                  return { ...prev, currentIndex: ev.index, currentItemName: ev.item_name, reasoningBuffer: '' }
                case 'reasoning_token':
                  return { ...prev, reasoningBuffer: prev.reasoningBuffer + ev.token }
                case 'item_done':
                  return {
                    ...prev, reasoningBuffer: '',
                    completedItems: [...prev.completedItems, {
                      boq_item_id: ev.boq_item_id,
                      item_name: prev.currentItemName,
                      matches: ev.matches || [],
                    }],
                  }
                case 'run_done':
                  return { ...prev, done: true }
                default:
                  return prev
              }
            })
            if (ev.type === 'run_done') {
              refreshRuns()
            }
          } catch { /* ignore parse error */ }
        }
        if (scrollRef.current) {
          scrollRef.current.scrollTop = scrollRef.current.scrollHeight
        }
      }
      setStreaming(false)
    }

    process().catch(() => setStreaming(false))
  }

  const stopMatch = () => {
    readerRef.current?.cancel()
    setStreaming(false)
  }

  if (loading) return <div className="text-center text-gray-400 py-16 animate-pulse">加载中…</div>
  if (!project) return <div className="text-center text-gray-400 py-16">工程不存在</div>

  const selectedChapters = chapters.filter(c => chapterIds.has(c.id))
  const totalSubitems = selectedChapters.reduce((s, c) => s + c.subitem_count, 0)

  return (
    <div className="space-y-4">
      {/* 面包屑 */}
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Link href="/new-boq" className="hover:text-gray-700">新工程管理</Link>
        <span>/</span>
        <span className="text-gray-800 font-medium">{project.project_name}</span>
      </div>

      {/* 主体：清单列表（左）+ 配置区（右）*/}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4 items-start">
        {/* 左：清单列表 */}
        <div>
          <div className="text-xs font-medium text-gray-500 mb-2 uppercase tracking-wide">
            清单项列表
          </div>
          <ItemList
            items={allItems}
            selected={selected}
            onToggle={toggleItem}
            onToggleAll={toggleAll}
          />
        </div>

        {/* 右：定额配置 */}
        <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-4">
          <div className="text-xs font-medium text-gray-500 uppercase tracking-wide">套定额配置</div>

          {/* 专业选择 */}
          <div>
            <label className="block text-xs text-gray-500 mb-2">定额专业（可多选）</label>
            <div className={`flex flex-col gap-1.5 ${streaming ? 'opacity-50 pointer-events-none' : ''}`}>
              {chapters.map(c => {
                const checked = chapterIds.has(c.id)
                return (
                  <label
                    key={c.id}
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs cursor-pointer select-none transition-colors ${
                      checked
                        ? 'bg-indigo-600 border-indigo-600 text-white'
                        : 'bg-white border-gray-200 text-gray-600 hover:border-indigo-300 hover:bg-indigo-50'
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="hidden"
                      checked={checked}
                      onChange={e => {
                        setChapterIds(prev => {
                          const n = new Set(prev)
                          e.target.checked ? n.add(c.id) : n.delete(c.id)
                          return n
                        })
                        setShowPrompt(false)
                        setPromptPreview(null)
                      }}
                    />
                    <span className="flex-1">第{c.chapter_no}章 {c.title}</span>
                    <span className={`shrink-0 ${checked ? 'text-indigo-200' : 'text-gray-400'}`}>
                      {c.subitem_count}目
                    </span>
                  </label>
                )
              })}
            </div>
          </div>

          {/* 已选统计 */}
          <div className="text-xs text-gray-500 space-y-0.5">
            <div>已选清单：<span className="font-medium text-gray-700">{selected.size} 条</span></div>
            {selectedChapters.length > 0 && (
              <div>定额子目：<span className="font-medium text-gray-700">{totalSubitems} 个</span></div>
            )}
          </div>
        </div>
      </div>

      {/* 批次名称 + 提示词预览 + 操作按钮 */}
      <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-3">
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label className="block text-xs text-gray-500 mb-1">批次名称</label>
            <input
              type="text"
              value={runName}
              onChange={e => setRunName(e.target.value)}
              disabled={streaming}
              placeholder="可选，方便区分多次套定额结果"
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </div>
          <button
            onClick={() => showPrompt ? setShowPrompt(false) : fetchPromptPreview()}
            disabled={chapterIds.size === 0 || loadingPrompt}
            className="px-4 py-1.5 border border-gray-300 text-gray-600 text-sm rounded-lg hover:bg-gray-50 disabled:opacity-40 shrink-0"
          >
            {loadingPrompt ? '加载中…' : showPrompt ? '收起提示词' : '查看提示词'}
          </button>
          {!streaming ? (
            <button
              onClick={startMatch}
              disabled={chapterIds.size === 0 || selected.size === 0}
              className="px-6 py-1.5 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 disabled:opacity-40 font-medium shrink-0"
            >
              开始套定额
            </button>
          ) : (
            <button
              onClick={stopMatch}
              className="px-6 py-1.5 bg-red-500 text-white text-sm rounded-lg hover:bg-red-600 font-medium shrink-0"
            >
              停止
            </button>
          )}
        </div>

        {/* 提示词预览区 */}
        {showPrompt && promptPreview && (
          <div className="border border-gray-200 rounded-lg overflow-hidden">
            <div className="px-3 py-2 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
              <span className="text-xs font-medium text-gray-600">系统提示词（发送给大模型）</span>
              <span className="text-xs text-gray-400">{promptPreview.length.toLocaleString()} 字符</span>
            </div>
            <pre className="text-xs text-gray-700 leading-relaxed p-4 max-h-96 overflow-y-auto whitespace-pre-wrap font-mono bg-white">
              {promptPreview}
            </pre>
          </div>
        )}
      </div>

      {/* 流式推理窗口（运行时全宽展示）*/}
      {streamState && (
        <div>
          <div className="text-xs font-medium text-gray-500 mb-2 uppercase tracking-wide">套定额进度</div>
          <StreamPanel state={streamState} scrollRef={scrollRef} projectId={projectId} />
        </div>
      )}

      {/* 历史批次（始终展示在底部）*/}
      <div>
        <div className="text-xs font-medium text-gray-500 mb-2 uppercase tracking-wide">历史批次</div>
        <div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
          {runs.length === 0 ? (
            <div className="text-center text-gray-400 py-8 text-sm">暂无套定额记录</div>
          ) : (
            <div className="divide-y divide-gray-100">
              {runs.map(r => (
                <div
                  key={r.id}
                  onClick={() => router.push(`/new-boq/${projectId}/run/${r.id}`)}
                  className="flex items-center gap-3 px-4 py-3 text-sm hover:bg-gray-50 cursor-pointer"
                >
                  <span className={`w-2 h-2 rounded-full shrink-0 ${
                    r.status === 'done' ? 'bg-green-500' :
                    r.status === 'running' ? 'bg-blue-400 animate-pulse' :
                    'bg-red-400'
                  }`} />
                  <div className="flex-1 min-w-0">
                    <div className="text-gray-800 font-medium truncate">{r.run_name || `批次 #${r.id}`}</div>
                    <div className="text-xs text-gray-400">{r.chapter_name} · {r.matched_items}/{r.total_items} 项命中</div>
                  </div>
                  <div className="text-xs text-gray-400 shrink-0">
                    {new Date(r.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                  </div>
                  <span className="text-gray-300 shrink-0">›</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
