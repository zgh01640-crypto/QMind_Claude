'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  BuildingStandardHeader,
  BuildingStandardSidebar,
  StandardStat,
} from '@/components/BuildingStandard2024Layout'
import {
  BS2024ChapterNode,
  BS2024Document,
  fetchBS2024Documents,
  fetchBS2024Tree,
  fetchStandardReferencePriceFilterOptions,
  fetchStandardReferencePrices,
  StandardReferencePrice,
  StandardReferencePriceFilterOptions,
} from '@/lib/api'

const PAGE_SIZE = 50

function formatPrice(price: number) {
  return price.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  })
}

export default function AppendixAPage() {
  const router = useRouter()
  const [documents, setDocuments] = useState<BS2024Document[]>([])
  const [documentId, setDocumentId] = useState<number | null>(null)
  const [tree, setTree] = useState<BS2024ChapterNode[]>([])
  const [options, setOptions] = useState<StandardReferencePriceFilterOptions | null>(null)
  const [items, setItems] = useState<StandardReferencePrice[]>([])
  const [total, setTotal] = useState(0)
  const [searchInput, setSearchInput] = useState('')
  const [query, setQuery] = useState('')
  const [resourceType, setResourceType] = useState<'材料' | '机械' | ''>('')
  const [unit, setUnit] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const selectedDocument = documents.find(document => document.id === documentId) ?? null
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const hasFilters = Boolean(query || resourceType || unit)

  useEffect(() => {
    setLoading(true)
    fetchBS2024Documents()
      .then(data => {
        setDocuments(data)
        setDocumentId(data[0]?.id ?? null)
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : '加载标准失败'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!documentId) return
    setLoading(true)
    setError('')
    Promise.all([
      fetchBS2024Tree(documentId),
      fetchStandardReferencePriceFilterOptions(documentId),
    ])
      .then(([treeData, filterOptions]) => {
        setTree(treeData)
        setOptions(filterOptions)
        setPage(1)
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : '加载附录失败'))
      .finally(() => setLoading(false))
  }, [documentId])

  useEffect(() => {
    if (!documentId) return
    setLoading(true)
    setError('')
    fetchStandardReferencePrices({
      document_id: documentId,
      appendix_code: 'A',
      q: query,
      unit,
      resource_type: resourceType,
      page,
      page_size: PAGE_SIZE,
    })
      .then(data => {
        setItems(data.items)
        setTotal(data.total)
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : '加载价格表失败'))
      .finally(() => setLoading(false))
  }, [documentId, page, query, resourceType, unit])

  const pageSummary = useMemo(() => {
    if (!total) return '0 条'
    const start = (page - 1) * PAGE_SIZE + 1
    const end = Math.min(page * PAGE_SIZE, total)
    return `${start}-${end} / ${total}`
  }, [page, total])

  function applySearch() {
    setQuery(searchInput.trim())
    setPage(1)
  }

  function clearFilters() {
    setSearchInput('')
    setQuery('')
    setResourceType('')
    setUnit('')
    setPage(1)
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <BuildingStandardHeader
        documents={documents}
        documentId={documentId}
        onDocumentChange={setDocumentId}
        error={error}
        stats={(
          <>
            <StandardStat label="附录总数" value={options?.total ?? 0} />
            <StandardStat label="材料" value={options?.material_count ?? 0} />
            <StandardStat label="机械" value={options?.machine_count ?? 0} />
            <StandardStat label="来源页" value="P268-277" />
            {selectedDocument && <StandardStat label="标准编号" value={selectedDocument.standard_code} />}
          </>
        )}
      />

      <div className="grid min-h-[calc(100vh-170px)] lg:grid-cols-[280px_minmax(0,1fr)]">
        <BuildingStandardSidebar
          tree={tree}
          selectedChapterId={null}
          appendixActive
          onChapterClick={chapter => router.push(`/building-standard-2024?chapter=${chapter.id}`)}
        />

        <main className="min-w-0 p-4 sm:p-5">
          <div className="mb-4">
            <div className="text-sm font-semibold text-gray-900">附录A 材料、机械台班参考价格表</div>
            <div className="mt-0.5 text-xs text-gray-500">结构化参考价格 · P268-277</div>
          </div>

          <div className="mb-4 border border-gray-200 bg-white p-3">
            <div className="grid gap-3 xl:grid-cols-[minmax(260px,1fr)_auto_180px_auto] xl:items-end">
              <div>
                <label className="mb-1 block text-xs text-gray-500">名称、型号或规格</label>
                <div className="flex gap-2">
                  <input
                    value={searchInput}
                    onChange={event => setSearchInput(event.target.value)}
                    onKeyDown={event => { if (event.key === 'Enter') applySearch() }}
                    placeholder="例如：混凝土输送泵、Φ、Q=60"
                    className="min-w-0 flex-1 rounded border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
                  />
                  <button
                    onClick={applySearch}
                    className="rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800"
                  >
                    查询
                  </button>
                </div>
              </div>

              <div>
                <label className="mb-1 block text-xs text-gray-500">资源类型</label>
                <div className="flex rounded border border-gray-200 bg-gray-50 p-1">
                  {([
                    ['', `全部 ${options?.total ?? 0}`],
                    ['材料', `材料 ${options?.material_count ?? 0}`],
                    ['机械', `机械 ${options?.machine_count ?? 0}`],
                  ] as const).map(([value, label]) => (
                    <button
                      key={value}
                      onClick={() => {
                        setResourceType(value)
                        setPage(1)
                      }}
                      className={`rounded px-3 py-1.5 text-sm ${
                        resourceType === value
                          ? 'bg-blue-700 text-white'
                          : 'text-gray-600 hover:bg-white'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="mb-1 block text-xs text-gray-500">单位</label>
                <select
                  value={unit}
                  onChange={event => {
                    setUnit(event.target.value)
                    setPage(1)
                  }}
                  className="w-full rounded border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700"
                >
                  <option value="">全部单位</option>
                  {options?.units.map(option => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              </div>

              <button
                onClick={clearFilters}
                disabled={!hasFilters && !searchInput}
                className="rounded border border-gray-300 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                清除条件
              </button>
            </div>
          </div>

          <div className="overflow-hidden border border-gray-200 bg-white">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 px-4 py-2.5 text-sm">
              <div className="text-gray-500">
                共 <span className="font-semibold text-gray-900">{total.toLocaleString()}</span> 条
                {hasFilters && <span className="ml-2 text-blue-700">已筛选</span>}
              </div>
              <div className="text-xs tabular-nums text-gray-400">{pageSummary}</div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[860px] border-collapse text-sm">
                <thead className="bg-gray-50 text-xs text-gray-600">
                  <tr>
                    <th className="w-20 px-4 py-2.5 text-left font-medium">序号</th>
                    <th className="w-20 px-4 py-2.5 text-left font-medium">类型</th>
                    <th className="px-4 py-2.5 text-left font-medium">名称及规格</th>
                    <th className="w-24 px-4 py-2.5 text-left font-medium">单位</th>
                    <th className="w-32 px-4 py-2.5 text-right font-medium">参考价（元）</th>
                    <th className="w-24 px-4 py-2.5 text-right font-medium">来源页</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {!loading && items.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-4 py-12 text-center text-gray-400">暂无匹配数据</td>
                    </tr>
                  )}
                  {items.map(item => (
                    <tr key={item.id} className="hover:bg-blue-50/40">
                      <td className="px-4 py-2.5 font-mono text-gray-500">{item.sequence_no}</td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-block min-w-12 rounded px-2 py-0.5 text-center text-xs ${
                          item.resource_type === '机械'
                            ? 'bg-amber-50 text-amber-700'
                            : 'bg-blue-50 text-blue-700'
                        }`}>
                          {item.resource_type}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 font-medium text-gray-800">{item.name}</td>
                      <td className="px-4 py-2.5 text-gray-600">{item.unit}</td>
                      <td className="px-4 py-2.5 text-right font-semibold tabular-nums text-blue-700">
                        {formatPrice(item.price)}
                      </td>
                      <td className="px-4 py-2.5 text-right text-gray-400">P{item.source_page_no}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-gray-200 px-4 py-3 text-sm text-gray-600">
              <span>第 {page} / {totalPages} 页</span>
              <div className="flex gap-1">
                <button
                  onClick={() => setPage(1)}
                  disabled={page === 1}
                  className="rounded border px-3 py-1.5 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  首页
                </button>
                <button
                  onClick={() => setPage(current => Math.max(1, current - 1))}
                  disabled={page === 1}
                  className="rounded border px-3 py-1.5 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  上一页
                </button>
                <button
                  onClick={() => setPage(current => Math.min(totalPages, current + 1))}
                  disabled={page === totalPages}
                  className="rounded border px-3 py-1.5 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  下一页
                </button>
                <button
                  onClick={() => setPage(totalPages)}
                  disabled={page === totalPages}
                  className="rounded border px-3 py-1.5 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  末页
                </button>
              </div>
            </div>
          </div>

          {loading && (
            <div className="mt-3 border border-gray-200 bg-white py-4 text-center text-sm text-gray-400">
              加载中...
            </div>
          )}
        </main>
      </div>
    </div>
  )
}

