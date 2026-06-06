'use client'

import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  fetchQuota2024Standards,
  fetchQuota2024Chapters,
  fetchQuota2024ChapterSections,
  fetchQuota2024Groups,
  fetchQuota2024Items,
  Quota2024Standard,
  Quota2024Chapter,
  Quota2024Section,
  Quota2024Group,
  Quota2024Item,
  Quota2024SubItem,
  Quota2024Resource,
} from '@/lib/api'

// ── 工具函数 ──────────────────────────────────────────────────────────────

function fmt(v: number | null | undefined) {
  if (v == null) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ── 价格卡片 ──────────────────────────────────────────────────────────────

function PriceCard({ label, value, hi }: { label: string; value: number | null; hi?: boolean }) {
  return (
    <div className={`rounded p-2 text-center ${hi ? 'bg-amber-50 border border-amber-200' : 'bg-gray-50'}`}>
      <div className="text-xs text-gray-400 mb-0.5 leading-none">{label}</div>
      <div className={`text-sm font-semibold tabular-nums ${hi ? 'text-amber-700' : 'text-gray-700'}`}>
        {value != null ? fmt(value) : <span className="text-gray-300 font-normal">—</span>}
      </div>
    </div>
  )
}

// ── 工料机表 ──────────────────────────────────────────────────────────────

interface ResTableProps {
  resources: Quota2024Resource[]
  type: string
  subitems: Quota2024SubItem[]
}

function ResTable({ resources, type, subitems }: ResTableProps) {
  const filtered = resources.filter(r => r.resource_type === type)
  if (!filtered.length) return null

  const colors: Record<string, string> = {
    人工: 'text-orange-700 bg-orange-50 border-orange-200',
    材料: 'text-green-700 bg-green-50 border-green-200',
    机械: 'text-purple-700 bg-purple-50 border-purple-200',
  }

  return (
    <div className="mb-4">
      <div className={`inline-block text-xs font-medium px-2 py-1 rounded border mb-2 ${colors[type] ?? 'text-gray-600 bg-gray-50 border-gray-200'}`}>
        {type}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-2 py-1 font-medium text-gray-600">名称</th>
              <th className="text-left px-2 py-1 font-medium text-gray-600 w-16">单位</th>
              {subitems.map((sub) => (
                <th key={sub.id} className="text-center px-2 py-1 font-medium text-gray-600 min-w-20">
                  {sub.subitem_code}
                </th>
              ))}
              <th className="text-right px-2 py-1 font-medium text-gray-600 w-28">参考价(元)</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((res, idx) => (
              <tr key={res.id} className={`border-b border-gray-100 ${idx % 2 === 0 ? 'bg-white' : 'bg-gray-50/30'}`}>
                <td className="px-2 py-1 text-gray-700">{res.resource_name}</td>
                <td className="px-2 py-1 text-gray-500">{res.unit ?? '—'}</td>
                {subitems.map((sub) => (
                  <td key={sub.id} className="px-2 py-1 text-center text-gray-800 tabular-nums">
                    {sub.id === 0 ? '—' : '—'}
                  </td>
                ))}
                <td className="px-2 py-1 text-right text-gray-600 tabular-nums font-medium">{fmt(res.ref_price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── 价格网格 ──────────────────────────────────────────────────────────────

function PriceGrid({ item }: { item: Quota2024Item }) {
  if (!item.subitems.length) return null

  const sub = item.subitems[0]
  return (
    <div className="mb-4">
      <div className="text-sm font-medium text-gray-700 mb-2">价格构成（元/{item.unit ?? '—'}）</div>

      {/* 全费用综合单价 */}
      <div className="mb-3 p-3 bg-amber-50 border border-amber-200 rounded">
        <div className="text-xs text-amber-600 mb-1">2023年8月全费用参考综合单价</div>
        <div className="text-xl font-bold text-amber-900 tabular-nums">{fmt(sub.total_unit_price)}</div>
      </div>

      {/* 分项费用 */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        <PriceCard label="参考综合单价" value={sub.unit_price} />
        <PriceCard label="— 人工费" value={sub.labor_cost} />
      </div>

      <div className="grid grid-cols-2 gap-2 mb-3">
        <PriceCard label="— 材料费" value={sub.material_cost} />
        <PriceCard label="— 机械费" value={sub.machine_cost} />
      </div>

      <div className="grid grid-cols-2 gap-2 mb-3">
        <PriceCard label="— 管理费" value={sub.management_fee} />
        <PriceCard label="— 利润" value={sub.profit} />
      </div>

      <div className="grid grid-cols-3 gap-2">
        <PriceCard label="安全文明措施费" value={sub.safety_fee} />
        <PriceCard label="规费" value={sub.statutory_fee} />
        <PriceCard label="税金" value={sub.tax} />
      </div>
    </div>
  )
}

// ── Markdown 渲染 ────────────────────────────────────────────────────────

function MarkdownView({ content }: { content: string | null }) {
  if (!content) return <div className="text-gray-400 text-sm">无内容</div>

  return (
    <div className="prose prose-sm max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          table: ({ node, ...props }) => (
            <table className="w-full border-collapse text-xs my-3" {...props} />
          ),
          th: ({ node, ...props }) => (
            <th className="border border-gray-300 bg-gray-100 px-2 py-1 text-left font-medium" {...props} />
          ),
          td: ({ node, ...props }) => (
            <td className="border border-gray-300 px-2 py-1" {...props} />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────────

export default function Quota2024Page() {
  const [standards, setStandards] = useState<Quota2024Standard[]>([])
  const [selectedStandard, setSelectedStandard] = useState<Quota2024Standard | null>(null)
  const [chapters, setChapters] = useState<Quota2024Chapter[]>([])
  const [selectedChapter, setSelectedChapter] = useState<Quota2024Chapter | null>(null)
  const [sections, setSections] = useState<Quota2024Section[]>([])
  const [activeTab, setActiveTab] = useState<'intro' | 'rules' | 'items'>('intro')
  const [groups, setGroups] = useState<Quota2024Group[]>([])
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set())
  const [loading, setLoading] = useState(false)

  // 加载标准
  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        const data = await fetchQuota2024Standards()
        setStandards(data)
        if (data.length > 0) {
          setSelectedStandard(data[0])
        }
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  // 加载章
  useEffect(() => {
    if (!selectedStandard) return
    async function load() {
      setLoading(true)
      try {
        const data = await fetchQuota2024Chapters(selectedStandard.id)
        setChapters(data)
        if (data.length > 0) {
          setSelectedChapter(data[0])
        }
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [selectedStandard])

  // 加载节
  useEffect(() => {
    if (!selectedChapter) return
    async function load() {
      setLoading(true)
      try {
        const detail = await fetchQuota2024ChapterSections(selectedChapter.id)
        setSections(detail.sections)
        setActiveTab('intro')
        setGroups([])
        setExpandedGroups(new Set())
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [selectedChapter])

  // 加载分组（切换到 items 标签时）
  async function loadGroups() {
    const itemsSection = sections.find(s => s.section_type === 'items')
    if (!itemsSection) return

    setLoading(true)
    try {
      const data = await fetchQuota2024Groups(itemsSection.id)
      setGroups(data)
    } finally {
      setLoading(false)
    }
  }

  function handleTabClick(tab: 'intro' | 'rules' | 'items') {
    setActiveTab(tab)
    if (tab === 'items' && groups.length === 0) {
      loadGroups()
    }
  }

  function toggleGroup(groupId: number) {
    const next = new Set(expandedGroups)
    if (next.has(groupId)) {
      next.delete(groupId)
    } else {
      next.add(groupId)
    }
    setExpandedGroups(next)
  }

  const currentSection = sections.find(s => s.section_type === activeTab)

  return (
    <div className="flex flex-col min-h-screen bg-gray-50">
      {/* 标题和标准选择 */}
      <div className="bg-white border-b border-gray-200 p-4">
        <h1 className="text-xl font-bold text-gray-900 mb-3">消耗量标准 2024</h1>

        <div className="flex gap-3">
          <label className="text-sm text-gray-600 flex items-center">
            标准：
            <select
              value={selectedStandard?.id ?? ''}
              onChange={(e) => {
                const std = standards.find(s => s.id === parseInt(e.target.value))
                if (std) setSelectedStandard(std)
              }}
              className="ml-2 px-3 py-1.5 border border-gray-300 rounded text-sm"
            >
              {standards.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.standard_code} - {s.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className="flex flex-1">
        {/* 左侧导航栏 */}
        <div className="w-56 bg-white border-r border-gray-200 overflow-y-auto">
          {chapters.map((ch) => (
            <div key={ch.id}>
              <button
                onClick={() => setSelectedChapter(ch)}
                className={`w-full text-left px-4 py-2.5 text-sm font-medium transition-colors ${
                  selectedChapter?.id === ch.id
                    ? 'bg-blue-50 text-blue-700 border-l-2 border-blue-700'
                    : 'text-gray-700 hover:bg-gray-50'
                }`}
              >
                第{ch.chapter_no}章 {ch.name}
              </button>

              {/* 三个节的链接 */}
              {selectedChapter?.id === ch.id && (
                <div className="bg-gray-50 px-4 py-1">
                  {['说明', '工程量计算规则', '子目构成表'].map((label, idx) => {
                    const tabType = idx === 0 ? 'intro' : idx === 1 ? 'rules' : 'items'
                    return (
                      <button
                        key={label}
                        onClick={() => handleTabClick(tabType as 'intro' | 'rules' | 'items')}
                        className={`block w-full text-left px-3 py-1.5 text-xs my-0.5 rounded ${
                          activeTab === tabType
                            ? 'bg-blue-100 text-blue-700 font-medium'
                            : 'text-gray-600 hover:bg-gray-200'
                        }`}
                      >
                        • {label}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* 主内容区 */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* 标签栏 */}
          <div className="bg-white border-b border-gray-200 px-6 py-0 flex gap-6">
            {(['intro', 'rules', 'items'] as const).map((tab, idx) => {
              const labels = ['说明', '工程量计算规则', '子目构成表']
              return (
                <button
                  key={tab}
                  onClick={() => handleTabClick(tab)}
                  className={`px-1 py-3 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === tab
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-600 hover:text-gray-900'
                  }`}
                >
                  {labels[idx]}
                </button>
              )
            })}
          </div>

          {/* 内容区 */}
          <div className="flex-1 overflow-y-auto p-6">
            {loading && <div className="text-gray-400">加载中...</div>}

            {activeTab === 'intro' && !loading && (
              <MarkdownView content={currentSection?.content_md ?? null} />
            )}

            {activeTab === 'rules' && !loading && (
              <MarkdownView content={currentSection?.content_md ?? null} />
            )}

            {activeTab === 'items' && !loading && (
              <div>
                {groups.length === 0 ? (
                  <div className="text-gray-400">无数据</div>
                ) : (
                  groups.map((group) => (
                    <div key={group.id} className="mb-6">
                      {/* 分组标题 */}
                      <button
                        onClick={() => toggleGroup(group.id)}
                        className="w-full text-left px-4 py-3 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition"
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-lg">{expandedGroups.has(group.id) ? '▼' : '▶'}</span>
                          <span className="font-semibold text-gray-900">
                            {group.group_code} {group.group_name}
                          </span>
                          <span className="text-xs text-gray-500 ml-2">({group.items.length} 项)</span>
                        </div>
                      </button>

                      {/* 展开的项目列表 */}
                      {expandedGroups.has(group.id) && (
                        <div className="ml-4 mt-3 space-y-4">
                          {group.items.map((item) => (
                            <div
                              key={item.id}
                              className="p-4 bg-white border border-gray-200 rounded-lg"
                            >
                              {/* 项目标题 */}
                              <div className="mb-3 pb-3 border-b border-gray-100">
                                <div className="text-base font-semibold text-gray-900">
                                  {item.item_no}. {item.item_name}
                                </div>
                                {item.work_content && (
                                  <div className="text-xs text-gray-600 mt-1">
                                    <span className="font-medium">工作内容：</span>
                                    {item.work_content}
                                  </div>
                                )}
                                {item.unit && (
                                  <div className="text-xs text-gray-600 mt-1">
                                    <span className="font-medium">计量单位：</span>
                                    {item.unit}
                                  </div>
                                )}
                              </div>

                              {/* 子目内容 */}
                              {item.subitems.length > 0 && (
                                <div>
                                  <PriceGrid item={item} />

                                  {item.subitems[0]?.resources && item.subitems[0].resources.length > 0 && (
                                    <div className="mt-4 pt-4 border-t border-gray-100">
                                      <div className="text-sm font-medium text-gray-700 mb-3">
                                        工料机消耗量（基准：2023年8月）
                                      </div>
                                      <ResTable
                                        resources={item.subitems[0].resources}
                                        type="人工"
                                        subitems={item.subitems}
                                      />
                                      <ResTable
                                        resources={item.subitems[0].resources}
                                        type="材料"
                                        subitems={item.subitems}
                                      />
                                      <ResTable
                                        resources={item.subitems[0].resources}
                                        type="机械"
                                        subitems={item.subitems}
                                      />
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
