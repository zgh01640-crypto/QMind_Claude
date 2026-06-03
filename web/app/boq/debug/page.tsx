'use client'
import { useState, useEffect, useRef } from 'react'
import {
  fetchBoqProjects, fetchAllBoqItems, fetchQuotaStandards, fetchManualBoqProjects,
  streamDebugMatch,
  BoqProject, BoqItem, QuotaStandard, ManualBoqProject,
  DebugMatchQuota, DebugManualQuota,
} from '@/lib/api'

// ── 类型 ───────────────────────────────────────────────────────────────────────

interface DebugState {
  phase: 'idle' | 'reasoning' | 'done' | 'error'
  reasoning: string
  matches: DebugMatchQuota[]
  missed: (DebugManualQuota & { missed_by_ai: boolean })[]
  manualQuotas: DebugManualQuota[]
  error?: string
}

const IDLE: DebugState = { phase: 'idle', reasoning: '', matches: [], missed: [], manualQuotas: [] }

// ── 标准选择器 ─────────────────────────────────────────────────────────────────

function StandardSelector({
  standards, selected, onChange, disabled,
}: {
  standards: QuotaStandard[]
  selected: number[]
  onChange: (ids: number[]) => void
  disabled: boolean
}) {
  const byRegion = standards.reduce<Record<string, QuotaStandard[]>>((acc, s) => {
    const r = s.region || '其他'
    ;(acc[r] = acc[r] || []).push(s)
    return acc
  }, {})

  return (
    <div className="flex flex-wrap gap-2">
      {Object.entries(byRegion).map(([region, stds]) => {
        const ids = stds.map(s => s.id)
        const allSel = ids.every(id => selected.includes(id))
        return (
          <div key={region} className="flex items-center gap-1.5 border rounded-lg px-2.5 py-1">
            <button
              onClick={() => onChange(allSel ? selected.filter(id => !ids.includes(id)) : [...new Set([...selected, ...ids])])}
              disabled={disabled}
              className={`text-xs font-semibold px-1.5 py-0.5 rounded transition ${allSel ? 'bg-indigo-600 text-white' : 'bg-white text-gray-600 border border-gray-300 hover:border-indigo-400'}`}
            >
              {region}（全部）
            </button>
            {stds.map(s => {
              const checked = selected.includes(s.id)
              return (
                <label key={s.id} className={`flex items-center gap-1 text-xs cursor-pointer ${disabled ? 'opacity-50' : ''}`}>
                  <input type="checkbox" checked={checked} disabled={disabled}
                    onChange={() => onChange(checked ? selected.filter(id => id !== s.id) : [...selected, s.id])}
                    className="accent-indigo-600" />
                  <span className="text-gray-700">{s.standard_code}</span>
                </label>
              )
            })}
          </div>
        )
      })}
    </div>
  )
}

// ── 人工定额展示 ───────────────────────────────────────────────────────────────

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

// ── 主页面 ─────────────────────────────────────────────────────────────────────

export default function BoqDebugPage() {
  const [projects, setProjects] = useState<BoqProject[]>([])
  const [manualProjects, setManualProjects] = useState<ManualBoqProject[]>([])
  const [standards, setStandards] = useState<QuotaStandard[]>([])
  const [items, setItems] = useState<BoqItem[]>([])

  const [projId, setProjId] = useState<number | null>(null)
  const [selectedStdIds, setSelectedStdIds] = useState<number[]>([])
  const [manualProjId, setManualProjId] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [selectedItem, setSelectedItem] = useState<BoqItem | null>(null)

  const [state, setState] = useState<DebugState>(IDLE)
  const [expandedIdx, setExpandedIdx] = useState<Set<number>>(new Set())
  const reasoningRef = useRef<HTMLDivElement>(null)

  // 初始加载
  useEffect(() => {
    Promise.all([fetchBoqProjects(), fetchManualBoqProjects(), fetchQuotaStandards()])
      .then(([ps, mps, stds]) => {
        setProjects(ps)
        setManualProjects(mps)
        setStandards(stds)
        setSelectedStdIds(stds.map(s => s.id))
        if (mps.length > 0) setManualProjId(mps[0].id)
      })
      .catch(() => {})
  }, [])

  // 工程变化时加载清单
  useEffect(() => {
    if (!projId) { setItems([]); setSelectedItem(null); return }
    fetchAllBoqItems(projId).then(setItems).catch(() => setItems([]))
    setSelectedItem(null)
  }, [projId])

  // 推理文字自动滚动
  useEffect(() => {
    if (reasoningRef.current)
      reasoningRef.current.scrollTop = reasoningRef.current.scrollHeight
  }, [state.reasoning])

  const filteredItems = items.filter(it =>
    !search || it.item_name.includes(search) || it.item_code.includes(search)
  )

  const canRun = selectedItem && selectedStdIds.length > 0 && state.phase !== 'reasoning'

  async function handleRun() {
    if (!selectedItem) return
    setState({ phase: 'reasoning', reasoning: '', matches: [], missed: [], manualQuotas: [] })
    setExpandedIdx(new Set())
    try {
      await streamDebugMatch(selectedItem.id, selectedStdIds, manualProjId, (evt) => {
        if (evt.type === 'item_info') {
          setState(s => ({ ...s, manualQuotas: evt.manual_quotas }))
        } else if (evt.type === 'reasoning_token') {
          setState(s => ({ ...s, reasoning: s.reasoning + evt.token }))
        } else if (evt.type === 'result') {
          setState(s => ({ ...s, phase: 'done', matches: evt.matches, missed: evt.missed }))
        } else if (evt.type === 'error') {
          setState(s => ({ ...s, phase: 'error', error: evt.error }))
        }
      })
    } catch (e: unknown) {
      setState(s => ({ ...s, phase: 'error', error: e instanceof Error ? e.message : '匹配失败' }))
    }
  }

  const descLen = selectedItem?.item_description?.length ?? 0
  const descWarning = descLen === 0 ? '⚠️ 无项目特征描述' : descLen < 30 ? '⚠️ 描述较短' : null

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <h1 className="text-xl font-bold text-gray-800 mb-1">单条套定额调试</h1>
      <p className="text-sm text-gray-500 mb-5">选择一条清单项，观察 AI 推理过程并与人工标准对比。结果不写入数据库。</p>

      <div className="grid grid-cols-5 gap-5" style={{ minHeight: '80vh' }}>

        {/* ══ 左栏：配置 + 选项 ══════════════════════════════════════════════════ */}
        <div className="col-span-2 flex flex-col gap-4">

          {/* 配置区 */}
          <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-4">
            {/* 工程选择 */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">BOQ 工程</label>
              <select
                className="w-full border border-gray-200 rounded px-2 py-1.5 text-sm"
                value={projId ?? ''}
                onChange={e => setProjId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">-- 请选择工程 --</option>
                {projects.map(p => (
                  <option key={p.id} value={p.id}>{p.project_name}{p.bid_section ? ` · ${p.bid_section}` : ''}</option>
                ))}
              </select>
            </div>

            {/* 定额标准 */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">定额标准</label>
              <StandardSelector
                standards={standards} selected={selectedStdIds}
                onChange={setSelectedStdIds} disabled={state.phase === 'reasoning'}
              />
            </div>

            {/* 人工标准工程（可选） */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">人工标准工程（可选）</label>
              <select
                className="w-full border border-gray-200 rounded px-2 py-1.5 text-sm"
                value={manualProjId ?? ''}
                onChange={e => setManualProjId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">-- 不对比人工标准 --</option>
                {manualProjects.map(p => (
                  <option key={p.id} value={p.id}>{p.project_name}</option>
                ))}
              </select>
            </div>
          </div>

          {/* 清单项列表 */}
          {projId && (
            <div className="bg-white rounded-lg border border-gray-200 flex flex-col" style={{ maxHeight: '38vh' }}>
              <div className="p-3 border-b border-gray-100">
                <input
                  type="text" placeholder="搜索清单项名称或编码…"
                  value={search} onChange={e => setSearch(e.target.value)}
                  className="w-full border border-gray-200 rounded px-2 py-1 text-sm"
                />
              </div>
              <div className="overflow-y-auto flex-1">
                {filteredItems.map(item => (
                  <button
                    key={item.id}
                    onClick={() => { setSelectedItem(item); setState(IDLE) }}
                    className={`w-full text-left px-3 py-2 border-b border-gray-50 hover:bg-blue-50 transition ${selectedItem?.id === item.id ? 'bg-blue-100' : ''}`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-gray-400 flex-shrink-0">{item.item_code}</span>
                      <span className="text-sm text-gray-800 truncate">{item.item_name}</span>
                    </div>
                    {!item.item_description && (
                      <span className="text-xs text-amber-500">⚠ 无项目特征</span>
                    )}
                  </button>
                ))}
                {filteredItems.length === 0 && (
                  <p className="text-center text-gray-400 text-sm py-6">无匹配清单项</p>
                )}
              </div>
            </div>
          )}

          {/* 选中项详情 */}
          {selectedItem && (
            <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-3">
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <div><span className="text-gray-500">编码：</span><span className="font-mono">{selectedItem.item_code}</span></div>
                <div><span className="text-gray-500">名称：</span>{selectedItem.item_name}</div>
                <div><span className="text-gray-500">单位：</span>{selectedItem.unit}</div>
                <div><span className="text-gray-500">工程量：</span>{selectedItem.quantity}</div>
              </div>

              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-medium text-gray-600">项目特征描述</span>
                  <span className="text-xs text-gray-400">{descLen} 字</span>
                  {descWarning && <span className="text-xs text-amber-600">{descWarning}</span>}
                </div>
                <pre className={`text-xs rounded p-2 whitespace-pre-wrap leading-relaxed font-sans ${descLen === 0 ? 'bg-amber-50 text-amber-700 italic' : 'bg-gray-50 text-gray-800'}`}>
                  {selectedItem.item_description || '（无项目特征描述）'}
                </pre>
              </div>

              {/* 人工标准答案（匹配完成后显示，或预先显示） */}
              {(state.manualQuotas.length > 0 || manualProjId) && (
                <div>
                  <span className="text-xs font-medium text-gray-600 block mb-1">人工标准答案</span>
                  <ManualQuotaList quotas={state.manualQuotas} />
                </div>
              )}
            </div>
          )}
        </div>

        {/* ══ 右栏：推理 + 结果 ══════════════════════════════════════════════════ */}
        <div className="col-span-3 flex flex-col gap-4">

          {/* 操作按钮 */}
          <div className="bg-white rounded-lg border border-gray-200 p-3 flex items-center gap-3">
            <button
              onClick={handleRun}
              disabled={!canRun}
              className="px-6 py-2 bg-indigo-600 text-white rounded-lg font-medium disabled:opacity-40 hover:bg-indigo-700 transition text-sm"
            >
              {state.phase === 'reasoning' ? '⏳ 推理中…' : '▶ 开始匹配'}
            </button>
            {selectedItem && (
              <span className="text-sm text-gray-600">
                {selectedItem.item_name}
                <span className="ml-2 text-gray-400 font-mono text-xs">{selectedItem.item_code}</span>
              </span>
            )}
            {state.phase === 'done' && (
              <span className="text-sm text-green-600 ml-auto">
                ✅ {state.matches.filter(m => m.in_manual).length} 一致
                {state.missed.length > 0 && <span className="ml-2 text-amber-600">⚠️ {state.missed.length} 漏套</span>}
                {state.matches.filter(m => !m.in_manual).length > 0 && (
                  <span className="ml-2 text-red-600">❌ {state.matches.filter(m => !m.in_manual).length} AI多套</span>
                )}
              </span>
            )}
            {!selectedItem && <span className="text-sm text-gray-400">← 请先选择清单项</span>}
          </div>

          {state.phase === 'error' && (
            <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">{state.error}</div>
          )}

          {/* 推理文字 */}
          {(state.reasoning || state.phase === 'reasoning') && (
            <div className="bg-white rounded-lg border border-gray-200 flex flex-col" style={{ maxHeight: '45vh' }}>
              <div className="px-4 py-2 border-b border-gray-100 text-xs font-medium text-gray-600 bg-gray-50 flex items-center gap-2">
                <span>AI 推理过程</span>
                {state.phase === 'reasoning' && <span className="text-indigo-500 animate-pulse">●</span>}
              </div>
              <div ref={reasoningRef} className="overflow-y-auto flex-1 p-4">
                <pre className="text-xs text-gray-700 whitespace-pre-wrap leading-relaxed font-sans">
                  {state.reasoning || '等待推理开始…'}
                </pre>
              </div>
            </div>
          )}

          {/* 匹配结果对比 */}
          {state.phase === 'done' && (
            <div className="space-y-3">
              {/* AI 匹配结果 */}
              {state.matches.length > 0 && (
                <div className="bg-white rounded-lg border border-gray-200">
                  <div className="px-4 py-2 border-b border-gray-100 text-xs font-medium text-gray-600 bg-gray-50">
                    AI 匹配结果（{state.matches.length} 条）
                    <span className="ml-2 text-green-600">{state.matches.filter(m => m.in_manual).length} 与人工一致</span>
                    {state.matches.some(m => !m.in_manual) && (
                      <span className="ml-2 text-red-500">{state.matches.filter(m => !m.in_manual).length} 仅AI有</span>
                    )}
                  </div>
                  <div className="p-3 space-y-2">
                    {state.matches.map((m, i) => (
                      <MatchRow
                        key={i} m={m}
                        expanded={expandedIdx.has(i)}
                        onToggle={() => setExpandedIdx(prev => {
                          const s = new Set(prev)
                          s.has(i) ? s.delete(i) : s.add(i)
                          return s
                        })}
                      />
                    ))}
                  </div>
                </div>
              )}

              {state.matches.length === 0 && (
                <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-center text-gray-500 text-sm">
                  AI 未返回任何匹配结果
                </div>
              )}

              {/* 人工有但 AI 漏套 */}
              {state.missed.length > 0 && (
                <div className="bg-white rounded-lg border border-amber-200">
                  <div className="px-4 py-2 border-b border-amber-100 text-xs font-medium text-amber-700 bg-amber-50">
                    ⚠️ 人工标准有，但 AI 漏套（{state.missed.length} 条）
                  </div>
                  <div className="p-3 space-y-1">
                    {state.missed.map((q, i) => (
                      <div key={i} className={`flex items-center gap-2 text-xs rounded px-2 py-1.5 ${q.is_formula ? 'bg-amber-50' : 'bg-orange-50'}`}>
                        <span className={`font-mono font-medium ${q.is_formula ? 'text-amber-700' : 'text-orange-700'}`}>{q.quota_code}</span>
                        <span className="text-gray-700 flex-1">{q.quota_name}</span>
                        {q.qty_factor != null && <span className="text-gray-400">×{q.qty_factor}</span>}
                        {q.is_formula && <span className="text-amber-500 text-xs">公式码</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 初始提示 */}
          {state.phase === 'idle' && !selectedItem && (
            <div className="flex-1 flex items-center justify-center text-gray-400 text-sm bg-gray-50 rounded-lg border border-dashed border-gray-200" style={{ minHeight: '300px' }}>
              选择左侧清单项后点击「开始匹配」
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
