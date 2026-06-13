'use client'

import { useState, useEffect, useRef } from 'react'
import { useParams } from 'next/navigation'
import { fetchAllBoqItems, BoqItem, streamPricingTaskItem, PricingTaskEvent, QuotaCandidate, QuotaMatch } from '@/lib/api'

interface PricingTask {
  id: string
  name: string
  project_id: number
  project_name: string
  chapter_ids: number[]
  chapter_names: string[]
  manual_project_id: number | null
  manual_project_name: string | null
  created_at: string
}

interface ItemResult {
  phase: 'reasoning' | 'done' | 'error'
  reasoning: string
  codeCheck?: { item_code: string; item_name: string; base_code: string; standard_name: string; found: boolean; is_consistent: boolean }
  judgment?: { is_consistent: boolean; reasoning: string }
  featureCheck?: { is_complete: boolean; missing_features: string[]; analysis: string }
  workProcedures?: string[]
  quotaCandidates?: { item_code: string; base_code: string; candidates: QuotaCandidate[]; total: number }
  quotaMatch?: { matches: QuotaMatch[]; issues: string[] }
  error?: string
}

export default function PricingTaskDetailPage() {
  const params = useParams()
  const taskId = params.tid as string

  const [task, setTask] = useState<PricingTask | null>(null)
  const [items, setItems] = useState<BoqItem[]>([])
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null)
  const [expandedItemId, setExpandedItemId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)

  // per-item 结果 Map
  const [itemResults, setItemResults] = useState<Map<number, ItemResult>>(new Map())
  const reasoningRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const stored = localStorage.getItem('pricing_tasks')
    if (stored) {
      const tasks = JSON.parse(stored) as PricingTask[]
      const found = tasks.find(t => t.id === taskId)
      if (found) {
        setTask(found)
        loadItems(found.project_id)
      }
    }
  }, [taskId])

  // 当前选中项的推理内容变化时自动滚到底部
  const currentResult = selectedItemId ? itemResults.get(selectedItemId) : undefined
  useEffect(() => {
    if (reasoningRef.current) {
      reasoningRef.current.scrollTop = reasoningRef.current.scrollHeight
    }
  }, [currentResult?.reasoning])

  const loadItems = async (projectId: number) => {
    try {
      const data = await fetchAllBoqItems(projectId)
      setItems(data)
    } catch (err) {
      console.error('加载清单项失败', err)
    } finally {
      setLoading(false)
    }
  }

  const updateResult = (itemId: number, updater: (prev: ItemResult) => ItemResult) => {
    setItemResults(m => {
      const prev = m.get(itemId) ?? { phase: 'reasoning', reasoning: '' }
      return new Map(m).set(itemId, updater(prev))
    })
  }

  const handleMatch = async (itemId: number) => {
    if (!task) return
    setItemResults(m => new Map(m).set(itemId, { phase: 'reasoning', reasoning: '' }))

    try {
      await streamPricingTaskItem(itemId, task.chapter_ids, task.manual_project_id, (evt: PricingTaskEvent) => {
        if (evt.type === 'reasoning_token') {
          updateResult(itemId, s => ({ ...s, reasoning: s.reasoning + evt.token }))
        } else if (evt.type === 'code_check') {
          updateResult(itemId, s => ({
            ...s,
            codeCheck: {
              item_code: evt.item_code,
              item_name: evt.item_name,
              base_code: evt.base_code,
              standard_name: evt.standard_name,
              found: evt.found,
              is_consistent: evt.is_consistent,
            },
          }))
        } else if (evt.type === 'judgment') {
          updateResult(itemId, s => ({
            ...s,
            judgment: { is_consistent: evt.is_consistent, reasoning: evt.reasoning },
          }))
        } else if (evt.type === 'feature_check') {
          updateResult(itemId, s => ({
            ...s,
            featureCheck: { is_complete: evt.is_complete, missing_features: evt.missing_features, analysis: evt.analysis },
          }))
        } else if (evt.type === 'work_procedures') {
          updateResult(itemId, s => ({
            ...s,
            workProcedures: evt.procedures,
          }))
        } else if (evt.type === 'quota_candidates') {
          updateResult(itemId, s => ({
            ...s,
            quotaCandidates: { item_code: evt.item_code, base_code: evt.base_code, candidates: evt.candidates, total: evt.total },
          }))
        } else if (evt.type === 'quota_match') {
          updateResult(itemId, s => ({
            ...s,
            phase: 'done',
            quotaMatch: { matches: evt.matches, issues: evt.issues },
          }))
        } else if (evt.type === 'error') {
          updateResult(itemId, s => ({ ...s, phase: 'error', error: evt.error }))
        }
      })
    } catch (err) {
      updateResult(itemId, s => ({
        ...s,
        phase: 'error',
        error: err instanceof Error ? err.message : '未知错误',
      }))
    }
  }

  if (loading || !task) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-500">加载中...</div>
      </div>
    )
  }

  const isRunning = currentResult?.phase === 'reasoning'

  return (
    <div className="min-h-screen bg-gray-50">
      {/* 顶部信息栏 */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-7xl mx-auto text-sm text-gray-700">
          <span className="font-semibold">工程：</span> {task.project_name}
          <span className="ml-4 font-semibold">定额库：</span> {task.chapter_names.join('、')}
          {task.manual_project_name && (
            <>
              <span className="ml-4 font-semibold">对比工程：</span> {task.manual_project_name}
            </>
          )}
        </div>
      </div>

      {/* 主内容区 */}
      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="flex gap-6 h-[calc(100vh-200px)]">
          {/* 左侧清单列表 */}
          <div className="w-72 bg-white rounded-lg shadow flex flex-col">
            <div className="px-4 py-3 border-b border-gray-200">
              <h3 className="font-semibold text-gray-900">清单项</h3>
            </div>
            <div className="flex-1 overflow-y-auto">
              {items.length === 0 ? (
                <div className="p-4 text-center text-gray-500 text-sm">暂无清单项</div>
              ) : (
                <div className="divide-y divide-gray-200">
                  {items.map(item => {
                    const result = itemResults.get(item.id)
                    const badge1 = result?.judgment
                      ? <span className={`text-[10px] font-bold w-4 h-4 flex items-center justify-center rounded-full text-white ${result.judgment.is_consistent ? 'bg-green-500' : 'bg-red-500'}`}>1</span>
                      : null
                    const badge2 = result?.featureCheck
                      ? <span className={`text-[10px] font-bold w-4 h-4 flex items-center justify-center rounded-full text-white ${result.featureCheck.is_complete ? 'bg-green-500' : 'bg-red-500'}`}>2</span>
                      : null
                    const badge3 = result?.workProcedures
                      ? <span className="text-[10px] font-bold w-4 h-4 flex items-center justify-center rounded-full text-white bg-green-500">3</span>
                      : null
                    const badge4 = result?.quotaCandidates
                      ? <span className={`text-[10px] font-bold w-4 h-4 flex items-center justify-center rounded-full text-white ${result.quotaCandidates.total > 0 ? 'bg-green-500' : 'bg-gray-400'}`}>4</span>
                      : null
                    const badge5 = result?.quotaMatch
                      ? (() => {
                          const hasMatches = result.quotaMatch.matches.length > 0
                          const allHigh = result.quotaMatch.matches.every(m => m.confidence === 'high')
                          const color = !hasMatches ? 'bg-gray-400' : allHigh ? 'bg-green-500' : 'bg-amber-500'
                          return <span className={`text-[10px] font-bold w-4 h-4 flex items-center justify-center rounded-full text-white ${color}`}>5</span>
                        })()
                      : null
                    return (
                      <div
                        key={item.id}
                        className={`cursor-pointer transition-colors ${
                          selectedItemId === item.id
                            ? 'border-l-2 border-blue-700 bg-blue-50'
                            : 'hover:bg-gray-50'
                        }`}
                      >
                        {/* 项目标题（可展开）*/}
                        <div
                          onClick={() => {
                            setSelectedItemId(item.id)
                            setExpandedItemId(expandedItemId === item.id ? null : item.id)
                          }}
                          className="px-4 py-3 flex items-start gap-2"
                        >
                          <div className="flex-1 min-w-0">
                            <div className="font-mono text-xs text-gray-600">
                              {item.item_code}
                            </div>
                            <div className="text-sm font-medium text-gray-900 truncate">
                              {item.item_name}
                            </div>
                          </div>
                          <div className="ml-auto flex-shrink-0 flex gap-1">
                            {badge1}
                            {badge2}
                            {badge3}
                            {badge4}
                            {badge5}
                          </div>
                        </div>

                        {/* 详情（展开时显示）*/}
                        {expandedItemId === item.id && (
                          <div className="px-4 py-3 bg-gray-50 border-t border-gray-200 text-xs text-gray-700 space-y-2">
                            {item.item_description && (
                              <p>
                                <span className="font-medium">特征：</span>
                                {item.item_description}
                              </p>
                            )}
                            <p>
                              <span className="font-medium">单位：</span>
                              {item.unit || '—'}
                            </p>
                            {item.quantity && (
                              <p>
                                <span className="font-medium">工程量：</span>
                                {item.quantity}
                              </p>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* 底部套定额按钮 */}
            {selectedItemId && (
              <div className="px-4 py-4 border-t border-gray-200 bg-gray-50">
                <button
                  onClick={() => handleMatch(selectedItemId)}
                  disabled={isRunning}
                  className="w-full px-3 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors disabled:opacity-50"
                >
                  {isRunning ? '推理中...' : '套定额'}
                </button>
              </div>
            )}
          </div>

          {/* 右侧面板 */}
          <div className="flex-1 bg-white rounded-lg shadow flex flex-col overflow-hidden">
            {!currentResult ? (
              <div className="flex-1 flex items-center justify-center text-gray-400 text-center">
                <div>
                  <p className="text-lg mb-2">📋</p>
                  <p>选择清单项后点击「套定额」开始</p>
                </div>
              </div>
            ) : currentResult.phase === 'error' ? (
              <div className="flex-1 flex items-center justify-center p-6">
                <div className="text-center">
                  <p className="text-red-600 font-semibold mb-2">出错了</p>
                  <p className="text-sm text-red-500">{currentResult.error}</p>
                </div>
              </div>
            ) : (
              <div className="flex-1 flex flex-col overflow-hidden">
                {/* 顶部标题栏 */}
                <div className="px-4 py-3 border-b bg-amber-50 flex items-center gap-2 flex-shrink-0">
                  <span className="text-amber-600 font-semibold text-sm">🧠 AI 推理</span>
                  {currentResult.phase === 'reasoning' && (
                    <span className="inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                  )}
                </div>

                {/* 推理文字区（固定高度，独立滚动，始终可见）*/}
                <div ref={reasoningRef} className="h-52 flex-shrink-0 overflow-y-auto border-b border-amber-100 bg-amber-50/20">
                  <div className="px-4 py-3 text-xs text-gray-600 whitespace-pre-wrap font-mono">
                    {currentResult.reasoning || '…'}
                  </div>
                </div>

                {/* 结果卡片区（独立滚动，占剩余空间）*/}
                <div className="flex-1 overflow-y-auto">

                  {/* 编码核查结果 */}
                  {currentResult.codeCheck && (
                    <div className="px-4 py-4 bg-blue-50 border-t border-blue-200">
                      <div className="font-semibold text-blue-900 text-sm mb-3">📝 编码核查</div>
                      <div className="space-y-2 text-xs">
                        <div>
                          <span className="text-gray-600">原始编码：</span>
                          <span className="font-mono text-blue-700 font-semibold">{currentResult.codeCheck.item_code}</span>
                        </div>
                        <div>
                          <span className="text-gray-600">基准编码：</span>
                          <span className="font-mono text-blue-600">{currentResult.codeCheck.base_code}</span>
                          <span className="text-gray-400 text-xs ml-2">（去掉末尾3位）</span>
                        </div>
                        <div>
                          <span className="text-gray-600">工程清单名称：</span>
                          <span className="text-gray-900">{currentResult.codeCheck.item_name}</span>
                        </div>
                        <div>
                          <span className="text-gray-600">标准清单名称：</span>
                          {currentResult.codeCheck.found ? (
                            <span className="text-green-800 font-medium">{currentResult.codeCheck.standard_name}</span>
                          ) : (
                            <span className="text-orange-600">⚠️ 标准库未找到该编码</span>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* 一致性判断结果 */}
                  {currentResult.judgment && (
                    <div className={`px-4 py-4 border-t ${currentResult.judgment.is_consistent ? 'bg-green-50 border-green-200' : 'bg-orange-50 border-orange-200'}`}>
                      <div className={`font-semibold text-sm ${currentResult.judgment.is_consistent ? 'text-green-900' : 'text-orange-900'}`}>
                        {currentResult.judgment.is_consistent ? '✅ 编码名称一致' : '⚠️ 编码名称不一致'}
                      </div>
                    </div>
                  )}

                  {/* 项目特征完整性结果 */}
                  {currentResult.featureCheck && (
                    <div className={`px-4 py-4 border-t ${currentResult.featureCheck.is_complete ? 'bg-green-50 border-green-200' : 'bg-orange-50 border-orange-200'}`}>
                      <div className={`font-semibold text-sm mb-2 ${currentResult.featureCheck.is_complete ? 'text-green-900' : 'text-orange-900'}`}>
                        {currentResult.featureCheck.is_complete ? '✅ 项目特征完整' : '⚠️ 项目特征不完整'}
                      </div>
                      {currentResult.featureCheck.missing_features.length > 0 && (
                        <ul className="text-xs text-orange-800 space-y-1 list-disc list-inside mb-2">
                          {currentResult.featureCheck.missing_features.map((f, i) => (
                            <li key={i}>{f}</li>
                          ))}
                        </ul>
                      )}
                      <p className="text-xs text-gray-600">{currentResult.featureCheck.analysis}</p>
                    </div>
                  )}

                  {/* 标准工序拆解 */}
                  {currentResult.workProcedures && (
                    <div className="px-4 py-4 border-t bg-indigo-50 border-indigo-200">
                      <div className="font-semibold text-sm text-indigo-900 mb-3">🔧 标准工序</div>
                      <div className="flex flex-wrap items-center gap-1 text-xs">
                        {currentResult.workProcedures.map((p, i) => (
                          <span key={i} className="flex items-center gap-1">
                            <span className="bg-indigo-100 text-indigo-800 px-2 py-0.5 rounded font-medium">
                              {'①②③④⑤⑥⑦⑧⑨⑩'[i] ?? `${i + 1}.`}{p}
                            </span>
                            {i < currentResult.workProcedures!.length - 1 && (
                              <span className="text-indigo-400">→</span>
                            )}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 定额候选子目 */}
                  {currentResult.quotaCandidates && (
                    <div className="px-4 py-4 border-t bg-slate-50 border-slate-200">
                      <div className="font-semibold text-sm text-slate-900 mb-2">
                        📦 定额候选子目
                        <span className="ml-2 text-xs font-normal text-slate-500">
                          共 {currentResult.quotaCandidates.total} 条
                        </span>
                      </div>
                      {currentResult.quotaCandidates.total === 0 ? (
                        <p className="text-xs text-slate-400">未找到候选定额子目</p>
                      ) : (
                        <div className="space-y-1 text-xs">
                          {currentResult.quotaCandidates.candidates.map((c, i) => (
                            <div key={i} className="bg-white border border-slate-200 rounded px-3 py-2">
                              <div className="flex items-center gap-2 mb-0.5">
                                <span className="font-mono text-slate-500">{c.zmbh}</span>
                                <span className="font-medium text-slate-900">{c.zmmc}</span>
                                <span className="text-slate-400 ml-auto flex-shrink-0">{c.dw}</span>
                              </div>
                              {c.gznr && (
                                <div className="text-slate-500 line-clamp-2">{c.gznr}</div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* 套定额结果 */}
                  {currentResult.quotaMatch && (
                    <div className="px-4 py-4 border-t bg-emerald-50 border-emerald-200">
                      <div className="font-semibold text-sm text-emerald-900 mb-3">
                        ✅ 套定额结果
                        <span className="ml-2 text-xs font-normal text-emerald-600">
                          {currentResult.quotaMatch.matches.length} 条匹配
                        </span>
                      </div>
                      {currentResult.quotaMatch.matches.length === 0 ? (
                        <p className="text-xs text-gray-400">未找到匹配定额</p>
                      ) : (
                        <div className="space-y-2 text-xs mb-3">
                          {currentResult.quotaMatch.matches.map((m, i) => {
                            const confColor = m.confidence === 'high' ? 'bg-green-100 text-green-800' : m.confidence === 'medium' ? 'bg-amber-100 text-amber-800' : 'bg-red-100 text-red-800'
                            const confLabel = m.confidence === 'high' ? '高' : m.confidence === 'medium' ? '中' : '低'
                            return (
                              <div key={i} className="bg-white border border-emerald-200 rounded px-3 py-2">
                                <div className="flex items-center gap-2 mb-1">
                                  <span className="font-mono text-emerald-700 font-semibold">{m.zmbh}</span>
                                  <span className="font-medium text-gray-900">{m.zmmc}</span>
                                  {m.qty_factor !== 1 && (
                                    <span className="text-gray-500 ml-1">×{m.qty_factor}</span>
                                  )}
                                  <span className={`ml-auto px-1.5 py-0.5 rounded text-[10px] font-bold flex-shrink-0 ${confColor}`}>{confLabel}</span>
                                </div>
                                <p className="text-gray-500">{m.match_reason}</p>
                              </div>
                            )
                          })}
                        </div>
                      )}
                      {currentResult.quotaMatch.issues.length > 0 && (
                        <div className="mt-2">
                          <div className="text-xs font-semibold text-amber-700 mb-1">⚠️ 模糊问题</div>
                          <ul className="text-xs text-amber-700 space-y-0.5 list-disc list-inside">
                            {currentResult.quotaMatch.issues.map((issue, i) => (
                              <li key={i}>{issue}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
