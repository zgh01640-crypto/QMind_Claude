'use client'
import { useState, useEffect, useCallback, Fragment } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import {
  fetchBoqProjects, fetchAllBoqItems, fetchBoqMatches, fetchBoqRuns,
  updateBoqMatch, deleteBoqMatch,
  BoqProject, BoqItem, BoqMatchResult, BoqMatchRun,
} from '@/lib/api'
import { MatchCard, DescBlock, SummaryPanel, fmt } from '@/components/boq'

// ── 分部树构建 ────────────────────────────────────────────────────────────────

interface SectionNode { section_name: string; items: BoqItem[] }

function buildSections(items: BoqItem[], filter: string): SectionNode[] {
  const q = filter.trim().toLowerCase()
  const filtered = q
    ? items.filter(it =>
        it.item_code.toLowerCase().includes(q) ||
        it.item_name.toLowerCase().includes(q) ||
        (it.item_description ?? '').toLowerCase().includes(q)
      )
    : items
  const map = new Map<string, SectionNode>()
  for (const it of filtered) {
    const key = it.section_name ?? '未分类'
    if (!map.has(key)) map.set(key, { section_name: key, items: [] })
    map.get(key)!.items.push(it)
  }
  return Array.from(map.values())
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

export default function RunResultPage() {
  const params = useParams()
  const projectId = Number(params.id)
  const runId = Number(params.rid)

  const [project, setProject] = useState<BoqProject | null>(null)
  const [run, setRun] = useState<BoqMatchRun | null>(null)
  const [allItems, setAllItems] = useState<BoqItem[]>([])
  const [matches, setMatches] = useState<BoqMatchResult[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set())
  const [expandedItemId, setExpandedItemId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<'list' | 'summary'>('list')

  useEffect(() => {
    Promise.all([
      fetchBoqProjects(),
      fetchAllBoqItems(projectId),
      fetchBoqMatches(runId),
      fetchBoqRuns(projectId),
    ]).then(([projs, items, mts, runs]) => {
      setProject(projs.find(p => p.id === projectId) ?? null)
      setAllItems(items)
      setMatches(mts)
      setRun(runs.find(r => r.id === runId) ?? null)
    }).catch(e => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false))
  }, [projectId, runId])

  const sections = buildSections(allItems, appliedSearch)

  useEffect(() => {
    if (!appliedSearch) return
    setExpandedSections(new Set(sections.map(s => s.section_name)))
    setExpandedItemId(null)
  }, [appliedSearch]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggleSection = useCallback((name: string) => {
    setExpandedSections(prev => {
      const next = new Set(prev)
      next.has(name) ? next.delete(name) : next.add(name)
      return next
    })
    setExpandedItemId(null)
  }, [])

  const toggleItem = useCallback((id: number) => {
    setExpandedItemId(prev => prev === id ? null : id)
  }, [])

  const handleConfirm = async (matchId: number) => {
    const updated = await updateBoqMatch(matchId, 'confirmed')
    setMatches(prev => prev.map(m => m.id === matchId ? updated : m))
  }

  const handleReject = async (matchId: number) => {
    const updated = await updateBoqMatch(matchId, 'rejected')
    setMatches(prev => prev.map(m => m.id === matchId ? updated : m))
  }

  const handleDelete = async (matchId: number) => {
    await deleteBoqMatch(matchId)
    setMatches(prev => prev.filter(m => m.id !== matchId))
  }

  const matchedCount = new Set(matches.filter(m => m.status !== 'rejected').map(m => m.boq_item_id)).size
  const confirmedCount = new Set(matches.filter(m => m.status === 'confirmed').map(m => m.boq_item_id)).size
  const totalVisible = sections.reduce((s, sec) => s + sec.items.length, 0)

  if (loading) return <div className="text-center text-gray-400 py-20 animate-pulse">加载中…</div>

  return (
    <div>
      {/* 面包屑 */}
      <div className="flex items-center gap-1.5 text-sm text-gray-500 mb-4">
        <Link href="/boq" className="hover:text-blue-600">工程管理</Link>
        <span>/</span>
        <Link href={`/boq/${projectId}`} className="hover:text-blue-600 max-w-xs truncate">
          {project?.project_name ?? `工程 #${projectId}`}
        </Link>
        <span>/</span>
        <span className="text-gray-800 font-medium">
          套定额结果 {run ? `（${new Date(run.created_at).toLocaleString('zh-CN')}）` : ''}
        </span>
      </div>

      {/* 运行元信息卡 */}
      {run && (
        <div className="bg-white rounded-lg shadow p-4 mb-4 flex flex-wrap gap-x-8 gap-y-2 text-sm">
          <div><span className="text-gray-400">定额标准：</span><span className="font-medium">{run.standard_code ?? `#${run.standard_id}`}</span></div>
          <div><span className="text-gray-400">已匹配：</span><span className="font-medium text-indigo-700">{matchedCount}</span> 项</div>
          <div><span className="text-gray-400">已确认：</span><span className="font-medium text-green-700">{confirmedCount}</span> 项</div>
          <div><span className="text-gray-400">运行时间：</span>{new Date(run.created_at).toLocaleString('zh-CN')}</div>
        </div>
      )}

      {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4 text-sm">{error}</div>}

      {/* Tab 切换 */}
      <div className="flex gap-1 mb-4">
        <button
          onClick={() => setActiveTab('list')}
          className={`px-4 py-2 rounded text-sm font-medium transition-colors ${activeTab === 'list' ? 'bg-white shadow text-blue-700' : 'text-gray-500 hover:text-gray-700'}`}
        >清单与匹配</button>
        <button
          onClick={() => setActiveTab('summary')}
          className={`px-4 py-2 rounded text-sm font-medium transition-colors ${activeTab === 'summary' ? 'bg-white shadow text-blue-700' : 'text-gray-500 hover:text-gray-700'}`}
        >造价汇总</button>
      </div>

      {/* 清单列表 Tab */}
      {activeTab === 'list' && (
        <div className="bg-white rounded-lg shadow">
          {/* 工具栏 */}
          <div className="px-4 py-3 border-b flex flex-wrap gap-3 items-center">
            <div className="flex gap-2 flex-1 min-w-[200px]">
              <input
                type="text" value={search}
                onChange={e => setSearch(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && setAppliedSearch(search)}
                placeholder="搜索编码/名称/特征…"
                className="flex-1 border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
              <button onClick={() => setAppliedSearch(search)} className="px-3 py-1.5 bg-blue-700 text-white text-sm rounded hover:bg-blue-800">查询</button>
              <button onClick={() => { setSearch(''); setAppliedSearch('') }} className="px-3 py-1.5 text-gray-600 text-sm rounded border hover:bg-gray-50">重置</button>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setExpandedSections(new Set(sections.map(s => s.section_name)))} className="px-2.5 py-1.5 text-xs text-blue-600 border border-blue-200 rounded hover:bg-blue-50">全展开</button>
              <button onClick={() => { setExpandedSections(new Set()); setExpandedItemId(null) }} className="px-2.5 py-1.5 text-xs text-gray-500 border rounded hover:bg-gray-50">全收起</button>
            </div>
            <span className="text-sm text-gray-500">
              <strong className="text-gray-700">{totalVisible}</strong> 条 · {sections.length} 个分部
            </span>
          </div>

          {/* 列头 */}
          {sections.length > 0 && (
            <div className="hidden md:grid grid-cols-[3rem_9rem_1fr_5rem_8rem] gap-2 px-4 py-2 text-xs text-gray-400 bg-gray-50 border-b">
              <span>序号</span><span>项目编码</span><span>项目名称</span><span>单位</span><span className="text-right">工程量</span>
            </div>
          )}

          {!loading && sections.length === 0 && (
            <div className="px-4 py-16 text-center text-gray-400">{allItems.length ? '没有匹配结果' : '暂无清单项'}</div>
          )}

          <div className="divide-y divide-gray-100">
            {sections.map(sec => {
              const open = expandedSections.has(sec.section_name)
              const secMatches = matches.filter(m => sec.items.some(it => it.id === m.boq_item_id))
              const secConfirmed = new Set(secMatches.filter(m => m.status === 'confirmed').map(m => m.boq_item_id)).size
              const secMatched = new Set(secMatches.filter(m => m.status !== 'rejected').map(m => m.boq_item_id)).size

              return (
                <div key={sec.section_name}>
                  <button
                    className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-gray-50 transition-colors group"
                    onClick={() => toggleSection(sec.section_name)}
                  >
                    <span className={`w-5 h-5 flex items-center justify-center rounded border text-xs font-bold shrink-0 ${open ? 'border-blue-400 text-blue-600 bg-blue-50' : 'border-gray-300 text-gray-500'}`}>
                      {open ? '−' : '+'}
                    </span>
                    <span className="font-semibold text-gray-800 text-sm">{sec.section_name}</span>
                    <span className="ml-auto text-xs text-gray-400 flex items-center gap-2">
                      {secMatched > 0 && <span className="text-indigo-500">{secConfirmed}/{sec.items.length} 已确认</span>}
                      <span>{sec.items.length} 项</span>
                    </span>
                  </button>

                  {open && (
                    <div>
                      {sec.items.map(item => {
                        const itemMatches = matches.filter(m => m.boq_item_id === item.id && m.status !== 'rejected')
                        const hasConfirmed = itemMatches.some(m => m.status === 'confirmed')
                        return (
                          <Fragment key={item.id}>
                            <div
                              className={`grid grid-cols-[3rem_9rem_1fr_5rem_8rem] gap-2 pl-10 pr-4 py-2.5 cursor-pointer items-start transition-colors ${expandedItemId === item.id ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                              onClick={() => toggleItem(item.id)}
                            >
                              <span className="text-xs text-gray-400 pt-0.5 tabular-nums">{item.item_seq}</span>
                              <span className="font-mono text-xs text-blue-600 font-medium pt-0.5 break-all">{item.item_code}</span>
                              <span className="text-sm text-gray-800 flex items-center gap-1.5">
                                {item.item_name}
                                {itemMatches.length > 0 && (
                                  <span className={`text-xs px-1 py-0.5 rounded shrink-0 ${hasConfirmed ? 'bg-green-100 text-green-600' : 'bg-indigo-100 text-indigo-600'}`}>
                                    {hasConfirmed ? '✓' : `AI(${itemMatches.length})`}
                                  </span>
                                )}
                              </span>
                              <span className="text-xs text-gray-500 pt-0.5">{item.unit ?? '—'}</span>
                              <span className="text-sm font-semibold text-gray-800 tabular-nums text-right pt-0.5">
                                {item.quantity?.toLocaleString('zh-CN', { maximumFractionDigits: 4 }) ?? '—'}
                              </span>
                            </div>

                            {expandedItemId === item.id && (
                              <div className="ml-10 mr-4 mb-3 px-4 py-3 bg-white border border-blue-100 rounded-lg shadow-sm">
                                {item.item_description && (
                                  <div className="mb-3">
                                    <div className="text-xs font-medium text-gray-600 mb-1">项目特征描述</div>
                                    <DescBlock text={item.item_description} />
                                  </div>
                                )}
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs mb-3">
                                  {[
                                    ['计量单位', item.unit ?? '—'],
                                    ['工程量', item.quantity?.toLocaleString('zh-CN', { maximumFractionDigits: 4 }) ?? '—'],
                                  ].map(([label, value]) => (
                                    <div key={label} className="bg-gray-50 rounded p-2">
                                      <div className="text-gray-400 mb-0.5">{label}</div>
                                      <div className="font-medium text-gray-700">{value}</div>
                                    </div>
                                  ))}
                                </div>

                                {/* 定额匹配结果 */}
                                <div className="mt-3 pt-3 border-t border-gray-100">
                                  <div className="text-xs font-medium text-gray-600 mb-2">
                                    定额匹配
                                    {matches.filter(m => m.boq_item_id === item.id).length > 0 && (
                                      <span className="ml-1 text-gray-400">{matches.filter(m => m.boq_item_id === item.id).length} 条</span>
                                    )}
                                  </div>
                                  {matches.filter(m => m.boq_item_id === item.id).length === 0 && (
                                    <div className="text-xs text-gray-400 py-1">此清单项无匹配结果</div>
                                  )}
                                  <div className="space-y-2">
                                    {matches.filter(m => m.boq_item_id === item.id).map(m => (
                                      <MatchCard key={m.id} m={m} onConfirm={handleConfirm} onReject={handleReject} onDelete={handleDelete} />
                                    ))}
                                  </div>
                                </div>
                              </div>
                            )}
                          </Fragment>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* 造价汇总 Tab */}
      {activeTab === 'summary' && (
        <div className="bg-white rounded-lg shadow p-4">
          <SummaryPanel runId={runId} matches={matches} />
        </div>
      )}
    </div>
  )
}
