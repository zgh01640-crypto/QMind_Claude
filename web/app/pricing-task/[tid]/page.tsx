'use client'

import { useState, useEffect, useRef } from 'react'
import { useParams } from 'next/navigation'
import { fetchAllBoqItems, BoqItem, streamPricingTaskItem, PricingTaskEvent } from '@/lib/api'

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
            phase: 'done',
            judgment: { is_consistent: evt.is_consistent, reasoning: evt.reasoning },
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
                    const badge = result?.phase === 'done' && result.judgment
                      ? result.judgment.is_consistent
                        ? <span className="ml-auto flex-shrink-0 text-xs font-bold w-5 h-5 flex items-center justify-center rounded-full bg-green-500 text-white">1</span>
                        : <span className="ml-auto flex-shrink-0 text-xs font-bold w-5 h-5 flex items-center justify-center rounded-full bg-red-500 text-white">1</span>
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
                          {badge}
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

                {/* 单一滚动区：推理文字 + 结果卡片顺序排列 */}
                <div ref={reasoningRef} className="flex-1 overflow-y-auto">
                  {/* 推理文字 */}
                  <div className="px-4 py-3 text-xs text-gray-600 whitespace-pre-wrap font-mono">
                    {currentResult.reasoning || '…'}
                  </div>

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
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
