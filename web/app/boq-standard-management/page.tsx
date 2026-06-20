'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  BoqFeatureDefaultList,
  BoqProcessList,
  BoqTreeCategory,
  BoqTreeChapterResponse,
  BoqTreeItem,
  PricingKbCandidate,
  PricingKbCandidateResponse,
  PricingKbBoqItem,
  QuotaTreeItemDetail,
  fetchBoqTreeChapter,
  fetchBoqTreeTopCategories,
  fetchBoqFeatureDefaults,
  fetchBoqProcesses,
  fetchPricingKbBoqItems,
  fetchPricingKbCandidates,
  fetchQuotaTreeItemDetail,
} from '@/lib/api'

const DEFAULT_CHAPTER_ID = 228
const PROCESS_PAGE_SIZE = 80
const FEATURE_DEFAULT_PAGE_SIZE = 80

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

const COST_LABELS = [
  ['dj', '综合单价'], ['rgf', '人工费'], ['clf', '材料费'], ['jxf', '机械费'],
  ['zcf', '主材费'], ['sbf', '设备费'], ['glf', '管理费'], ['lr', '利润'],
  ['aqwmsgf', '安全文明施工费'], ['qtcsf', '其他措施费'], ['gf', '规费'], ['sj', '税金'],
] as const

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
    <div
      className={`w-full border-t border-gray-100 px-3 py-2 text-left transition ${
        selected ? 'bg-blue-50/70' : 'bg-white hover:bg-blue-50/40'
      }`}
      style={{ paddingLeft: `${depth * 24 + 44}px` }}
    >
      <div className="grid gap-2 text-sm md:grid-cols-[140px_minmax(220px,1fr)_90px_110px] md:items-center">
        <div className="select-text font-mono font-semibold text-blue-700">{item.zmbh}</div>
        <div className="select-text font-medium text-gray-900">{item.zmmc}</div>
        <div className="text-gray-500">单位：{item.dw ?? '-'}</div>
        <div className="text-gray-500">
          候选：
          <button
            type="button"
            onClick={() => onSelect(item)}
            className={`rounded border px-2 py-0.5 font-semibold tabular-nums transition ${
              selected
                ? 'border-blue-600 bg-blue-600 text-white'
                : 'border-blue-200 bg-white text-blue-700 hover:bg-blue-50'
            }`}
            title="展开候选定额"
          >
            {item.candidate_count}
          </button>
        </div>
      </div>
    </div>
  )
}

function CandidateDetail({
  detail,
}: {
  detail: QuotaTreeItemDetail
}) {
  return (
    <div className="mt-3 space-y-3 border-t border-gray-100 pt-3">
      <div>
        <div className="mb-2 text-xs font-semibold text-gray-500">费用构成</div>
        <div className="grid grid-cols-2 border-l border-t border-gray-200 sm:grid-cols-3 xl:grid-cols-4">
          {COST_LABELS.map(([key, label]) => (
            <div key={key} className="border-b border-r border-gray-200 bg-white px-3 py-2">
              <div className="text-xs text-gray-500">{label}</div>
              <div className="mt-1 font-mono text-sm font-semibold text-gray-900">
                {detail.cost_breakdown?.[key]?.toFixed(2) ?? '-'}
              </div>
            </div>
          ))}
        </div>
      </div>

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

      {(detail.input_prompt_rules?.length ?? 0) > 0 && (
        <div>
          <div className="mb-2 text-xs font-semibold text-gray-500">实际值提示</div>
          <div className="overflow-x-auto border border-gray-200">
            <table className="min-w-full divide-y divide-gray-200 text-xs">
              <thead className="bg-gray-50 text-gray-500">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">提示</th>
                  <th className="px-3 py-2 text-left font-medium">关联换算编号</th>
                  <th className="px-3 py-2 text-right font-medium">基准值</th>
                  <th className="px-3 py-2 text-right font-medium">增减单位</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {(detail.input_prompt_rules ?? []).map((rule, index) => (
                  <tr key={`${rule.adjustment_code ?? ''}-${index}`}>
                    <td className="px-3 py-2 text-gray-700">{rule.prompt ?? '-'}</td>
                    <td className="px-3 py-2 font-mono text-blue-700">{rule.adjustment_code ?? '-'}</td>
                    <td className="px-3 py-2 text-right font-mono">{rule.base_value ?? '-'}</td>
                    <td className="px-3 py-2 text-right font-mono">{rule.increment_unit ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
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
                      <div className="grid gap-2 text-sm lg:grid-cols-[140px_minmax(240px,1fr)_90px_120px] lg:items-start">
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

function ProcessManagementPanel() {
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [appendixCode, setAppendixCode] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<BoqProcessList | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const loadProcesses = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await fetchBoqProcesses({
        q: searchQuery,
        appendix_code: appendixCode || null,
        library_id: null,
        page,
        page_size: PROCESS_PAGE_SIZE,
      })
      setData(result)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加载清单工序失败')
    } finally {
      setLoading(false)
    }
  }, [appendixCode, page, searchQuery])

  useEffect(() => {
    loadProcesses().catch(() => undefined)
  }, [loadProcesses])

  function handleSearch(event?: FormEvent) {
    event?.preventDefault()
    setSearchQuery(searchInput.trim())
    setPage(1)
  }

  function handleAppendixChange(value: string) {
    setAppendixCode(value)
    setPage(1)
  }

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PROCESS_PAGE_SIZE))

  return (
    <div className="space-y-4">
      <div className="border border-gray-200 bg-white px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-gray-900">清单工序管理</div>
            <div className="mt-1 text-xs text-gray-500">按清单编码、项目名称、工序名称检索标准施工工序。</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatPill label="工序链条" value={loading ? '加载中' : data?.total ?? '-'} />
            <StatPill label="清单" value={loading ? '加载中' : data?.item_total ?? '-'} />
            <StatPill label="附录" value={data?.appendices.length ?? '-'} />
          </div>
        </div>

        <form onSubmit={handleSearch} className="mt-3 grid gap-2 lg:grid-cols-[minmax(260px,1fr)_180px_auto_auto]">
          <input
            value={searchInput}
            onChange={event => setSearchInput(event.target.value)}
            placeholder="搜索编码、名称或工序链条，例如 010102001、砌块墙、开挖"
            className="min-w-0 rounded border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />
          <select
            value={appendixCode}
            onChange={event => handleAppendixChange(event.target.value)}
            className="rounded border border-gray-300 px-3 py-2 text-sm text-gray-700 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          >
            <option value="">全部附录</option>
            {(data?.appendices ?? []).map(appendix => (
              <option key={appendix.appendix_code ?? 'none'} value={appendix.appendix_code ?? ''}>
                {appendix.appendix_code ? `${appendix.appendix_code} ${appendix.appendix_name ?? ''}` : appendix.appendix_name ?? '未分组'}
              </option>
            ))}
          </select>
          <button type="submit" disabled={loading} className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
            {loading ? '查询中...' : '查询'}
          </button>
          {(searchQuery || appendixCode) && (
            <button
              type="button"
              onClick={() => {
                setSearchInput('')
                setSearchQuery('')
                setAppendixCode('')
                setPage(1)
              }}
              className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
            >
              清除
            </button>
          )}
        </form>

        {error && <div className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {(data?.appendices ?? []).slice(0, 8).map(appendix => (
          <button
            key={appendix.appendix_code ?? 'none'}
            onClick={() => handleAppendixChange(appendix.appendix_code ?? '')}
            className={`border px-3 py-2 text-left text-sm transition ${
              appendixCode === (appendix.appendix_code ?? '')
                ? 'border-blue-500 bg-blue-50'
                : 'border-gray-200 bg-white hover:border-blue-200 hover:bg-blue-50/40'
            }`}
          >
            <div className="font-semibold text-gray-900">
              {appendix.appendix_code ? `附录 ${appendix.appendix_code}` : '未分组'}
            </div>
            <div className="mt-1 truncate text-xs text-gray-500">{appendix.appendix_name ?? '-'}</div>
            <div className="mt-2 flex gap-2 text-xs text-gray-500">
              <span>清单 {appendix.item_count}</span>
              <span>链条 {appendix.process_count}</span>
            </div>
          </button>
        ))}
      </div>

      <div className="overflow-hidden border border-gray-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 bg-gray-50 px-4 py-2.5 text-xs text-gray-600">
          <span>工序链条：{loading ? '加载中...' : `共 ${data?.total ?? 0} 条，当前第 ${page}/${totalPages} 页`}</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(current => Math.max(1, current - 1))}
              disabled={page <= 1 || loading}
              className="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 disabled:opacity-40"
            >
              上一页
            </button>
            <button
              onClick={() => setPage(current => Math.min(totalPages, current + 1))}
              disabled={page >= totalPages || loading}
              className="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        </div>
        {!loading && (data?.items.length ?? 0) === 0 && (
          <div className="px-4 py-12 text-center text-sm text-gray-400">暂无工序链条数据</div>
        )}
        <div className="divide-y divide-gray-100">
          {(data?.items ?? []).map(item => (
            <div key={item.id} className="px-4 py-3">
              <div className="grid gap-3 text-sm xl:grid-cols-[120px_minmax(220px,1fr)_80px_minmax(320px,1.6fr)_110px] xl:items-start">
                <div>
                  <div className="font-mono font-semibold text-blue-700">{item.zmbh}</div>
                  <div className="mt-1 text-xs text-gray-400">源行 {item.source_rowid}</div>
                </div>
                <div>
                  <div className="font-medium text-gray-900">{item.zmmc}</div>
                  <div className="mt-1 text-xs text-gray-500">
                    {item.appendix_code ? `附录${item.appendix_code} ${item.appendix_name ?? ''}` : item.appendix_name ?? '-'}
                  </div>
                </div>
                <div className="text-gray-500">单位：{item.unit ?? '-'}</div>
                <div>
                  <div className="text-xs font-semibold text-gray-500">标准施工工序</div>
                  <div className="mt-1 leading-6 text-gray-800">{item.procedure_text}</div>
                </div>
                <div>
                  <span className={`rounded border px-2 py-0.5 text-xs ${
                    item.linked
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                      : 'border-amber-200 bg-amber-50 text-amber-700'
                  }`}>
                    {item.linked ? '已关联清单' : '未关联清单'}
                  </span>
                  <div className="mt-1 text-xs text-gray-400">{item.chapter_name ?? item.library_name}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function FeatureDefaultsPanel() {
  const [codeInput, setCodeInput] = useState('')
  const [itemNameInput, setItemNameInput] = useState('')
  const [featureNameInput, setFeatureNameInput] = useState('')
  const [codeQuery, setCodeQuery] = useState('')
  const [itemNameQuery, setItemNameQuery] = useState('')
  const [featureNameQuery, setFeatureNameQuery] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<BoqFeatureDefaultList | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const loadFeatureDefaults = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await fetchBoqFeatureDefaults({
        code: codeQuery,
        item_name: itemNameQuery,
        feature_name: featureNameQuery,
        library_id: null,
        page,
        page_size: FEATURE_DEFAULT_PAGE_SIZE,
      })
      setData(result)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加载综合考虑规则库失败')
    } finally {
      setLoading(false)
    }
  }, [codeQuery, featureNameQuery, itemNameQuery, page])

  useEffect(() => {
    loadFeatureDefaults().catch(() => undefined)
  }, [loadFeatureDefaults])

  function handleSearch(event?: FormEvent) {
    event?.preventDefault()
    setCodeQuery(codeInput.trim())
    setItemNameQuery(itemNameInput.trim())
    setFeatureNameQuery(featureNameInput.trim())
    setPage(1)
  }

  function clearSearch() {
    setCodeInput('')
    setItemNameInput('')
    setFeatureNameInput('')
    setCodeQuery('')
    setItemNameQuery('')
    setFeatureNameQuery('')
    setPage(1)
  }

  const totalPages = Math.max(1, Math.ceil((data?.item_total ?? 0) / FEATURE_DEFAULT_PAGE_SIZE))
  const hasQuery = Boolean(codeQuery || itemNameQuery || featureNameQuery)

  return (
    <div className="space-y-4">
      <div className="border border-gray-200 bg-white px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-gray-900">综合考虑规则库</div>
            <div className="mt-1 text-xs text-gray-500">
              展示清单编码关联的清单名称、特征名称、特征值和综合考虑默认值。
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatPill label="规则" value={loading ? '加载中' : data?.total ?? '-'} />
            <StatPill label="清单" value={loading ? '加载中' : data?.item_total ?? '-'} />
            <StatPill label="每页" value={FEATURE_DEFAULT_PAGE_SIZE} />
          </div>
        </div>

        <form onSubmit={handleSearch} className="mt-3 grid gap-2 xl:grid-cols-[160px_minmax(220px,1fr)_220px_auto_auto]">
          <input
            value={codeInput}
            onChange={event => setCodeInput(event.target.value)}
            placeholder="字母编号/编码，如 010101"
            className="min-w-0 rounded border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />
          <input
            value={itemNameInput}
            onChange={event => setItemNameInput(event.target.value)}
            placeholder="子目名称，如 砖砌体、混凝土"
            className="min-w-0 rounded border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />
          <input
            value={featureNameInput}
            onChange={event => setFeatureNameInput(event.target.value)}
            placeholder="特征名称，如 运距、强度等级"
            className="min-w-0 rounded border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />
          <button type="submit" disabled={loading} className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
            {loading ? '查询中...' : '查询'}
          </button>
          {hasQuery && (
            <button type="button" onClick={clearSearch} className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
              清除
            </button>
          )}
        </form>

        {error && <div className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
      </div>

      <div className="overflow-hidden border border-gray-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 bg-gray-50 px-4 py-2.5 text-xs text-gray-600">
          <span>综合考虑默认值：{loading ? '加载中...' : `共 ${data?.item_total ?? 0} 个清单、${data?.total ?? 0} 条规则，当前第 ${page}/${totalPages} 页`}</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(current => Math.max(1, current - 1))}
              disabled={page <= 1 || loading}
              className="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 disabled:opacity-40"
            >
              上一页
            </button>
            <button
              onClick={() => setPage(current => Math.min(totalPages, current + 1))}
              disabled={page >= totalPages || loading}
              className="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        </div>
        {!loading && (data?.items.length ?? 0) === 0 && (
          <div className="px-4 py-12 text-center text-sm text-gray-400">暂无综合考虑规则数据</div>
        )}
        <div className="divide-y divide-gray-100">
          {(data?.items ?? []).map(item => (
            <div key={item.id} className="px-4 py-3">
              <div className="grid gap-3 text-sm xl:grid-cols-[130px_minmax(240px,1fr)_150px] xl:items-start">
                <div>
                  <div className="font-mono font-semibold text-blue-700">{item.zmbh}</div>
                  <div className="mt-1 text-xs text-gray-400">{item.features.length} 条特征</div>
                </div>
                <div>
                  <div className="font-medium text-gray-900">{item.zmmc ?? '未关联清单名称'}</div>
                  <div className="mt-1 text-xs text-gray-500">
                    {item.chapter_name ?? item.library_name}
                    {item.unit ? ` / 单位：${item.unit}` : ''}
                  </div>
                </div>
                <div>
                  <span className={`rounded border px-2 py-0.5 text-xs ${
                    item.linked
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                      : 'border-amber-200 bg-amber-50 text-amber-700'
                  }`}>
                    {item.linked ? '已关联清单' : '未关联清单'}
                  </span>
                </div>
              </div>
              <div className="mt-3 overflow-x-auto border border-gray-200">
                <table className="min-w-full divide-y divide-gray-200 text-xs">
                  <thead className="bg-gray-50 text-gray-500">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium">特征名称</th>
                      <th className="px-3 py-2 text-left font-medium">特征值</th>
                      <th className="px-3 py-2 text-left font-medium">综合考虑默认值</th>
                      <th className="px-3 py-2 text-right font-medium">源行</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 bg-white">
                    {item.features.map(feature => (
                      <tr key={feature.id}>
                        <td className="px-3 py-2 font-medium text-gray-900">{feature.feature_name}</td>
                        <td className="px-3 py-2 text-gray-700">{feature.feature_value}</td>
                        <td className="px-3 py-2 text-gray-900">{feature.default_value}</td>
                        <td className="px-3 py-2 text-right font-mono text-gray-400">{feature.source_rowid}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function BoqStandardManagementPage() {
  const [categories, setCategories] = useState<BoqTreeCategory[]>([])
  const [activeTab, setActiveTab] = useState<'tree' | 'process' | 'featureDefaults'>('tree')
  const [selectedCategory, setSelectedCategory] = useState<BoqTreeCategory | null>(null)
  const [chapterData, setChapterData] = useState<Record<number, BoqTreeChapterResponse>>({})
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())
  const [loadingIds, setLoadingIds] = useState<Set<number>>(new Set())
  const [selectedItem, setSelectedItem] = useState<BoqTreeItem | null>(null)
  const [candidateData, setCandidateData] = useState<Record<string, PricingKbCandidateResponse>>({})
  const [loadingCandidateKey, setLoadingCandidateKey] = useState<string | null>(null)
  const [quotaDetails, setQuotaDetails] = useState<Record<string, QuotaTreeItemDetail>>({})
  const [expandedQuotaDetailKeys, setExpandedQuotaDetailKeys] = useState<Set<string>>(new Set())
  const [loadingQuotaDetailKeys, setLoadingQuotaDetailKeys] = useState<Set<string>>(new Set())
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<PricingKbBoqItem[]>([])
  const [searchTotal, setSearchTotal] = useState(0)
  const [searchLoading, setSearchLoading] = useState(false)
  const [error, setError] = useState('')

  const selectedData = selectedCategory ? chapterData[selectedCategory.id] : null
  const selectedStats = useMemo(() => {
    if (!selectedData) return { childCount: 0, itemCount: 0 }
    return {
      childCount: selectedData.children.length,
      itemCount:
        selectedData.chapter.descendant_item_count
        ?? selectedCategory?.descendant_item_count
        ?? selectedData.children.reduce(
          (sum, child) => sum + (child.descendant_item_count ?? child.item_count),
          selectedData.items.length,
        ),
    }
  }, [selectedCategory?.descendant_item_count, selectedData])

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
    const itemKey = `${item.qdkid}:${item.id}`
    if (selectedItem?.qdkid === item.qdkid && selectedItem.id === item.id) {
      setSelectedItem(null)
      setExpandedQuotaDetailKeys(new Set())
      return
    }
    setSelectedItem(item)
    setError('')
    if (candidateData[itemKey]) return
    setLoadingCandidateKey(itemKey)
    try {
      const data = await fetchPricingKbCandidates(item.id, item.qdkid)
      setCandidateData(prev => ({ ...prev, [itemKey]: data }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加载候选定额失败')
    } finally {
      setLoadingCandidateKey(current => current === itemKey ? null : current)
    }
  }

  async function handleSearch(event?: FormEvent) {
    event?.preventDefault()
    const query = searchInput.trim()
    setSearchQuery(query)
    setSearchResults([])
    setSearchTotal(0)
    setSelectedItem(null)
    if (!query) return
    setSearchLoading(true)
    setError('')
    try {
      const data = await fetchPricingKbBoqItems({
        q: query,
        library_id: null,
        page: 1,
        page_size: 80,
      })
      setSearchResults(data.items)
      setSearchTotal(data.total)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '搜索国标清单失败')
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

  function selectSearchResult(item: PricingKbBoqItem) {
    void handleItemSelect({
      id: item.id,
      qdkid: item.source_library_id,
      zmbh: item.code ?? '',
      zmmc: item.name,
      dw: item.unit,
      zjh: 0,
      chapter_name: item.chapter_name,
      candidate_count: item.candidate_count,
    })
  }

  function searchResultPath(item: PricingKbBoqItem) {
    const chapters = item.chapter_path?.length
      ? item.chapter_path
      : item.chapter_name
        ? [item.chapter_name]
        : []
    return [item.library_name, ...chapters].filter(Boolean)
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
    if (quotaDetails[key]?.cost_breakdown && quotaDetails[key]?.input_prompt_rules) return
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
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setActiveTab('tree')}
            className={`rounded border px-3 py-1.5 text-sm font-medium transition ${
              activeTab === 'tree'
                ? 'border-blue-600 bg-blue-600 text-white'
                : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
            }`}
          >
            国标清单管理
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('process')}
            className={`rounded border px-3 py-1.5 text-sm font-medium transition ${
              activeTab === 'process'
                ? 'border-blue-600 bg-blue-600 text-white'
                : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
            }`}
          >
            清单工序管理
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('featureDefaults')}
            className={`rounded border px-3 py-1.5 text-sm font-medium transition ${
              activeTab === 'featureDefaults'
                ? 'border-blue-600 bg-blue-600 text-white'
                : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
            }`}
          >
            综合考虑规则库
          </button>
        </div>
        {activeTab === 'tree' && (
          <div className="mt-4 border-t border-gray-100 pt-4">
            <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
              <div>
                <div className="text-sm font-semibold text-gray-900">全专业工程库查询</div>
                <div className="mt-0.5 text-xs text-gray-500">查询范围覆盖全部专业工程库，结果展示完整专业归属和章节级联关系。</div>
              </div>
              {searchQuery && (
                <div className="text-xs text-gray-500">
                  {searchLoading ? '查询中...' : `共 ${searchTotal} 条结果`}
                </div>
              )}
            </div>
            <form onSubmit={handleSearch} className="flex flex-col gap-2 sm:flex-row">
              <input
                value={searchInput}
                onChange={event => setSearchInput(event.target.value)}
                placeholder="搜索全部专业工程库中的清单编码或名称，例如 010402001、砌块墙"
                className="min-w-0 flex-1 rounded border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              />
              <button type="submit" disabled={searchLoading} className="rounded bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
                {searchLoading ? '查询中...' : '全库查询'}
              </button>
              {searchQuery && (
                <button type="button" onClick={clearSearch} className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
                  返回章节浏览
                </button>
              )}
            </form>
          </div>
        )}
      </div>

      {activeTab === 'tree' && searchQuery ? (
        <main className="p-4 sm:p-5">
          <div className="overflow-hidden border border-gray-200 bg-white">
            <div className="border-b border-gray-200 bg-gray-50 px-4 py-2.5 text-xs font-medium text-gray-600">
              全专业工程库查询结果：{searchLoading ? '查询中...' : `共 ${searchTotal} 条，显示前 ${searchResults.length} 条`}
            </div>
            {!searchLoading && searchResults.length === 0 && (
              <div className="px-4 py-12 text-center text-sm text-gray-400">未找到匹配清单</div>
            )}
            <div className="divide-y divide-gray-100">
              {searchResults.map(item => {
                const path = searchResultPath(item)
                return (
                  <div
                    key={`${item.source_library_id}:${item.id}`}
                    className={`w-full px-4 py-3 text-left text-sm hover:bg-blue-50/40 ${
                      selectedItem?.id === item.id && selectedItem.qdkid === item.source_library_id
                        ? 'bg-blue-50/70'
                        : 'bg-white'
                    }`}
                  >
                    <div className="grid gap-3 lg:grid-cols-[150px_minmax(280px,1fr)_100px_110px] lg:items-center">
                      <div className="select-text font-mono font-semibold text-blue-700">{item.code ?? '-'}</div>
                      <div className="min-w-0">
                        <div className="select-text font-medium text-gray-900">{item.name}</div>
                        <div className="mt-1 flex flex-wrap items-center gap-1 text-xs text-gray-500">
                          {path.map((part, index) => (
                            <span key={`${part}-${index}`} className="inline-flex items-center gap-1">
                              {index > 0 && <span className="text-gray-300">/</span>}
                              <span className={index === 0 ? 'font-medium text-indigo-700' : ''}>{part}</span>
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="text-gray-500">单位：{item.unit ?? '-'}</div>
                      <div className="text-gray-500">
                        候选：
                        <button
                          type="button"
                          onClick={() => selectSearchResult(item)}
                          className={`rounded border px-2 py-0.5 font-semibold tabular-nums transition ${
                            selectedItem?.id === item.id && selectedItem.qdkid === item.source_library_id
                              ? 'border-blue-600 bg-blue-600 text-white'
                              : 'border-blue-200 bg-white text-blue-700 hover:bg-blue-50'
                          }`}
                          title="展开候选定额"
                        >
                          {item.candidate_count}
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
          {selectedItem && (
            <CandidatePanel
              selectedItem={selectedItem}
              candidates={candidateData[`${selectedItem.qdkid}:${selectedItem.id}`]}
              loading={loadingCandidateKey === `${selectedItem.qdkid}:${selectedItem.id}`}
              details={quotaDetails}
              expandedDetailKeys={expandedQuotaDetailKeys}
              loadingDetailKeys={loadingQuotaDetailKeys}
              onToggleDetail={toggleCandidateDetail}
              onClose={() => setSelectedItem(null)}
            />
          )}
        </main>
      ) : (
      <div className="grid min-h-[calc(100vh-210px)] lg:grid-cols-[300px_minmax(0,1fr)]">
        <CategorySidebar
          categories={categories}
          selectedId={selectedCategory?.id ?? DEFAULT_CHAPTER_ID}
          onSelect={handleCategorySelect}
        />

        <main className="min-w-0 p-4 sm:p-5">
          {activeTab === 'process' ? (
            <ProcessManagementPanel />
          ) : activeTab === 'featureDefaults' ? (
            <FeatureDefaultsPanel />
          ) : (
          <>
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
          {selectedItem && (
            <CandidatePanel
              selectedItem={selectedItem}
              candidates={candidateData[`${selectedItem.qdkid}:${selectedItem.id}`]}
              loading={loadingCandidateKey === `${selectedItem.qdkid}:${selectedItem.id}`}
              details={quotaDetails}
              expandedDetailKeys={expandedQuotaDetailKeys}
              loadingDetailKeys={loadingQuotaDetailKeys}
              onToggleDetail={toggleCandidateDetail}
              onClose={() => setSelectedItem(null)}
            />
          )}
          </>
          )}
        </main>
      </div>
      )}
    </div>
  )
}
