'use client'

import { useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  fetchBS2024Documents,
  fetchBS2024Tree,
  fetchBS2024Section,
  fetchBS2024Groups,
  fetchBS2024GroupItems,
  fetchBS2024Issues,
  searchBS2024,
  BS2024Document,
  BS2024ChapterNode,
  BS2024SectionNode,
  BS2024SectionDetail,
  BS2024Group,
  BS2024Item,
  BS2024Subitem,
  BS2024Resource,
  BS2024Issue,
  BS2024SearchResult,
} from '@/lib/api'

type TabType = 'intro' | 'rules' | 'items'

const tabLabels: Record<TabType, string> = {
  intro: '说明',
  rules: '工程量计算规则',
  items: '子目构成表',
}

function fmt(v: number | null | undefined, digits = 2) {
  if (v == null) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function pageRange(start: number | null, end: number | null) {
  if (!start && !end) return '—'
  if (start === end || !end) return `P${start}`
  return `P${start}-${end}`
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="min-w-28 rounded border border-gray-200 bg-white px-3 py-2">
      <div className="text-xs text-gray-400">{label}</div>
      <div className="mt-0.5 text-sm font-semibold text-gray-800 tabular-nums">{value}</div>
    </div>
  )
}

function MarkdownView({ content }: { content: string | null }) {
  if (!content) {
    return <div className="rounded border border-dashed border-gray-200 bg-white py-12 text-center text-sm text-gray-400">暂无内容</div>
  }
  return (
    <div className="rounded border border-gray-200 bg-white px-5 py-4">
      <div className="prose prose-sm max-w-none text-gray-700">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            table: ({ node, ...props }) => (
              <div className="my-3 overflow-x-auto">
                <table className="w-full border-collapse text-xs" {...props} />
              </div>
            ),
            th: ({ node, ...props }) => (
              <th className="border border-gray-300 bg-gray-100 px-2 py-1 text-left font-medium text-gray-700" {...props} />
            ),
            td: ({ node, ...props }) => (
              <td className="border border-gray-300 px-2 py-1 text-gray-700" {...props} />
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </div>
  )
}

function IssueStrip({ issues }: { issues: BS2024Issue[] }) {
  if (!issues.length) return null
  return (
    <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
      <div className="font-medium">解析提示 {issues.length} 条</div>
      <div className="mt-1 flex flex-wrap gap-2">
        {issues.slice(0, 6).map(issue => (
          <span key={issue.id} className="rounded bg-white/70 px-2 py-1">
            {issue.page_no ? `P${issue.page_no} ` : ''}{issue.issue_type}
          </span>
        ))}
      </div>
    </div>
  )
}

function PriceTable({ items }: { items: BS2024Item[] }) {
  const subitems = items.flatMap(item => item.subitems.map(sub => ({ item, sub })))
  if (!subitems.length) return <div className="text-xs text-gray-400">暂无子目价格数据</div>
  return (
    <div className="overflow-x-auto rounded border border-gray-200">
      <table className="w-full min-w-[1120px] border-collapse text-xs">
        <thead className="bg-gray-50 text-gray-600">
          <tr>
            <th className="px-2 py-2 text-left font-medium">子目编号</th>
            <th className="px-2 py-2 text-left font-medium">项目 / 变体</th>
            <th className="px-2 py-2 text-right font-medium">全费用</th>
            <th className="px-2 py-2 text-right font-medium">综合单价</th>
            <th className="px-2 py-2 text-right font-medium">人工</th>
            <th className="px-2 py-2 text-right font-medium">材料</th>
            <th className="px-2 py-2 text-right font-medium">机械</th>
            <th className="px-2 py-2 text-right font-medium">管理</th>
            <th className="px-2 py-2 text-right font-medium">利润</th>
            <th className="px-2 py-2 text-right font-medium">安全文明施工措施费</th>
            <th className="px-2 py-2 text-right font-medium">规费</th>
            <th className="px-2 py-2 text-right font-medium">税金</th>
            <th className="px-2 py-2 text-right font-medium">页码</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {subitems.map(({ item, sub }) => (
            <tr key={sub.id} className="hover:bg-blue-50/40">
              <td className="px-2 py-2 font-mono font-medium text-blue-700">{sub.subitem_code}</td>
              <td className="px-2 py-2 text-gray-700">
                <div className="font-medium">{sub.subitem_name || item.item_name}</div>
                {sub.variant_desc && <div className="mt-0.5 text-gray-400">{sub.variant_desc}</div>}
              </td>
              <td className="px-2 py-2 text-right tabular-nums text-amber-700">{fmt(sub.total_unit_price)}</td>
              <td className="px-2 py-2 text-right tabular-nums">{fmt(sub.unit_price)}</td>
              <td className="px-2 py-2 text-right tabular-nums">{fmt(sub.labor_cost)}</td>
              <td className="px-2 py-2 text-right tabular-nums">{fmt(sub.material_cost)}</td>
              <td className="px-2 py-2 text-right tabular-nums">{fmt(sub.machine_cost)}</td>
              <td className="px-2 py-2 text-right tabular-nums">{fmt(sub.management_fee)}</td>
              <td className="px-2 py-2 text-right tabular-nums">{fmt(sub.profit)}</td>
              <td className="px-2 py-2 text-right tabular-nums">{fmt(sub.safety_fee)}</td>
              <td className="px-2 py-2 text-right tabular-nums">{fmt(sub.statutory_fee)}</td>
              <td className="px-2 py-2 text-right tabular-nums">{fmt(sub.tax)}</td>
              <td className="px-2 py-2 text-right text-gray-400">{sub.page_no ? `P${sub.page_no}` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ResourceTable({ items }: { items: BS2024Item[] }) {
  const rows = items.flatMap(item =>
    item.subitems.flatMap(sub =>
      sub.resources.map(res => ({ item, sub, res }))
    )
  )
  if (!rows.length) return <div className="text-xs text-gray-400">暂无工料机消耗量</div>
  return (
    <div className="overflow-x-auto rounded border border-gray-200">
      <table className="w-full min-w-[880px] border-collapse text-xs">
        <thead className="bg-gray-50 text-gray-600">
          <tr>
            <th className="px-2 py-2 text-left font-medium">类型</th>
            <th className="px-2 py-2 text-left font-medium">工料机名称</th>
            <th className="px-2 py-2 text-left font-medium">子目</th>
            <th className="px-2 py-2 text-left font-medium">单位</th>
            <th className="px-2 py-2 text-right font-medium">消耗量</th>
            <th className="px-2 py-2 text-right font-medium">参考价</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {rows.map(({ sub, res }) => (
            <tr key={`${sub.id}-${res.id}`} className="hover:bg-gray-50">
              <td className="px-2 py-2 text-gray-500">{res.resource_type}</td>
              <td className="px-2 py-2 text-gray-700">{res.resource_name}</td>
              <td className="px-2 py-2 font-mono text-blue-700">{sub.subitem_code}</td>
              <td className="px-2 py-2 text-gray-500">{res.unit ?? '—'}</td>
              <td className="px-2 py-2 text-right tabular-nums">{fmt(res.quantity, 4)}</td>
              <td className="px-2 py-2 text-right tabular-nums">{fmt(res.ref_price)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SubitemResourceTable({ resources }: { resources: BS2024Resource[] }) {
  if (!resources.length) return <div className="text-xs text-gray-400">暂无工料机消耗量</div>
  return (
    <div className="overflow-x-auto rounded border border-gray-200">
      <table className="w-full min-w-[720px] border-collapse text-xs">
        <thead className="bg-gray-50 text-gray-600">
          <tr>
            <th className="px-2 py-2 text-left font-medium">类型</th>
            <th className="px-2 py-2 text-left font-medium">工料机名称</th>
            <th className="px-2 py-2 text-left font-medium">单位</th>
            <th className="px-2 py-2 text-right font-medium">消耗量</th>
            <th className="px-2 py-2 text-right font-medium">参考价</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {resources.map(res => (
            <tr key={res.id} className="hover:bg-gray-50">
              <td className="px-2 py-2 text-gray-500">{res.resource_type}</td>
              <td className="px-2 py-2 text-gray-700">{res.resource_name}</td>
              <td className="px-2 py-2 text-gray-500">{res.unit ?? '—'}</td>
              <td className="px-2 py-2 text-right tabular-nums">{fmt(res.quantity, 4)}</td>
              <td className="px-2 py-2 text-right tabular-nums">{fmt(res.ref_price)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PriceMetric({ label, value, emphasis = false }: { label: string; value: number | null | undefined; emphasis?: boolean }) {
  return (
    <div className="rounded border border-gray-100 bg-white px-3 py-2">
      <div className="text-xs text-gray-400">{label}</div>
      <div className={`mt-1 text-right text-sm font-semibold tabular-nums ${emphasis ? 'text-amber-700' : 'text-gray-800'}`}>
        {fmt(value)}
      </div>
    </div>
  )
}

function SubitemCard({ item, subitem }: { item: BS2024Item; subitem: BS2024Subitem }) {
  const titlePath = subitem.name_path?.length
    ? subitem.name_path
    : [item.item_name, subitem.subitem_name, subitem.variant_desc].filter(Boolean) as string[]
  return (
    <div className="rounded border border-blue-100 bg-white">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-blue-50 px-3 py-3">
        <div className="min-w-0">
          <div className="font-mono text-sm font-semibold text-blue-700">{subitem.subitem_code}</div>
          <div className="mt-1 text-sm font-medium text-gray-800">{subitem.subitem_name || item.item_name}</div>
          {subitem.variant_desc && <div className="mt-0.5 text-xs text-gray-500">{subitem.variant_desc}</div>}
          {titlePath.length > 1 && (
            <div className="mt-2 flex flex-wrap items-center gap-1 text-xs text-gray-500">
              {titlePath.map((part, idx) => (
                <span key={`${part}-${idx}`} className="inline-flex items-center gap-1">
                  {idx > 0 && <span className="text-gray-300">/</span>}
                  <span className="rounded bg-blue-50 px-2 py-0.5 text-blue-700">{part}</span>
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          {(subitem.unit || item.unit) && (
            <span className="rounded bg-blue-50 px-2 py-1 text-blue-700">单位：{subitem.unit || item.unit}</span>
          )}
          {subitem.page_no && <span className="rounded bg-gray-50 px-2 py-1">P{subitem.page_no}</span>}
          {subitem.confidence != null && <span className="rounded bg-gray-50 px-2 py-1">置信度 {fmt(subitem.confidence * 100, 0)}%</span>}
        </div>
      </div>
      <div className="space-y-3 p-3">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5">
          <PriceMetric label="全费用" value={subitem.total_unit_price} emphasis />
          <PriceMetric label="综合单价" value={subitem.unit_price} />
          <PriceMetric label="人工费" value={subitem.labor_cost} />
          <PriceMetric label="材料费" value={subitem.material_cost} />
          <PriceMetric label="机械费" value={subitem.machine_cost} />
          <PriceMetric label="管理费" value={subitem.management_fee} />
          <PriceMetric label="利润" value={subitem.profit} />
          <PriceMetric label="安全文明施工措施费" value={subitem.safety_fee} />
          <PriceMetric label="规费" value={subitem.statutory_fee} />
          <PriceMetric label="税金" value={subitem.tax} />
        </div>
        <div>
          <div className="mb-2 text-xs font-medium text-gray-500">工料机消耗量</div>
          <SubitemResourceTable resources={subitem.resources} />
        </div>
      </div>
    </div>
  )
}

const concreteCategoryOrder = [
  '泵送现浇混凝土',
  '建筑物非泵送现浇混凝土',
  '构筑物非泵送现浇混凝土',
]

function concreteCategory(item: BS2024Item) {
  if (concreteCategoryOrder.includes(item.item_name)) return item.item_name
  const code = item.subitems[0]?.subitem_code
  if (!code?.startsWith('010002-')) return item.item_name
  const number = code ? Number(code.split('-')[1]) : Number.NaN
  if (number >= 1 && number <= 23) return concreteCategoryOrder[0]
  if (number >= 24 && number <= 72) return concreteCategoryOrder[1]
  if (number >= 73 && number <= 102) return concreteCategoryOrder[2]
  return item.item_name
}

function subitemOrdinal(code?: string) {
  if (!code) return Number.MAX_SAFE_INTEGER
  const parts = code.split('-')
  const ordinal = Number(parts[parts.length - 1])
  return Number.isFinite(ordinal) ? ordinal : Number.MAX_SAFE_INTEGER
}

function firstSubitemOrdinal(items: BS2024Item[]) {
  return Math.min(
    ...items.flatMap(item => item.subitems.map(subitem => subitemOrdinal(subitem.subitem_code))),
    Number.MAX_SAFE_INTEGER,
  )
}

function GroupPanel({ group, detail, onOpen }: {
  group: BS2024Group
  detail: BS2024Group | undefined
  onOpen: (id: number) => void
}) {
  const open = !!detail
  const categoryGroups = useMemo(() => {
    const grouped = new Map<string, BS2024Item[]>()
    for (const item of detail?.items ?? []) {
      const category = concreteCategory(item)
      grouped.set(category, [...(grouped.get(category) ?? []), item])
    }
    return Array.from(grouped.entries()).map(([category, items]) => [
      category,
      [...items].sort((a, b) => firstSubitemOrdinal([a]) - firstSubitemOrdinal([b])),
    ] as [string, BS2024Item[]]).sort(([a, aItems], [b, bItems]) => {
      const aIndex = concreteCategoryOrder.indexOf(a)
      const bIndex = concreteCategoryOrder.indexOf(b)
      if (aIndex === -1 && bIndex === -1) {
        return firstSubitemOrdinal(aItems) - firstSubitemOrdinal(bItems)
      }
      if (aIndex === -1) return 1
      if (bIndex === -1) return -1
      return aIndex - bIndex
    })
  }, [detail])
  const [openCategories, setOpenCategories] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (!categoryGroups.length) {
      setOpenCategories(new Set())
      return
    }
    setOpenCategories(current => current.size ? current : new Set([categoryGroups[0][0]]))
  }, [categoryGroups])

  function toggleCategory(category: string) {
    setOpenCategories(current => {
      const next = new Set(current)
      if (next.has(category)) next.delete(category)
      else next.add(category)
      return next
    })
  }

  return (
    <div className="rounded border border-gray-200 bg-white">
      <button
        onClick={() => onOpen(group.id)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-blue-50/60"
      >
        <span className="w-5 text-sm text-blue-600">{open ? '−' : '+'}</span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-gray-800">
            {group.group_code ? `${group.group_code} ` : ''}{group.group_name}
          </div>
          <div className="mt-0.5 text-xs text-gray-400">
            {group.item_count} 项 · {pageRange(group.page_start, group.page_end)}
          </div>
        </div>
      </button>
      {open && (
        <div className="border-t border-gray-100">
          {categoryGroups.map(([category, items], categoryIndex) => {
            const categoryOpen = openCategories.has(category)
            const subitemCount = items.reduce((sum, item) => sum + item.subitems.length, 0)
            const pages = items.map(item => item.page_no).filter((page): page is number => page != null)
            const pageStart = pages.length ? Math.min(...pages) : null
            const pageEnd = pages.length ? Math.max(...pages) : null
            const accent = categoryIndex === 0
              ? 'border-l-blue-500 bg-blue-50/50'
              : categoryIndex === 1
                ? 'border-l-emerald-500 bg-emerald-50/40'
                : 'border-l-amber-500 bg-amber-50/40'
            return (
              <section key={category} className="border-b border-gray-100 last:border-b-0">
                <button
                  type="button"
                  onClick={() => toggleCategory(category)}
                  className={`flex w-full items-center gap-3 border-l-4 px-4 py-3 text-left transition-colors hover:bg-gray-50 ${accent}`}
                >
                  <span className="w-4 text-sm font-semibold text-gray-500">{categoryOpen ? '−' : '+'}</span>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-gray-800">
                      {categoryIndex + 1}. {category}
                    </div>
                    <div className="mt-0.5 text-xs text-gray-500">
                      {subitemCount} 个子目 · {pageRange(pageStart, pageEnd)}
                    </div>
                  </div>
                </button>
                {categoryOpen && (
                  <div className="divide-y divide-gray-100 px-4">
                    {items.map(item => (
                      <div key={item.id} className="py-4">
                        <div className="flex flex-wrap items-center gap-2 pb-2">
                          {item.page_no && <div className="rounded bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">P{item.page_no}</div>}
                          {item.unit && <div className="text-xs text-gray-500">单位：{item.unit}</div>}
                          <div className="text-xs text-gray-400">{item.subitems.length} 个子目</div>
                        </div>
                        {item.work_content && (
                          <div className="mb-3 text-xs leading-relaxed text-gray-600">
                            <span className="font-medium text-gray-700">工作内容：</span>{item.work_content}
                          </div>
                        )}
                        <div className="space-y-3">
                          {item.subitems.length ? (
                            item.subitems.map(subitem => (
                              <SubitemCard key={subitem.id} item={item} subitem={subitem} />
                            ))
                          ) : (
                            <div className="border border-dashed border-gray-200 bg-white py-6 text-center text-xs text-gray-400">
                              暂无子目数据
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function BuildingStandard2024Page() {
  const [documents, setDocuments] = useState<BS2024Document[]>([])
  const [documentId, setDocumentId] = useState<number | null>(null)
  const [tree, setTree] = useState<BS2024ChapterNode[]>([])
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<TabType>('intro')
  const [section, setSection] = useState<BS2024SectionDetail | null>(null)
  const [groups, setGroups] = useState<BS2024Group[]>([])
  const [groupDetails, setGroupDetails] = useState<Record<number, BS2024Group>>({})
  const [issues, setIssues] = useState<BS2024Issue[]>([])
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<BS2024SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const selectedDocument = documents.find(d => d.id === documentId) ?? null
  const selectedChapter = tree.find(ch => ch.id === selectedChapterId) ?? null

  const activeSection = useMemo(() => {
    if (!selectedChapter) return null
    return selectedChapter.sections.find(s => s.section_type === activeTab) ?? null
  }, [selectedChapter, activeTab])

  const activeSections = useMemo(() => {
    if (!selectedChapter) return []
    return selectedChapter.sections.filter(s => s.section_type === activeTab)
  }, [selectedChapter, activeTab])

  const activePageRange = useMemo(() => {
    if (!activeSections.length) return '—'
    const starts = activeSections.map(s => s.page_start).filter((v): v is number => v != null)
    const ends = activeSections.map(s => s.page_end).filter((v): v is number => v != null)
    if (!starts.length && !ends.length) return '—'
    return pageRange(starts.length ? Math.min(...starts) : null, ends.length ? Math.max(...ends) : null)
  }, [activeSections])

  useEffect(() => {
    if (!selectedChapter) return
    if (selectedChapter.sections.some(s => s.section_type === activeTab)) return
    const first = selectedChapter.sections.find(s =>
      s.section_type === 'intro' || s.section_type === 'rules' || s.section_type === 'items'
    )
    if (first && (first.section_type === 'intro' || first.section_type === 'rules' || first.section_type === 'items')) {
      setActiveTab(first.section_type)
    }
  }, [selectedChapter, activeTab])

  useEffect(() => {
    setLoading(true)
    fetchBS2024Documents()
      .then(data => {
        setDocuments(data)
        if (data[0]) setDocumentId(data[0].id)
      })
      .catch(e => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!documentId) return
    setLoading(true)
    Promise.all([fetchBS2024Tree(documentId), fetchBS2024Issues(documentId)])
      .then(([treeData, issueData]) => {
        setTree(treeData)
        setSelectedChapterId(treeData[0]?.id ?? null)
        setIssues(issueData)
        setActiveTab('intro')
      })
      .catch(e => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false))
  }, [documentId])

  useEffect(() => {
    if (!activeSection) {
      setSection(null)
      setGroups([])
      return
    }
    setLoading(true)
    if (activeTab === 'items') {
      Promise.all([
        fetchBS2024Section(activeSection.id),
        Promise.all(activeSections.map(s => fetchBS2024Groups(s.id))),
      ])
        .then(([sectionData, groupData]) => {
          setSection(sectionData)
          setGroups(groupData.flat())
        })
        .catch(e => setError(e instanceof Error ? e.message : '加载失败'))
        .finally(() => setLoading(false))
    } else {
      fetchBS2024Section(activeSection.id)
        .then(data => {
          setSection(data)
          setGroups([])
        })
        .catch(e => setError(e instanceof Error ? e.message : '加载失败'))
        .finally(() => setLoading(false))
    }
  }, [activeSection, activeSections, activeTab])

  async function openGroup(groupId: number) {
    if (groupDetails[groupId]) {
      const next = { ...groupDetails }
      delete next[groupId]
      setGroupDetails(next)
      return
    }
    const detail = await fetchBS2024GroupItems(groupId)
    setGroupDetails(prev => ({ ...prev, [groupId]: detail }))
  }

  async function runSearch() {
    if (!documentId || !query.trim()) {
      setResults([])
      return
    }
    const data = await searchBS2024(documentId, query.trim())
    setResults(data)
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="border-b border-gray-200 bg-white px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-gray-900">建筑消耗量标准2024</h1>
            <p className="mt-1 text-sm text-gray-500">本地 OCR 解析入库，保留页源、层级、说明规则和子目表结构。</p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={documentId ?? ''}
              onChange={e => setDocumentId(Number(e.target.value))}
              className="rounded border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700"
            >
              {documents.map(doc => (
                <option key={doc.id} value={doc.id}>{doc.standard_code} - {doc.name}</option>
              ))}
            </select>
          </div>
        </div>

        {selectedDocument && (
          <div className="mt-4 flex flex-wrap gap-2">
            <Stat label="页数" value={selectedDocument.page_count} />
            <Stat label="章节" value={selectedDocument.chapter_count} />
            <Stat label="子目" value={selectedDocument.subitem_count} />
            <Stat label="解析问题" value={selectedDocument.issue_count} />
            <Stat label="导入状态" value={selectedDocument.latest_run_status ?? '—'} />
          </div>
        )}

        {error && <div className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
      </div>

      <div className="grid min-h-[calc(100vh-170px)] grid-cols-[280px_1fr]">
        <aside className="border-r border-gray-200 bg-white">
          <div className="border-b border-gray-100 p-3">
            <div className="flex gap-2">
              <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') runSearch() }}
                placeholder="搜索子目、项目、工料机"
                className="min-w-0 flex-1 rounded border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-blue-500"
              />
              <button
                onClick={runSearch}
                className="rounded bg-blue-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-800"
              >
                搜索
              </button>
            </div>
          </div>
          {results.length > 0 && (
            <div className="max-h-64 overflow-y-auto border-b border-gray-100 p-3">
              <div className="mb-2 text-xs font-medium text-gray-500">搜索结果</div>
              <div className="space-y-1">
                {results.map(r => (
                  <div key={r.id} className="rounded border border-gray-100 px-2 py-1.5 text-xs">
                    <div className="font-mono font-medium text-blue-700">{r.subitem_code}</div>
                    <div className="truncate text-gray-700">{r.name}</div>
                    <div className="truncate text-gray-400">{r.group_code} {r.group_name}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="max-h-[calc(100vh-260px)] overflow-y-auto py-2">
            {tree.map(chapter => (
              <div key={chapter.id}>
                <button
                  onClick={() => {
                    setSelectedChapterId(chapter.id)
                    setActiveTab('intro')
                    setGroupDetails({})
                  }}
                  className={`w-full px-4 py-2.5 text-left text-sm transition ${
                    selectedChapterId === chapter.id
                      ? 'border-l-2 border-blue-700 bg-blue-50 text-blue-700'
                      : 'border-l-2 border-transparent text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <div className="font-medium">第{chapter.chapter_no}章 {chapter.title}</div>
                  <div className="mt-0.5 text-xs text-gray-400">{pageRange(chapter.page_start, chapter.page_end)}</div>
                </button>
                {selectedChapterId === chapter.id && (
                  <div className="bg-gray-50 px-4 py-1.5">
                    {(['intro', 'rules', 'items'] as TabType[]).map(tab => {
                      const sec = chapter.sections.find(s => s.section_type === tab)
                      const tabSections = chapter.sections.filter(s => s.section_type === tab)
                      const starts = tabSections.map(s => s.page_start).filter((v): v is number => v != null)
                      const ends = tabSections.map(s => s.page_end).filter((v): v is number => v != null)
                      const tabRange = tabSections.length
                        ? pageRange(starts.length ? Math.min(...starts) : null, ends.length ? Math.max(...ends) : null)
                        : ''
                      return (
                        <button
                          key={tab}
                          disabled={!sec}
                          onClick={() => {
                            setActiveTab(tab)
                            setGroupDetails({})
                          }}
                          className={`my-0.5 block w-full rounded px-3 py-1.5 text-left text-xs ${
                            activeTab === tab
                              ? 'bg-blue-100 font-medium text-blue-700'
                              : sec ? 'text-gray-600 hover:bg-gray-200' : 'text-gray-300'
                          }`}
                        >
                          {tabLabels[tab]} {sec ? <span className="text-gray-400">{tabRange}</span> : ''}
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            ))}
          </div>
        </aside>

        <main className="min-w-0 p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-gray-900">
                {selectedChapter ? `第${selectedChapter.chapter_no}章 ${selectedChapter.title}` : '未选择章节'}
              </div>
              <div className="mt-0.5 text-xs text-gray-500">
                {section?.title ?? tabLabels[activeTab]} · {activePageRange}
              </div>
            </div>
            <div className="flex rounded border border-gray-200 bg-white p-1">
              {(['intro', 'rules', 'items'] as TabType[]).map(tab => (
                (() => {
                  const enabled = selectedChapter?.sections.some(s => s.section_type === tab) ?? false
                  return (
                <button
                  key={tab}
                  disabled={!enabled}
                  onClick={() => setActiveTab(tab)}
                  className={`rounded px-3 py-1.5 text-sm ${
                    activeTab === tab
                      ? 'bg-blue-700 text-white'
                      : enabled ? 'text-gray-600 hover:bg-gray-100' : 'text-gray-300'
                  }`}
                >
                  {tabLabels[tab]}
                </button>
                  )
                })()
              ))}
            </div>
          </div>

          <IssueStrip issues={issues} />

          <div className="mt-4">
            {loading && <div className="rounded border border-gray-200 bg-white py-12 text-center text-sm text-gray-400">加载中...</div>}
            {!loading && activeTab !== 'items' && <MarkdownView content={section?.content_md ?? null} />}
            {!loading && activeTab === 'items' && (
              <div className="space-y-3">
                {groups.length === 0 ? (
                  <div className="rounded border border-dashed border-gray-200 bg-white py-12 text-center text-sm text-gray-400">暂无子目表数据</div>
                ) : (
                  groups.map(group => (
                    <GroupPanel
                      key={group.id}
                      group={group}
                      detail={groupDetails[group.id]}
                      onOpen={openGroup}
                    />
                  ))
                )}
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
