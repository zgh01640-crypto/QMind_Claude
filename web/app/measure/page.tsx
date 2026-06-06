'use client'
import { useState, useEffect, useCallback, Fragment } from 'react'
import {
  fetchMeasureStandards, fetchMeasureSections, fetchAllMeasureItems,
  MeasureStandard, MeasureSection, MeasureItem,
} from '@/lib/api'

// ── 工具函数 ──────────────────────────────────────────────────────────────────

function buildSectionTree(sections: MeasureSection[]) {
  const roots = sections.filter(s => s.level === 1).sort((a, b) => a.sort_order - b.sort_order)
  const children = sections.filter(s => s.level === 2).sort((a, b) => a.sort_order - b.sort_order)
  return roots.map(root => ({
    ...root,
    children: children.filter(c => c.parent_id === root.id),
  }))
}

type SectionWithChildren = MeasureSection & { children: MeasureSection[] }

// 按节分组清单项目：先匹配 section_id，再 fallback 到 item_code 前6位
function groupItems(items: MeasureItem[], sections: MeasureSection[]) {
  const secById = new Map(sections.map(s => [s.id, s]))
  const grouped = new Map<number | null, MeasureItem[]>()
  for (const it of items) {
    const key = it.section_id ?? null
    if (!grouped.has(key)) grouped.set(key, [])
    grouped.get(key)!.push(it)
  }
  return grouped
}

// ── 详情面板 ─────────────────────────────────────────────────────────────────

function DetailPanel({ item }: { item: MeasureItem }) {
  return (
    <div className="ml-12 mr-4 mb-3 mt-0.5 p-4 bg-white border border-blue-100 rounded-lg shadow-sm text-xs text-gray-600 space-y-2.5">
      {item.item_features && (
        <div>
          <span className="font-medium text-gray-700">项目特征：</span>
          <span className="leading-relaxed whitespace-pre-line">{item.item_features}</span>
        </div>
      )}
      {item.calc_rule && (
        <div>
          <span className="font-medium text-gray-700">工程量计算规则：</span>
          <span className="leading-relaxed whitespace-pre-line">{item.calc_rule}</span>
        </div>
      )}
      {item.work_content && (
        <div>
          <span className="font-medium text-gray-700">工作内容：</span>
          <span className="leading-relaxed whitespace-pre-line">{item.work_content}</span>
        </div>
      )}
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

export default function MeasurePage() {
  const [standards, setStandards] = useState<MeasureStandard[]>([])
  const [standardId, setStandardId] = useState<number | null>(null)
  const [sections, setSections] = useState<MeasureSection[]>([])
  const [allItems, setAllItems] = useState<MeasureItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')

  // 展开状态
  const [expandedAppendices, setExpandedAppendices] = useState<Set<number>>(new Set())
  const [expandedSections, setExpandedSections] = useState<Set<number>>(new Set())
  const [expandedItemId, setExpandedItemId] = useState<number | null>(null)

  // 加载标准列表
  useEffect(() => {
    fetchMeasureStandards()
      .then(list => { setStandards(list); if (list.length) setStandardId(list[0].id) })
      .catch(() => setError('加载标准列表失败'))
  }, [])

  // 加载节和全量项目
  useEffect(() => {
    if (!standardId) return
    setLoading(true); setError('')
    setExpandedAppendices(new Set()); setExpandedSections(new Set()); setExpandedItemId(null)
    Promise.all([
      fetchMeasureSections(standardId),
      fetchAllMeasureItems(standardId),
    ])
      .then(([secs, items]) => { setSections(secs); setAllItems(items) })
      .catch(e => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false))
  }, [standardId])

  // 构建树
  const tree: SectionWithChildren[] = buildSectionTree(sections)

  // 搜索过滤
  const q = appliedSearch.trim().toLowerCase()
  const filteredItems = q
    ? allItems.filter(it =>
        it.item_code.includes(q) ||
        it.item_name.toLowerCase().includes(q) ||
        (it.item_features ?? '').toLowerCase().includes(q)
      )
    : allItems

  const groupedItems = groupItems(filteredItems, sections)

  // 搜索时自动展开
  useEffect(() => {
    if (!appliedSearch || !sections.length) return
    const hitSecIds = new Set(filteredItems.map(it => it.section_id).filter(Boolean) as number[])
    const secById = new Map(sections.map(s => [s.id, s]))
    const appendixIds = new Set<number>()
    const sectionIds = new Set<number>()
    for (const sid of hitSecIds) {
      const sec = secById.get(sid)
      if (!sec) continue
      if (sec.level === 2 && sec.parent_id) {
        appendixIds.add(sec.parent_id)
        sectionIds.add(sec.id)
      } else if (sec.level === 1) {
        appendixIds.add(sec.id)
      }
    }
    setExpandedAppendices(appendixIds)
    setExpandedSections(sectionIds)
    setExpandedItemId(null)
  }, [appliedSearch]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggleAppendix = useCallback((id: number) => {
    setExpandedAppendices(prev => {
      const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next
    })
    setExpandedItemId(null)
  }, [])

  const toggleSection = useCallback((id: number) => {
    setExpandedSections(prev => {
      const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next
    })
    setExpandedItemId(null)
  }, [])

  const toggleItem = useCallback((id: number) => {
    setExpandedItemId(prev => prev === id ? null : id)
  }, [])

  const expandAll = () => {
    setExpandedAppendices(new Set(tree.map(a => a.id)))
    setExpandedSections(new Set(tree.flatMap(a => a.children.map(s => s.id))))
    setExpandedItemId(null)
  }
  const collapseAll = () => {
    setExpandedAppendices(new Set()); setExpandedSections(new Set()); setExpandedItemId(null)
  }

  const handleSearch = () => setAppliedSearch(search)
  const handleReset = () => { setSearch(''); setAppliedSearch('') }

  const totalVisible = filteredItems.length

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-800 mb-4">国标清单</h1>

      {/* 顶部工具栏 */}
      <div className="bg-white rounded-lg shadow p-4 mb-4">
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex flex-col gap-1 min-w-[240px]">
            <label className="text-xs text-gray-500">标准版本</label>
            <select
              className="border rounded px-2 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400"
              value={standardId ?? ''}
              onChange={e => setStandardId(Number(e.target.value))}
            >
              {standards.map(s => (
                <option key={s.id} value={s.id}>
                  {s.name}（{s.item_count?.toLocaleString()} 条）
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1 flex-1 min-w-[220px]">
            <label className="text-xs text-gray-500">搜索（编码 / 项目名称 / 项目特征）</label>
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
        <div className="px-4 py-2.5 border-b text-sm text-gray-500 flex items-center justify-between">
          <span>
            {loading
              ? <span className="animate-pulse">加载中…</span>
              : <><strong className="text-gray-700">{totalVisible.toLocaleString()}</strong> 条清单项目 · {tree.length} 个附录</>
            }
          </span>
        </div>

        {!loading && tree.length === 0 && (
          <div className="px-4 py-16 text-center text-gray-400">
            {allItems.length ? '没有匹配结果' : '暂无数据，请先运行 import_measure.py 导入文档'}
          </div>
        )}

        <div className="divide-y divide-gray-100">
          {tree.map(appendix => {
            const appOpen = expandedAppendices.has(appendix.id)
            // 该附录下的所有直属项目（无节归属）
            const directItems = groupedItems.get(appendix.id) ?? []

            return (
              <div key={appendix.id}>
                {/* ── 附录行（level=1）────────────────────────────────── */}
                <button
                  className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-gray-50 transition-colors group"
                  onClick={() => toggleAppendix(appendix.id)}
                >
                  <span className={`w-5 h-5 flex items-center justify-center rounded border text-xs font-bold flex-shrink-0 transition-colors ${
                    appOpen ? 'border-blue-400 text-blue-600 bg-blue-50' : 'border-gray-300 text-gray-500 group-hover:border-gray-400'
                  }`}>
                    {appOpen ? '−' : '+'}
                  </span>
                  <span className="font-mono text-xs text-blue-500 w-6 flex-shrink-0">{appendix.code}</span>
                  <span className="font-semibold text-gray-800 text-sm">{appendix.name}</span>
                  <span className="ml-auto text-xs text-gray-400 flex-shrink-0">
                    {appendix.children.length} 节
                  </span>
                </button>

                {/* ── 节（level=2）──────────────────────────────────── */}
                {appOpen && (
                  <div className="bg-gray-50/50">
                    {appendix.children.map(section => {
                      const secOpen = expandedSections.has(section.id)
                      const secItems = groupedItems.get(section.id) ?? []
                      if (!secItems.length && appliedSearch) return null

                      return (
                        <div key={section.id}>
                          <button
                            className="w-full flex items-center gap-2 pl-10 pr-4 py-2 text-left hover:bg-gray-100/80 transition-colors group"
                            onClick={() => toggleSection(section.id)}
                          >
                            <span className={`w-4 h-4 flex items-center justify-center rounded border text-xs font-bold flex-shrink-0 transition-colors ${
                              secOpen ? 'border-emerald-400 text-emerald-600 bg-emerald-50' : 'border-gray-300 text-gray-400 group-hover:border-gray-400'
                            }`}>
                              {secOpen ? '−' : '+'}
                            </span>
                            <span className="font-mono text-xs text-emerald-600 w-16 flex-shrink-0">{section.num_code || section.code}</span>
                            <span className="text-sm text-gray-700 font-medium">{section.name}</span>
                            <span className="ml-auto text-xs text-gray-400 flex-shrink-0">{secItems.length} 条</span>
                          </button>

                          {/* ── 节描述文字（如：其他规定）──────────────── */}
                          {secOpen && section.description && (
                            <div className="pl-14 pr-4 py-3 bg-amber-50/40 border-b border-amber-100/60">
                              <pre className="text-xs text-gray-600 whitespace-pre-wrap leading-relaxed font-sans">
                                {section.description}
                              </pre>
                            </div>
                          )}

                          {/* ── 清单项目行 ─────────────────────────────── */}
                          {secOpen && secItems.length > 0 && (
                            <div>
                              {/* 表头 */}
                              <div className="grid grid-cols-[6rem_1fr_4rem_1.5rem] gap-2 pl-20 pr-4 py-1.5 text-xs text-gray-400 border-b border-gray-100 bg-white/60">
                                <span>项目编码</span>
                                <span>项目名称</span>
                                <span>计量单位</span>
                                <span />
                              </div>
                              {secItems.map(item => (
                                <Fragment key={item.id}>
                                  <div
                                    className={`grid grid-cols-[6rem_1fr_4rem_1.5rem] gap-2 pl-20 pr-4 py-2 cursor-pointer items-center transition-colors ${
                                      expandedItemId === item.id ? 'bg-blue-50' : 'hover:bg-gray-100/60'
                                    }`}
                                    onClick={() => toggleItem(item.id)}
                                  >
                                    <span className="font-mono text-xs text-blue-600 font-medium">{item.item_code}</span>
                                    <span className="text-xs text-gray-700">{item.item_name}</span>
                                    <span className="text-xs text-gray-500">{item.unit ?? '—'}</span>
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
