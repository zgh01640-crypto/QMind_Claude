'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  fetchPricingKbBoqItems,
  fetchPricingKbCandidates,
  fetchPricingKbImportIssues,
  fetchPricingKbImportRuns,
  fetchPricingKbLibraries,
  fetchPricingKbQuotaItems,
  fetchPricingKbSummary,
  PricingKbBoqItem,
  PricingKbCandidateResponse,
  PricingKbImportIssue,
  PricingKbImportRun,
  PricingKbLibrary,
  PricingKbQuotaItem,
  PricingKbSummary,
} from '@/lib/api'
import ImportManager from '@/components/pricing-kb/ImportManager'

const PAGE_SIZE = 50
const COST_LABELS = [
  ['dj', '综合单价'], ['rgf', '人工费'], ['clf', '材料费'], ['jxf', '机械费'],
  ['zcf', '主材费'], ['sbf', '设备费'], ['glf', '管理费'], ['lr', '利润'],
  ['aqwmsgf', '安全文明施工费'], ['qtcsf', '其他措施费'], ['gf', '规费'], ['sj', '税金'],
] as const

type TabKey = 'boq' | 'quota' | 'imports'

function fmt(v: number | null | undefined) {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN')
}

function statusClass(status: string) {
  const map: Record<string, string> = {
    matched: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    review: 'border-amber-200 bg-amber-50 text-amber-700',
    unmatched: 'border-red-200 bg-red-50 text-red-700',
    unlinked: 'border-gray-200 bg-gray-50 text-gray-500',
    done: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    running: 'border-blue-200 bg-blue-50 text-blue-700',
    failed: 'border-red-200 bg-red-50 text-red-700',
    warning: 'border-amber-200 bg-amber-50 text-amber-700',
  }
  return map[status] ?? 'border-gray-200 bg-gray-50 text-gray-600'
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex rounded border px-2 py-0.5 text-xs font-medium ${statusClass(status)}`}>
      {status}
    </span>
  )
}

function StatCard({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <div className="border border-gray-200 bg-white px-3 py-2">
      <div className="text-xs text-gray-400">{label}</div>
      <div className="mt-1 text-lg font-semibold tabular-nums text-gray-900">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-gray-400">{hint}</div>}
    </div>
  )
}

function Pagination({
  page,
  total,
  onPageChange,
}: {
  page: number
  total: number
  onPageChange: (page: number) => void
}) {
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  return (
    <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm text-gray-600">
      <span className="tabular-nums">第 {page} / {totalPages} 页</span>
      <div className="flex gap-1">
        {[
          ['首页', 1],
          ['上一页', page - 1],
          ['下一页', page + 1],
          ['末页', totalPages],
        ].map(([label, target]) => (
          <button
            key={label}
            onClick={() => onPageChange(Number(target))}
            disabled={Number(target) < 1 || Number(target) > totalPages || Number(target) === page}
            className="rounded border border-gray-300 px-3 py-1.5 text-xs hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}

function LibrarySidebar({
  libraries,
  selectedLibraryId,
  onSelect,
}: {
  libraries: PricingKbLibrary[]
  selectedLibraryId: number | null
  onSelect: (id: number | null) => void
}) {
  return (
    <aside className="border-b border-gray-200 bg-white lg:border-b-0 lg:border-r">
      <div className="border-b border-gray-200 px-4 py-3">
        <div className="text-sm font-semibold text-gray-900">标准库目录</div>
        <div className="mt-0.5 text-xs text-gray-400">SQLite 来源库</div>
      </div>
      <div className="max-h-[42vh] overflow-y-auto py-2 lg:max-h-[calc(100vh-250px)]">
        <button
          onClick={() => onSelect(null)}
          className={`w-full border-l-2 px-4 py-2.5 text-left text-sm transition ${
            selectedLibraryId == null
              ? 'border-blue-700 bg-blue-50 text-blue-700'
              : 'border-transparent text-gray-700 hover:bg-gray-50'
          }`}
        >
          <div className="font-medium">全部标准库</div>
          <div className="mt-0.5 text-xs text-gray-400">跨专业检索</div>
        </button>
        {libraries.map(library => (
          <button
            key={library.id}
            onClick={() => onSelect(library.id)}
            className={`w-full border-l-2 px-4 py-2.5 text-left text-sm transition ${
              selectedLibraryId === library.id
                ? 'border-blue-700 bg-blue-50 text-blue-700'
                : 'border-transparent text-gray-700 hover:bg-gray-50'
            }`}
          >
            <div className="font-medium leading-snug">{library.name}</div>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-400">
              <span>{library.source_library_id}</span>
              <span>清单 {fmt(library.boq_count)}</span>
              <span>定额 {fmt(library.quota_count)}</span>
            </div>
          </button>
        ))}
      </div>
    </aside>
  )
}

function CandidatePanel({
  detail,
  loading,
  onClose,
}: {
  detail: PricingKbCandidateResponse | null
  loading: boolean
  onClose: () => void
}) {
  if (!detail && !loading) return null
  return (
    <div className="mt-4 border border-blue-100 bg-white">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-blue-100 bg-blue-50 px-4 py-3">
        <div>
          <div className="text-sm font-semibold text-blue-900">候选定额详情</div>
          {detail && (
            <div className="mt-1 text-xs text-blue-700">
              {detail.boq_item.code ?? '-'} · {detail.boq_item.name} · 共 {detail.total} 条候选
            </div>
          )}
        </div>
        <button onClick={onClose} className="rounded border border-blue-200 bg-white px-3 py-1.5 text-xs text-blue-700 hover:bg-blue-50">
          关闭
        </button>
      </div>
      {loading && <div className="px-4 py-8 text-center text-sm text-gray-400">候选定额加载中...</div>}
      {!loading && detail && (
        <div className="max-h-[520px] overflow-y-auto divide-y divide-gray-100">
          {detail.candidates.map(candidate => (
            <div key={candidate.candidate_id} className="px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-sm font-semibold text-blue-700">{candidate.quota_item.code ?? '-'}</span>
                    <span className="text-xs text-gray-400">{candidate.quota_item.library_name}</span>
                  </div>
                  <div className="mt-1 text-sm font-medium text-gray-900">{candidate.quota_item.name}</div>
                  <div className="mt-1 flex flex-wrap gap-3 text-xs text-gray-500">
                    <span>单位：{candidate.quota_item.unit ?? '-'}</span>
                    <span>工料机：{candidate.resource_count}</span>
                  </div>
                </div>
              </div>
              {candidate.quota_item.work_content && (
                <div className="mt-2 rounded bg-gray-50 px-3 py-2 text-xs leading-relaxed text-gray-600">
                  {candidate.quota_item.work_content}
                </div>
              )}
              <div className="mt-3">
                <div className="mb-2 text-xs font-semibold text-gray-500">费用构成</div>
                <div className="grid grid-cols-2 border-l border-t border-gray-200 sm:grid-cols-4 xl:grid-cols-6">
                  {COST_LABELS.map(([key, label]) => (
                    <div key={key} className="border-b border-r border-gray-200 px-2 py-1.5">
                      <div className="text-[11px] text-gray-400">{label}</div>
                      <div className="mt-0.5 font-mono text-xs font-medium text-gray-800">
                        {candidate.quota_item.cost_breakdown?.[key]?.toFixed(2) ?? '-'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              {candidate.resource_summary.length > 0 && (
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full min-w-[620px] border-collapse text-xs">
                    <thead className="bg-gray-50 text-gray-500">
                      <tr>
                        <th className="px-2 py-1.5 text-left font-medium">类型</th>
                        <th className="px-2 py-1.5 text-left font-medium">编码</th>
                        <th className="px-2 py-1.5 text-left font-medium">名称</th>
                        <th className="px-2 py-1.5 text-left font-medium">单位</th>
                        <th className="px-2 py-1.5 text-right font-medium">消耗量</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {candidate.resource_summary.map((resource, idx) => (
                        <tr key={`${candidate.candidate_id}-${idx}`}>
                          <td className="px-2 py-1.5 text-gray-500">{resource.resource_type ?? '-'}</td>
                          <td className="px-2 py-1.5 font-mono text-gray-400">{resource.resource_code ?? '-'}</td>
                          <td className="px-2 py-1.5 text-gray-700">{resource.resource_name}</td>
                          <td className="px-2 py-1.5 text-gray-500">{resource.unit ?? '-'}</td>
                          <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">{resource.quantity ?? '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {candidate.conversion_rules.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {candidate.conversion_rules.slice(0, 6).map((rule, idx) => (
                    <span key={`${candidate.candidate_id}-rule-${idx}`} className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-800">
                      {rule.prompt || rule.description || rule.rule_type}
                    </span>
                  ))}
                </div>
              )}
              {(candidate.input_prompt_rules?.length ?? 0) > 0 && (
                <div className="mt-3 overflow-x-auto border border-gray-200">
                  <table className="w-full min-w-[620px] border-collapse text-xs">
                    <thead className="bg-gray-50 text-gray-500">
                      <tr>
                        <th className="px-2 py-1.5 text-left font-medium">实际值提示</th>
                        <th className="px-2 py-1.5 text-left font-medium">关联换算编号</th>
                        <th className="px-2 py-1.5 text-right font-medium">基准值</th>
                        <th className="px-2 py-1.5 text-right font-medium">增减单位</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {(candidate.input_prompt_rules ?? []).map((rule, idx) => (
                        <tr key={`${candidate.candidate_id}-prompt-${idx}`}>
                          <td className="px-2 py-1.5 text-gray-700">{rule.prompt ?? '-'}</td>
                          <td className="px-2 py-1.5 font-mono text-blue-700">{rule.adjustment_code ?? '-'}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{rule.base_value ?? '-'}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{rule.increment_unit ?? '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function SearchBar({
  query,
  code,
  onQueryChange,
  onCodeChange,
  onSearch,
  onClear,
  placeholder,
}: {
  query: string
  code: string
  onQueryChange: (value: string) => void
  onCodeChange: (value: string) => void
  onSearch: () => void
  onClear: () => void
  placeholder: string
}) {
  return (
    <div className="mb-4 border border-gray-200 bg-white p-3">
      <div className="grid gap-3 md:grid-cols-[180px_minmax(260px,1fr)_auto] md:items-end">
        <div>
          <label className="mb-1 block text-xs text-gray-500">编码前缀</label>
          <input
            value={code}
            onChange={event => onCodeChange(event.target.value)}
            onKeyDown={event => { if (event.key === 'Enter') onSearch() }}
            className="w-full rounded border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
            placeholder="如 040504"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-500">名称关键词</label>
          <input
            value={query}
            onChange={event => onQueryChange(event.target.value)}
            onKeyDown={event => { if (event.key === 'Enter') onSearch() }}
            className="w-full rounded border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
            placeholder={placeholder}
          />
        </div>
        <div className="flex gap-2">
          <button onClick={onSearch} className="rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800">
            查询
          </button>
          <button onClick={onClear} className="rounded border border-gray-300 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50">
            清除
          </button>
        </div>
      </div>
    </div>
  )
}

export default function PricingKbPage() {
  const [summary, setSummary] = useState<PricingKbSummary | null>(null)
  const [libraries, setLibraries] = useState<PricingKbLibrary[]>([])
  const [selectedLibraryId, setSelectedLibraryId] = useState<number | null>(null)
  const [tab, setTab] = useState<TabKey>('boq')
  const [error, setError] = useState('')

  const [boqItems, setBoqItems] = useState<PricingKbBoqItem[]>([])
  const [boqTotal, setBoqTotal] = useState(0)
  const [boqPage, setBoqPage] = useState(1)
  const [boqQueryInput, setBoqQueryInput] = useState('')
  const [boqCodeInput, setBoqCodeInput] = useState('')
  const [boqQuery, setBoqQuery] = useState('')
  const [boqCode, setBoqCode] = useState('')
  const [selectedBoqId, setSelectedBoqId] = useState<number | null>(null)
  const [candidateDetail, setCandidateDetail] = useState<PricingKbCandidateResponse | null>(null)
  const [candidateLoading, setCandidateLoading] = useState(false)

  const [quotaItems, setQuotaItems] = useState<PricingKbQuotaItem[]>([])
  const [quotaTotal, setQuotaTotal] = useState(0)
  const [quotaPage, setQuotaPage] = useState(1)
  const [quotaQueryInput, setQuotaQueryInput] = useState('')
  const [quotaCodeInput, setQuotaCodeInput] = useState('')
  const [quotaQuery, setQuotaQuery] = useState('')
  const [quotaCode, setQuotaCode] = useState('')

  const [runs, setRuns] = useState<PricingKbImportRun[]>([])
  const [issues, setIssues] = useState<PricingKbImportIssue[]>([])
  const [issueTotal, setIssueTotal] = useState(0)
  const [issuePage, setIssuePage] = useState(1)
  const [issueType, setIssueType] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    Promise.all([fetchPricingKbSummary(), fetchPricingKbLibraries()])
      .then(([summaryData, libraryData]) => {
        setSummary(summaryData)
        setLibraries(libraryData)
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : '加载知识库概览失败'))
  }, [])

  useEffect(() => {
    setBoqPage(1)
    setQuotaPage(1)
    setSelectedBoqId(null)
    setCandidateDetail(null)
  }, [selectedLibraryId])

  const loadBoqItems = useCallback(() => {
    setLoading(true)
    setError('')
    fetchPricingKbBoqItems({
      library_id: selectedLibraryId,
      q: boqQuery,
      code: boqCode,
      page: boqPage,
      page_size: PAGE_SIZE,
    })
      .then(data => {
        setBoqItems(data.items)
        setBoqTotal(data.total)
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : '加载清单项目失败'))
      .finally(() => setLoading(false))
  }, [boqCode, boqPage, boqQuery, selectedLibraryId])

  const loadQuotaItems = useCallback(() => {
    setLoading(true)
    setError('')
    fetchPricingKbQuotaItems({
      library_id: selectedLibraryId,
      q: quotaQuery,
      code: quotaCode,
      page: quotaPage,
      page_size: PAGE_SIZE,
    })
      .then(data => {
        setQuotaItems(data.items)
        setQuotaTotal(data.total)
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : '加载定额子目失败'))
      .finally(() => setLoading(false))
  }, [quotaCode, quotaPage, quotaQuery, selectedLibraryId])

  const loadIssues = useCallback(() => {
    Promise.all([
      fetchPricingKbImportRuns(1, 10),
      fetchPricingKbImportIssues({ issue_type: issueType, page: issuePage, page_size: PAGE_SIZE }),
    ])
      .then(([runData, issueData]) => {
        setRuns(runData.items)
        setIssues(issueData.items)
        setIssueTotal(issueData.total)
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : '加载导入问题失败'))
  }, [issuePage, issueType])

  useEffect(() => { if (tab === 'boq') loadBoqItems() }, [tab, loadBoqItems])
  useEffect(() => { if (tab === 'quota') loadQuotaItems() }, [tab, loadQuotaItems])
  useEffect(() => { if (tab === 'imports') loadIssues() }, [tab, loadIssues])

  function openCandidates(item: PricingKbBoqItem) {
    setSelectedBoqId(item.id)
    setCandidateDetail(null)
    if (!item.candidate_count) return
    setCandidateLoading(true)
    fetchPricingKbCandidates(item.id, item.source_library_id)
      .then(setCandidateDetail)
      .catch(reason => setError(reason instanceof Error ? reason.message : '加载候选定额失败'))
      .finally(() => setCandidateLoading(false))
  }

  const selectedLibrary = libraries.find(library => library.id === selectedLibraryId) ?? null
  const issueTypes = useMemo(() => Object.keys(summary?.issue_type_counts ?? {}), [summary])

  return (
    <div className="min-h-[calc(100vh-104px)] bg-gray-50">
      <div className="border-b border-gray-200 bg-white px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-gray-900">组价知识库</h1>
            <p className="mt-1 text-sm text-gray-500">SQLite 组价知识库只读检索，查看清单、定额、候选关系和链接状态。</p>
          </div>
          <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-500">
            {selectedLibrary ? `当前库：${selectedLibrary.source_library_id}` : '当前库：全部'}
          </div>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
          <StatCard label="标准库" value={fmt(summary?.library_count)} />
          <StatCard label="清单项目" value={fmt(summary?.boq_item_count)} hint={`有候选 ${fmt(summary?.boq_with_candidates)}`} />
          <StatCard label="定额子目" value={fmt(summary?.quota_item_count)} />
          <StatCard label="工料机" value={fmt(summary?.resource_count)} />
          <StatCard label="候选关系" value={fmt(summary?.candidate_count)} />
          <StatCard label="导入问题" value={fmt(summary?.issue_count)} />
        </div>
        {error && <div className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
      </div>

      <div className="grid min-h-[calc(100vh-260px)] lg:grid-cols-[300px_minmax(0,1fr)]">
        <LibrarySidebar libraries={libraries} selectedLibraryId={selectedLibraryId} onSelect={setSelectedLibraryId} />

        <main className="min-w-0 p-4 sm:p-5">
          <div className="mb-4 flex flex-wrap gap-2 border-b border-gray-200">
            {([
              ['boq', '清单项目'],
              ['quota', '定额子目'],
              ['imports', '导入与问题'],
            ] as const).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                className={`border-b-2 px-4 py-2 text-sm font-medium transition ${
                  tab === key
                    ? 'border-blue-700 text-blue-700'
                    : 'border-transparent text-gray-500 hover:text-gray-800'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === 'boq' && (
            <>
              <SearchBar
                query={boqQueryInput}
                code={boqCodeInput}
                onQueryChange={setBoqQueryInput}
                onCodeChange={setBoqCodeInput}
                onSearch={() => {
                  setBoqQuery(boqQueryInput.trim())
                  setBoqCode(boqCodeInput.trim())
                  setBoqPage(1)
                  setSelectedBoqId(null)
                  setCandidateDetail(null)
                }}
                onClear={() => {
                  setBoqQueryInput('')
                  setBoqCodeInput('')
                  setBoqQuery('')
                  setBoqCode('')
                  setBoqPage(1)
                }}
                placeholder="如 砌筑井、挖基坑土方"
              />
              <div className="overflow-hidden border border-gray-200 bg-white">
                <div className="flex items-center justify-between border-b border-gray-200 px-4 py-2.5 text-sm">
                  <div className="text-gray-500">共 <span className="font-semibold text-gray-900">{fmt(boqTotal)}</span> 条清单</div>
                  {loading && <div className="text-xs text-blue-600">加载中...</div>}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[920px] border-collapse text-sm">
                    <thead className="bg-gray-50 text-xs text-gray-600">
                      <tr>
                        <th className="px-4 py-2.5 text-left font-medium">库</th>
                        <th className="px-4 py-2.5 text-left font-medium">清单编码</th>
                        <th className="px-4 py-2.5 text-left font-medium">名称</th>
                        <th className="px-4 py-2.5 text-left font-medium">单位</th>
                        <th className="px-4 py-2.5 text-left font-medium">章节</th>
                        <th className="px-4 py-2.5 text-right font-medium">候选数</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {!loading && boqItems.length === 0 && (
                        <tr><td colSpan={6} className="px-4 py-12 text-center text-gray-400">暂无匹配清单</td></tr>
                      )}
                      {boqItems.map(item => (
                        <tr
                          key={item.id}
                          onClick={() => openCandidates(item)}
                          className={`cursor-pointer hover:bg-blue-50/40 ${selectedBoqId === item.id ? 'bg-blue-50' : ''}`}
                        >
                          <td className="px-4 py-2.5 text-xs text-gray-500">{item.source_library_id}</td>
                          <td className="px-4 py-2.5 font-mono font-semibold text-blue-700">{item.code ?? '-'}</td>
                          <td className="px-4 py-2.5 font-medium text-gray-900">{item.name}</td>
                          <td className="px-4 py-2.5 text-gray-500">{item.unit ?? '-'}</td>
                          <td className="px-4 py-2.5 text-xs text-gray-500">{item.chapter_name ?? '-'}</td>
                          <td className="px-4 py-2.5 text-right tabular-nums text-gray-800">{fmt(item.candidate_count)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Pagination page={boqPage} total={boqTotal} onPageChange={setBoqPage} />
              </div>
              <CandidatePanel
                detail={candidateDetail}
                loading={candidateLoading}
                onClose={() => {
                  setSelectedBoqId(null)
                  setCandidateDetail(null)
                }}
              />
            </>
          )}

          {tab === 'quota' && (
            <>
              <SearchBar
                query={quotaQueryInput}
                code={quotaCodeInput}
                onQueryChange={setQuotaQueryInput}
                onCodeChange={setQuotaCodeInput}
                onSearch={() => {
                  setQuotaQuery(quotaQueryInput.trim())
                  setQuotaCode(quotaCodeInput.trim())
                  setQuotaPage(1)
                }}
                onClear={() => {
                  setQuotaQueryInput('')
                  setQuotaCodeInput('')
                  setQuotaQuery('')
                  setQuotaCode('')
                  setQuotaPage(1)
                }}
                placeholder="如 混凝土输送泵、脚手架"
              />
              <div className="overflow-hidden border border-gray-200 bg-white">
                <div className="flex items-center justify-between border-b border-gray-200 px-4 py-2.5 text-sm">
                  <div className="text-gray-500">共 <span className="font-semibold text-gray-900">{fmt(quotaTotal)}</span> 条定额</div>
                  {loading && <div className="text-xs text-blue-600">加载中...</div>}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[980px] border-collapse text-sm">
                    <thead className="bg-gray-50 text-xs text-gray-600">
                      <tr>
                        <th className="px-4 py-2.5 text-left font-medium">库</th>
                        <th className="px-4 py-2.5 text-left font-medium">定额编号</th>
                        <th className="px-4 py-2.5 text-left font-medium">名称</th>
                        <th className="px-4 py-2.5 text-left font-medium">单位</th>
                        <th className="px-4 py-2.5 text-left font-medium">章节</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {!loading && quotaItems.length === 0 && (
                        <tr><td colSpan={5} className="px-4 py-12 text-center text-gray-400">暂无匹配定额</td></tr>
                      )}
                      {quotaItems.map(item => (
                        <tr key={item.id} className="hover:bg-blue-50/40">
                          <td className="px-4 py-2.5 text-xs text-gray-500">{item.source_library_id}</td>
                          <td className="px-4 py-2.5 font-mono font-semibold text-blue-700">{item.code ?? '-'}</td>
                          <td className="px-4 py-2.5 font-medium text-gray-900">{item.name}</td>
                          <td className="px-4 py-2.5 text-gray-500">{item.unit ?? '-'}</td>
                          <td className="px-4 py-2.5 text-xs text-gray-500">{item.chapter_name ?? '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Pagination page={quotaPage} total={quotaTotal} onPageChange={setQuotaPage} />
              </div>
            </>
          )}

          {tab === 'imports' && (
            <div className="space-y-4">
              <ImportManager onRefresh={loadIssues} />
              <div className="border border-gray-200 bg-white">
                <div className="border-b border-gray-200 px-4 py-2.5 text-sm font-semibold text-gray-900">最近导入批次</div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[900px] border-collapse text-sm">
                    <thead className="bg-gray-50 text-xs text-gray-600">
                      <tr>
                        <th className="px-4 py-2.5 text-left font-medium">批次</th>
                        <th className="px-4 py-2.5 text-left font-medium">状态</th>
                        <th className="px-4 py-2.5 text-left font-medium">来源</th>
                        <th className="px-4 py-2.5 text-left font-medium">完成时间</th>
                        <th className="px-4 py-2.5 text-left font-medium">统计摘要</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {runs.map(run => (
                        <tr key={run.id} className="hover:bg-gray-50">
                          <td className="px-4 py-2.5 font-mono text-gray-500">#{run.id}</td>
                          <td className="px-4 py-2.5"><StatusBadge status={run.status} /></td>
                          <td className="px-4 py-2.5 text-xs text-gray-500">{run.source_file}</td>
                          <td className="px-4 py-2.5 text-xs text-gray-500">{run.finished_at ? new Date(run.finished_at).toLocaleString('zh-CN') : '-'}</td>
                          <td className="px-4 py-2.5 text-xs text-gray-500">
                            <code className="line-clamp-2 break-all">{JSON.stringify(run.stats_json)}</code>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="border border-gray-200 bg-white">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-4 py-2.5">
                  <div className="text-sm font-semibold text-gray-900">导入问题</div>
                  <select
                    value={issueType}
                    onChange={event => {
                      setIssueType(event.target.value)
                      setIssuePage(1)
                    }}
                    className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700"
                  >
                    <option value="">全部问题类型</option>
                    {issueTypes.map(type => <option key={type} value={type}>{type}</option>)}
                  </select>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[900px] border-collapse text-sm">
                    <thead className="bg-gray-50 text-xs text-gray-600">
                      <tr>
                        <th className="px-4 py-2.5 text-left font-medium">级别</th>
                        <th className="px-4 py-2.5 text-left font-medium">类型</th>
                        <th className="px-4 py-2.5 text-left font-medium">消息</th>
                        <th className="px-4 py-2.5 text-left font-medium">来源表</th>
                        <th className="px-4 py-2.5 text-left font-medium">库</th>
                        <th className="px-4 py-2.5 text-left font-medium">记录</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {issues.map(issue => (
                        <tr key={issue.id} className="hover:bg-gray-50">
                          <td className="px-4 py-2.5"><StatusBadge status={issue.severity} /></td>
                          <td className="px-4 py-2.5 text-xs text-gray-700">{issue.issue_type}</td>
                          <td className="px-4 py-2.5 text-gray-700">{issue.message}</td>
                          <td className="px-4 py-2.5 text-xs text-gray-500">{issue.source_table ?? '-'}</td>
                          <td className="px-4 py-2.5 text-xs text-gray-500">{issue.source_library_id ?? '-'}</td>
                          <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{issue.source_record_id ?? '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Pagination page={issuePage} total={issueTotal} onPageChange={setIssuePage} />
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
