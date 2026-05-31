'use client'
import { useState, useEffect, Fragment, useCallback } from 'react'
import { fetchBoqSummary, BoqMatchResult, BoqSummaryItem, BoqResourceSummary, QuotaResource } from '@/lib/api'

// ── 工具函数 ──────────────────────────────────────────────────────────────────

export function fmt(v: number | null | undefined, digits = 2) {
  if (v == null) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

// ── 定额子目详情弹窗 ──────────────────────────────────────────────────────────

function QuotaDetailModal({ match, onClose }: { match: BoqMatchResult; onClose: () => void }) {
  // 点遮罩关闭
  const onBackdrop = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose()
  }, [onClose])

  // ESC 关闭
  useEffect(() => {
    const fn = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', fn)
    return () => window.removeEventListener('keydown', fn)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      onClick={onBackdrop}
    >
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col">
        {/* 标题栏 */}
        <div className="flex items-start gap-3 px-5 py-4 border-b">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-blue-600 font-semibold text-base">{match.quota_item_code}</span>
              <span className="font-semibold text-gray-800">{match.quota_item_name}</span>
              {match.quota_variant_desc && (
                <span className="text-gray-500 text-sm">（{match.quota_variant_desc}）</span>
              )}
            </div>
            <div className="text-xs text-gray-400 mt-0.5">计量单位：{match.quota_unit ?? '—'}</div>
          </div>
          <button onClick={onClose} className="shrink-0 text-gray-400 hover:text-gray-600 text-xl leading-none">✕</button>
        </div>

        {/* 内容区（可滚动）*/}
        <div className="overflow-y-auto flex-1 px-5 py-4 space-y-4">

          {/* 工作内容 */}
          {match.quota_work_content && (
            <div>
              <div className="text-xs font-medium text-gray-500 mb-1">工作内容</div>
              <div className="text-sm text-gray-700 leading-relaxed">
                {match.quota_work_content.replace(/单位\s*[：:].+$/, '').trim()}
              </div>
            </div>
          )}

          {/* 价格构成 */}
          {match.quota_total_unit_price != null && (
            <div>
              <div className="text-xs font-medium text-gray-500 mb-2">价格构成（元 / {match.quota_unit ?? '—'}）</div>
              <div className="grid grid-cols-2 gap-2 mb-2">
                <div className="rounded-lg p-3 bg-blue-50 border border-blue-100 text-center">
                  <div className="text-xs text-gray-400 mb-0.5">全费用综合单价</div>
                  <div className="text-lg font-bold text-blue-700 tabular-nums">{fmt(match.quota_total_unit_price)}</div>
                </div>
                <div className="rounded-lg p-3 bg-gray-50 text-center">
                  <div className="text-xs text-gray-400 mb-0.5">综合单价</div>
                  <div className="text-lg font-bold text-gray-700 tabular-nums">{fmt(match.quota_unit_price)}</div>
                </div>
              </div>
              <div className="grid grid-cols-5 gap-1.5 mb-1.5">
                {[
                  ['人工费', match.quota_labor_cost],
                  ['材料费', match.quota_material_cost],
                  ['机械费', match.quota_machine_cost],
                  ['管理费', match.quota_management_fee],
                  ['利润',   match.quota_profit],
                ].map(([label, value]) => (
                  <div key={label as string} className="rounded p-2 bg-gray-50 text-center">
                    <div className="text-xs text-gray-400 mb-0.5">{label}</div>
                    <div className="text-sm font-semibold text-gray-700 tabular-nums">{fmt(value as number | null)}</div>
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-3 gap-1.5">
                {[
                  ['安全文明措施费', match.quota_safety_fee],
                  ['规费',         match.quota_statutory_fee],
                  ['税金',         match.quota_tax],
                ].map(([label, value]) => (
                  <div key={label as string} className="rounded p-2 bg-gray-50 text-center">
                    <div className="text-xs text-gray-400 mb-0.5">{label}</div>
                    <div className="text-sm font-semibold text-gray-700 tabular-nums">{fmt(value as number | null)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 工料机消耗量 */}
          {match.quota_resources.length > 0 && (
            <div>
              <div className="text-xs font-medium text-gray-500 mb-2">工料机消耗量</div>
              {(['人工', '材料', '机械'] as const).map(type => {
                const rows = match.quota_resources.filter(r => r.resource_type === type)
                if (!rows.length) return null
                const colors: Record<string, string> = {
                  人工: 'text-orange-700 bg-orange-50 border-orange-200',
                  材料: 'text-green-700 bg-green-50 border-green-200',
                  机械: 'text-purple-700 bg-purple-50 border-purple-200',
                }
                return (
                  <div key={type} className="mb-3">
                    <span className={`inline-block text-xs font-medium px-1.5 py-0.5 rounded border mb-1.5 ${colors[type]}`}>{type}</span>
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-gray-400 border-b border-gray-100">
                          <th className="text-left pb-1 font-normal pr-2">名称</th>
                          <th className="text-left pb-1 font-normal w-12">单位</th>
                          <th className="text-right pb-1 font-normal w-20">消耗量</th>
                          <th className="text-right pb-1 font-normal w-24">参考价（元）</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map(r => (
                          <tr key={r.id} className="border-b border-gray-50 last:border-0">
                            <td className="py-1 pr-2 text-gray-700">{r.resource_name}</td>
                            <td className="py-1 text-gray-500">{r.unit ?? '—'}</td>
                            <td className="py-1 text-right text-gray-800 tabular-nums">
                              {r.quantity?.toLocaleString('zh-CN', { maximumFractionDigits: 4 }) ?? '—'}
                            </td>
                            <td className="py-1 text-right text-gray-600 tabular-nums">{fmt(r.ref_price)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── 标签组件 ──────────────────────────────────────────────────────────────────

export function ConfBadge({ c }: { c: string | null }) {
  const map: Record<string, string> = {
    high: 'bg-green-100 text-green-700 border-green-200',
    medium: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    low: 'bg-red-100 text-red-700 border-red-200',
  }
  const label: Record<string, string> = { high: '高', medium: '中', low: '低' }
  const cls = map[c ?? ''] ?? 'bg-gray-100 text-gray-500 border-gray-200'
  return <span className={`text-xs border px-1.5 py-0.5 rounded ${cls}`}>{label[c ?? ''] ?? c}</span>
}

export function StatusBadge({ s }: { s: string }) {
  const map: Record<string, string> = {
    ai: 'bg-blue-100 text-blue-700',
    confirmed: 'bg-green-100 text-green-700',
    rejected: 'bg-red-100 text-red-600 line-through',
  }
  const label: Record<string, string> = { ai: 'AI建议', confirmed: '已确认', rejected: '已拒绝' }
  return <span className={`text-xs px-1.5 py-0.5 rounded ${map[s] ?? ''}`}>{label[s] ?? s}</span>
}

// ── 价格卡片 ──────────────────────────────────────────────────────────────────

export function PriceCard({ label, value, hi }: { label: string; value: number | null | undefined; hi?: boolean }) {
  return (
    <div className={`rounded p-2 text-center ${hi ? 'bg-blue-50 border border-blue-200' : 'bg-gray-50'}`}>
      <div className="text-xs text-gray-400 mb-0.5 leading-none">{label}</div>
      <div className={`text-sm font-semibold tabular-nums ${hi ? 'text-blue-700' : 'text-gray-700'}`}>
        {value != null ? value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : <span className="text-gray-300 font-normal">—</span>}
      </div>
    </div>
  )
}

// ── 工料机表 ──────────────────────────────────────────────────────────────────

export function ResTable({ resources, type }: { resources: QuotaResource[]; type: string }) {
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
          <th className="text-left pb-0.5 font-normal w-12">单位</th>
          <th className="text-right pb-0.5 font-normal w-16">消耗量</th>
          <th className="text-right pb-0.5 font-normal w-20">参考价（元）</th>
        </tr></thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.id} className="border-b border-gray-50 last:border-0">
              <td className="py-0.5 pr-2 text-gray-700 leading-snug">{r.resource_name}</td>
              <td className="py-0.5 text-gray-500">{r.unit ?? '—'}</td>
              <td className="py-0.5 text-right text-gray-800 tabular-nums">
                {r.quantity != null ? r.quantity.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 4 }) : '—'}
              </td>
              <td className="py-0.5 text-right text-gray-600 tabular-nums">
                {r.ref_price != null ? r.ref_price.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── 单条匹配卡片（可展开）────────────────────────────────────────────────────

export function MatchCard({
  m, onConfirm, onReject, onDelete,
}: {
  m: BoqMatchResult
  onConfirm: (id: number) => void
  onReject: (id: number) => void
  onDelete: (id: number) => void
}) {
  const [open, setOpen] = useState(false)
  const hasDetail = !!(m.reasoning_chain || m.quota_work_content || m.quota_total_unit_price != null || m.quota_resources.length > 0)

  return (
    <div className={`rounded border text-xs ${
      m.status === 'rejected' ? 'border-red-100 bg-red-50/50 opacity-60' :
      m.status === 'confirmed' ? 'border-green-200 bg-green-50/50' :
      'border-gray-200 bg-gray-50'
    }`}>
      <div
        className={`flex items-center gap-1.5 px-2.5 py-2 flex-wrap ${hasDetail ? 'cursor-pointer hover:bg-black/5' : ''}`}
        onClick={() => hasDetail && setOpen(o => !o)}
      >
        <span className="font-mono text-blue-600 font-medium shrink-0">{m.quota_item_code}</span>
        <span className="text-gray-800 font-medium">{m.quota_item_name}</span>
        {m.quota_variant_desc && <span className="text-gray-500">（{m.quota_variant_desc}）</span>}
        {m.quota_unit && <span className="text-gray-400 shrink-0">{m.quota_unit}</span>}
        {m.qty_factor !== 1 && <span className="text-orange-600 shrink-0 font-medium">×{m.qty_factor}</span>}
        <div className="ml-auto flex items-center gap-1.5 shrink-0">
          <ConfBadge c={m.confidence} />
          <StatusBadge s={m.status} />
          {hasDetail && <span className="text-gray-400 select-none">{open ? '▲' : '▼'}</span>}
        </div>
      </div>

      {open && (
        <div className="px-2.5 pb-2.5 border-t border-gray-100 space-y-3 pt-2.5">
          {/* 施工工序 + 换算说明 */}
          {(m.work_procedure || m.factor_explanation) && (
            <div className="flex flex-wrap gap-3 text-xs">
              {m.work_procedure && (
                <span className="flex items-center gap-1 text-gray-600">
                  <span>🔨</span>
                  <span className="font-medium">施工工序：</span>
                  <span>{m.work_procedure}</span>
                </span>
              )}
              {m.factor_explanation && (
                <span className="flex items-center gap-1 text-gray-500">
                  <span>📐</span>
                  <span className="font-medium">换算说明：</span>
                  <span>{m.factor_explanation}</span>
                </span>
              )}
            </div>
          )}

          {m.reasoning_chain && (
            <div>
              <div className="text-xs font-medium text-indigo-700 mb-1">🧠 AI 推理过程</div>
              <div className="text-xs text-gray-600 leading-relaxed bg-indigo-50/60 rounded p-2 whitespace-pre-wrap max-h-48 overflow-y-auto">
                {m.reasoning_chain}
              </div>
            </div>
          )}
          {!m.reasoning_chain && m.ai_reasoning && (
            <div>
              <div className="text-xs font-medium text-gray-600 mb-0.5">匹配理由</div>
              <div className="text-xs text-gray-600 leading-relaxed">{m.ai_reasoning}</div>
            </div>
          )}
          {m.quota_work_content && (
            <div>
              <div className="text-xs font-medium text-gray-600 mb-0.5">📋 定额工作内容</div>
              <div className="text-xs text-gray-500 leading-relaxed">
                {m.quota_work_content.replace(/单位\s*[：:].+$/, '').trim()}
              </div>
            </div>
          )}
          {m.quota_total_unit_price != null && (
            <div>
              <div className="text-xs font-medium text-gray-600 mb-1.5">💰 价格构成（元 / {m.quota_unit ?? '—'}）</div>
              <div className="grid grid-cols-2 gap-1.5 mb-1.5">
                <PriceCard label="全费用综合单价" value={m.quota_total_unit_price} hi />
                <PriceCard label="综合单价" value={m.quota_unit_price} />
              </div>
              <div className="grid grid-cols-5 gap-1.5 mb-1.5">
                <PriceCard label="人工费" value={m.quota_labor_cost} />
                <PriceCard label="材料费" value={m.quota_material_cost} />
                <PriceCard label="机械费" value={m.quota_machine_cost} />
                <PriceCard label="管理费" value={m.quota_management_fee} />
                <PriceCard label="利润" value={m.quota_profit} />
              </div>
              <div className="grid grid-cols-3 gap-1.5">
                <PriceCard label="安全文明措施费" value={m.quota_safety_fee} />
                <PriceCard label="规费" value={m.quota_statutory_fee} />
                <PriceCard label="税金" value={m.quota_tax} />
              </div>
            </div>
          )}
          {m.quota_resources.length > 0 && (
            <div>
              <div className="text-xs font-medium text-gray-600 mb-1.5">🔧 工料机消耗量</div>
              <ResTable resources={m.quota_resources} type="人工" />
              <ResTable resources={m.quota_resources} type="材料" />
              <ResTable resources={m.quota_resources} type="机械" />
            </div>
          )}
        </div>
      )}

      <div className={`flex gap-1.5 px-2.5 py-1.5 ${open ? 'border-t border-gray-100' : ''}`}>
        {m.status !== 'confirmed' && (
          <button onClick={() => onConfirm(m.id)} className="px-2 py-0.5 rounded text-xs bg-green-600 text-white hover:bg-green-700">确认</button>
        )}
        {m.status !== 'rejected' && (
          <button onClick={() => onReject(m.id)} className="px-2 py-0.5 rounded text-xs border border-red-300 text-red-600 hover:bg-red-50">拒绝</button>
        )}
        <button onClick={() => onDelete(m.id)} className="px-2 py-0.5 rounded text-xs border text-gray-400 hover:bg-gray-100 ml-auto">删除</button>
      </div>
    </div>
  )
}

// ── 项目特征展示 ──────────────────────────────────────────────────────────────

export function DescBlock({ text }: { text: string }) {
  return (
    <div className="text-xs text-gray-500 space-y-0.5 leading-relaxed">
      {text.split('\n').filter(Boolean).map((l, i) => <div key={i}>{l}</div>)}
    </div>
  )
}

// ── 造价汇总面板 ──────────────────────────────────────────────────────────────

export function SummaryPanel({ runId, matches = [] }: { runId: number; matches?: BoqMatchResult[] }) {
  const [data, setData] = useState<{ items: BoqSummaryItem[]; resources: BoqResourceSummary[] } | null>(null)
  const [loading, setLoading] = useState(false)
  const [tab, setTab] = useState<'items' | 'labor' | 'material' | 'machine'>('items')
  const [expandedItemId, setExpandedItemId] = useState<number | null>(null)
  const [modalMatch, setModalMatch] = useState<BoqMatchResult | null>(null)

  useEffect(() => {
    setLoading(true)
    fetchBoqSummary(runId).then(setData).finally(() => setLoading(false))
  }, [runId])

  if (loading) return <div className="py-8 text-center text-gray-400 animate-pulse">计算中…</div>
  if (!data) return null

  const totalPrice = data.items.reduce((s, it) => s + (it.total_price ?? 0), 0)
  const resOfType = (t: string) => data.resources.filter(r => r.resource_type === t)
  const resTotal = (t: string) => resOfType(t).length

  // 按 boq_item_id 分组匹配结果（用于展示计算明细）
  const matchesByItem = new Map<number, BoqMatchResult[]>()
  for (const m of matches) {
    if (!matchesByItem.has(m.boq_item_id)) matchesByItem.set(m.boq_item_id, [])
    matchesByItem.get(m.boq_item_id)!.push(m)
  }

  const tabs = [
    { key: 'items' as const, label: `综合单价（${data.items.length}条）` },
    { key: 'labor' as const, label: `人工（${resTotal('人工')}种）` },
    { key: 'material' as const, label: `材料（${resTotal('材料')}种）` },
    { key: 'machine' as const, label: `机械（${resTotal('机械')}种）` },
  ]

  return (
    <>
      {modalMatch && <QuotaDetailModal match={modalMatch} onClose={() => setModalMatch(null)} />}
    <div>
      <div className="flex items-center gap-4 mb-4">
        <span className="text-sm text-gray-500">工程造价合计：</span>
        <span className="text-2xl font-bold text-blue-700">{fmt(totalPrice)} 元</span>
      </div>
      <div className="flex gap-1 border-b mb-4">
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-3 py-1.5 text-sm rounded-t border-b-2 -mb-px transition-colors ${
              tab === t.key ? 'border-blue-600 text-blue-700 font-medium' : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}>{t.label}</button>
        ))}
      </div>
      {tab === 'items' && (
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-gray-50 text-gray-500">
              <th className="text-left px-2 py-2 font-normal border-b w-8">序</th>
              <th className="text-left px-2 py-2 font-normal border-b">项目名称</th>
              <th className="text-left px-2 py-2 font-normal border-b w-12">单位</th>
              <th className="text-right px-2 py-2 font-normal border-b w-20">工程量</th>
              <th className="text-right px-2 py-2 font-normal border-b w-24">综合单价</th>
              <th className="text-right px-2 py-2 font-normal border-b w-24">合价（元）</th>
              <th className="text-center px-2 py-2 font-normal border-b w-8"></th>
            </tr>
          </thead>
          <tbody>
            {data.items.map(it => {
              const itemMatches = matchesByItem.get(it.boq_item_id) ?? []
              const open = expandedItemId === it.boq_item_id
              return (
                <Fragment key={it.boq_item_id}>
                  <tr
                    className={`border-b border-gray-50 ${itemMatches.length > 0 ? 'cursor-pointer hover:bg-gray-50' : ''} ${open ? 'bg-blue-50/40' : ''}`}
                    onClick={() => itemMatches.length > 0 && setExpandedItemId(open ? null : it.boq_item_id)}
                  >
                    <td className="px-2 py-1.5 text-gray-400 tabular-nums">{it.item_seq}</td>
                    <td className="px-2 py-1.5 text-gray-800">{it.item_name}</td>
                    <td className="px-2 py-1.5 text-gray-500">{it.unit ?? '—'}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{fmt(it.quantity, 4)}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums text-blue-700 font-medium">{fmt(it.unit_price, 2)}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums font-semibold">{fmt(it.total_price)}</td>
                    <td className="px-2 py-1.5 text-center text-gray-400 select-none">
                      {itemMatches.length > 0 ? (open ? '▲' : '▼') : ''}
                    </td>
                  </tr>

                  {open && itemMatches.length > 0 && (
                    <tr>
                      <td colSpan={7} className="px-0 pb-2 bg-blue-50/30">
                        <div className="mx-2 mt-1 border border-blue-100 rounded overflow-hidden">
                          {/* 计算公式说明 */}
                          <div className="px-3 py-2 bg-blue-50 border-b border-blue-100 text-xs text-blue-700 font-medium">
                            📐 综合单价计算：Σ（定额全费用综合单价 × 换算系数）= {fmt(it.unit_price, 4)} 元/{it.unit}
                          </div>
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="bg-gray-50 text-gray-400 border-b border-gray-100">
                                <th className="text-left px-3 py-1.5 font-normal">定额子目</th>
                                <th className="text-left px-2 py-1.5 font-normal w-14">单位</th>
                                <th className="text-right px-2 py-1.5 font-normal w-28">全费用综合单价</th>
                                <th className="text-right px-2 py-1.5 font-normal w-16">换算系数</th>
                                <th className="text-right px-2 py-1.5 font-normal w-28">折算单价</th>
                              </tr>
                            </thead>
                            <tbody>
                              {itemMatches.map(m => {
                                const unitPrice = m.quota_total_unit_price ?? 0
                                const converted = unitPrice * m.qty_factor
                                return (
                                  <tr key={m.id} className="border-b border-gray-50 last:border-0">
                                    <td className="px-3 py-1.5">
                                      <button
                                        onClick={e => { e.stopPropagation(); setModalMatch(m) }}
                                        className="font-mono text-blue-600 hover:text-blue-800 hover:underline mr-1.5 cursor-pointer"
                                      >{m.quota_item_code}</button>
                                      <span className="text-gray-700">{m.quota_item_name}</span>
                                      {m.quota_variant_desc && <span className="text-gray-400 ml-1">（{m.quota_variant_desc}）</span>}
                                    </td>
                                    <td className="px-2 py-1.5 text-gray-500">{m.quota_unit ?? '—'}</td>
                                    <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">{fmt(unitPrice, 2)}</td>
                                    <td className="px-2 py-1.5 text-right tabular-nums text-orange-600">
                                      {m.qty_factor === 1 ? <span className="text-gray-400">×1</span> : `×${m.qty_factor}`}
                                    </td>
                                    <td className="px-2 py-1.5 text-right tabular-nums font-medium text-blue-700">
                                      {fmt(converted, 4)}
                                    </td>
                                  </tr>
                                )
                              })}
                            </tbody>
                            {itemMatches.length > 1 && (
                              <tfoot>
                                <tr className="bg-gray-50">
                                  <td colSpan={4} className="px-3 py-1.5 text-right text-gray-500">合计</td>
                                  <td className="px-2 py-1.5 text-right tabular-nums font-semibold text-blue-700">
                                    {fmt(itemMatches.reduce((s, m) => s + (m.quota_total_unit_price ?? 0) * m.qty_factor, 0), 4)}
                                  </td>
                                </tr>
                              </tfoot>
                            )}
                          </table>
                          {/* 合价计算 */}
                          <div className="px-3 py-2 bg-gray-50 border-t border-gray-100 text-xs text-gray-500">
                            合价 = {fmt(it.unit_price, 4)} × {fmt(it.quantity, 4)} = <span className="font-semibold text-gray-700">{fmt(it.total_price)} 元</span>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
          <tfoot>
            <tr className="bg-gray-50 font-semibold">
              <td colSpan={5} className="px-2 py-2 text-right text-gray-600">合计</td>
              <td className="px-2 py-2 text-right text-blue-700 tabular-nums">{fmt(totalPrice)}</td>
              <td />
            </tr>
          </tfoot>
        </table>
      )}
      {(tab === 'labor' || tab === 'material' || tab === 'machine') && (() => {
        const typeMap: Record<string, string> = { labor: '人工', material: '材料', machine: '机械' }
        const rows = resOfType(typeMap[tab])
        return rows.length === 0 ? (
          <div className="py-8 text-center text-gray-400">暂无数据</div>
        ) : (
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="bg-gray-50 text-gray-500">
                <th className="text-left px-2 py-2 font-normal border-b">名称</th>
                <th className="text-left px-2 py-2 font-normal border-b w-16">单位</th>
                <th className="text-right px-2 py-2 font-normal border-b w-28">总消耗量</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {rows.map((r, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-2 py-1.5 text-gray-800">{r.resource_name}</td>
                  <td className="px-2 py-1.5 text-gray-500">{r.unit ?? '—'}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums font-medium">{fmt(r.total_quantity, 4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      })()}
    </div>
    </>
  )
}
