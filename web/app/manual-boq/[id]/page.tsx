'use client'
import { useState, useEffect, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  fetchManualBoqProject, ManualBoqProjectDetail, ManualBoqItem, ManualBoqQuota
} from '@/lib/api'

// ── 数字格式化 ──────────────────────────────────────────

function fmt(v: number | null | undefined, digits = 2) {
  if (v == null) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

// ── 是否简单定额码（可链接） ───────────────────────────

function isSimpleCode(code: string | null | undefined) {
  if (!code) return false
  return /^\d{6}-\d+$/.test(code.trim())
}

// ── 定额子目详情弹窗 ─────────────────────────────────

function QuotaModal({ quota, onClose }: { quota: ManualBoqQuota; onClose: () => void }) {
  const onBackdrop = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose()
  }, [onClose])

  useEffect(() => {
    const fn = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', fn)
    return () => window.removeEventListener('keydown', fn)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onBackdrop}>
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-xl max-h-[85vh] flex flex-col">
        {/* 标题 */}
        <div className="flex items-start gap-3 px-5 py-4 border-b">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-blue-600 font-semibold">{quota.quota_code}</span>
              <span className="font-semibold text-gray-800">{quota.quota_name}</span>
              {quota.qi_variant_desc && <span className="text-gray-500 text-sm">（{quota.qi_variant_desc}）</span>}
            </div>
            <div className="text-xs text-gray-400 mt-0.5">计量单位：{quota.qi_unit ?? quota.quota_unit ?? '—'}</div>
          </div>
          <button onClick={onClose} className="shrink-0 text-gray-400 hover:text-gray-600 text-xl leading-none">✕</button>
        </div>

        <div className="overflow-y-auto flex-1 px-5 py-4 space-y-4">
          {/* 工作内容 */}
          {quota.qi_work_content && (
            <div>
              <div className="text-xs font-medium text-gray-500 mb-1">工作内容</div>
              <div className="text-sm text-gray-700 leading-relaxed">{quota.qi_work_content.replace(/单位\s*[：:].+$/, '').trim()}</div>
            </div>
          )}

          {/* 价格构成 */}
          {quota.qi_total_unit_price != null && (
            <div>
              <div className="text-xs font-medium text-gray-500 mb-2">价格构成（元 / {quota.qi_unit ?? quota.quota_unit ?? '—'}）</div>
              <div className="grid grid-cols-2 gap-2 mb-2">
                <div className="rounded-lg p-3 bg-blue-50 border border-blue-100 text-center">
                  <div className="text-xs text-gray-400 mb-0.5">全费用综合单价</div>
                  <div className="text-lg font-bold text-blue-700 tabular-nums">{fmt(quota.qi_total_unit_price)}</div>
                </div>
                <div className="rounded-lg p-3 bg-gray-50 text-center">
                  <div className="text-xs text-gray-400 mb-0.5">综合单价</div>
                  <div className="text-lg font-bold text-gray-700 tabular-nums">{fmt(quota.qi_unit_price)}</div>
                </div>
              </div>
              <div className="grid grid-cols-5 gap-1.5 text-center">
                {[
                  ['人工费', quota.qi_labor_cost],
                  ['材料费', quota.qi_material_cost],
                  ['机械费', quota.qi_machine_cost],
                  ['管理费', quota.qi_management_fee],
                  ['利润', quota.qi_profit],
                ].map(([label, val]) => (
                  <div key={String(label)} className="rounded p-2 bg-gray-50 border border-gray-100">
                    <div className="text-xs text-gray-400">{label}</div>
                    <div className="font-semibold text-gray-700 tabular-nums text-sm">{fmt(val as number | null)}</div>
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-3 gap-1.5 text-center mt-1.5">
                {[
                  ['安全文明费', quota.qi_safety_fee],
                  ['规费', quota.qi_statutory_fee],
                  ['税金', quota.qi_tax],
                ].map(([label, val]) => (
                  <div key={String(label)} className="rounded p-2 bg-gray-50 border border-gray-100">
                    <div className="text-xs text-gray-400">{label}</div>
                    <div className="font-semibold text-gray-700 tabular-nums text-sm">{fmt(val as number | null)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!quota.quota_item_id && (
            <div className="text-sm text-gray-400 italic">该定额子目编码未在定额库中找到匹配记录，仅显示清单原始数据。</div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── 定额子目行 ───────────────────────────────────────

function QuotaRow({ quota, onSelect }: { quota: ManualBoqQuota; onSelect: (q: ManualBoqQuota) => void }) {
  const linked = !!quota.quota_item_id
  return (
    <tr className="bg-blue-50/40 text-xs border-t border-blue-100/60">
      <td className="pl-10 pr-2 py-1.5 text-gray-400 w-8">↳</td>
      <td className="px-2 py-1.5">
        {linked && isSimpleCode(quota.quota_code) ? (
          <button
            onClick={() => onSelect(quota)}
            className="font-mono text-blue-600 hover:text-blue-800 hover:underline"
          >{quota.quota_code}</button>
        ) : (
          <span className="font-mono text-gray-500">{quota.quota_code ?? '—'}</span>
        )}
      </td>
      <td className="px-2 py-1.5 text-gray-600 max-w-xs">{quota.quota_name ?? '—'}</td>
      <td className="px-2 py-1.5 text-gray-400 text-center">{quota.quota_unit ?? '—'}</td>
      <td className="px-2 py-1.5 text-right tabular-nums text-gray-600">{fmt(quota.quantity, 4)}</td>
      <td className="px-2 py-1.5 text-right tabular-nums text-gray-600">{fmt(quota.unit_price)}</td>
      <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">{fmt(quota.total_price)}</td>
    </tr>
  )
}

// ── 清单项行 ─────────────────────────────────────────

function ItemRow({ item, onSelect }: { item: ManualBoqItem; onSelect: (q: ManualBoqQuota) => void }) {
  const [expanded, setExpanded] = useState(true)
  const hasQuotas = item.quotas.length > 0
  return (
    <>
      <tr
        className="hover:bg-gray-50 cursor-pointer border-t border-gray-100"
        onClick={() => hasQuotas && setExpanded(e => !e)}
      >
        <td className="px-3 py-2 text-xs text-gray-400 w-8">{item.item_seq ?? ''}</td>
        <td className="px-2 py-2 font-mono text-xs text-gray-600">{item.item_code ?? '—'}</td>
        <td className="px-2 py-2 text-sm text-gray-800 font-medium">
          <div className="flex items-start gap-1">
            {hasQuotas && (
              <span className="text-gray-400 text-xs mt-0.5 select-none">{expanded ? '▾' : '▸'}</span>
            )}
            <span>{item.item_name ?? '—'}</span>
          </div>
          {item.item_description && (
            <div className="text-xs text-gray-400 mt-0.5 leading-snug whitespace-pre-line">{item.item_description}</div>
          )}
        </td>
        <td className="px-2 py-2 text-xs text-gray-500 text-center">{item.unit ?? '—'}</td>
        <td className="px-2 py-2 text-right text-sm tabular-nums text-gray-700">{fmt(item.quantity, 3)}</td>
        <td className="px-2 py-2 text-right text-sm tabular-nums text-gray-700">{fmt(item.unit_price)}</td>
        <td className="px-2 py-2 text-right text-sm tabular-nums font-medium text-gray-800">{fmt(item.total_price)}</td>
      </tr>
      {expanded && item.quotas.map(q => (
        <QuotaRow key={q.id} quota={q} onSelect={onSelect} />
      ))}
    </>
  )
}

// ── 分部组 ──────────────────────────────────────────

function SectionGroup({
  sectionName, items, onSelect
}: {
  sectionName: string | null,
  items: ManualBoqItem[],
  onSelect: (q: ManualBoqQuota) => void
}) {
  const [expanded, setExpanded] = useState(true)
  const sectionTotal = items.reduce((s, it) => s + (it.total_price ?? 0), 0)

  return (
    <div className="mb-4">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-gray-500 text-sm select-none">{expanded ? '▾' : '▸'}</span>
          <span className="font-semibold text-gray-800 text-sm">{sectionName ?? '（未分类）'}</span>
          <span className="text-xs text-gray-400">{items.length} 项</span>
        </div>
        <span className="text-sm font-medium text-gray-700 tabular-nums">¥ {sectionTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}</span>
      </button>

      {expanded && (
        <div className="overflow-x-auto mt-1">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-400 border-b">
                <th className="px-3 py-1.5 text-left w-8">序</th>
                <th className="px-2 py-1.5 text-left">编码</th>
                <th className="px-2 py-1.5 text-left">名称 / 项目描述</th>
                <th className="px-2 py-1.5 text-center w-14">单位</th>
                <th className="px-2 py-1.5 text-right w-24">数量</th>
                <th className="px-2 py-1.5 text-right w-24">综合单价</th>
                <th className="px-2 py-1.5 text-right w-28">合价</th>
              </tr>
            </thead>
            <tbody>
              {items.map(item => (
                <ItemRow key={item.id} item={item} onSelect={onSelect} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── 主页面 ──────────────────────────────────────────

export default function ManualBoqDetailPage() {
  const params = useParams()
  const router = useRouter()
  const id = Number(params.id)
  const [detail, setDetail] = useState<ManualBoqProjectDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedQuota, setSelectedQuota] = useState<ManualBoqQuota | null>(null)

  useEffect(() => {
    fetchManualBoqProject(id)
      .then(setDetail)
      .catch(() => router.push('/manual-boq'))
      .finally(() => setLoading(false))
  }, [id, router])

  if (loading) return <div className="text-center text-gray-400 py-20 animate-pulse">加载中…</div>
  if (!detail) return null

  const { project, items } = detail

  // 按 section_name 分组
  const sectionMap = new Map<string | null, ManualBoqItem[]>()
  for (const item of items) {
    const key = item.section_name
    if (!sectionMap.has(key)) sectionMap.set(key, [])
    sectionMap.get(key)!.push(item)
  }

  const grandTotal = items.reduce((s, it) => s + (it.total_price ?? 0), 0)
  const totalQuotas = items.reduce((s, it) => s + it.quotas.length, 0)

  return (
    <div>
      {/* 工程头部 */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <button onClick={() => router.push('/manual-boq')} className="text-sm text-gray-400 hover:text-blue-600 mb-1">← 返回列表</button>
          <h1 className="text-xl font-bold text-gray-800">{project.project_name}</h1>
          {project.bid_section && <div className="text-sm text-gray-500 mt-0.5">{project.bid_section}</div>}
          <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
            {project.tag && <span className="bg-green-100 text-green-700 px-1.5 py-0.5 rounded">{project.tag}</span>}
            <span>人工套定额</span>
            <span>·</span>
            <span>{project.item_count ?? items.length} 个清单项</span>
            <span>·</span>
            <span>{totalQuotas} 条定额子目</span>
            <span>·</span>
            <span>导入于 {new Date(project.imported_at).toLocaleDateString('zh-CN')}</span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-gray-400 mb-0.5">合计金额</div>
          <div className="text-2xl font-bold text-blue-700 tabular-nums">
            ¥ {grandTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
          </div>
        </div>
      </div>

      {/* 分部列表 */}
      {Array.from(sectionMap.entries()).map(([sectionName, sectionItems]) => (
        <SectionGroup
          key={sectionName ?? '__none__'}
          sectionName={sectionName}
          items={sectionItems}
          onSelect={setSelectedQuota}
        />
      ))}

      {/* 定额详情弹窗 */}
      {selectedQuota && (
        <QuotaModal quota={selectedQuota} onClose={() => setSelectedQuota(null)} />
      )}
    </div>
  )
}
