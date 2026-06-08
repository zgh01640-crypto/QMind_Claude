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
  matches: SubitemMatch[]
}

export default function NewBoqRunPage() {
  const params = useParams()
  const projectId = params.id as string
  const runId = Number(params.rid)

  const [run, setRun] = useState<MatchRun | null>(null)
  const [results, setResults] = useState<BoqItemResult[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  useEffect(() => {
    Promise.all([
      fetch(`${API}/api/bs2024-match/runs?project_id=${projectId}`).then(r => r.json()),
      fetch(`${API}/api/bs2024-match/runs/${runId}/matches`).then(r => r.json()),
    ]).then(([runs, matches]) => {
      setRun(runs.find((r: MatchRun) => r.id === runId) || null)
      setResults(matches)
    }).finally(() => setLoading(false))
  }, [projectId, runId])

  const toggleExpand = (id: number) =>
    setExpanded(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })

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
  const totalUnitPriceSum = results.reduce((sum, r) =>
    sum + r.matches
      .filter(m => m.status !== 'rejected')
      .reduce((s, m) => s + (m.total_unit_price || 0) * m.qty_factor * (r.quantity || 0), 0)
  , 0)

  return (
    <div className="space-y-4">
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
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-lg font-semibold text-gray-800">{run.run_name || `批次 #${runId}`}</div>
              <div className="text-sm text-gray-500 mt-0.5">
                {run.chapter_name} · {new Date(run.created_at).toLocaleString('zh-CN')}
              </div>
            </div>
            <div className="flex gap-4 text-center">
              <div>
                <div className="text-2xl font-bold text-indigo-600">{hitCount}</div>
                <div className="text-xs text-gray-400">命中条目</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-gray-600">{results.length}</div>
                <div className="text-xs text-gray-400">总清单项</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-green-600">
                  {totalUnitPriceSum > 0 ? `¥${totalUnitPriceSum.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}` : '—'}
                </div>
                <div className="text-xs text-gray-400">合价合计</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 结果列表 */}
      <div className="space-y-2">
        {results.map(item => (
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

            {/* 展开：匹配详情 */}
            {expanded.has(item.boq_item_id) && (
              <div className="border-t border-gray-100">
                {item.matches.length === 0 ? (
                  <div className="px-8 py-4 text-sm text-gray-400">该清单项未找到匹配的定额子目</div>
                ) : (
                  <div className="divide-y divide-gray-100">
                    {item.matches.map((m, i) => (
                      <div key={m.match_id} className={`px-6 py-3 ${m.status === 'rejected' ? 'opacity-40' : ''}`}>
                        <div className="flex items-start gap-3 mb-2">
                          <span className="text-xs text-gray-400 shrink-0 mt-0.5">#{i + 1}</span>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="font-mono text-blue-700 font-medium text-sm">{m.subitem_code}</span>
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
                              {m.total_unit_price && (
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
                              <button
                                onClick={() => updateStatus(m.match_id, 'confirmed')}
                                className="text-xs px-2 py-1 rounded border border-green-300 text-green-700 hover:bg-green-50"
                              >确认</button>
                            )}
                            {m.status !== 'rejected' && (
                              <button
                                onClick={() => updateStatus(m.match_id, 'rejected')}
                                className="text-xs px-2 py-1 rounded border border-red-300 text-red-600 hover:bg-red-50"
                              >拒绝</button>
                            )}
                            {m.status !== 'ai' && (
                              <button
                                onClick={() => updateStatus(m.match_id, 'ai')}
                                className="text-xs px-2 py-1 rounded border border-gray-300 text-gray-500 hover:bg-gray-50"
                              >重置</button>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
