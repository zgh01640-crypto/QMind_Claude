'use client'
import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface MatchRun {
  id: number
  chapter_name: string
  run_name: string | null
  status: string
  total_items: number
  matched_items: number
  created_at: string
  system_prompt?: string
}

interface SubitemMatch {
  match_id: number
  subitem_id: number
  subitem_code: string
  name_path: string
  work_procedure: string
  qty_factor: number
  factor_explanation: string
  ai_reasoning: string
  confidence: string
  missing_info: string
  status: string
  total_unit_price: number | null
  quota_unit: string | null
}

interface BoqItemResult {
  boq_item_id: number
  item_code: string
  item_name: string
  boq_unit: string
  quantity: number | null
  item_description: string
  reasoning_chain: string
  matches: SubitemMatch[]
}

interface ManualProject {
  id: number
  project_name: string
  bid_section?: string
  item_count?: number
}

interface ManualQuota {
  quota_code: string
  quota_name: string
  quota_unit: string | null
  qty_factor: number
  unit_price: number | null
  total_price: number | null
}

interface ManualCompareData {
  project_name: string
  items: Record<string, { item_code: string; item_name: string; unit: string | null; quantity: number | null; quotas: ManualQuota[] }>
}

interface SubitemDetail {
  subitem_code: string
  name_path: string
  unit: string
  total_unit_price: number | null
  unit_price: number | null
  labor_cost: number | null
  material_cost: number | null
  machine_cost: number | null
  management_fee: number | null
  profit: number | null
  safety_fee: number | null
  statutory_fee: number | null
  tax: number | null
  work_content: string
  resources: { resource_type: string; resource_name: string; unit: string; quantity: number | null; ref_price: number | null }[]
}

// ── 子目详情弹窗 ──────────────────────────────────────────────────────────────

function SubitemModal({ subitemId, onClose }: { subitemId: number; onClose: () => void }) {
  const [detail, setDetail] = useState<SubitemDetail | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API}/api/bs2024-match/subitems/${subitemId}`)
      .then(r => r.json())
      .then(setDetail)
      .finally(() => setLoading(false))
  }, [subitemId])

  const fmt = (v: number | null) => v != null ? v.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) : '—'

  const typeColor = (t: string) =>
    t === '人工' ? 'bg-orange-50 text-orange-700' :
    t === '材料' ? 'bg-blue-50 text-blue-700' :
    'bg-purple-50 text-purple-700'

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* 标题 */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 shrink-0">
          <div>
            {detail && (
              <>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-blue-700 font-bold text-lg">{detail.subitem_code}</span>
                  <span className="text-gray-400 text-sm">{detail.unit}</span>
                </div>
                <div className="text-sm text-gray-500 mt-0.5">{detail.name_path}</div>
              </>
            )}
            {loading && <div className="text-gray-400 text-sm animate-pulse">加载中…</div>}
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none shrink-0 ml-4">×</button>
        </div>

        {detail && (
          <div className="overflow-y-auto flex-1 px-5 py-4 space-y-4">
            {/* 工作内容 */}
            {detail.work_content && (
              <div className="text-sm text-gray-600 bg-gray-50 rounded px-3 py-2">
                <span className="font-medium text-gray-500 text-xs mr-2">工作内容</span>
                {detail.work_content}
              </div>
            )}

            {/* 费用分解 */}
            <div>
              <div className="text-xs font-medium text-gray-500 mb-2 uppercase tracking-wide">费用分解（元/{detail.unit}）</div>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { label: '全费用单价', value: detail.total_unit_price, highlight: true },
                  { label: '综合单价', value: detail.unit_price },
                  { label: '人工费', value: detail.labor_cost },
                  { label: '材料费', value: detail.material_cost },
                  { label: '机械费', value: detail.machine_cost },
                  { label: '管理费', value: detail.management_fee },
                  { label: '利润', value: detail.profit },
                  { label: '安全文明费', value: detail.safety_fee },
                  { label: '规费', value: detail.statutory_fee },
                  { label: '税金', value: detail.tax },
                ].map(item => (
                  <div key={item.label} className={`rounded px-3 py-2 ${item.highlight ? 'bg-indigo-50 col-span-3' : 'bg-gray-50'}`}>
                    <div className="text-xs text-gray-400">{item.label}</div>
                    <div className={`font-mono font-medium ${item.highlight ? 'text-indigo-700 text-lg' : 'text-gray-700 text-sm'}`}>
                      {fmt(item.value)}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 工料机 */}
            {detail.resources.length > 0 && (
              <div>
                <div className="text-xs font-medium text-gray-500 mb-2 uppercase tracking-wide">工料机消耗量</div>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-gray-50">
                      <th className="px-2 py-1.5 text-left text-gray-500 font-medium">类型</th>
                      <th className="px-2 py-1.5 text-left text-gray-500 font-medium">名称规格</th>
                      <th className="px-2 py-1.5 text-right text-gray-500 font-medium">单位</th>
                      <th className="px-2 py-1.5 text-right text-gray-500 font-medium">数量</th>
                      <th className="px-2 py-1.5 text-right text-gray-500 font-medium">参考单价</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {detail.resources.map((r, i) => (
                      <tr key={i} className="hover:bg-gray-50">
                        <td className="px-2 py-1.5">
                          <span className={`px-1.5 py-0.5 rounded text-xs ${typeColor(r.resource_type)}`}>{r.resource_type}</span>
                        </td>
                        <td className="px-2 py-1.5 text-gray-700">{r.resource_name}</td>
                        <td className="px-2 py-1.5 text-right text-gray-500">{r.unit || '—'}</td>
                        <td className="px-2 py-1.5 text-right font-mono text-gray-700">
                          {r.quantity != null ? r.quantity.toLocaleString('zh-CN', { maximumFractionDigits: 4 }) : '—'}
                        </td>
                        <td className="px-2 py-1.5 text-right font-mono text-gray-600">
                          {r.ref_price != null ? fmt(r.ref_price) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

export default function NewBoqRunPage() {
  const params = useParams()
  const projectId = params.id as string
  const runId = Number(params.rid)

  const [run, setRun] = useState<MatchRun | null>(null)
  const [results, setResults] = useState<BoqItemResult[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [expandedReasoning, setExpandedReasoning] = useState<Set<number>>(new Set())
  const [showAll, setShowAll] = useState<'all' | 'matched' | 'unmatched'>('all')
  const [modalSubitemId, setModalSubitemId] = useState<number | null>(null)
  const [showPrompt, setShowPrompt] = useState(false)
  const [compareMode, setCompareMode] = useState(false)
  const [manualProjects, setManualProjects] = useState<ManualProject[]>([])
  const [selectedManualId, setSelectedManualId] = useState<number | null>(null)
  const [manualData, setManualData] = useState<ManualCompareData | null>(null)
  const [loadingManual, setLoadingManual] = useState(false)

  useEffect(() => {
    fetch(`${API}/api/manual-boq/projects`).then(r => r.json())
      .then(d => setManualProjects(Array.isArray(d) ? d : []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!selectedManualId) { setManualData(null); return }
    setLoadingManual(true)
    fetch(`${API}/api/bs2024-match/manual-compare?manual_project_id=${selectedManualId}`)
      .then(r => r.json())
      .then(d => setManualData(d && !d.detail ? d : null))
      .catch(() => setManualData(null))
      .finally(() => setLoadingManual(false))
  }, [selectedManualId])

  useEffect(() => {
    Promise.all([
      fetch(`${API}/api/bs2024-match/runs/${runId}/detail`).then(r => r.json()),
      fetch(`${API}/api/bs2024-match/runs/${runId}/matches`).then(r => r.json()),
    ]).then(([detail, matches]) => {
      setRun(detail && !detail.detail ? detail : null)
      setResults(Array.isArray(matches) ? matches : [])
    }).finally(() => setLoading(false))
  }, [projectId, runId])

  const toggleExpand = (id: number) =>
    setExpanded(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })

  const toggleReasoning = (id: number) =>
    setExpandedReasoning(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })

  const updateStatus = async (matchId: number, status: string) => {
    await fetch(`${API}/api/bs2024-match/matches/${matchId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    })
    setResults(prev => prev.map(item => ({
      ...item,
      matches: item.matches.map(m => m.match_id === matchId ? { ...m, status } : m),
    })))
  }

  const confColor = (c: string) =>
    c === 'high' ? 'text-green-700 bg-green-50 border-green-200' :
    c === 'medium' ? 'text-yellow-700 bg-yellow-50 border-yellow-200' :
    'text-red-700 bg-red-50 border-red-200'
  const confLabel = (c: string) => c === 'high' ? '高置信' : c === 'medium' ? '中置信' : '低置信'
  const statusColor = (s: string) =>
    s === 'confirmed' ? 'text-green-700 bg-green-100' :
    s === 'rejected' ? 'text-red-700 bg-red-100' :
    'text-blue-700 bg-blue-100'

  if (loading) return <div className="text-center text-gray-400 py-16 animate-pulse">加载中…</div>

  const hitCount = results.filter(r => r.matches.length > 0).length

  return (
    <div className="space-y-4">
      {/* 弹窗 */}
      {modalSubitemId !== null && (
        <SubitemModal subitemId={modalSubitemId} onClose={() => setModalSubitemId(null)} />
      )}

      {/* 面包屑 */}
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Link href="/new-boq" className="hover:text-gray-700">新工程管理</Link>
        <span>/</span>
        <Link href={`/new-boq/${projectId}`} className="hover:text-gray-700">工程详情</Link>
        <span>/</span>
        <span className="text-gray-800 font-medium">{run?.run_name || `批次 #${runId}`}</span>
      </div>

      {/* 批次摘要 */}
      {run && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="flex items-center justify-between p-4">
            <div>
              <div className="text-lg font-semibold text-gray-800">{run.run_name || `批次 #${runId}`}</div>
              <div className="text-sm text-gray-500 mt-0.5">
                {run.chapter_name} · {new Date(run.created_at).toLocaleString('zh-CN')}
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex gap-4 text-center">
                <div>
                  <div className="text-2xl font-bold text-indigo-600">{hitCount}</div>
                  <div className="text-xs text-gray-400">命中条目</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-gray-600">{results.length}</div>
                  <div className="text-xs text-gray-400">总清单项</div>
                </div>
              </div>
              {run.system_prompt && (
                <button
                  onClick={() => setShowPrompt(v => !v)}
                  className="px-3 py-1.5 border border-gray-300 text-gray-600 text-xs rounded-lg hover:bg-gray-50"
                >
                  {showPrompt ? '收起提示词' : '查看提示词'}
                </button>
              )}
            </div>
          </div>
          {/* 保存的系统提示词 */}
          {showPrompt && run.system_prompt && (
            <div className="border-t border-gray-200">
              <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
                <span className="text-xs font-medium text-gray-600">本次使用的系统提示词</span>
                <span className="text-xs text-gray-400">{run.system_prompt.length.toLocaleString()} 字符</span>
              </div>
              <pre className="text-xs text-gray-700 leading-relaxed p-4 max-h-96 overflow-y-auto whitespace-pre-wrap font-mono bg-white">
                {run.system_prompt}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* 人工套定额对比控制栏 */}
      <div className="bg-white rounded-lg border border-gray-200 p-3 flex items-center gap-3 flex-wrap">
        <button
          onClick={() => { setCompareMode(v => !v); if (compareMode) { setSelectedManualId(null); setManualData(null) } }}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
            compareMode
              ? 'bg-green-600 border-green-600 text-white'
              : 'bg-white border-gray-300 text-gray-600 hover:border-green-400'
          }`}
        >
          {compareMode ? '✓ 对比模式开启' : '对比人工套定额'}
        </button>
        {compareMode && (
          <>
            <select
              value={selectedManualId ?? ''}
              onChange={e => setSelectedManualId(e.target.value ? Number(e.target.value) : null)}
              className="border border-gray-300 rounded px-3 py-1.5 text-sm flex-1 min-w-48 focus:outline-none focus:ring-2 focus:ring-green-400"
            >
              <option value="">-- 选择人工套定额工程 --</option>
              {manualProjects.map(p => (
                <option key={p.id} value={p.id}>{p.project_name}{p.bid_section ? ` · ${p.bid_section}` : ''}</option>
              ))}
            </select>
            {loadingManual && <span className="text-xs text-gray-400 animate-pulse">加载中…</span>}
            {manualData && !loadingManual && (
              <span className="text-xs text-green-600">已加载：{manualData.project_name}（{Object.keys(manualData.items).length} 条清单）</span>
            )}
          </>
        )}
      </div>

      {/* 过滤栏 */}
      <div className="flex items-center gap-2">
        {([
          { label: `全部 (${results.length})`, value: 'all' },
          { label: `已命中 (${hitCount})`, value: 'matched' },
          { label: `未命中 (${results.length - hitCount})`, value: 'unmatched' },
        ] as const).map(opt => (
          <button
            key={opt.value}
            onClick={() => setShowAll(opt.value)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
              showAll === opt.value
                ? 'bg-indigo-600 border-indigo-600 text-white'
                : 'bg-white border-gray-300 text-gray-600 hover:border-indigo-400'
            }`}
          >{opt.label}</button>
        ))}
      </div>

      {/* 结果列表 */}
      <div className="space-y-2">
        {results
          .filter(item =>
            showAll === 'all' ? true :
            showAll === 'matched' ? item.matches.length > 0 :
            item.matches.length === 0
          )
          .map(item => (
          <div key={item.boq_item_id} className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            {/* 清单项标题行 */}
            <div
              className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-gray-50"
              onClick={() => toggleExpand(item.boq_item_id)}
            >
              <span className={`w-2 h-2 rounded-full shrink-0 ${item.matches.length > 0 ? 'bg-green-500' : 'bg-gray-300'}`} />
              <span className="font-mono text-blue-600 text-sm shrink-0 w-28 truncate">{item.item_code}</span>
              <span className="text-gray-800 font-medium text-sm flex-1 truncate">{item.item_name}</span>
              <span className="text-gray-400 text-xs shrink-0">{item.boq_unit}</span>
              <span className="text-gray-500 text-xs tabular-nums shrink-0 w-20 text-right">
                {item.quantity?.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) ?? '—'}
              </span>
              <span className="text-xs text-gray-400 shrink-0 w-16 text-right">
                {item.matches.length > 0 ? `${item.matches.length} 条匹配` : '无匹配'}
              </span>
              <span className="text-gray-300 shrink-0">{expanded.has(item.boq_item_id) ? '▲' : '▼'}</span>
            </div>

            {/* 展开内容 */}
            {expanded.has(item.boq_item_id) && (
              <div className="border-t border-gray-100">
                {/* 项目特征 */}
                {item.item_description && (
                  <div className="px-6 py-3 bg-amber-50 border-b border-amber-100">
                    <div className="text-xs font-medium text-amber-700 mb-1.5">项目特征</div>
                    <div className="text-xs text-amber-900 leading-relaxed space-y-0.5">
                      {item.item_description.split('\n').filter(Boolean).map((l, i) => (
                        <div key={i}>{l}</div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 推理过程 */}
                {item.reasoning_chain && (
                  <div className="border-b border-gray-100">
                    <button
                      onClick={() => toggleReasoning(item.boq_item_id)}
                      className="w-full flex items-center gap-2 px-6 py-2 text-xs text-gray-500 hover:bg-gray-50 text-left"
                    >
                      <span className="text-purple-500">🧠</span>
                      <span className="font-medium">AI 推理过程</span>
                      <span className="ml-auto text-gray-300">{expandedReasoning.has(item.boq_item_id) ? '▲' : '▼'}</span>
                    </button>
                    {expandedReasoning.has(item.boq_item_id) && (
                      <div className="px-6 pb-3 bg-purple-50/40">
                        <div className="text-xs text-gray-600 leading-relaxed whitespace-pre-wrap font-mono max-h-64 overflow-y-auto bg-white rounded border border-purple-100 p-3">
                          {item.reasoning_chain}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* 匹配结果 */}
                {compareMode && manualData ? (
                  /* 对比双栏 */
                  <div className="grid grid-cols-2 divide-x divide-gray-200">
                    {/* 左：AI 套定额 */}
                    <div>
                      <div className="px-4 py-2 bg-indigo-50 border-b border-indigo-100 text-xs font-medium text-indigo-700">
                        🤖 AI 套定额
                      </div>
                      {item.matches.length === 0 ? (
                        <div className="px-4 py-6 text-xs text-gray-400 text-center">无 AI 匹配</div>
                      ) : (
                        <div className="divide-y divide-gray-100">
                          {item.matches.map((m, i) => (
                            <div key={m.match_id} className={`px-4 py-2.5 text-xs ${m.status === 'rejected' ? 'opacity-40' : ''}`}>
                              <div className="flex items-center gap-2 mb-1">
                                <button onClick={() => setModalSubitemId(m.subitem_id)}
                                  className="font-mono text-blue-700 font-bold hover:underline">{m.subitem_code}</button>
                                <span className={`px-1.5 py-0.5 rounded border text-xs ${confColor(m.confidence)}`}>{confLabel(m.confidence)}</span>
                              </div>
                              <div className="text-gray-700 mb-1">{m.name_path}</div>
                              <div className="flex flex-wrap gap-2 text-gray-500">
                                <span>工序：{m.work_procedure || '—'}</span>
                                <span>系数：{m.qty_factor}</span>
                                {m.total_unit_price != null && (
                                  <span className="text-indigo-600 font-medium">¥{m.total_unit_price.toLocaleString('zh-CN', {maximumFractionDigits:2})}</span>
                                )}
                              </div>
                              {m.ai_reasoning && (
                                <div className="mt-1 text-gray-400 bg-gray-50 rounded px-2 py-1 leading-relaxed">{m.ai_reasoning}</div>
                              )}
                              <div className="flex gap-1 mt-1">
                                {m.status !== 'confirmed' && <button onClick={() => updateStatus(m.match_id, 'confirmed')} className="px-1.5 py-0.5 rounded border border-green-300 text-green-700 hover:bg-green-50">确认</button>}
                                {m.status !== 'rejected' && <button onClick={() => updateStatus(m.match_id, 'rejected')} className="px-1.5 py-0.5 rounded border border-red-300 text-red-600 hover:bg-red-50">拒绝</button>}
                                {m.status !== 'ai' && <button onClick={() => updateStatus(m.match_id, 'ai')} className="px-1.5 py-0.5 rounded border border-gray-300 text-gray-500 hover:bg-gray-50">重置</button>}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    {/* 右：人工套定额 */}
                    <div>
                      <div className="px-4 py-2 bg-green-50 border-b border-green-100 text-xs font-medium text-green-700">
                        👷 人工套定额 · {manualData.project_name}
                      </div>
                      {(() => {
                        const manualItem = manualData.items[item.item_code]
                        if (!manualItem || manualItem.quotas.length === 0) {
                          return <div className="px-4 py-6 text-xs text-gray-400 text-center">无人工匹配</div>
                        }
                        return (
                          <div className="divide-y divide-gray-100">
                            {manualItem.quotas.map((q, i) => (
                              <div key={i} className="px-4 py-2.5 text-xs">
                                <div className="font-mono text-green-700 font-bold mb-1">{q.quota_code}</div>
                                <div className="text-gray-700 mb-1">{q.quota_name}</div>
                                <div className="flex flex-wrap gap-2 text-gray-500">
                                  <span>单位：{q.quota_unit || '—'}</span>
                                  <span>系数：{q.qty_factor}</span>
                                  {q.unit_price != null && (
                                    <span className="text-green-600 font-medium">¥{q.unit_price.toLocaleString('zh-CN', {maximumFractionDigits:2})}</span>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        )
                      })()}
                    </div>
                  </div>
                ) : (
                  /* 单列：原有展示 */
                  item.matches.length === 0 ? (
                    <div className="px-8 py-4 text-sm text-gray-400">该清单项未找到匹配的定额子目</div>
                  ) : (
                    <div className="divide-y divide-gray-100">
                      {item.matches.map((m, i) => (
                        <div key={m.match_id} className={`px-6 py-3 ${m.status === 'rejected' ? 'opacity-40' : ''}`}>
                          <div className="flex items-start gap-3">
                            <span className="text-xs text-gray-400 shrink-0 mt-1">#{i + 1}</span>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <button
                                  onClick={() => setModalSubitemId(m.subitem_id)}
                                  className="font-mono text-blue-700 font-bold text-sm hover:text-blue-900 hover:underline underline-offset-2"
                                >
                                  {m.subitem_code}
                                </button>
                                <span className={`text-xs px-1.5 py-0.5 rounded border ${confColor(m.confidence)}`}>{confLabel(m.confidence)}</span>
                                <span className={`text-xs px-1.5 py-0.5 rounded ${statusColor(m.status)}`}>
                                  {m.status === 'confirmed' ? '已确认' : m.status === 'rejected' ? '已拒绝' : 'AI建议'}
                                </span>
                              </div>
                              <div className="text-sm text-gray-700 mb-1">{m.name_path}</div>
                              <div className="flex flex-wrap gap-3 text-xs text-gray-500">
                                <span>工序：{m.work_procedure || '—'}</span>
                                <span>单位：{m.quota_unit || '—'}</span>
                                <span>换算系数：{m.qty_factor}</span>
                                {m.factor_explanation && <span>（{m.factor_explanation}）</span>}
                                {m.total_unit_price != null && (
                                  <span className="text-indigo-600 font-medium">
                                    全费用单价：¥{m.total_unit_price.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}
                                  </span>
                                )}
                              </div>
                              {m.ai_reasoning && (
                                <div className="mt-1.5 text-xs text-gray-400 bg-gray-50 rounded px-2 py-1.5 leading-relaxed">
                                  {m.ai_reasoning}
                                </div>
                              )}
                              {m.missing_info && (
                                <div className="mt-1 text-xs text-orange-500">⚠ 缺少信息：{m.missing_info}</div>
                              )}
                            </div>
                            <div className="flex gap-1 shrink-0">
                              {m.status !== 'confirmed' && (
                                <button onClick={() => updateStatus(m.match_id, 'confirmed')}
                                  className="text-xs px-2 py-1 rounded border border-green-300 text-green-700 hover:bg-green-50">确认</button>
                              )}
                              {m.status !== 'rejected' && (
                                <button onClick={() => updateStatus(m.match_id, 'rejected')}
                                  className="text-xs px-2 py-1 rounded border border-red-300 text-red-600 hover:bg-red-50">拒绝</button>
                              )}
                              {m.status !== 'ai' && (
                                <button onClick={() => updateStatus(m.match_id, 'ai')}
                                  className="text-xs px-2 py-1 rounded border border-gray-300 text-gray-500 hover:bg-gray-50">重置</button>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
