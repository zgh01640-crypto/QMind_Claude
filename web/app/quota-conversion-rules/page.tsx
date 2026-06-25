'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  QuotaConversionRuleListItem,
  QuotaTreeCategory,
  QuotaTreeItemDetail,
  fetchQuotaConversionRules,
  fetchQuotaTreeItemDetail,
  fetchQuotaTreeTopLibraries,
} from '@/lib/api'

const PAGE_SIZE = 50

function libraryKey(library: QuotaTreeCategory | null) {
  return library ? `${library.dekid}:${library.id}` : 'all'
}

function StatPill({ label, value }: { label: string; value: number | string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-500">
      {label}
      <span className="font-semibold tabular-nums text-gray-800">{value}</span>
    </span>
  )
}

function ManagementCards({ active }: { active: 'library' | 'prompts' | 'conversionRules' }) {
  const cards = [
    {
      key: 'library',
      href: '/quota-management',
      title: '完整定额库',
      description: '按 TDEK_TZJMC 章节树浏览完整定额子目，查看费用构成、工料机和换算信息。',
      stat: 'TDEK_TDEZM',
    },
    {
      key: 'prompts',
      href: '/quota-input-prompts',
      title: '实际值提示',
      description: '只查看 tdek_tzhhs 中存在实际值提示的定额，按定额库筛选和分页查询。',
      stat: 'tdek_tzhhs',
    },
    {
      key: 'conversionRules',
      href: '/quota-conversion-rules',
      title: '换算说明',
      description: '只查看 TDEK_TZNHS 中存在换算说明的定额，集中核查提示、说明和分组。',
      stat: 'TDEK_TZNHS',
    },
  ] as const

  return (
    <div className="mt-4 grid gap-3 border-t border-gray-100 pt-4 md:grid-cols-3">
      {cards.map(card => {
        const selected = active === card.key
        return (
          <Link
            key={card.key}
            href={card.href}
            className={`block border p-4 transition ${
              selected
                ? 'border-blue-600 bg-blue-50'
                : 'border-gray-200 bg-white hover:border-blue-300 hover:bg-blue-50/40'
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className={`text-sm font-semibold ${selected ? 'text-blue-800' : 'text-gray-900'}`}>{card.title}</div>
                <div className="mt-1 text-xs leading-5 text-gray-500">{card.description}</div>
              </div>
              <span className={`shrink-0 rounded border px-2 py-1 font-mono text-xs ${
                selected ? 'border-blue-200 bg-white text-blue-700' : 'border-gray-200 bg-gray-50 text-gray-500'
              }`}>
                {card.stat}
              </span>
            </div>
          </Link>
        )
      })}
    </div>
  )
}

function LibrarySidebar({
  libraries,
  selected,
  onSelect,
}: {
  libraries: QuotaTreeCategory[]
  selected: QuotaTreeCategory | null
  onSelect: (library: QuotaTreeCategory | null) => void
}) {
  const selectedKey = libraryKey(selected)
  return (
    <aside className="border-b border-gray-200 bg-white lg:border-b-0 lg:border-r">
      <div className="border-b border-gray-200 px-4 py-3">
        <div className="text-sm font-semibold text-gray-900">定额库</div>
        <div className="mt-0.5 text-xs text-gray-400">按 DEKID 筛选换算说明</div>
      </div>
      <div className="max-h-[42vh] overflow-y-auto py-2 lg:max-h-[calc(100vh-220px)]">
        <button
          type="button"
          onClick={() => onSelect(null)}
          className={`w-full border-l-2 px-4 py-2.5 text-left text-sm transition ${
            selectedKey === 'all'
              ? 'border-blue-700 bg-blue-50 text-blue-700'
              : 'border-transparent text-gray-700 hover:bg-gray-50'
          }`}
        >
          <div className="font-medium leading-snug">全部定额库</div>
          <div className="mt-1 text-xs text-gray-400">跨库查询</div>
        </button>
        {libraries.map(library => {
          const active = selectedKey === libraryKey(library)
          return (
            <button
              key={libraryKey(library)}
              type="button"
              onClick={() => onSelect(library)}
              className={`w-full border-l-2 px-4 py-2.5 text-left text-sm transition ${
                active
                  ? 'border-blue-700 bg-blue-50 text-blue-700'
                  : 'border-transparent text-gray-700 hover:bg-gray-50'
              }`}
            >
              <div className="font-medium leading-snug">{library.zjmc}</div>
              <div className="mt-1 flex flex-wrap gap-2 text-xs text-gray-400">
                <span className="font-mono">DEKID {library.dekid}</span>
                <span>子目 {library.quota_count ?? '-'}</span>
              </div>
            </button>
          )
        })}
      </div>
    </aside>
  )
}

function RuleList({ item }: { item: QuotaConversionRuleListItem }) {
  return (
    <div className="mt-3 space-y-2">
      {item.conversion_rules.map((rule, index) => (
        <div key={`${item.dekid}:${item.quota_item_id}:${index}`} className="border border-gray-200 bg-gray-50 px-3 py-2 text-xs">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="select-text font-medium text-gray-900">{rule.prompt ?? '-'}</div>
            <span className="shrink-0 rounded border border-gray-200 bg-white px-2 py-0.5 font-mono text-gray-500">
              分组 {rule.group_no ?? '-'}
            </span>
          </div>
          {rule.description && (
            <div className="mt-1 select-text whitespace-pre-wrap leading-5 text-gray-600">{rule.description}</div>
          )}
        </div>
      ))}
    </div>
  )
}

function DetailDrawer({
  detail,
  loading,
  error,
  onClose,
}: {
  detail: QuotaTreeItemDetail | null
  loading: boolean
  error: string
  onClose: () => void
}) {
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-gray-950/25" onClick={onClose}>
      <div
        className="h-full w-full overflow-y-auto border-l border-gray-200 bg-gray-50 shadow-2xl sm:w-[88vw] xl:w-[72vw]"
        onClick={event => event.stopPropagation()}
      >
        <div className="sticky top-0 z-10 border-b border-gray-200 bg-white px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-gray-900">定额详情</div>
              <div className="mt-1 text-xs text-gray-500">
                {detail ? `${detail.item.zmbh ?? '-'} ${detail.item.zmmc}` : '加载中...'}
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
            >
              关闭
            </button>
          </div>
        </div>
        {loading && <div className="px-5 py-12 text-center text-sm text-gray-400">定额详情加载中...</div>}
        {error && <div className="m-5 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
        {detail && (
          <div className="space-y-4 p-5">
            <section className="border border-gray-200 bg-white px-4 py-3">
              <div className="grid gap-3 text-sm lg:grid-cols-[150px_minmax(260px,1fr)_90px_120px] lg:items-start">
                <div className="select-text font-mono font-semibold text-blue-700">{detail.item.zmbh ?? '-'}</div>
                <div>
                  <div className="select-text font-medium text-gray-900">{detail.item.zmmc}</div>
                  <div className="mt-1 select-text text-xs text-gray-500">{detail.item.chapter_name ?? '-'}</div>
                  {detail.item.gznr && <div className="mt-2 select-text text-xs leading-5 text-gray-600">工作内容：{detail.item.gznr}</div>}
                </div>
                <div className="text-gray-500">单位：{detail.item.dw ?? '-'}</div>
                <div className="text-xs text-gray-500">DEKID {detail.item.dekid}</div>
              </div>
            </section>

            {detail.conversion_rules.length > 0 && (
              <section>
                <div className="mb-2 text-xs font-semibold text-gray-500">换算说明</div>
                <div className="space-y-2">
                  {detail.conversion_rules.map((rule, index) => (
                    <div key={index} className="border border-gray-200 bg-white px-3 py-2 text-xs text-gray-700">
                      {rule.prompt && <div className="font-medium text-gray-900">{rule.prompt}</div>}
                      {rule.description && <div className="mt-1 whitespace-pre-wrap">{rule.description}</div>}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {detail.resources.length > 0 && (
              <section>
                <div className="mb-2 text-xs font-semibold text-gray-500">工料机消耗量</div>
                <div className="overflow-x-auto border border-gray-200 bg-white">
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
                    <tbody className="divide-y divide-gray-100">
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
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default function QuotaConversionRulesPage() {
  const [libraries, setLibraries] = useState<QuotaTreeCategory[]>([])
  const [selectedLibrary, setSelectedLibrary] = useState<QuotaTreeCategory | null>(null)
  const [items, setItems] = useState<QuotaConversionRuleListItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [detail, setDetail] = useState<QuotaTreeItemDetail | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const selectedLibraryId = selectedLibrary?.dekid ?? null
  const currentRuleTotal = useMemo(
    () => items.reduce((sum, item) => sum + item.rule_count, 0),
    [items],
  )

  useEffect(() => {
    fetchQuotaTreeTopLibraries()
      .then(setLibraries)
      .catch(reason => setError(reason instanceof Error ? reason.message : '加载定额库失败'))
  }, [])

  const loadData = useCallback(async (nextPage: number, query: string, libraryId: number | null) => {
    setLoading(true)
    setError('')
    try {
      const result = await fetchQuotaConversionRules({
        library_id: libraryId,
        q: query,
        page: nextPage,
        page_size: PAGE_SIZE,
      })
      setItems(result.items)
      setTotal(result.total)
      setPage(result.page)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加载换算说明失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData(1, searchQuery, selectedLibraryId).catch(() => undefined)
  }, [loadData, searchQuery, selectedLibraryId])

  function handleSearch(event?: FormEvent) {
    event?.preventDefault()
    setSearchQuery(searchInput.trim())
  }

  function clearSearch() {
    setSearchInput('')
    setSearchQuery('')
  }

  function handleLibrarySelect(library: QuotaTreeCategory | null) {
    setSelectedLibrary(library)
    setPage(1)
  }

  function changePage(nextPage: number) {
    const safePage = Math.min(Math.max(1, nextPage), totalPages)
    void loadData(safePage, searchQuery, selectedLibraryId)
  }

  async function openQuotaDetail(dekid: number, itemId: number) {
    setDetailOpen(true)
    setDetail(null)
    setDetailError('')
    setDetailLoading(true)
    try {
      const result = await fetchQuotaTreeItemDetail(dekid, itemId)
      setDetail(result)
    } catch (reason) {
      setDetailError(reason instanceof Error ? reason.message : '加载定额详情失败')
    } finally {
      setDetailLoading(false)
    }
  }

  return (
    <div className="min-h-[calc(100vh-104px)] bg-gray-50">
      <div className="border-b border-gray-200 bg-white px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-gray-900">换算说明管理</h1>
            <p className="mt-1 text-sm text-gray-500">只展示 TDEK_TZNHS 中存在换算说明的定额子目。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatPill label="定额库" value={libraries.length || '-'} />
            <StatPill label="定额子目" value={loading ? '加载中' : total} />
            <StatPill label="当前页说明" value={loading ? '加载中' : currentRuleTotal} />
          </div>
        </div>
        {error && <div className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
        <ManagementCards active="conversionRules" />
        <form onSubmit={handleSearch} className="mt-4 flex flex-col gap-2 border-t border-gray-100 pt-4 sm:flex-row">
          <input
            value={searchInput}
            onChange={event => setSearchInput(event.target.value)}
            placeholder="搜索定额编号、定额名称、换算提示或换算说明"
            className="min-w-0 flex-1 rounded border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />
          <button type="submit" disabled={loading} className="rounded bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
            {loading ? '查询中...' : '查询'}
          </button>
          {searchQuery && (
            <button type="button" onClick={clearSearch} className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
              清除
            </button>
          )}
        </form>
      </div>

      <div className="grid min-h-[calc(100vh-220px)] lg:grid-cols-[320px_minmax(0,1fr)]">
        <LibrarySidebar libraries={libraries} selected={selectedLibrary} onSelect={handleLibrarySelect} />

        <main className="min-w-0 p-4 sm:p-5">
          <div className="mb-4 border border-gray-200 bg-white px-4 py-3">
            <div className="text-sm font-semibold text-gray-900">
              {selectedLibrary ? selectedLibrary.zjmc : '全部定额库'}
            </div>
            <div className="mt-1 text-xs text-gray-500">
              按定额库分页查看存在换算说明的定额；定额编号和说明文本可直接选择复制。
            </div>
          </div>

          <div className="overflow-hidden border border-gray-200 bg-white">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 bg-gray-50 px-4 py-2.5 text-xs font-medium text-gray-600">
              <span>
                {loading ? '加载中...' : `共 ${total} 个定额子目，第 ${page}/${totalPages} 页，当前 ${items.length} 个`}
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => changePage(page - 1)}
                  disabled={page <= 1 || loading}
                  className="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 disabled:opacity-40"
                >
                  上一页
                </button>
                <button
                  type="button"
                  onClick={() => changePage(page + 1)}
                  disabled={page >= totalPages || loading}
                  className="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 disabled:opacity-40"
                >
                  下一页
                </button>
              </div>
            </div>

            {!loading && items.length === 0 && (
              <div className="px-4 py-12 text-center text-sm text-gray-400">暂无换算说明数据</div>
            )}

            <div className="divide-y divide-gray-100">
              {items.map(item => (
                <section key={`${item.dekid}:${item.quota_item_id}`} className="px-4 py-3">
                  <div className="grid gap-3 text-sm xl:grid-cols-[150px_minmax(260px,1fr)_90px_90px] xl:items-start">
                    <div>
                      {item.quota_code ? (
                        <button
                          type="button"
                          onClick={() => openQuotaDetail(item.dekid, item.quota_item_id)}
                          className="select-text font-mono font-semibold text-blue-700 hover:underline"
                          title="查看定额详情"
                        >
                          {item.quota_code}
                        </button>
                      ) : (
                        <div className="font-mono font-semibold text-blue-700">-</div>
                      )}
                      <div className="mt-1 font-mono text-xs text-gray-400">DEKID {item.dekid}</div>
                    </div>
                    <div>
                      <div className="select-text font-medium text-gray-900">{item.quota_name}</div>
                      <div className="mt-1 select-text text-xs text-gray-500">
                        {[item.library_name, item.chapter_name].filter(Boolean).join(' / ')}
                      </div>
                    </div>
                    <div className="text-gray-500">单位：{item.unit ?? '-'}</div>
                    <div className="text-gray-500">说明：{item.rule_count}</div>
                  </div>
                  <RuleList item={item} />
                </section>
              ))}
            </div>
          </div>
        </main>
      </div>

      {detailOpen && (
        <DetailDrawer
          detail={detail}
          loading={detailLoading}
          error={detailError}
          onClose={() => setDetailOpen(false)}
        />
      )}
    </div>
  )
}
