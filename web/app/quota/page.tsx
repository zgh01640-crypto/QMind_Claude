'use client'
import { useState, useEffect, useCallback, Fragment } from 'react'
import { fetchQuotaStandards, fetchQuotaChapters, fetchAllQuotaItems, QuotaStandard, QuotaChapter, QuotaItem, QuotaResource } from '@/lib/api'

// ── 工具函数 ──────────────────────────────────────────────────────────────

function getPrefix(code: string): string {
  return code.replace(/-\d+$/, '').trim().replace(/\s+/g, '')
}

function fmt(v: number | null | undefined) {
  if (v == null) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ── 树形数据结构 ─────────────────────────────────────────────────────────

interface GroupNode { name: string; key: string; items: QuotaItem[] }
interface ChapterNode { prefix: string; label: string; groups: GroupNode[]; count: number }

function buildTree(items: QuotaItem[], filter: string, chapterMap: Map<string, string>): ChapterNode[] {
  const q = filter.trim().toLowerCase()
  const filtered = q
    ? items.filter(it =>
        it.item_code.toLowerCase().includes(q) ||
        it.item_name.toLowerCase().includes(q) ||
        (it.variant_desc ?? '').toLowerCase().includes(q)
      )
    : items

  // 按 item_code 前缀分组（如 010001、120001 等），再按子目名称聚合变体
  const prefixMap = new Map<string, QuotaItem[]>()
  for (const it of filtered) {
    const prefix = getPrefix(it.item_code)
    if (!prefixMap.has(prefix)) prefixMap.set(prefix, [])
    prefixMap.get(prefix)!.push(it)
  }

  return Array.from(prefixMap.entries())
    .map(([prefix, chItems]) => {
      const groupMap = new Map<string, QuotaItem[]>()
      for (const it of chItems) {
        const existing = groupMap.get(it.item_name) ?? []
        existing.push(it)
        groupMap.set(it.item_name, existing)
      }
      const groups: GroupNode[] = Array.from(groupMap.entries()).map(([name, its]) => ({
        name,
        key: `${prefix}|${name}`,
        items: its,
      }))
      const chapterName = chItems[0]?.chapter_name
        ? `${prefix} ${chItems[0].chapter_name}`
        : (chapterMap.get(prefix) ?? prefix)
      return {
        prefix,
        label: chapterName,
        groups,
        count: chItems.length,
      }
    })
    .filter(ch => ch.count > 0)
    .sort((a, b) => a.prefix.localeCompare(b.prefix))
}

// ── 价格卡片 ─────────────────────────────────────────────────────────────

function PriceCard({ label, value, hi }: { label: string; value: number | null; hi?: boolean }) {
  return (
    <div className={`rounded p-2 text-center ${hi ? 'bg-blue-50 border border-blue-200' : 'bg-gray-50'}`}>
      <div className="text-xs text-gray-400 mb-0.5 leading-none">{label}</div>
      <div className={`text-sm font-semibold tabular-nums ${hi ? 'text-blue-700' : 'text-gray-700'}`}>
        {value != null ? fmt(value) : <span className="text-gray-300 font-normal">—</span>}
      </div>
    </div>
  )
}

// ── 工料机小表 ────────────────────────────────────────────────────────────

function ResTable({ resources, type }: { resources: QuotaResource[]; type: string }) {
  const rows = resources.filter(r => r.resource_type === type)
  if (!rows.length) return null
  const colors: Record<string, string> = {
    人工: 'text-orange-700 bg-orange-50 border-orange-200',
    材料: 'text-green-700 bg-green-50 border-green-200',
    机械: 'text-purple-700 bg-purple-50 border-purple-200',
  }
  return (
    <div className="mb-2">
      <span className={`inline-block text-xs font-medium px-1.5 py-0.5 rounded border mb-1 ${colors[type] ?? 'text-gray-600 bg-gray-50 border-gray-200'}`}>{type}</span>
      <table className="w-full text-xs">
        <thead><tr className="text-gray-400 border-b border-gray-100">
          <th className="text-left pb-0.5 font-normal pr-2">名称</th>
          <th className="text-left pb-0.5 font-normal w-14">单位</th>
          <th className="text-right pb-0.5 font-normal w-20">消耗量</th>
          <th className="text-right pb-0.5 font-normal w-24">参考价（元）</th>
        </tr></thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.id} className="border-b border-gray-50 last:border-0">
              <td className="py-0.5 pr-2 text-gray-700 leading-snug">{r.resource_name}</td>
              <td className="py-0.5 text-gray-500">{r.unit ?? '—'}</td>
              <td className="py-0.5 text-right text-gray-800 tabular-nums">
                {r.quantity != null ? r.quantity.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 4 }) : '—'}
              </td>
              <td className="py-0.5 text-right text-gray-600 tabular-nums">{fmt(r.ref_price)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── 详情面板 ─────────────────────────────────────────────────────────────

function DetailPanel({ item }: { item: QuotaItem }) {
  return (
    <div className="ml-12 mr-4 mb-3 mt-1 p-4 bg-white border border-blue-100 rounded-lg shadow-sm">
      {item.work_content && (
        <p className="text-xs text-gray-500 mb-3 leading-relaxed">
          <span className="font-medium text-gray-600">工作内容：</span>
          {item.work_content.replace(/单位\s*[：:].+$/, '').trim()}
        </p>
      )}
      <div className="mb-3">
        <div className="text-xs font-medium text-gray-600 mb-1.5">价格构成（元 / {item.unit ?? '—'}）</div>
        <div className="grid grid-cols-2 gap-1.5 mb-1.5">
          <PriceCard label="全费用综合单价" value={item.total_unit_price} hi />
          <PriceCard label="综合单价" value={item.unit_price} />
        </div>
        <div className="grid grid-cols-5 gap-1.5 mb-1.5">
          <PriceCard label="人工费" value={item.labor_cost} />
          <PriceCard label="材料费" value={item.material_cost} />
          <PriceCard label="机械费" value={item.machine_cost} />
          <PriceCard label="管理费" value={item.management_fee} />
          <PriceCard label="利润" value={item.profit} />
        </div>
        <div className="grid grid-cols-3 gap-1.5">
          <PriceCard label="安全文明施工措施费" value={item.safety_fee} />
          <PriceCard label="规费" value={item.statutory_fee} />
          <PriceCard label="税金" value={item.tax} />
        </div>
      </div>
      {item.resources.length > 0 && (
        <div>
          <div className="text-xs font-medium text-gray-600 mb-1.5">工料机消耗量（基准：2023年8月）</div>
          <ResTable resources={item.resources} type="人工" />
          <ResTable resources={item.resources} type="材料" />
          <ResTable resources={item.resources} type="机械" />
        </div>
      )}
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────────

export default function QuotaPage() {
  const [standards, setStandards] = useState<QuotaStandard[]>([])
  const [standardId, setStandardId] = useState<number | null>(null)
  const [chapterMap, setChapterMap] = useState<Map<string, string>>(new Map())
  const [allItems, setAllItems] = useState<QuotaItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')

  // 展开状态
  const [expandedChapters, setExpandedChapters] = useState<Set<string>>(new Set())
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())
  const [expandedItemId, setExpandedItemId] = useState<number | null>(null)

  // 加载标准列表
  useEffect(() => {
    fetchQuotaStandards()
      .then(list => { setStandards(list); if (list.length) setStandardId(list[0].id) })
      .catch(() => setError('加载标准列表失败'))
  }, [])

  // 加载全量子目 + 章节
  useEffect(() => {
    if (!standardId) return
    setLoading(true); setError('')
    Promise.all([fetchAllQuotaItems(standardId), fetchQuotaChapters(standardId)])
      .then(([items, chapters]) => {
        setAllItems(items)
        // 建立 prefix → name 映射（章节 code 即为 item_code 前缀）
        const map = new Map<string, string>()
        for (const ch of chapters) {
          if (ch.code) map.set(ch.code, ch.name)
        }
        setChapterMap(map)
        setExpandedChapters(new Set()); setExpandedGroups(new Set()); setExpandedItemId(null)
      })
      .catch(e => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false))
  }, [standardId])

  // 构建树
  const tree = buildTree(allItems, appliedSearch, chapterMap)

  // 搜索时自动展开有结果的节点
  useEffect(() => {
    if (!appliedSearch) return
    const chs = new Set<string>()
    const grps = new Set<string>()
    for (const ch of tree) { chs.add(ch.prefix); for (const g of ch.groups) grps.add(g.key) }
    setExpandedChapters(chs)
    setExpandedGroups(grps)
    setExpandedItemId(null)
  }, [appliedSearch]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggleChapter = useCallback((prefix: string) => {
    setExpandedChapters(prev => {
      const next = new Set(prev)
      next.has(prefix) ? next.delete(prefix) : next.add(prefix)
      return next
    })
    setExpandedItemId(null)
  }, [])

  const toggleGroup = useCallback((key: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
    setExpandedItemId(null)
  }, [])

  const toggleItem = useCallback((id: number) => {
    setExpandedItemId(prev => prev === id ? null : id)
  }, [])

  const expandAll = () => {
    setExpandedChapters(new Set(tree.map(c => c.prefix)))
    setExpandedGroups(new Set(tree.flatMap(c => c.groups.map(g => g.key))))
    setExpandedItemId(null)
  }
  const collapseAll = () => {
    setExpandedChapters(new Set())
    setExpandedGroups(new Set())
    setExpandedItemId(null)
  }

  const handleSearch = () => { setAppliedSearch(search) }
  const handleReset = () => { setSearch(''); setAppliedSearch('') }

  const totalVisible = tree.reduce((s, c) => s + c.count, 0)

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-800 mb-4">消耗量标准</h1>

      {/* 顶部工具栏 */}
      <div className="bg-white rounded-lg shadow p-4 mb-4">
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex flex-col gap-1 min-w-[200px]">
            <label className="text-xs text-gray-500">标准版本</label>
            <select
              className="border rounded px-2 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400"
              value={standardId ?? ''}
              onChange={e => setStandardId(Number(e.target.value))}
            >
              {standards.map(s => (
                <option key={s.id} value={s.id}>{s.region ? `[${s.region}] ` : ''}{s.name}（{s.standard_code}，{s.item_count?.toLocaleString()} 条）</option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1 flex-1 min-w-[220px]">
            <label className="text-xs text-gray-500">搜索（编号 / 名称 / 变体描述）</label>
            <div className="flex gap-2">
              <input
                type="text" value={search}
                onChange={e => setSearch(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
                placeholder="输入关键词后回车…"
                className="flex-1 border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
              <button onClick={handleSearch} className="px-3 py-1.5 bg-blue-700 text-white text-sm rounded hover:bg-blue-800">查询</button>
              <button onClick={handleReset} className="px-3 py-1.5 text-gray-600 text-sm rounded border hover:bg-gray-50">重置</button>
            </div>
          </div>

          <div className="flex gap-2 pb-0.5">
            <button onClick={expandAll} className="px-2.5 py-1.5 text-xs text-blue-600 border border-blue-200 rounded hover:bg-blue-50">全部展开</button>
            <button onClick={collapseAll} className="px-2.5 py-1.5 text-xs text-gray-500 border rounded hover:bg-gray-50">全部收起</button>
          </div>
        </div>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4 text-sm">{error}</div>}

      {/* 树形内容区 */}
      <div className="bg-white rounded-lg shadow">
        {/* 状态行 */}
        <div className="px-4 py-2.5 border-b text-sm text-gray-500 flex items-center justify-between">
          <span>
            {loading
              ? <span className="animate-pulse">加载中…</span>
              : <><strong className="text-gray-700">{totalVisible.toLocaleString()}</strong> 条子目 · {tree.length} 个章节</>
            }
          </span>
          {standardId && standards.length > 0 && (
            <span className="text-xs text-gray-400">
              基准价格：{standards.find(s => s.id === standardId)?.base_date?.slice(0, 7) ?? '—'}
            </span>
          )}
        </div>

        {!loading && tree.length === 0 && (
          <div className="px-4 py-16 text-center text-gray-400">
            {allItems.length ? '没有匹配结果' : '暂无数据'}
          </div>
        )}

        <div className="divide-y divide-gray-100">
          {tree.map(chapter => {
            const chOpen = expandedChapters.has(chapter.prefix)
            return (
              <div key={chapter.prefix}>
                {/* ── 章节行 ─────────────────────────── */}
                <button
                  className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-gray-50 transition-colors group"
                  onClick={() => toggleChapter(chapter.prefix)}
                >
                  <span className={`w-5 h-5 flex items-center justify-center rounded border text-xs font-bold flex-shrink-0 transition-colors ${
                    chOpen ? 'border-blue-400 text-blue-600 bg-blue-50' : 'border-gray-300 text-gray-500 group-hover:border-gray-400'
                  }`}>
                    {chOpen ? '−' : '+'}
                  </span>
                  <span className="font-semibold text-gray-800 text-sm">{chapter.label}</span>
                  <span className="ml-auto text-xs text-gray-400 flex-shrink-0">{chapter.count} 条</span>
                </button>

                {/* ── 子目名称组 ─────────────────────── */}
                {chOpen && (
                  <div className="bg-gray-50/50">
                    {chapter.groups.map(group => {
                      const grpOpen = expandedGroups.has(group.key)
                      return (
                        <div key={group.key}>
                          {/* 子目名称行 */}
                          <button
                            className="w-full flex items-center gap-2 pl-10 pr-4 py-2 text-left hover:bg-gray-100/80 transition-colors group"
                            onClick={() => toggleGroup(group.key)}
                          >
                            <span className={`w-4 h-4 flex items-center justify-center rounded border text-xs font-bold flex-shrink-0 transition-colors ${
                              grpOpen ? 'border-emerald-400 text-emerald-600 bg-emerald-50' : 'border-gray-300 text-gray-400 group-hover:border-gray-400'
                            }`}>
                              {grpOpen ? '−' : '+'}
                            </span>
                            <span className="text-sm text-gray-700 font-medium">{group.name}</span>
                            <span className="ml-auto text-xs text-gray-400 flex-shrink-0">{group.items.length} 条</span>
                          </button>

                          {/* 变体行列表 */}
                          {grpOpen && (
                            <div>
                              {/* 表头 */}
                              <div className="grid grid-cols-[7rem_1fr_5rem_8rem_1.5rem] gap-2 pl-16 pr-4 py-1.5 text-xs text-gray-400 border-b border-gray-100 bg-white/60">
                                <span>子目编号</span>
                                <span>变体描述</span>
                                <span>单位</span>
                                <span className="text-right">全费用综合单价（元）</span>
                                <span />
                              </div>
                              {group.items.map(item => (
                                <Fragment key={item.id}>
                                  <div
                                    className={`grid grid-cols-[7rem_1fr_5rem_8rem_1.5rem] gap-2 pl-16 pr-4 py-2 cursor-pointer items-center transition-colors ${
                                      expandedItemId === item.id ? 'bg-blue-50' : 'hover:bg-gray-100/60'
                                    }`}
                                    onClick={() => toggleItem(item.id)}
                                  >
                                    <span className="font-mono text-xs text-blue-600 font-medium">{item.item_code}</span>
                                    <span className="text-xs text-gray-600 truncate">{item.variant_desc ?? <span className="text-gray-300">—</span>}</span>
                                    <span className="text-xs text-gray-500">{item.unit ?? '—'}</span>
                                    <span className="text-sm font-semibold text-blue-700 tabular-nums text-right">
                                      {item.total_unit_price != null ? fmt(item.total_unit_price) : <span className="text-gray-300 font-normal">—</span>}
                                    </span>
                                    <span className="text-xs text-gray-400 text-center select-none">
                                      {expandedItemId === item.id ? '▲' : '▼'}
                                    </span>
                                  </div>
                                  {expandedItemId === item.id && <DetailPanel item={item} />}
                                </Fragment>
                              ))}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
