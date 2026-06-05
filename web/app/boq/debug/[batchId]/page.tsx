'use client'
import { useState, useEffect, useRef } from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  fetchDebugBatch, fetchAllBoqItems, fetchBatchResults, renameDebugBatch,
  streamDebugMatch,
  DebugBatchDetail, BoqItem, DebugMatchQuota, DebugManualQuota, DebugItemResult,
} from '@/lib/api'

// ── 类型 ───────────────────────────────────────────────────────────────────────

interface DebugState {
  phase: 'idle' | 'reasoning' | 'done' | 'error'
  reasoning: string
  matches: DebugMatchQuota[]
  missed: (DebugManualQuota & { missed_by_ai: boolean })[]
  manualQuotas: DebugManualQuota[]
  promptPreview?: { system_prompt: string; system_prompt_len: number; user_message: string }
  ranAt?: string
  error?: string
}

const IDLE: DebugState = { phase: 'idle', reasoning: '', matches: [], missed: [], manualQuotas: [] }

function fromSaved(r: DebugItemResult): DebugState {
  return {
    phase: 'done',
    reasoning: r.reasoning_chain ?? '',
    matches: r.result.matches,
    missed: r.result.missed,
    manualQuotas: r.result.manual_quotas,
    ranAt: r.ran_at,
  }
}

// ── 人工定额列表 ───────────────────────────────────────────────────────────────

function ManualQuotaList({ quotas }: { quotas: DebugManualQuota[] }) {
  if (quotas.length === 0)
    return <p className="text-xs text-gray-400 italic">无人工标准数据</p>
  return (
    <div className="space-y-1">
      {quotas.map((q, i) => (
        <div key={i} className={`flex items-start gap-2 text-xs rounded px-2 py-1 ${q.is_formula ? 'bg-amber-50' : 'bg-green-50'}`}>
          <span className={`font-mono font-medium flex-shrink-0 ${q.is_formula ? 'text-amber-700' : 'text-green-700'}`}>
            {q.quota_code}
          </span>
          <span className="text-gray-600 flex-1">{q.quota_name}</span>
          {q.qty_factor != null && (
            <span className="text-gray-400 flex-shrink-0">×{q.qty_factor}</span>
          )}
          {q.is_formula && <span className="text-amber-500 flex-shrink-0">公式</span>}
        </div>
      ))}
    </div>
  )
}

// ── 匹配结果行 ─────────────────────────────────────────────────────────────────

function MatchRow({ m, expanded, onToggle }: {
  m: DebugMatchQuota
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <div className={`border rounded-lg overflow-hidden ${m.in_manual ? 'border-green-200' : 'border-red-200'}`}>
      <button
        onClick={onToggle}
        className={`w-full text-left px-3 py-2 flex items-center gap-2 text-sm ${m.in_manual ? 'bg-green-50 hover:bg-green-100' : 'bg-red-50 hover:bg-red-100'}`}
      >
        <span>{m.in_manual ? '✅' : '❌'}</span>
        <span className="font-mono text-xs font-medium text-blue-700 flex-shrink-0">{m.quota_item_code}</span>
        <span className="flex-1 truncate text-gray-800">{m.quota_item_name}</span>
        {m.quota_variant_desc && <span className="text-xs text-gray-500 flex-shrink-0">{m.quota_variant_desc}</span>}
        <span className="text-xs text-gray-500 flex-shrink-0">×{m.qty_factor}</span>
        {m.confidence && (
          <span className={`text-xs px-1.5 py-0.5 rounded flex-shrink-0 ${
            m.confidence === 'high' ? 'bg-green-100 text-green-700' :
            m.confidence === 'medium' ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-600'
          }`}>{m.confidence}</span>
        )}
        <span className="text-gray-400 text-xs">{expanded ? '▲' : '▼'}</span>
      </button>
      {expanded && (
        <div className="px-3 py-2 space-y-2 bg-white text-xs">
          {m.work_procedure && <p><span className="text-gray-500">🔨 工序：</span>{m.work_procedure}</p>}
          {m.factor_explanation && <p><span className="text-gray-500">📐 换算：</span>{m.factor_explanation}</p>}
          {m.reasoning && (
            <p className="text-gray-600 border-l-2 border-blue-200 pl-2 whitespace-pre-wrap">{m.reasoning}</p>
          )}
          {(m.total_unit_price != null || m.labor_cost != null) && (
            <div className="flex gap-3 flex-wrap text-gray-600">
              {m.total_unit_price != null && <span>综合单价 <strong>{m.total_unit_price}</strong></span>}
              {m.labor_cost != null && <span>人工 <strong>{m.labor_cost}</strong></span>}
              {m.material_cost != null && <span>材料 <strong>{m.material_cost}</strong></span>}
              {m.machine_cost != null && <span>机械 <strong>{m.machine_cost}</strong></span>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── 批次名内联编辑 ─────────────────────────────────────────────────────────────

function InlineBatchName({ batchId, initialName }: { batchId: number; initialName: string }) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(initialName)
  const [saving, setSaving] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { if (editing) inputRef.current?.select() }, [editing])

  async function save() {
    const trimmed = name.trim()
    if (!trimmed || trimmed === initialName) { setName(initialName); setEditing(false); return }
    setSaving(true)
    try {
      await renameDebugBatch(batchId, trimmed)
    } finally {
      setSaving(false)
      setEditing(false)
    }
  }

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={name}
        onChange={e => setName(e.target.value)}
        onBlur={save}
        onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') { setName(initialName); setEditing(false) } }}
        disabled={saving}
        className="text-lg font-bold text-gray-800 border-b border-indigo-400 outline-none bg-transparent min-w-[200px]"
      />
    )
  }
  return (
    <button onClick={() => setEditing(true)} title="点击编辑批次名"
      className="text-lg font-bold text-gray-800 hover:text-indigo-600 transition text-left">
      {name} <span className="text-xs text-gray-400 font-normal">✏</span>
    </button>
  )
}

// ── 提示词预览面板 ────────────────────────────────────────────────────────────

function PromptPreviewPanel({ preview }: { preview: { system_prompt: string; system_prompt_len: number; user_message: string } }) {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<'system' | 'user'>('user')
  const isTruncated = preview.system_prompt_len > preview.system_prompt.length
  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
      >
        <span className="flex items-center gap-1.5">
          <span className="text-indigo-500">📋</span> 提示词预览
        </span>
        <span className="text-gray-400">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="border-t border-gray-100">
          <div className="flex border-b border-gray-100">
            <button onClick={() => setTab('user')}
              className={`px-4 py-1.5 text-xs font-medium transition ${tab === 'user' ? 'border-b-2 border-indigo-500 text-indigo-600' : 'text-gray-500 hover:text-gray-700'}`}>
              User Message
            </button>
            <button onClick={() => setTab('system')}
              className={`px-4 py-1.5 text-xs font-medium transition ${tab === 'system' ? 'border-b-2 border-indigo-500 text-indigo-600' : 'text-gray-500 hover:text-gray-700'}`}>
              System Prompt（{(preview.system_prompt_len / 1000).toFixed(0)}k 字符）
            </button>
          </div>
          {isTruncated && tab === 'system' && (
            <p className="px-4 py-1.5 text-xs text-amber-600 bg-amber-50 border-b border-amber-100">
              仅显示前 2000 字符，完整内容约 {(preview.system_prompt_len / 1000).toFixed(0)}k 字符（含全量定额子目库）
            </p>
          )}
          <pre className="px-4 py-3 text-xs text-gray-700 whitespace-pre-wrap font-mono overflow-y-auto" style={{ maxHeight: '40vh' }}>
            {tab === 'user' ? preview.user_message : preview.system_prompt}
          </pre>
        </div>
      )}
    </div>
  )
}

// ── 主页面 ─────────────────────────────────────────────────────────────────────

export default function DebugWorkspacePage() {
  const { batchId } = useParams<{ batchId: string }>()
  const router = useRouter()
  const bid = Number(batchId)

  const [batch, setBatch] = useState<DebugBatchDetail | null>(null)
  const [items, setItems] = useState<BoqItem[]>([])
  const [savedStates, setSavedStates] = useState<Map<number, DebugState>>(new Map())

  const [search, setSearch] = useState('')
  const [selectedItem, setSelectedItem] = useState<BoqItem | null>(null)
  const [state, setState] = useState<DebugState>(IDLE)
  const [expandedIdx, setExpandedIdx] = useState<Set<number>>(new Set())
  const [showReasoning, setShowReasoning] = useState(false)
  const reasoningRef = useRef<HTMLDivElement>(null)

  // 加载批次信息 + 清单项 + 已保存结果
  useEffect(() => {
    if (!bid) return
    Promise.all([
      fetchDebugBatch(bid),
      fetchBatchResults(bid),
    ]).then(([b, results]) => {
      setBatch(b)
      return fetchAllBoqItems(b.boq_project_id).then(its => {
        setItems(its)
        // 将已保存结果填充到 savedStates
        const map = new Map<number, DebugState>()
        for (const [itemIdStr, r] of Object.entries(results)) {
          map.set(Number(itemIdStr), fromSaved(r))
        }
        setSavedStates(map)
      })
    }).catch(() => {})
  }, [bid])

  // 推理文字自动滚动
  useEffect(() => {
    if (reasoningRef.current)
      reasoningRef.current.scrollTop = reasoningRef.current.scrollHeight
  }, [state.reasoning])

  // 推理完成后保存到 savedStates
  useEffect(() => {
    if ((state.phase === 'done' || state.phase === 'error') && selectedItem) {
      setSavedStates(prev => new Map(prev).set(selectedItem.id, state))
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.phase])

  const filteredItems = items.filter(it =>
    !search || it.item_name.includes(search) || (it.item_code ?? '').includes(search)
  )

  const canRun = selectedItem && batch && state.phase !== 'reasoning'

  async function handleRun() {
    if (!selectedItem || !batch) return
    setState({ phase: 'reasoning', reasoning: '', matches: [], missed: [], manualQuotas: [] })
    setExpandedIdx(new Set())
    setShowReasoning(true)
    try {
      await streamDebugMatch(
        selectedItem.id,
        batch.standard_ids,
        batch.manual_project_id,
        (evt) => {
          if (evt.type === 'item_info') {
            setState(s => ({
              ...s,
              manualQuotas: evt.manual_quotas,
              ...(evt.system_prompt != null ? {
                promptPreview: {
                  system_prompt: evt.system_prompt,
                  system_prompt_len: evt.system_prompt_len ?? evt.system_prompt.length,
                  user_message: evt.user_message ?? '',
                }
              } : {}),
            }))
          } else if (evt.type === 'reasoning_token') {
            setState(s => ({ ...s, reasoning: s.reasoning + evt.token }))
          } else if (evt.type === 'result') {
            setState(s => ({ ...s, phase: 'done', matches: evt.matches, missed: evt.missed }))
          } else if (evt.type === 'error') {
            setState(s => ({ ...s, phase: 'error', error: evt.error }))
          }
        },
        bid,
      )
    } catch (e: unknown) {
      setState(s => ({ ...s, phase: 'error', error: e instanceof Error ? e.message : '匹配失败' }))
    }
  }

  const descLen = selectedItem?.item_description?.length ?? 0
  const descWarning = descLen === 0 ? '⚠️ 无项目特征描述' : descLen < 30 ? '⚠️ 描述较短' : null

  if (!batch) {
    return <div className="flex items-center justify-center h-64 text-gray-400 text-sm">加载中…</div>
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-4">

      {/* 顶部面包屑 + 批次信息 */}
      <div className="mb-4">
        <div className="flex items-center gap-1.5 text-xs text-gray-400 mb-1">
          <button onClick={() => router.push('/boq/debug')} className="hover:text-indigo-500">套定额调试</button>
          <span>/</span>
          <span className="text-gray-600">{batch.name}</span>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <InlineBatchName batchId={bid} initialName={batch.name} />
          <span className="text-xs text-gray-400 bg-gray-100 rounded px-2 py-0.5">{batch.project_name}</span>
          {batch.standards.map(s => (
            <span key={s.id} className="text-xs text-indigo-600 bg-indigo-50 rounded px-2 py-0.5">{s.standard_code}</span>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-5 gap-5" style={{ height: 'calc(100vh - 130px)' }}>

        {/* ══ 左栏：清单项列表 ════════════════════════════════════════════════════ */}
        <div className="col-span-2 flex flex-col gap-3 overflow-hidden">

          {/* 清单项搜索 */}
          <div className="bg-white rounded-lg border border-gray-200 flex flex-col flex-1 min-h-0">
            <div className="p-3 border-b border-gray-100 flex-shrink-0">
              <input
                type="text" placeholder="搜索清单项名称或编码…"
                value={search} onChange={e => setSearch(e.target.value)}
                className="w-full border border-gray-200 rounded px-2 py-1 text-sm"
              />
            </div>
            <div className="overflow-y-auto flex-1">
              {filteredItems.map(item => {
                const saved = savedStates.get(item.id)
                return (
                  <button
                    key={item.id}
                    onClick={() => {
                      setSelectedItem(item)
                      setState(savedStates.get(item.id) ?? IDLE)
                      setExpandedIdx(new Set())
                      setShowReasoning(false)
                    }}
                    className={`w-full text-left px-3 py-2 border-b border-gray-50 hover:bg-blue-50 transition ${selectedItem?.id === item.id ? 'bg-blue-100' : ''}`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-gray-400 flex-shrink-0">{item.item_code}</span>
                      <span className="text-sm text-gray-800 truncate">{item.item_name}</span>
                      {saved && (
                        <span className="w-2 h-2 rounded-full bg-green-400 flex-shrink-0 ml-auto" title={`已推理 ${saved.ranAt ? new Date(saved.ranAt).toLocaleString('zh-CN') : ''}`} />
                      )}
                    </div>
                    {!item.item_description && (
                      <span className="text-xs text-amber-500">⚠ 无项目特征</span>
                    )}
                  </button>
                )
              })}
              {filteredItems.length === 0 && (
                <p className="text-center text-gray-400 text-sm py-6">无匹配清单项</p>
              )}
            </div>
          </div>

          {/* 选中项详情（可滚动） */}
          {selectedItem && (
            <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-3 overflow-y-auto flex-shrink-0" style={{ maxHeight: '28vh' }}>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <div><span className="text-gray-500">编码：</span><span className="font-mono">{selectedItem.item_code}</span></div>
                <div><span className="text-gray-500">名称：</span>{selectedItem.item_name}</div>
                <div><span className="text-gray-500">单位：</span>{selectedItem.unit}</div>
                <div><span className="text-gray-500">工程量：</span>{selectedItem.quantity}</div>
              </div>

              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs text-gray-500 font-medium">项目特征描述</span>
                  {descWarning && <span className="text-xs text-amber-500">{descWarning}</span>}
                </div>
                <p className="text-xs text-gray-700 whitespace-pre-wrap border border-gray-100 rounded p-2 bg-gray-50">
                  {selectedItem.item_description || '（无）'}
                </p>
              </div>

              {state.phase === 'done' && state.manualQuotas.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 font-medium mb-1">人工标准答案</p>
                  <ManualQuotaList quotas={state.manualQuotas} />
                </div>
              )}
            </div>
          )}

          {/* 推理按钮（始终可见） */}
          <button
            onClick={handleRun} disabled={!canRun}
            className="w-full py-2 rounded-lg text-sm font-medium transition bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0"
          >
            {!selectedItem ? '请先选择清单项' : state.phase === 'reasoning' ? '推理中…' : state.phase === 'done' ? '重新推理' : '开始推理'}
          </button>
        </div>

        {/* ══ 右栏：推理 + 结果 ══════════════════════════════════════════════════ */}
        <div className="col-span-3 flex flex-col gap-4 overflow-y-auto">
          {!selectedItem ? (
            <div className="flex items-center justify-center h-64 text-gray-400 text-sm bg-white rounded-lg border border-gray-200">
              从左侧选择一条清单项
            </div>
          ) : (
            <>
              {/* 提示词预览（可折叠） */}
              {state.promptPreview && (
                <PromptPreviewPanel preview={state.promptPreview} />
              )}

              {/* 推理过程（可折叠） */}
              {(state.phase === 'reasoning' || (state.phase !== 'idle' && state.reasoning)) && (
                <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                  <button
                    onClick={() => setShowReasoning(v => !v)}
                    className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
                  >
                    <span className="flex items-center gap-2">
                      {state.phase === 'reasoning' && (
                        <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                      )}
                      推理过程
                      {state.ranAt && state.phase === 'done' && (
                        <span className="text-gray-400 font-normal">
                          · {new Date(state.ranAt).toLocaleString('zh-CN')}
                        </span>
                      )}
                    </span>
                    <span className="text-gray-400">{showReasoning ? '▲' : '▼'}</span>
                  </button>
                  {showReasoning && (
                    <div
                      ref={reasoningRef}
                      className="px-4 pb-4 text-xs text-gray-600 whitespace-pre-wrap font-mono overflow-y-auto"
                      style={{ maxHeight: '28vh' }}
                    >
                      {state.reasoning || '…'}
                    </div>
                  )}
                </div>
              )}

              {/* 错误 */}
              {state.phase === 'error' && (
                <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-600">
                  {state.error}
                </div>
              )}

              {/* 匹配结果 */}
              {state.phase === 'done' && (
                <div className="space-y-3">
                  {state.matches.length === 0 && state.missed.length === 0 ? (
                    <p className="text-sm text-gray-400 text-center py-8">AI 未匹配到任何定额</p>
                  ) : (
                    <>
                      {state.matches.length > 0 && (
                        <div>
                          <p className="text-xs font-medium text-gray-500 mb-2">AI 匹配结果（{state.matches.length} 条）</p>
                          <div className="space-y-2">
                            {state.matches.map((m, i) => (
                              <MatchRow
                                key={i} m={m}
                                expanded={expandedIdx.has(i)}
                                onToggle={() => setExpandedIdx(prev => {
                                  const next = new Set(prev)
                                  next.has(i) ? next.delete(i) : next.add(i)
                                  return next
                                })}
                              />
                            ))}
                          </div>
                        </div>
                      )}
                      {state.missed.length > 0 && (
                        <div>
                          <p className="text-xs font-medium text-amber-600 mb-2">⚠️ AI 漏套（{state.missed.length} 条）</p>
                          <div className="space-y-1">
                            {state.missed.map((q, i) => (
                              <div key={i} className="flex items-start gap-2 text-xs bg-amber-50 border border-amber-200 rounded px-3 py-1.5">
                                <span className="font-mono font-medium text-amber-700 flex-shrink-0">{q.quota_code}</span>
                                <span className="text-gray-600 flex-1">{q.quota_name}</span>
                                {q.qty_factor != null && <span className="text-gray-400 flex-shrink-0">×{q.qty_factor}</span>}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* idle 提示 */}
              {state.phase === 'idle' && (
                <div className="flex items-center justify-center h-48 text-gray-400 text-sm bg-white rounded-lg border border-gray-200">
                  点击「开始推理」查看 AI 匹配过程
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
