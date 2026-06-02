'use client'
import { useState, useEffect } from 'react'
import {
  fetchBoqProjects, fetchBoqRuns, fetchBoqCompare,
  BoqProject, BoqMatchRun, CompareResult, CompareBoqItem, CompareQuota,
} from '@/lib/api'

// ── 工具函数 ─────────────────────────────────────────────────────────────────

type FilterKey = 'all' | 'consistent' | 'different' | 'only_a' | 'only_b' | 'both_empty'

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
    <div className="space-y-1">
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
        <span className="text-xs text-gray-400 flex-shrink-0 w-12">
          A:{item.quotas_a.length} / B:{item.quotas_b.length}
        </span>
      </button>

      {open && (
        <div className="grid grid-cols-2 gap-4 px-4 pb-3 pt-1 bg-white border-t border-gray-100">
          <div>
            <div className="text-xs text-gray-500 font-medium mb-2 pb-1 border-b border-gray-100">批次 A</div>
            <QuotaLines quotas={item.quotas_a} />
          </div>
          <div>
            <div className="text-xs text-gray-500 font-medium mb-2 pb-1 border-b border-gray-100">批次 B</div>
            <QuotaLines quotas={item.quotas_b} />
          </div>
        </div>
      )}
    </div>
  )
}

// ── 批次选择器 ────────────────────────────────────────────────────────────────

function RunSelector({
  label,
  projects,
  selectedProject, setSelectedProject,
  runs, selectedRun, setSelectedRun,
}: {
  label: string
  projects: BoqProject[]
  selectedProject: number | null
  setSelectedProject: (id: number | null) => void
  runs: BoqMatchRun[]
  selectedRun: number | null
  setSelectedRun: (id: number | null) => void
}) {
  return (
    <div className="flex-1 bg-white rounded-lg border border-gray-200 p-4 space-y-3">
      <div className="text-sm font-semibold text-gray-700">{label}</div>
      <div>
        <label className="block text-xs text-gray-500 mb-1">选择工程</label>
        <select
          className="w-full border border-gray-200 rounded px-2 py-1.5 text-sm"
          value={selectedProject ?? ''}
          onChange={e => {
            const v = e.target.value ? Number(e.target.value) : null
            setSelectedProject(v)
            setSelectedRun(null)
          }}
        >
          <option value="">-- 请选择工程 --</option>
          {projects.map(p => (
            <option key={p.id} value={p.id}>
              {p.project_name}{p.bid_section ? ` · ${p.bid_section}` : ''}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="block text-xs text-gray-500 mb-1">选择批次</label>
        <select
          className="w-full border border-gray-200 rounded px-2 py-1.5 text-sm"
          value={selectedRun ?? ''}
          onChange={e => setSelectedRun(e.target.value ? Number(e.target.value) : null)}
          disabled={!selectedProject || runs.length === 0}
        >
          <option value="">-- 请选择批次 --</option>
          {runs.map(r => (
            <option key={r.id} value={r.id}>
              {r.run_name || `批次 #${r.id}`}
              {r.standard_code ? ` (${r.standard_code})` : ''}
              {r.status !== 'done' ? ` [${r.status}]` : ''}
            </option>
          ))}
        </select>
        {selectedProject && runs.length === 0 && (
          <p className="text-xs text-gray-400 mt-1">该工程暂无套定额批次</p>
        )}
      </div>
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

export default function ComparePage() {
  const [projects, setProjects] = useState<BoqProject[]>([])

  const [projA, setProjA] = useState<number | null>(null)
  const [projB, setProjB] = useState<number | null>(null)
  const [runsA, setRunsA] = useState<BoqMatchRun[]>([])
  const [runsB, setRunsB] = useState<BoqMatchRun[]>([])
  const [runA, setRunA] = useState<number | null>(null)
  const [runB, setRunB] = useState<number | null>(null)

  const [result, setResult] = useState<CompareResult | null>(null)
  const [filter, setFilter] = useState<FilterKey>('all')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchBoqProjects().then(setProjects).catch(() => {})
  }, [])

  useEffect(() => {
    if (!projA) { setRunsA([]); setRunA(null); return }
    fetchBoqRuns(projA).then(setRunsA).catch(() => setRunsA([]))
  }, [projA])

  useEffect(() => {
    if (!projB) { setRunsB([]); setRunB(null); return }
    fetchBoqRuns(projB).then(setRunsB).catch(() => setRunsB([]))
  }, [projB])

  async function doCompare() {
    if (!runA || !runB) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const r = await fetchBoqCompare(runA, runB)
      setResult(r)
      setFilter('all')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '比较失败')
    } finally {
      setLoading(false)
    }
  }

  const displayed = result ? filterItems(result.items, filter) : []

  const filterOptions: { key: FilterKey; label: string; count: (r: CompareResult) => number; color: string }[] = [
    { key: 'all',        label: '全部',     count: r => r.summary.total,       color: 'bg-gray-100 text-gray-700 hover:bg-gray-200' },
    { key: 'consistent', label: '一致',     count: r => r.summary.consistent,  color: 'bg-green-100 text-green-700 hover:bg-green-200' },
    { key: 'different',  label: '不同',     count: r => r.summary.different,   color: 'bg-red-100 text-red-700 hover:bg-red-200' },
    { key: 'only_a',     label: '仅A有结果', count: r => r.summary.only_a,      color: 'bg-amber-100 text-amber-700 hover:bg-amber-200' },
    { key: 'only_b',     label: '仅B有结果', count: r => r.summary.only_b,      color: 'bg-blue-100 text-blue-700 hover:bg-blue-200' },
    { key: 'both_empty', label: '均无结果',  count: r => r.summary.both_empty,  color: 'bg-gray-100 text-gray-500 hover:bg-gray-200' },
  ]

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      <h1 className="text-xl font-bold text-gray-800">定额比较</h1>

      {/* 批次选择区 */}
      <div className="flex gap-4 items-stretch">
        <RunSelector
          label="批次 A"
          projects={projects}
          selectedProject={projA} setSelectedProject={setProjA}
          runs={runsA} selectedRun={runA} setSelectedRun={setRunA}
        />
        <div className="flex items-center">
          <span className="text-2xl text-gray-300 select-none">⇄</span>
        </div>
        <RunSelector
          label="批次 B"
          projects={projects}
          selectedProject={projB} setSelectedProject={setProjB}
          runs={runsB} selectedRun={runB} setSelectedRun={setRunB}
        />
      </div>

      <div className="flex justify-center">
        <button
          onClick={doCompare}
          disabled={!runA || !runB || loading}
          className="px-8 py-2 bg-blue-600 text-white rounded-lg font-medium disabled:opacity-40 hover:bg-blue-700 transition"
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
          {/* 批次信息标题 */}
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-white rounded-lg border border-gray-200 px-4 py-3">
              <div className="text-xs text-gray-500">批次 A</div>
              <div className="font-semibold text-gray-800">{result.run_a.project_name}</div>
              <div className="text-sm text-gray-600">{result.run_a.run_name || `批次 #${result.run_a.run_id}`}</div>
              {result.run_a.standard_code && (
                <div className="text-xs text-blue-600 mt-0.5">{result.run_a.standard_code}</div>
              )}
            </div>
            <div className="bg-white rounded-lg border border-gray-200 px-4 py-3">
              <div className="text-xs text-gray-500">批次 B</div>
              <div className="font-semibold text-gray-800">{result.run_b.project_name}</div>
              <div className="text-sm text-gray-600">{result.run_b.run_name || `批次 #${result.run_b.run_id}`}</div>
              {result.run_b.standard_code && (
                <div className="text-xs text-blue-600 mt-0.5">{result.run_b.standard_code}</div>
              )}
            </div>
          </div>

          {/* 筛选按钮 */}
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

          {/* 列表表头 */}
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <div className="flex items-center gap-3 px-4 py-2 bg-gray-50 border-b border-gray-200 text-xs text-gray-500 font-medium">
              <span className="w-4" />
              <span className="w-10">状态</span>
              <span className="w-32">清单编码</span>
              <span className="flex-1">名称</span>
              <span className="w-28 text-right">单位 / 数量</span>
              <span className="w-12 text-right">A/B 数量</span>
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
