'use client'

import type {
  BoqItem,
  PricingTaskCoefficientCheck,
  PricingTaskConversionCheck,
  PricingTaskEvaluation,
  QuotaMatch,
} from '@/lib/api'

type ResourceRow = NonNullable<PricingTaskConversionCheck['items'][number]['resources']>[number]
type CoefficientRules = PricingTaskCoefficientCheck['items'][number]['coefficient_rules']

export interface BatchPricingResultDetail {
  quotaMatch?: { matches?: QuotaMatch[] } | null
  evaluation?: PricingTaskEvaluation | null
  conversionCheck?: PricingTaskConversionCheck | null
  coefficientCheck?: PricingTaskCoefficientCheck | null
}

interface Props {
  item: Pick<BoqItem, 'id' | 'item_code' | 'item_name' | 'item_description' | 'unit' | 'quantity'>
  result: BatchPricingResultDetail
  onClose: () => void
  onReview?: () => void
}

function resourceTypeLabel(type?: number | null) {
  if (type === 1) return '人工'
  if (type === 2) return '材料'
  if (type === 3) return '机械'
  return '-'
}

function coefficientRulesForResource(resource: ResourceRow, rules?: CoefficientRules) {
  return (rules ?? []).filter(rule => {
    if (!rule.matched) return false
    if (rule.target_resource_types.includes('all')) return true
    return resource.type != null && rule.target_resource_types.includes(String(resource.type) as '1' | '2' | '3')
  })
}

function ConsistencyBadge({ evaluation }: { evaluation?: PricingTaskEvaluation | null }) {
  if (!evaluation) return null
  const exact = evaluation.missed_count === 0 && evaluation.extra_count === 0
  const partial = !exact && evaluation.hit_count > 0
  const label = exact ? '完全一致' : partial ? '部分一致' : '不一致'
  const tone = exact
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : partial
      ? 'border-amber-200 bg-amber-50 text-amber-700'
      : 'border-rose-200 bg-rose-50 text-rose-700'
  return <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${tone}`}>{label}</span>
}

export default function BatchPricingResultDetailModal({ item, result, onClose, onReview }: Props) {
  const matches = result.quotaMatch?.matches ?? []
  const reviewable = Boolean(
    onReview && result.evaluation
    && (result.evaluation.missed_count > 0 || result.evaluation.extra_count > 0),
  )

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/40 px-4" onClick={onClose}>
      <div className="max-h-[86vh] w-full max-w-4xl overflow-hidden rounded-lg bg-white shadow-xl" onClick={event => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-4 border-b border-gray-200 px-5 py-4">
          <div className="min-w-0">
            <div className="font-mono text-xs text-gray-500">{item.item_code}</div>
            <h3 className="mt-1 truncate text-base font-semibold text-gray-900">{item.item_name}</h3>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <ConsistencyBadge evaluation={result.evaluation} />
            {reviewable && (
              <button type="button" onClick={onReview} className="rounded border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 hover:border-amber-400 hover:bg-amber-100">
                复核差异并修正人工工程
              </button>
            )}
            <button type="button" onClick={onClose} className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50">关闭</button>
          </div>
        </div>

        <div className="max-h-[calc(86vh-72px)] overflow-y-auto px-5 py-4">
          <div className="mb-4 rounded border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-600">
            <div className="whitespace-pre-wrap"><span className="font-semibold text-gray-700">项目特征：</span>{item.item_description || '未填写'}</div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
              <span><span className="font-semibold text-gray-700">单位：</span>{item.unit || '-'}</span>
              <span><span className="font-semibold text-gray-700">工程量：</span>{item.quantity ?? '-'}</span>
            </div>
          </div>

          <div className="space-y-2">
            <h4 className="text-sm font-semibold text-gray-900">套定额结果</h4>
            {matches.length === 0 ? (
              <div className="rounded border border-dashed border-gray-300 px-3 py-8 text-center text-xs text-gray-400">暂无套定额结果</div>
            ) : matches.map((match, index) => (
              <div key={`${match.zmbh}-${index}`} className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono font-semibold text-emerald-800">{match.zmbh}</span>
                  <span className="font-medium text-gray-900">{match.zmmc}</span>
                  <span className="rounded bg-white px-1.5 py-0.5 text-[10px] text-gray-500">{match.confidence}</span>
                  <span className="text-gray-500">系数 {match.qty_factor}</span>
                </div>
                {match.match_reason && <div className="mt-1 text-gray-600">{match.match_reason}</div>}
              </div>
            ))}
          </div>

          {result.conversionCheck && (
            <div className="mt-5 space-y-2">
              <h4 className="text-sm font-semibold text-gray-900">组合换算结果</h4>
              {result.conversionCheck.items.map(conversionItem => (
                <div key={`${conversionItem.dekid}-${conversionItem.dezmid}`} className="rounded border border-cyan-200 bg-cyan-50 px-3 py-2 text-xs">
                  <div><span className="font-mono text-cyan-800">{conversionItem.quota_code}</span><span className="ml-2 text-gray-900">{conversionItem.quota_name}</span></div>
                  {(conversionItem.adjustment_rules ?? []).map(rule => (
                    <div key={`${rule.rule_index}-${rule.combo_code}`} className="mt-1 rounded bg-white px-2 py-1 text-cyan-900">
                      <span className="font-mono">{rule.combo_code}</span><span className="ml-2">{rule.combo_name}</span><span className="ml-2">次数 {rule.calculated_times ?? '-'}</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}

          {result.conversionCheck && (
            <div className="mt-5 space-y-3">
              <h4 className="text-sm font-semibold text-gray-900">工料机明细</h4>
              {result.conversionCheck.items.flatMap(conversionItem => {
                const coefficientByKey = new Map((result.coefficientCheck?.items ?? []).map(coefficientItem => [coefficientItem.quota_key, coefficientItem.coefficient_rules]))
                const coefficientByCode = new Map((result.coefficientCheck?.items ?? []).map(coefficientItem => [coefficientItem.quota_code, coefficientItem.coefficient_rules]))
                const groups = [
                  {
                    key: `base-${conversionItem.dekid}-${conversionItem.dezmid}`,
                    code: conversionItem.quota_code,
                    name: conversionItem.quota_name,
                    resources: conversionItem.resources ?? [],
                    rules: coefficientByKey.get(`base:${conversionItem.dekid}:${conversionItem.dezmid}`) ?? coefficientByCode.get(conversionItem.quota_code),
                  },
                  ...((conversionItem.adjustment_rules ?? []).map(rule => ({
                    key: `combo-${conversionItem.dekid}-${rule.combo_dezmid}-${rule.combo_code}`,
                    code: rule.combo_code,
                    name: `${rule.combo_name || '-'}（来源 ${conversionItem.quota_code || '-'}；次数 ${rule.calculated_times ?? '-'}）`,
                    resources: rule.combo_resources ?? [],
                    rules: coefficientByKey.get(`combo:${conversionItem.dekid}:${rule.combo_dezmid}:${rule.combo_code}`) ?? coefficientByCode.get(rule.combo_code),
                  }))),
                ]
                return groups.map(group => (
                  <div key={group.key} className="overflow-hidden rounded border border-gray-200">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 bg-gray-50 px-3 py-2 text-xs">
                      <div className="min-w-0"><span className="font-mono font-semibold text-gray-700">{group.code || '-'}</span><span className="ml-2 font-medium text-gray-900">{group.name || '-'}</span></div>
                      <span className="text-gray-500">{group.resources.length} 条工料机</span>
                    </div>
                    {group.resources.length === 0 ? <div className="px-3 py-4 text-center text-xs text-gray-400">暂无工料机明细</div> : (
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[800px] text-left text-xs">
                          <thead className="bg-white text-gray-500"><tr><th className="px-3 py-2 font-medium">类别</th><th className="px-3 py-2 font-medium">编码</th><th className="px-3 py-2 font-medium">名称</th><th className="px-3 py-2 font-medium">单位</th><th className="px-3 py-2 text-right font-medium">含量</th><th className="px-3 py-2 text-center font-medium">是否主材</th><th className="px-3 py-2 font-medium">换算</th></tr></thead>
                          <tbody className="divide-y divide-gray-100 bg-white">{group.resources.map((resource, index) => {
                            const matchedRules = coefficientRulesForResource(resource, group.rules)
                            return <tr key={`${resource.code}-${resource.name}-${index}`} className={resource.zycl === true ? 'bg-emerald-200/80' : matchedRules.length > 0 ? 'bg-amber-50/70' : undefined}>
                              <td className="px-3 py-2 text-gray-500">{resourceTypeLabel(resource.type)}</td><td className="px-3 py-2 font-mono text-gray-600">{resource.code || '-'}</td><td className="px-3 py-2 text-gray-900">{resource.name || '-'}</td><td className="px-3 py-2 text-gray-500">{resource.unit || '-'}</td><td className="px-3 py-2 text-right text-gray-700">{resource.confirmed_quantity ?? resource.quantity ?? resource.original_quantity ?? '-'}</td><td className="px-3 py-2 text-center">{resource.zycl === true ? <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700">是</span> : resource.zycl === false ? <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">否</span> : <span className="text-gray-400">-</span>}</td>
                              <td className="px-3 py-2 text-gray-500">{matchedRules.length === 0 ? '-' : <div className="flex flex-wrap gap-1">{matchedRules.map(rule => <span key={rule.rule_index} className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">系数 x{rule.factor}</span>)}</div>}</td>
                            </tr>
                          })}</tbody>
                        </table>
                      </div>
                    )}
                  </div>
                ))
              })}
            </div>
          )}

          {result.coefficientCheck && (
            <div className="mt-5 space-y-2">
              <h4 className="text-sm font-semibold text-gray-900">系数换算结果</h4>
              {result.coefficientCheck.items.map(coefficientItem => (
                <div key={coefficientItem.quota_key} className="rounded border border-violet-200 bg-violet-50 px-3 py-2 text-xs">
                  <div><span className="font-mono text-violet-800">{coefficientItem.quota_code}</span><span className="ml-2 text-gray-900">{coefficientItem.quota_name}</span></div>
                  {coefficientItem.coefficient_rules.map(rule => <div key={rule.rule_index} className={`mt-1 rounded px-2 py-1 ${rule.matched ? 'bg-amber-50 text-amber-800' : 'bg-white text-violet-900'}`}><span>规则 {rule.rule_index}</span><span className="ml-2">{rule.matched ? `系数 x${rule.factor}` : '未命中'}</span>{rule.matched_feature && <span className="ml-2">{rule.matched_feature}</span>}</div>)}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
