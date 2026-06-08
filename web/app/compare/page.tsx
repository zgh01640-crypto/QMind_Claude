'use client'
import { useState, useEffect } from 'react'
import {
  fetchBoqProjects, fetchBoqCompare,
  fetchManualBoqProjects,
  BoqProject, ManualBoqProject,
  CompareResult, CompareBoqItem, CompareQuota,
} from '@/lib/api'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ── 工具函数 ─────────────────────────────────────────────────────────────────

type SrcType = 'bs2024' | 'manual'
type FilterKey = 'all' | 'consistent' | 'different' | 'only_a' | 'only_b' | 'both_empty'

interface Bs2024Run {
  id: number
  chapter_name: string
  run_name: string | null
  status: string
  total_items: number
  matched_items: number
  created_at: string
}

function filterItems(items: CompareBoqItem[], f: FilterKey) {
  if (f === 'consistent') return items.filter(i => i.consistent)
  if (f === 'different')  return items.filter(i => !i.consistent && i.quotas_a.length > 0 && i.quotas_b.length > 0)
  if (f === 'only_a')     return items.filter(i => i.quotas_a.length > 0 && i.quotas_b.length === 0)
  if (f === 'only_b')     return items.filter(i => i.quotas_a.length === 0 && i.quotas_b.length > 0)
  if (f === 'both_empty') return items.filter(i => i.quotas_a.length === 0 && i.quotas_b.length === 0)
  return items
}

function itemStatus(item: CompareBoqItem) {
  if (item.consistent)
    return { label: '一致', bg: 'bg-green-50', badge: 'bg-green-100 text-green-700' }
  if (item.quotas_a.length > 0 && item.quotas_b.length > 0)
    return { label: '不同', bg: 'bg-red-50', badge: 'bg-red-100 text-red-700' }
  if (item.quotas_a.length > 0)
    return { label: '仅A', bg: 'bg-amber-50', badge: 'bg-amber-100 text-amber-700' }
  if (item.quotas_b.length > 0)
    return { label: '仅B', bg: 'bg-blue-50', badge: 'bg-blue-100 text-blue-700' }
  return { label: '均空', bg: 'bg-gray-50', badge: 'bg-gray-100 text-gray-500' }
}

// ── 定额行 ────────────────────────────────────────────────────────────────────

function QuotaLines({ quotas }: { quotas: CompareQuota[] }) {
  if (quotas.length === 0)
    return <span className="text-gray-400 text-xs italic">无匹配</span>
  return (
    <div className="space-y-2">
      {quotas.map((q, i) => (
        <div key={i} className="flex flex-col gap-0.5">
          <span className="font-mono text-xs text-blue-700 font-medium">{q.quota_item_code}</span>
          <span className="text-xs text-gray-700">{q.quota_item_name}</span>
          {q.work_procedure && (
            <span className="text-xs text-gray-500">工序: {q.work_procedure}</span>
          )}
          <span className="text-xs text-gray-500">
            系数 ×{q.qty_factor}
            {q.confidence && (
              <span className={`ml-1 px-1 rounded ${
                q.confidence === 'high' ? 'text-green-600' :
                q.confidence === 'medium' ? 'text-amber-600' : 'text-red-500'
              }`}>{q.confidence}</span>
            )}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── 清单项行 ──────────────────────────────────────────────────────────────────

function ItemRow({ item }: { item: CompareBoqItem }) {
  const [open, setOpen] = useState(false)
  const st = itemStatus(item)

  return (
    <div className={`border-b border-gray-100 ${st.bg}`}>
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full text-left px-4 py-2 flex items-center gap-3 hover:brightness-95 transition"
      >
        <span className="text-gray-400 w-4 text-xs">{open ? '▼' : '▶'}</span>
        <span className={`text-xs px-2 py-0.5 rounded font-medium w-10 text-center flex-shrink-0 ${st.badge}`}>
          {st.label}
        </span>
        <span className="font-mono text-xs text-gray-500 w-32 flex-shrink-0">{item.item_code}</span>
        <span className="text-sm font-medium text-gray-800 flex-1 truncate">{item.item_name}</span>
        <span className="text-xs text-gray-500 flex-shrink-0">
          {item.unit} {item.quantity != null ? item.quantity.toLocaleString() : ''}
        </span>
        <span className="text-xs text-gray-400 flex-shrink-0 w-12 text-right">
          A:{item.quotas_a.length} / B:{item.quotas_b.length}
        </span>
      </button>

      {open && (
        <div className="bg-white border-t border-gray-100">
          {/* 项目特征 */}
          {item.item_description && (
            <div className="px-4 py-2 bg-amber-50 border-b border-amber-100">
              <div className="text-xs font-medium text-amber-700 mb-1">项目特征</div>
              <div className="text-xs text-amber-900 leading-relaxed space-y-0.5">
                {item.item_description.split('\n').filter(Boolean).map((l, i) => (
                  <div key={i}>{l}</div>
                ))}
              </div>
            </div>
          )}
          {/* 定额对比 */}
          <div className="grid grid-cols-2 gap-4 px-4 pb-3 pt-2">
            <div>
              <div className="text-xs text-gray-500 font-medium mb-2 pb-1 border-b border-gray-100">批次 A</div>
              <QuotaLines quotas={item.quotas_a} />
            </div>
            <div>
              <div className="text-xs text-gray-500 font-medium mb-2 pb-1 border-b border-gray-100">批次 B</div>
              <QuotaLines quotas={item.quotas_b} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── 批次/工程选择器 ────────────────────────────────────────────────────────────

interface SelectorProps {
  label: string
  srcType: SrcType
  onSrcTypeChange: (t: SrcType) => void
  // 新工程AI批次
  boqProjects: BoqProject[]
  selectedProject: number | null
  setSelectedProject: (id: number | null) => void
  bs2024Runs: Bs2024Run[]
  selectedRun: number | null
  setSelectedRun: (id: number | null) => void
  // 人工套定额
  manualProjects: ManualBoqProject[]
  selectedManual: number | null
  setSelectedManual: (id: number | null) => void
}

function Selector(p: SelectorProps) {
  return (
    <div className="flex-1 bg-white rounded-lg border border-gray-200 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-700">{p.label}</span>
        <div className="flex rounded overflow-hidden border border-gray-200 text-xs">
          {(['bs2024', 'manual'] as SrcType[]).map(t => (
            <button
              key={t}
              onClick={() => p.onSrcTypeChange(t)}
              className={`px-3 py-1 transition ${
                p.srcType === t
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white text-gray-600 hover:bg-gray-50'
              }`}
            >
              {t === 'bs2024' ? '新工程AI' : '人工套定额'}
            </button>
          ))}
        </div>
      </div>

      {p.srcType === 'bs2024' ? (
        <>
          <div>
            <label className="block text-xs text-gray-500 mb-1">选择工程</label>
            <select
              className="w-full border border-gray-200 rounded px-2 py-1.5 text-sm"
              value={p.selectedProject ?? ''}
              onChange={e => {
                const v = e.target.value ? Number(e.target.value) : null
                p.setSelectedProject(v)
                p.setSelectedRun(null)
              }}
            >
              <option value="">-- 请选择工程 --</option>
              {p.boqProjects.map(proj => (
                <option key={proj.id} value={proj.id}>
                  {proj.project_name}{proj.bid_section ? ` · ${proj.bid_section}` : ''}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">选择批次</label>
            <select
              className="w-full border border-gray-200 rounded px-2 py-1.5 text-sm"
              value={p.selectedRun ?? ''}
              onChange={e => p.setSelectedRun(e.target.value ? Number(e.target.value) : null)}
              disabled={!p.selectedProject || p.bs2024Runs.length === 0}
            >
              <option value="">-- 请选择批次 --</option>
              {p.bs2024Runs.map(r => (
                <option key={r.id} value={r.id}>
                  {r.run_name || `批次 #${r.id}`}
                  {r.chapter_name ? ` [${r.chapter_name}]` : ''}
                  {r.status !== 'done' ? ` (${r.status})` : ''}
                </option>
              ))}
            </select>
            {p.selectedProject && p.bs2024Runs.length === 0 && (
              <p className="text-xs text-gray-400 mt-1">该工程暂无新工程套定额批次，请先在「新工程管理」中套定额</p>
            )}
          </div>
        </>
      ) : (
        <div>
          <label className="block text-xs text-gray-500 mb-1">选择人工套定额工程</label>
          <select
            className="w-full border border-gray-200 rounded px-2 py-1.5 text-sm"
            value={p.selectedManual ?? ''}
            onChange={e => p.setSelectedManual(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">-- 请选择工程 --</option>
            {p.manualProjects.map(proj => (
              <option key={proj.id} value={proj.id}>
                {proj.project_name}{proj.bid_section ? ` · ${proj.bid_section}` : ''}
                {proj.item_count != null ? ` (${proj.item_count} 项)` : ''}
              </option>
            ))}
          </select>
          {p.manualProjects.length === 0 && (
            <p className="text-xs text-gray-400 mt-1">暂无人工套定额工程，请先在「工程管理（人工）」中导入</p>
          )}
        </div>
      )}
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

export default function ComparePage() {
  const [boqProjects, setBoqProjects] = useState<BoqProject[]>([])
  const [manualProjects, setManualProjects] = useState<ManualBoqProject[]>([])

  const [typeA, setTypeA] = useState<SrcType>('bs2024')
  const [typeB, setTypeB] = useState<SrcType>('manual')

  const [projA, setProjA] = useState<number | null>(null)
  const [projB, setProjB] = useState<number | null>(null)
  const [runsA, setRunsA] = useState<Bs2024Run[]>([])
  const [runsB, setRunsB] = useState<Bs2024Run[]>([])
  const [runA, setRunA] = useState<number | null>(null)
  const [runB, setRunB] = useState<number | null>(null)
  const [manualA, setManualA] = useState<number | null>(null)
  const [manualB, setManualB] = useState<number | null>(null)

  const [result, setResult] = useState<CompareResult | null>(null)
  const [filter, setFilter] = useState<FilterKey>('all')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchBoqProjects().then(setBoqProjects).catch(() => {})
    fetchManualBoqProjects().then(setManualProjects).catch(() => {})
  }, [])

  // 加载 bs2024 批次
  useEffect(() => {
    if (!projA) { setRunsA([]); setRunA(null); return }
    fetch(`${API}/api/bs2024-match/runs?project_id=${projA}`)
      .then(r => r.json()).then(d => setRunsA(Array.isArray(d) ? d : [])).catch(() => setRunsA([]))
  }, [projA])

  useEffect(() => {
    if (!projB) { setRunsB([]); setRunB(null); return }
    fetch(`${API}/api/bs2024-match/runs?project_id=${projB}`)
      .then(r => r.json()).then(d => setRunsB(Array.isArray(d) ? d : [])).catch(() => setRunsB([]))
  }, [projB])

  function getSelection(type: SrcType, run: number | null, manual: number | null) {
    return type === 'manual' ? manual : run
  }

  async function doCompare() {
    const idA = getSelection(typeA, runA, manualA)
    const idB = getSelection(typeB, runB, manualB)
    if (!idA || !idB) return
    setLoading(true); setError(null); setResult(null)
    try {
      const r = await fetchBoqCompare(idA, idB, typeA, typeB)
      setResult(r)
      setFilter('all')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '比较失败')
    } finally {
      setLoading(false)
    }
  }

  const idA = getSelection(typeA, runA, manualA)
  const idB = getSelection(typeB, runB, manualB)
  const canCompare = Boolean(idA && idB)
  const displayed = result ? filterItems(result.items, filter) : []

  const filterOptions: {
    key: FilterKey; label: string
    count: (r: CompareResult) => number; color: string
  }[] = [
    { key: 'all',        label: '全部',      count: r => r.summary.total,       color: 'bg-gray-100 text-gray-700 hover:bg-gray-200' },
    { key: 'consistent', label: '一致',      count: r => r.summary.consistent,  color: 'bg-green-100 text-green-700 hover:bg-green-200' },
    { key: 'different',  label: '不同',      count: r => r.summary.different,   color: 'bg-red-100 text-red-700 hover:bg-red-200' },
    { key: 'only_a',     label: '仅A有结果', count: r => r.summary.only_a,      color: 'bg-amber-100 text-amber-700 hover:bg-amber-200' },
    { key: 'only_b',     label: '仅B有结果', count: r => r.summary.only_b,      color: 'bg-blue-100 text-blue-700 hover:bg-blue-200' },
    { key: 'both_empty', label: '均无结果',  count: r => r.summary.both_empty,  color: 'bg-gray-100 text-gray-500 hover:bg-gray-200' },
  ]

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      <h1 className="text-xl font-bold text-gray-800">定额比较</h1>
      <p className="text-sm text-gray-500 -mt-4">
        对比「新工程管理」AI套定额批次与人工套定额工程，按清单编码对齐后逐项比较定额结果。
      </p>

      {/* 选择区 */}
      <div className="flex gap-4 items-stretch">
        <Selector
          label="批次 A"
          srcType={typeA} onSrcTypeChange={t => { setTypeA(t); setResult(null) }}
          boqProjects={boqProjects}
          selectedProject={projA} setSelectedProject={setProjA}
          bs2024Runs={runsA} selectedRun={runA} setSelectedRun={setRunA}
          manualProjects={manualProjects}
          selectedManual={manualA} setSelectedManual={setManualA}
        />
        <div className="flex items-center">
          <span className="text-2xl text-gray-300 select-none">⇄</span>
        </div>
        <Selector
          label="批次 B"
          srcType={typeB} onSrcTypeChange={t => { setTypeB(t); setResult(null) }}
          boqProjects={boqProjects}
          selectedProject={projB} setSelectedProject={setProjB}
          bs2024Runs={runsB} selectedRun={runB} setSelectedRun={setRunB}
          manualProjects={manualProjects}
          selectedManual={manualB} setSelectedManual={setManualB}
        />
      </div>

      <div className="flex justify-center">
        <button
          onClick={doCompare}
          disabled={!canCompare || loading}
          className="px-8 py-2 bg-indigo-600 text-white rounded-lg font-medium disabled:opacity-40 hover:bg-indigo-700 transition"
        >
          {loading ? '比较中…' : '开始比较'}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">{error}</div>
      )}

      {/* 比较结果 */}
      {result && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            {[result.run_a, result.run_b].map((info, idx) => (
              <div key={idx} className="bg-white rounded-lg border border-gray-200 px-4 py-3">
                <div className="text-xs text-gray-500 mb-0.5">批次 {idx === 0 ? 'A' : 'B'}</div>
                <div className="font-semibold text-gray-800">{info.project_name}</div>
                <div className="text-sm text-gray-600">
                  {info.run_name || (info.standard_code === '人工套定额' ? '' : `批次 #${info.run_id}`)}
                </div>
                {info.standard_code && (
                  <span className={`inline-block text-xs mt-1 px-2 py-0.5 rounded ${
                    info.standard_code === '人工套定额'
                      ? 'bg-green-100 text-green-700'
                      : 'bg-indigo-50 text-indigo-600'
                  }`}>{info.standard_code}</span>
                )}
              </div>
            ))}
          </div>

          <div className="flex flex-wrap gap-2">
            {filterOptions.map(opt => (
              <button
                key={opt.key}
                onClick={() => setFilter(opt.key)}
                className={`px-3 py-1 rounded-full text-sm font-medium transition ${opt.color} ${
                  filter === opt.key ? 'ring-2 ring-offset-1 ring-current' : ''
                }`}
              >
                {opt.label}
                <span className="ml-1 font-bold">{opt.count(result)}</span>
              </button>
            ))}
          </div>

          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <div className="flex items-center gap-3 px-4 py-2 bg-gray-50 border-b border-gray-200 text-xs text-gray-500 font-medium">
              <span className="w-4" />
              <span className="w-10">状态</span>
              <span className="w-32">清单编码</span>
              <span className="flex-1">名称</span>
              <span className="w-28 text-right">单位 / 数量</span>
              <span className="w-12 text-right">A/B</span>
            </div>
            {displayed.length === 0 ? (
              <div className="px-4 py-8 text-center text-gray-400 text-sm">无匹配数据</div>
            ) : (
              displayed.map(item => <ItemRow key={item.item_code} item={item} />)
            )}
          </div>
        </div>
      )}
    </div>
  )
}
