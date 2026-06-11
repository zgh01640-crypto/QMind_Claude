'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  BoqTreeCategory,
  BoqTreeChapterResponse,
  BoqTreeItem,
  PricingKbCandidate,
  PricingKbCandidateResponse,
  QuotaTreeItemDetail,
  fetchBoqTreeChapter,
  fetchBoqTreeTopCategories,
  fetchPricingKbCandidates,
  fetchQuotaTreeItemDetail,
} from '@/lib/api'

const DEFAULT_CHAPTER_ID = 228

function splitTitle(title: string) {
  const match = title.match(/^([0-9A-Z]+)\s+(.+)$/)
  if (!match) return { code: '', name: title }
  return { code: match[1], name: match[2] }
}

function StatPill({ label, value }: { label: string; value: number | string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-500">
      {label}
      <span className="font-semibold tabular-nums text-gray-800">{value}</span>
    </span>
  )
}

function CategorySidebar({
  categories,
  selectedId,
  onSelect,
}: {
  categories: BoqTreeCategory[]
  selectedId: number
  onSelect: (category: BoqTreeCategory) => void
}) {
  return (
    <aside className="border-b border-gray-200 bg-white lg:border-b-0 lg:border-r">
      <div className="border-b border-gray-200 px-4 py-3">
        <div className="text-sm font-semibold text-gray-900">清单大类</div>
        <div className="mt-0.5 text-xs text-gray-400">国标清单(2024含深圳补充)</div>
      </div>
      <div className="max-h-[42vh] overflow-y-auto py-2 lg:max-h-[calc(100vh-210px)]">
        {categories.map(category => {
          const title = splitTitle(category.zjmc)
          const enabled = category.enabled !== false
          return (
            <button
              key={category.id}
              onClick={() => enabled && onSelect(category)}
              disabled={!enabled}
              className={`w-full border-l-2 px-4 py-2.5 text-left text-sm transition ${
                selectedId === category.id
                  ? 'border-blue-700 bg-blue-50 text-blue-700'
                  : enabled
                    ? 'border-transparent text-gray-700 hover:bg-gray-50'
                    : 'border-transparent text-gray-400'
              }`}
            >
              <div className="flex items-start gap-2">
                {title.code && <span className="mt-0.5 font-mono text-xs">{title.code}</span>}
                <span className="font-medium leading-snug">{title.name}</span>
              </div>
              {!enabled && <div className="mt-1 text-xs text-gray-400">稍后开放</div>}
            </button>
          )
        })}
      </div>
    </aside>
  )
}

function LinkStatusBadge({ status }: { status: string }) {
  const cls =
    status === 'matched'
      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
      : status === 'review'
        ? 'border-amber-200 bg-amber-50 text-amber-700'
        : status === 'unmatched'
          ? 'border-red-200 bg-red-50 text-red-700'
          : 'border-gray-200 bg-gray-50 text-gray-500'
  return <span className={`rounded border px-2 py-0.5 text-xs ${cls}`}>{status}</span>
}

function ItemRow({
  item,
  depth,
  selected,
  onSelect,
}: {
  item: BoqTreeItem
  depth: number
  selected: boolean
  onSelect: (item: BoqTreeItem) => void
}) {
  return (
    <button
      onClick={() => onSelect(item)}
      className={`w-full border-t border-gray-100 px-3 py-2 text-left transition ${
        selected ? 'bg-blue-50/70' : 'bg-white hover:bg-blue-50/40'
      }`}
      style={{ paddingLeft: `${depth * 24 + 44}px` }}
    >
      <div className="grid gap-2 text-sm md:grid-cols-[140px_minmax(220px,1fr)_90px_110px] md:items-center">
        <div className="font-mono font-semibold text-blue-700">{item.zmbh}</div>
        <div className="font-medium text-gray-900">{item.zmmc}</div>
        <div className="text-gray-500">单位：{item.dw ?? '-'}</div>
        <div className="text-gray-500">候选：<span className="font-semibold tabular-nums text-gray-800">{item.candidate_count}</span></div>
      </div>
    </button>
  )
}

function CandidateDetail({
  detail,
}: {
  detail: QuotaTreeItemDetail
}) {
  return (
    <div className="mt-3 space-y-3 border-t border-gray-100 pt-3">
      {detail.resources.length > 0 && (
        <div>
          <div className="mb-2 text-xs font-semibold text-gray-500">工料机消耗量</div>
          <div className="overflow-x-auto border border-gray-200">
            <table className="min-w-full divide-y divide-gray-200 text-xs">
              <thead className="bg-gray-50 text-gray-500">
                <tr>
                  <th className="px-2 py-2 text-left font-medium">类型</th>
                  <th className="px-2 py-2 text-left font-medium">编码</th>
                  <th className="px-2 py-2 text-left font-medium">名称</th>
                  <th className="px-2 py-2 text-left font-medium">单位</th>
                  <th className="px-2 py-2 text-right font-medium">消耗量</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {detail.resources.map((resource, index) => (
                  <tr key={`${resource.resource_code ?? ''}-${index}`}>
                    <td className="px-2 py-2 text-gray-500">{resource.resource_type ?? '-'}</td>
                    <td className="px-2 py-2 font-mono text-gray-500">{resource.resource_code ?? '-'}</td>
                    <td className="px-2 py-2 text-gray-900">{resource.resource_name}</td>
                    <td className="px-2 py-2 text-gray-500">{resource.unit ?? '-'}</td>
                    <td className="px-2 py-2 text-right font-mono text-gray-900">{resource.quantity ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {detail.conversion_rules.length > 0 && (
        <div>
          <div className="mb-2 text-xs font-semibold text-gray-500">换算说明</div>
          <div className="space-y-2">
            {detail.conversion_rules.map((rule, index) => (
              <div key={index} className="rounded border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-700">
                {rule.prompt && <div className="font-medium text-gray-900">{rule.prompt}</div>}
                {rule.description && <div className="mt-1 whitespace-pre-wrap">{rule.description}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {detail.input_prompts.length > 0 && (
        <div>
          <div className="mb-2 text-xs font-semibold text-gray-500">实际值提示</div>
          <div className="space-y-1">
            {detail.input_prompts.map((prompt, index) => (
              <div key={index} className="rounded border border-gray-200 bg-white px-3 py-2 text-xs text-gray-700">
                {prompt}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function CandidatePanel({
  selectedItem,
  candidates,
  loading,
  details,
  expandedDetailKeys,
  loadingDetailKeys,
  onToggleDetail,
  onClose,
  className = 'mt-4',
}: {
  selectedItem: BoqTreeItem | null
  candidates?: PricingKbCandidateResponse
  loading: boolean
  details: Record<string, QuotaTreeItemDetail>
  expandedDetailKeys: Set<string>
  loadingDetailKeys: Set<string>
  onToggleDetail: (candidate: PricingKbCandidate) => void
  onClose?: () => void
  className?: string
}) {
  if (!selectedItem) {
    return (
      <div className={`${className} border border-gray-200 bg-white px-4 py-8 text-center text-sm text-gray-400`}>
        点击末级清单项目后，在这里查看候选定额。
      </div>
    )
  }

  const grouped = new Map<string, PricingKbCandidate[]>()
  for (const candidate of candidates?.candidates ?? []) {
    const key = `${candidate.quota_item.library_name} / ${candidate.quota_item.chapter_name ?? '未分类'}`
    grouped.set(key, [...(grouped.get(key) ?? []), candidate])
  }

  return (
    <div className={`${className} overflow-hidden border border-gray-200 bg-white`}>
      <div className="border-b border-gray-200 bg-gray-50 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-sm font-semibold text-gray-900">候选定额</div>
            <div className="mt-1 text-xs text-gray-500">
              {selectedItem.zmbh} {selectedItem.zmmc}，单位：{selectedItem.dw ?? '-'}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatPill label="候选" value={loading ? '加载中' : candidates?.total ?? selectedItem.candidate_count} />
            {onClose && (
              <button
                onClick={onClose}
                className="flex h-8 w-8 items-center justify-center rounded border border-gray-200 bg-white text-lg leading-none text-gray-500 hover:bg-gray-100 hover:text-gray-900"
                title="关闭候选定额"
                aria-label="关闭候选定额"
              >
                ×
              </button>
            )}
          </div>
        </div>
      </div>

      {loading && <div className="px-4 py-8 text-center text-sm text-gray-400">候选定额加载中...</div>}
      {!loading && candidates && candidates.total === 0 && (
        <div className="px-4 py-8 text-center text-sm text-gray-400">暂无候选定额</div>
      )}
      {!loading && candidates && candidates.total > 0 && (
        <div className="divide-y divide-gray-200">
          {Array.from(grouped.entries()).map(([groupName, groupCandidates]) => (
            <section key={groupName} className="bg-white">
              <div className="border-b border-gray-100 bg-white px-4 py-2 text-xs font-semibold text-gray-600">
                {groupName}
              </div>
              <div className="divide-y divide-gray-100">
                {groupCandidates.map(candidate => {
                  const key = `${candidate.quota_item.source_library_id}:${candidate.quota_item.id}`
                  const detail = details[key]
                  const expanded = expandedDetailKeys.has(key)
                  const loadingDetail = loadingDetailKeys.has(key)
                  return (
                    <div key={candidate.candidate_id} className="px-4 py-3">
                      <div className="grid gap-2 text-sm lg:grid-cols-[140px_minmax(240px,1fr)_90px_110px_120px] lg:items-start">
                        <div className="font-mono font-semibold text-blue-700">{candidate.quota_item.code ?? '-'}</div>
                        <div>
                          <div className="font-medium text-gray-900">{candidate.quota_item.name}</div>
                          {candidate.quota_item.work_content && (
                            <div className="mt-1 text-xs leading-5 text-gray-500">
                              工作内容：{candidate.quota_item.work_content}
                            </div>
                          )}
                        </div>
                        <div className="text-gray-500">单位：{candidate.quota_item.unit ?? '-'}</div>
                        <LinkStatusBadge status={candidate.target_link.link_status} />
                        <button
                          onClick={() => onToggleDetail(candidate)}
                          className="w-fit rounded border border-blue-200 px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-50"
                        >
                          {loadingDetail ? '加载中...' : expanded ? '收起详情' : '完整信息'}
                        </button>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-500">
                        <StatPill label="工料机" value={candidate.resource_count} />
                        <StatPill label="换算" value={candidate.conversion_rules.length} />
                      </div>
                      {expanded && detail && <CandidateDetail detail={detail} />}
                    </div>
                  )
                })}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

function TreeNode({
  node,
  depth,
  chapterData,
  loadingIds,
  expandedIds,
  selectedItemId,
  onToggle,
  onSelectItem,
}: {
  node: BoqTreeCategory
  depth: number
  chapterData: Record<number, BoqTreeChapterResponse>
  loadingIds: Set<number>
  expandedIds: Set<number>
  selectedItemId: number | null
  onToggle: (node: BoqTreeCategory) => void
  onSelectItem: (item: BoqTreeItem) => void
}) {
  const expanded = expandedIds.has(node.id)
  const data = chapterData[node.id]
  const hasChildren = node.child_count > 0 || node.item_count > 0
  const title = splitTitle(node.zjmc)

  return (
    <div className="border-t border-gray-100">
      <button
        onClick={() => onToggle(node)}
        className="flex w-full items-center gap-2 bg-white px-3 py-2.5 text-left text-sm hover:bg-blue-50/40"
        style={{ paddingLeft: `${depth * 24 + 16}px` }}
      >
        <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded border text-xs ${
          hasChildren ? 'border-blue-200 text-blue-700' : 'border-gray-200 text-gray-300'
        }`}>
          {hasChildren ? (expanded ? '-' : '+') : ''}
        </span>
        {title.code && <span className="w-20 shrink-0 font-mono font-semibold text-blue-700">{title.code}</span>}
        <span className="min-w-0 flex-1 font-medium text-gray-900">{title.name}</span>
        {loadingIds.has(node.id) && <span className="text-xs text-blue-600">加载中...</span>}
      </button>

      {expanded && data && (
        <div>
          {data.children.map(child => (
            <TreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              chapterData={chapterData}
              loadingIds={loadingIds}
              expandedIds={expandedIds}
              selectedItemId={selectedItemId}
              onToggle={onToggle}
              onSelectItem={onSelectItem}
            />
          ))}
          {data.items.map(item => (
            <ItemRow
              key={item.id}
              item={item}
              depth={depth + 1}
              selected={selectedItemId === item.id}
              onSelect={onSelectItem}
            />
          ))}
          {data.children.length === 0 && data.items.length === 0 && (
            <div className="border-t border-gray-100 bg-white px-3 py-6 text-center text-sm text-gray-400">
              暂无下级内容
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function BoqStandardManagementPage() {
  const [categories, setCategories] = useState<BoqTreeCategory[]>([])
  const [selectedCategory, setSelectedCategory] = useState<BoqTreeCategory | null>(null)
  const [chapterData, setChapterData] = useState<Record<number, BoqTreeChapterResponse>>({})
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())
  const [loadingIds, setLoadingIds] = useState<Set<number>>(new Set())
  const [selectedItem, setSelectedItem] = useState<BoqTreeItem | null>(null)
  const [candidateData, setCandidateData] = useState<Record<number, PricingKbCandidateResponse>>({})
  const [loadingCandidateId, setLoadingCandidateId] = useState<number | null>(null)
  const [quotaDetails, setQuotaDetails] = useState<Record<string, QuotaTreeItemDetail>>({})
  const [expandedQuotaDetailKeys, setExpandedQuotaDetailKeys] = useState<Set<string>>(new Set())
  const [loadingQuotaDetailKeys, setLoadingQuotaDetailKeys] = useState<Set<string>>(new Set())
  const [error, setError] = useState('')

  const selectedData = selectedCategory ? chapterData[selectedCategory.id] : null
  const selectedStats = useMemo(() => {
    if (!selectedData) return { childCount: 0, itemCount: 0 }
    return {
      childCount: selectedData.children.length,
      itemCount: selectedData.children.reduce((sum, child) => sum + child.item_count, selectedData.items.length),
    }
  }, [selectedData])

  const loadChapter = useCallback(async (chapterId: number) => {
    if (chapterData[chapterId]) return chapterData[chapterId]
    setLoadingIds(prev => new Set(prev).add(chapterId))
    setError('')
    try {
      const data = await fetchBoqTreeChapter(chapterId)
      setChapterData(prev => ({ ...prev, [chapterId]: data }))
      return data
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加载章节失败')
      throw reason
    } finally {
      setLoadingIds(prev => {
        const next = new Set(prev)
        next.delete(chapterId)
        return next
      })
    }
  }, [chapterData])

  useEffect(() => {
    fetchBoqTreeTopCategories()
      .then(data => {
        setCategories(data)
        const building = data.find(item => item.id === DEFAULT_CHAPTER_ID) ?? data[0] ?? null
        if (building) {
          setSelectedCategory(building)
          setExpandedIds(new Set([building.id]))
          loadChapter(building.id).catch(() => undefined)
        }
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : '加载清单大类失败'))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleCategorySelect(category: BoqTreeCategory) {
    setSelectedCategory(category)
    setExpandedIds(new Set([category.id]))
    setSelectedItem(null)
    setExpandedQuotaDetailKeys(new Set())
    await loadChapter(category.id)
  }

  async function toggleNode(node: BoqTreeCategory) {
    const isExpanded = expandedIds.has(node.id)
    if (isExpanded) {
      setExpandedIds(prev => {
        const next = new Set(prev)
        next.delete(node.id)
        return next
      })
      return
    }
    setExpandedIds(prev => new Set(prev).add(node.id))
    if (node.child_count > 0 || node.item_count > 0) {
      await loadChapter(node.id)
    }
  }

  async function handleItemSelect(item: BoqTreeItem) {
    setSelectedItem(item)
    setError('')
    if (candidateData[item.id]) return
    setLoadingCandidateId(item.id)
    try {
      const data = await fetchPricingKbCandidates(item.id)
      setCandidateData(prev => ({ ...prev, [item.id]: data }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加载候选定额失败')
    } finally {
      setLoadingCandidateId(current => current === item.id ? null : current)
    }
  }

  async function toggleCandidateDetail(candidate: PricingKbCandidate) {
    const key = `${candidate.quota_item.source_library_id}:${candidate.quota_item.id}`
    if (expandedQuotaDetailKeys.has(key)) {
      setExpandedQuotaDetailKeys(prev => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
      return
    }
    setExpandedQuotaDetailKeys(prev => new Set(prev).add(key))
    if (quotaDetails[key]) return
    setLoadingQuotaDetailKeys(prev => new Set(prev).add(key))
    try {
      const detail = await fetchQuotaTreeItemDetail(candidate.quota_item.source_library_id, candidate.quota_item.id)
      setQuotaDetails(prev => ({ ...prev, [key]: detail }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加载候选定额详情失败')
    } finally {
      setLoadingQuotaDetailKeys(prev => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
    }
  }

  return (
    <div className="min-h-[calc(100vh-104px)] bg-gray-50">
      <div className="border-b border-gray-200 bg-white px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-gray-900">国标清单管理</h1>
            <p className="mt-1 text-sm text-gray-500">按国标清单章节逐级浏览，支持 01-09 及深圳市补充清单。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatPill label="大类" value={categories.length || '-'} />
            <StatPill label="当前下级" value={selectedStats.childCount} />
            <StatPill label="当前清单" value={selectedStats.itemCount} />
          </div>
        </div>
        {error && <div className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
      </div>

      <div className="grid min-h-[calc(100vh-210px)] lg:grid-cols-[300px_minmax(0,1fr)]">
        <CategorySidebar
          categories={categories}
          selectedId={selectedCategory?.id ?? DEFAULT_CHAPTER_ID}
          onSelect={handleCategorySelect}
        />

        <main className="min-w-0 p-4 sm:p-5">
          <div className="mb-4 border border-gray-200 bg-white px-4 py-3">
            <div className="text-sm font-semibold text-gray-900">
              {selectedCategory?.zjmc ?? '01 房屋建筑与装饰工程'}
            </div>
            <div className="mt-1 text-xs text-gray-500">
              点击章节左侧的 + 展开下一层，最末级显示清单项目。
            </div>
          </div>

          <div className="overflow-hidden border border-gray-200 bg-white">
            <div className="border-b border-gray-200 bg-gray-50 px-4 py-2.5 text-xs font-medium text-gray-600">
              章节树 / 清单项目
            </div>
            {!selectedCategory && (
              <div className="px-4 py-12 text-center text-sm text-gray-400">暂无清单大类</div>
            )}
            {selectedCategory && (
              <TreeNode
                node={selectedCategory}
                depth={0}
                chapterData={chapterData}
                loadingIds={loadingIds}
                expandedIds={expandedIds}
                selectedItemId={selectedItem?.id ?? null}
                onToggle={toggleNode}
                onSelectItem={handleItemSelect}
              />
            )}
          </div>
        </main>
      </div>

      {selectedItem && (
        <div className="fixed inset-0 z-40 flex justify-end bg-gray-950/25" onClick={() => setSelectedItem(null)}>
          <div
            className="h-full w-full overflow-y-auto border-l border-gray-200 bg-gray-50 shadow-2xl sm:w-[88vw] xl:w-[72vw] 2xl:w-[64vw]"
            onClick={event => event.stopPropagation()}
          >
            <CandidatePanel
              selectedItem={selectedItem}
              candidates={candidateData[selectedItem.id]}
              loading={loadingCandidateId === selectedItem.id}
              details={quotaDetails}
              expandedDetailKeys={expandedQuotaDetailKeys}
              loadingDetailKeys={loadingQuotaDetailKeys}
              onToggleDetail={toggleCandidateDetail}
              onClose={() => setSelectedItem(null)}
              className="min-h-full border-0"
            />
          </div>
        </div>
      )}
    </div>
  )
}
