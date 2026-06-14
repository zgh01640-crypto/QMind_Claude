'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  PricingKbQuotaItem,
  QuotaTreeCategory,
  QuotaTreeChapterResponse,
  QuotaTreeItem,
  QuotaTreeItemDetail,
  fetchPricingKbQuotaItems,
  fetchQuotaTreeChapter,
  fetchQuotaTreeItemDetail,
  fetchQuotaTreeTopLibraries,
} from '@/lib/api'

const DEFAULT_DEKID = 1020109

function nodeKey(dekid: number, id: number) {
  return `${dekid}:${id}`
}

function splitTitle(title: string, normalizeTopChapter = false) {
  const normalized = normalizeTopChapter
    ? title.replace(/^(\d+)\.3\s+(.+?)(?:\s+子目构成表)?$/, '$1 $2')
    : title
  const match = normalized.match(/^([0-9.]+)\s+(.+)$/)
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

function LibrarySidebar({
  libraries,
  selectedKey,
  onSelect,
}: {
  libraries: QuotaTreeCategory[]
  selectedKey: string
  onSelect: (library: QuotaTreeCategory) => void
}) {
  return (
    <aside className="border-b border-gray-200 bg-white lg:border-b-0 lg:border-r">
      <div className="border-b border-gray-200 px-4 py-3">
        <div className="text-sm font-semibold text-gray-900">定额专业库</div>
        <div className="mt-0.5 text-xs text-gray-400">TDEK_TZJMC 根节点</div>
      </div>
      <div className="max-h-[42vh] overflow-y-auto py-2 lg:max-h-[calc(100vh-210px)]">
        {libraries.map(library => {
          const active = selectedKey === nodeKey(library.dekid, library.id)
          return (
            <button
              key={nodeKey(library.dekid, library.id)}
              onClick={() => onSelect(library)}
              className={`w-full border-l-2 px-4 py-2.5 text-left text-sm transition ${
                active
                  ? 'border-blue-700 bg-blue-50 text-blue-700'
                  : 'border-transparent text-gray-700 hover:bg-gray-50'
              }`}
            >
              <div className="font-medium leading-snug">{library.zjmc}</div>
              <div className="mt-1 font-mono text-xs text-gray-400">DEKID {library.dekid}</div>
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

function ItemDetailView({ detail }: { detail: QuotaTreeItemDetail }) {
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
                    <td className="px-2 py-2 text-right font-mono text-gray-900">
                      {resource.quantity ?? '-'}
                    </td>
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

function ItemRow({
  item,
  depth,
  detail,
  loading,
  expanded,
  onToggle,
}: {
  item: QuotaTreeItem
  depth: number
  detail?: QuotaTreeItemDetail
  loading: boolean
  expanded: boolean
  onToggle: (item: QuotaTreeItem) => void
}) {
  return (
    <div className="border-t border-gray-100 bg-white px-3 py-3" style={{ paddingLeft: `${depth * 24 + 44}px` }}>
      <div className="grid gap-2 text-sm lg:grid-cols-[140px_minmax(220px,1fr)_90px_120px_120px] lg:items-start">
        <div className="font-mono font-semibold text-blue-700">{item.zmbh ?? '-'}</div>
        <div>
          <div className="font-medium text-gray-900">{item.zmmc}</div>
          {item.gznr && <div className="mt-1 text-xs leading-5 text-gray-500">工作内容：{item.gznr}</div>}
        </div>
        <div className="text-gray-500">单位：{item.dw ?? '-'}</div>
        <LinkStatusBadge status={item.link_status} />
        <button
          onClick={() => onToggle(item)}
          className="w-fit rounded border border-blue-200 px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-50"
        >
          {loading ? '加载中...' : expanded ? '收起详情' : '查看完整信息'}
        </button>
      </div>
      {expanded && detail && <ItemDetailView detail={detail} />}
    </div>
  )
}

function TreeNode({
  node,
  depth,
  chapterData,
  loadingKeys,
  expandedKeys,
  detailData,
  detailLoadingKeys,
  detailExpandedKeys,
  onToggle,
  onToggleItem,
}: {
  node: QuotaTreeCategory
  depth: number
  chapterData: Record<string, QuotaTreeChapterResponse>
  loadingKeys: Set<string>
  expandedKeys: Set<string>
  detailData: Record<string, QuotaTreeItemDetail>
  detailLoadingKeys: Set<string>
  detailExpandedKeys: Set<string>
  onToggle: (node: QuotaTreeCategory) => void
  onToggleItem: (item: QuotaTreeItem) => void
}) {
  const key = nodeKey(node.dekid, node.id)
  const expanded = expandedKeys.has(key)
  const data = chapterData[key]
  const hasChildren = node.child_count > 0 || node.item_count > 0
  const title = splitTitle(node.zjmc, depth === 1)

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
        {loadingKeys.has(key) && <span className="text-xs text-blue-600">加载中...</span>}
      </button>

      {expanded && data && (
        <div>
          {data.children.map(child => (
            <TreeNode
              key={nodeKey(child.dekid, child.id)}
              node={child}
              depth={depth + 1}
              chapterData={chapterData}
              loadingKeys={loadingKeys}
              expandedKeys={expandedKeys}
              detailData={detailData}
              detailLoadingKeys={detailLoadingKeys}
              detailExpandedKeys={detailExpandedKeys}
              onToggle={onToggle}
              onToggleItem={onToggleItem}
            />
          ))}
          {data.items.map(item => {
            const itemKey = nodeKey(item.dekid, item.id)
            return (
              <ItemRow
                key={itemKey}
                item={item}
                depth={depth + 1}
                detail={detailData[itemKey]}
                loading={detailLoadingKeys.has(itemKey)}
                expanded={detailExpandedKeys.has(itemKey)}
                onToggle={onToggleItem}
              />
            )
          })}
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

export default function QuotaManagementPage() {
  const [libraries, setLibraries] = useState<QuotaTreeCategory[]>([])
  const [selectedLibrary, setSelectedLibrary] = useState<QuotaTreeCategory | null>(null)
  const [chapterData, setChapterData] = useState<Record<string, QuotaTreeChapterResponse>>({})
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set())
  const [loadingKeys, setLoadingKeys] = useState<Set<string>>(new Set())
  const [detailData, setDetailData] = useState<Record<string, QuotaTreeItemDetail>>({})
  const [detailExpandedKeys, setDetailExpandedKeys] = useState<Set<string>>(new Set())
  const [detailLoadingKeys, setDetailLoadingKeys] = useState<Set<string>>(new Set())
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<PricingKbQuotaItem[]>([])
  const [searchTotal, setSearchTotal] = useState(0)
  const [searchLoading, setSearchLoading] = useState(false)
  const [error, setError] = useState('')

  const selectedKey = selectedLibrary ? nodeKey(selectedLibrary.dekid, selectedLibrary.id) : ''
  const selectedData = selectedKey ? chapterData[selectedKey] : null
  const selectedStats = useMemo(() => {
    if (!selectedData) return { childCount: 0, itemCount: 0 }
    return {
      childCount: selectedData.children.length,
      itemCount: selectedData.children.reduce((sum, child) => sum + child.item_count, selectedData.items.length),
    }
  }, [selectedData])

  const loadChapter = useCallback(async (dekid: number, chapterId: number) => {
    const key = nodeKey(dekid, chapterId)
    if (chapterData[key]) return chapterData[key]
    setLoadingKeys(prev => new Set(prev).add(key))
    setError('')
    try {
      const data = await fetchQuotaTreeChapter(dekid, chapterId)
      setChapterData(prev => ({ ...prev, [key]: data }))
      return data
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加载定额章节失败')
      throw reason
    } finally {
      setLoadingKeys(prev => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
    }
  }, [chapterData])

  useEffect(() => {
    fetchQuotaTreeTopLibraries()
      .then(data => {
        setLibraries(data)
        const defaultLibrary = data.find(item => item.dekid === DEFAULT_DEKID) ?? data[0] ?? null
        if (defaultLibrary) {
          const key = nodeKey(defaultLibrary.dekid, defaultLibrary.id)
          setSelectedLibrary(defaultLibrary)
          setExpandedKeys(new Set([key]))
          loadChapter(defaultLibrary.dekid, defaultLibrary.id).catch(() => undefined)
        }
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : '加载定额专业库失败'))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleLibrarySelect(library: QuotaTreeCategory) {
    const key = nodeKey(library.dekid, library.id)
    setSelectedLibrary(library)
    setExpandedKeys(new Set([key]))
    setDetailExpandedKeys(new Set())
    await loadChapter(library.dekid, library.id)
  }

  async function toggleNode(node: QuotaTreeCategory) {
    const key = nodeKey(node.dekid, node.id)
    const isExpanded = expandedKeys.has(key)
    if (isExpanded) {
      setExpandedKeys(prev => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
      return
    }
    setExpandedKeys(prev => new Set(prev).add(key))
    if (node.child_count > 0 || node.item_count > 0) {
      await loadChapter(node.dekid, node.id)
    }
  }

  async function toggleItem(item: QuotaTreeItem) {
    const key = nodeKey(item.dekid, item.id)
    if (detailExpandedKeys.has(key)) {
      setDetailExpandedKeys(prev => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
      return
    }
    setDetailExpandedKeys(prev => new Set(prev).add(key))
    if (detailData[key]) return
    setDetailLoadingKeys(prev => new Set(prev).add(key))
    try {
      const detail = await fetchQuotaTreeItemDetail(item.dekid, item.id)
      setDetailData(prev => ({ ...prev, [key]: detail }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加载定额子目详情失败')
    } finally {
      setDetailLoadingKeys(prev => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
    }
  }

  async function handleSearch(event?: FormEvent) {
    event?.preventDefault()
    const query = searchInput.trim()
    setSearchQuery(query)
    setSearchResults([])
    setSearchTotal(0)
    if (!query) return
    setSearchLoading(true)
    setError('')
    try {
      const data = await fetchPricingKbQuotaItems({
        q: query,
        library_id: selectedLibrary?.dekid ?? null,
        page: 1,
        page_size: 80,
      })
      setSearchResults(data.items)
      setSearchTotal(data.total)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '搜索定额失败')
    } finally {
      setSearchLoading(false)
    }
  }

  function clearSearch() {
    setSearchInput('')
    setSearchQuery('')
    setSearchResults([])
    setSearchTotal(0)
  }

  function searchResultToTreeItem(item: PricingKbQuotaItem): QuotaTreeItem {
    return {
      id: item.id,
      dekid: item.source_library_id,
      zmbh: item.code,
      zmmc: item.name,
      dw: item.unit,
      gznr: null,
      zjh: 0,
      chapter_name: item.chapter_name,
      resource_count: 0,
      conversion_rule_count: 0,
      input_prompt_count: 0,
      link_status: item.link_status,
      target_table: item.target_table,
      target_item_id: item.target_item_id,
    }
  }

  return (
    <div className="min-h-[calc(100vh-104px)] bg-gray-50">
      <div className="border-b border-gray-200 bg-white px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-gray-900">定额管理</h1>
            <p className="mt-1 text-sm text-gray-500">按 TDEK_TZJMC 章节树浏览定额专业库，末级展示 TDEK_TDEZM 子目详情。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatPill label="专业库" value={libraries.length || '-'} />
            <StatPill label="当前下级" value={selectedStats.childCount} />
            <StatPill label="当前子目" value={selectedStats.itemCount} />
            <StatPill label="库内子目" value={selectedLibrary?.quota_count ?? '-'} />
          </div>
        </div>
        {error && <div className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
      </div>

      <div className="grid min-h-[calc(100vh-210px)] lg:grid-cols-[320px_minmax(0,1fr)]">
        <LibrarySidebar
          libraries={libraries}
          selectedKey={selectedKey}
          onSelect={handleLibrarySelect}
        />

        <main className="min-w-0 p-4 sm:p-5">
          <div className="mb-4 border border-gray-200 bg-white px-4 py-3">
            <div className="text-sm font-semibold text-gray-900">
              {selectedLibrary?.zjmc ?? '定额专业库'}
            </div>
            <div className="mt-1 text-xs text-gray-500">
              点击章节左侧的 + 展开下一层；出现定额子目后可展开查看完整工料机和换算信息。
            </div>
            <form onSubmit={handleSearch} className="mt-3 flex flex-col gap-2 sm:flex-row">
              <input
                value={searchInput}
                onChange={event => setSearchInput(event.target.value)}
                placeholder="搜索定额编码或名称，例如 010001-32、加气混凝土"
                className="min-w-0 flex-1 rounded border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              />
              <button type="submit" disabled={searchLoading} className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
                {searchLoading ? '搜索中...' : '搜索'}
              </button>
              {searchQuery && (
                <button type="button" onClick={clearSearch} className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
                  清除
                </button>
              )}
            </form>
          </div>

          {searchQuery ? (
            <div className="overflow-hidden border border-gray-200 bg-white">
              <div className="border-b border-gray-200 bg-gray-50 px-4 py-2.5 text-xs font-medium text-gray-600">
                搜索结果：{searchLoading ? '搜索中...' : `共 ${searchTotal} 条，显示前 ${searchResults.length} 条`}
              </div>
              {!searchLoading && searchResults.length === 0 && (
                <div className="px-4 py-12 text-center text-sm text-gray-400">未找到匹配定额</div>
              )}
              <div className="divide-y divide-gray-100">
                {searchResults.map(item => {
                  const treeItem = searchResultToTreeItem(item)
                  const itemKey = nodeKey(treeItem.dekid, treeItem.id)
                  return (
                    <ItemRow
                      key={itemKey}
                      item={treeItem}
                      depth={0}
                      detail={detailData[itemKey]}
                      loading={detailLoadingKeys.has(itemKey)}
                      expanded={detailExpandedKeys.has(itemKey)}
                      onToggle={toggleItem}
                    />
                  )
                })}
              </div>
            </div>
          ) : (
          <div className="overflow-hidden border border-gray-200 bg-white">
            <div className="border-b border-gray-200 bg-gray-50 px-4 py-2.5 text-xs font-medium text-gray-600">
              定额章节树 / 定额子目
            </div>
            {!selectedLibrary && (
              <div className="px-4 py-12 text-center text-sm text-gray-400">暂无定额专业库</div>
            )}
            {selectedLibrary && (
              <TreeNode
                node={selectedLibrary}
                depth={0}
                chapterData={chapterData}
                loadingKeys={loadingKeys}
                expandedKeys={expandedKeys}
                detailData={detailData}
                detailLoadingKeys={detailLoadingKeys}
                detailExpandedKeys={detailExpandedKeys}
                onToggle={toggleNode}
                onToggleItem={toggleItem}
              />
            )}
          </div>
          )}
        </main>
      </div>
    </div>
  )
}
