'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { fetchAllBoqItems, BoqItem } from '@/lib/api'

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

export default function PricingTaskDetailPage() {
  const params = useParams()
  const taskId = params.tid as string

  const [task, setTask] = useState<PricingTask | null>(null)
  const [items, setItems] = useState<BoqItem[]>([])
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null)
  const [expandedItemId, setExpandedItemId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // 加载任务
    const stored = localStorage.getItem('pricing_tasks')
    if (stored) {
      const tasks = JSON.parse(stored) as PricingTask[]
      const found = tasks.find(t => t.id === taskId)
      if (found) {
        setTask(found)
        // 加载清单项
        loadItems(found.project_id)
      }
    }
  }, [taskId])

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

  if (loading || !task) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-500">加载中...</div>
      </div>
    )
  }

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
                  {items.map(item => (
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
                          setExpandedItemId(
                            expandedItemId === item.id ? null : item.id
                          )
                        }}
                        className="px-4 py-3"
                      >
                        <div className="flex-1 min-w-0">
                            <div className="font-mono text-xs text-gray-600">
                              {item.item_code}
                            </div>
                            <div className="text-sm font-medium text-gray-900 truncate">
                              {item.item_name}
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* 详情（展开时显示） */}
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
                  ))}
                </div>
              )}
            </div>

            {/* 底部套定额按钮 */}
            {selectedItemId && (
              <div className="px-4 py-4 border-t border-gray-200 bg-gray-50">
                <button
                  onClick={() => console.log('套定额:', selectedItemId)}
                  className="w-full px-3 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors"
                >
                  套定额
                </button>
              </div>
            )}
          </div>

          {/* 右侧占位区 */}
          <div className="flex-1 bg-white rounded-lg shadow flex items-center justify-center border-2 border-dashed border-gray-300">
            <div className="text-center">
              <div className="text-4xl mb-4">📝</div>
              <p className="font-semibold text-gray-900 mb-1">提示词</p>
              <p className="text-sm text-gray-500 mb-6">
                提示词模板功能即将上线
              </p>

              <div className="text-4xl mb-4">🧠</div>
              <p className="font-semibold text-gray-900 mb-1">推理过程</p>
              <p className="text-sm text-gray-500 mb-6">
                选择清单后点击套定额开始
              </p>

              <div className="text-4xl mb-4">✓</div>
              <p className="font-semibold text-gray-900 mb-1">匹配结果</p>
              <p className="text-sm text-gray-500">推理完成后展示</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
