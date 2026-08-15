'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import {
  BoqItem,
  PricingTask,
  PricingTaskCoefficientCheck,
  PricingTaskChapterRuleCheck,
  PricingTaskConversionCheck,
  PricingTaskConversionResource,
  PricingTaskDetailReport,
  PricingTaskEvaluation,
  PricingTaskEvent,
  PricingTaskRun,
  PricingTaskStepTiming,
  QuotaCandidate,
  QuotaMatch,
  confirmPricingTaskRun,
  exportPricingTaskDetailReportExcel,
  fetchAllBoqItems,
  fetchPricingTaskDetailReport,
  fetchPricingTaskLatestRuns,
  fetchPricingTask,
  fetchPricingTaskItemRuns,
  fetchPricingTaskManualComparisonHistory,
  generatePricingTaskAccuracyReport,
  rejectPricingTaskRun,
  streamPricingTaskCoefficientCheck,
  streamPricingTaskConversionCheck,
  streamPricingTaskRunItem,
  updateBoqItemDescription,
  updatePricingTaskManualComparison,
} from '@/lib/api'
import ManualComparisonReviewModal from '@/components/pricing-task/ManualComparisonReviewModal'

interface CodeCheck {
  item_code: string
  item_name: string
  base_code: string
  standard_name: string
  found: boolean
  is_consistent: boolean
}

interface FeatureDefaultFill {
  candidate_id: string
  feature_name: string
  target_feature_name: string
  original_value: string
  default_value: string
  source: 'TQDK_TQDXMTZ' | 'tqdk_tzhkl'
  source_code: string
  source_rowid?: number
  reason: string
  confidence: 'high' | 'medium' | 'low'
}

interface FeatureSchemaItem {
  feature_name: string
  native_default_value?: string
  source: 'TQDK_TQDXMTZ'
  source_rowid?: number
}

interface FeatureDefaultCandidate {
  candidate_id: string
  source: 'TQDK_TQDXMTZ' | 'tqdk_tzhkl'
  priority: number
  source_code: string
  feature_name: string
  target_feature_name: string
  feature_value: string
  default_value: string
  source_rowid?: number
  blocked_by_native_default?: boolean
}

interface FeatureCheck {
  is_complete: boolean
  missing_features: string[]
  analysis: string
  original_description?: string
  normalized_description?: string
  effective_description?: string
  default_fills?: FeatureDefaultFill[]
  description_updated?: boolean
  schema_kb_version_id?: number
  feature_schema?: FeatureSchemaItem[]
  default_candidates?: FeatureDefaultCandidate[]
  unresolved_features?: string[]
}
interface ItemResult {
  phase: 'reasoning' | 'done' | 'error'
  reasoning: string
  runId?: number
  status?: string
  codeCheck?: CodeCheck
  judgment?: { is_consistent: boolean; reasoning: string }
  featureCheck?: FeatureCheck
  chapterRuleCheck?: PricingTaskChapterRuleCheck
  quotaCandidates?: { item_code: string; base_code: string; candidates: QuotaCandidate[]; total: number }
  quotaMatch?: { matches: QuotaMatch[]; issues: string[] }
  evaluation?: PricingTaskEvaluation
  comboAdjustmentPreview?: PricingTaskConversionCheck['items']
  conversionCheck?: PricingTaskConversionCheck
  conversionChecking?: boolean
  conversionError?: string
  coefficientPreview?: PricingTaskCoefficientCheck['items']
  coefficientCheck?: PricingTaskCoefficientCheck
  coefficientChecking?: boolean
  autoConfirming?: boolean
  coefficientError?: string
  confirmedResults?: PricingTaskRun['confirmed_results']
  stepTimings?: Record<string, PricingTaskStepTiming>
  error?: string
}

function runToResult(run: PricingTaskRun): ItemResult {
  const quotaMatch = run.quota_match as ItemResult['quotaMatch']
  const normalizedQuotaMatch = quotaMatch && Array.isArray(quotaMatch.matches)
    ? { matches: quotaMatch.matches, issues: Array.isArray(quotaMatch.issues) ? quotaMatch.issues : [] }
    : undefined
  return {
    phase: run.status === 'failed' ? 'error' : 'done',
    reasoning: run.reasoning_text || '',
    runId: run.id,
    status: run.status,
    codeCheck: run.code_check as CodeCheck | undefined,
    judgment: run.code_check
      ? {
          is_consistent: Boolean((run.code_check as CodeCheck).is_consistent),
          reasoning: `标准清单名称：${(run.code_check as CodeCheck).standard_name || '未找到'}`,
        }
      : undefined,
    featureCheck: run.feature_check as ItemResult['featureCheck'],
    chapterRuleCheck: run.chapter_rule_check ?? undefined,
    quotaCandidates: run.quota_candidates as ItemResult['quotaCandidates'],
    quotaMatch: normalizedQuotaMatch,
    evaluation: run.evaluation ?? undefined,
    conversionCheck: run.conversion_check ?? undefined,
    coefficientCheck: run.coefficient_check ?? undefined,
    confirmedResults: run.confirmed_results ?? undefined,
    stepTimings: run.step_timings ?? undefined,
    error: run.error_message || undefined,
  }
}

function statusLabel(status?: string) {
  if (status === 'confirmed') return '已确认'
  if (status === 'rejected') return '已驳回'
  if (status === 'completed') return '待确认'
  if (status === 'failed') return '失败'
  if (status === 'running') return '运行中'
  return '未运行'
}

function statusClassName(status?: string) {
  if (status === 'confirmed') return 'bg-emerald-100 text-emerald-700 border-emerald-200'
  if (status === 'completed') return 'bg-blue-100 text-blue-700 border-blue-200'
  if (status === 'rejected') return 'bg-gray-100 text-gray-600 border-gray-200'
  if (status === 'failed') return 'bg-red-100 text-red-700 border-red-200'
  if (status === 'running') return 'bg-amber-100 text-amber-700 border-amber-200'
  return 'bg-slate-100 text-slate-500 border-slate-200'
}

function matchCountLabel(result?: ItemResult) {
  if (!result?.quotaMatch) return ''
  return `${result.quotaMatch.matches.length} 条定额`
}

function quotaHitBadge(result?: ItemResult) {
  if (!result?.quotaMatch) return null
  const evaluation = result.evaluation
  if (!evaluation || evaluation.manual_count === 0) {
    return {
      label: '待对比',
      title: '尚无人工定额对比结果',
      className: 'border-slate-200 bg-slate-100 text-slate-600',
    }
  }
  const title = `双方一致 ${evaluation.hit_count} / 仅人工 ${evaluation.missed_count} / 仅AI ${evaluation.extra_count}`
  if (evaluation.missed_count === 0 && evaluation.extra_count === 0) {
    return {
      label: '完全一致',
      title,
      className: 'border-emerald-200 bg-emerald-100 text-emerald-700',
    }
  }
  if (evaluation.hit_count > 0) {
    return {
      label: '部分一致',
      title,
      className: 'border-amber-200 bg-amber-100 text-amber-700',
    }
  }
  return {
    label: '不一致',
    title,
    className: 'border-rose-200 bg-rose-100 text-rose-700',
  }
}

function stepBadgeClass(tone: 'success' | 'warning' | 'error' | 'pending') {
  if (tone === 'success') return 'bg-green-500 text-white border-green-500'
  if (tone === 'warning') return 'bg-amber-500 text-white border-amber-500'
  if (tone === 'error') return 'bg-red-700 text-white border-red-700'
  return 'bg-gray-100 text-gray-400 border-gray-200'
}

function formatDuration(ms?: number) {
  if (ms == null) return ''
  if (ms < 1000) return `${ms}ms`
  const seconds = ms / 1000
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  return `${minutes}m${rest}s`
}

function stepTiming(result: ItemResult | undefined, stepNo: number) {
  return result?.stepTimings?.[String(stepNo)]
}

function StepDuration({ result, stepNo }: { result: ItemResult; stepNo: number }) {
  const timing = stepTiming(result, stepNo)
  if (!timing) return null
  return (
    <span className="ml-2 rounded-full bg-white/70 px-1.5 py-0.5 text-[10px] font-normal text-gray-500">
      {formatDuration(timing.duration_ms)}
    </span>
  )
}

function resourceTypeLabel(type?: number | null) {
  if (type === 1) return '人工'
  if (type === 2) return '材料'
  if (type === 3) return '机械'
  return '其他'
}

function stepBadges(result?: ItemResult) {
  return [
    {
      no: 1,
      title: '编码核查',
      tone: !result?.codeCheck ? 'pending' : result.codeCheck.is_consistent ? 'success' : 'warning',
    },
    {
      no: 2,
      title: '项目特征',
      tone: !result?.featureCheck ? 'pending' : result.featureCheck.is_complete ? 'success' : 'warning',
    },
    {
      no: 3,
      title: '章节规则',
      tone: !result?.chapterRuleCheck
        ? 'pending'
        : result.chapterRuleCheck.validation?.status === 'failed'
          ? 'error'
          : result.chapterRuleCheck.validation?.status === 'manual_review'
            ? 'warning'
            : 'success',
    },
    {
      no: 4,
      title: '定额候选',
      tone: !result?.quotaCandidates ? 'pending' : result.quotaCandidates.total > 0 ? 'success' : 'warning',
    },
    {
      no: 5,
      title: '套定额结果',
      tone: !result?.quotaMatch ? (result?.phase === 'error' ? 'error' : 'pending') : result.quotaMatch.matches.length > 0 ? 'success' : 'warning',
    },
    {
      no: 6,
      title: '人工对比',
      tone: !result?.evaluation
        ? 'pending'
        : result.evaluation.manual_count === 0
          ? 'pending'
          : result.evaluation.missed_count === 0 && result.evaluation.extra_count === 0
            ? 'success'
            : 'warning',
    },
    {
      no: 7,
      title: '组合换算',
      tone: result?.conversionChecking
        ? 'pending'
        : !result?.conversionCheck
          ? 'pending'
          : result.conversionCheck.items.some(item => item.needs_conversion)
            ? 'warning'
            : 'success',
    },
    {
      no: 8,
      title: '系数换算',
      tone: result?.coefficientChecking
        ? 'pending'
        : !result?.coefficientCheck
          ? 'pending'
          : result.coefficientCheck.items.some(item => item.coefficient_rules.some(rule => rule.matched))
            ? 'warning'
            : 'success',
    },
  ] as const
}

function activeStepNo(result?: ItemResult) {
  if (result?.coefficientChecking) return 8
  if (result?.conversionChecking) return 7
  if (!result || result.phase !== 'reasoning') return null
  if (!result.codeCheck) return 1
  if (!result.featureCheck) return 2
  if (!result.chapterRuleCheck) return 3
  if (!result.quotaCandidates) return 4
  if (!result.quotaMatch) return 5
  if (!result.evaluation) return 6
  return null
}

function buildQuotaHitStats(results: Map<number, ItemResult>, totalItems: number) {
  const evaluatedResults = Array.from(results.values()).filter(result => result.evaluation)
  const totals = evaluatedResults.reduce(
    (acc, result) => {
      const evaluation = result.evaluation
      if (!evaluation) return acc
      acc.hitCount += evaluation.hit_count
      acc.missedCount += evaluation.missed_count
      acc.extraCount += evaluation.extra_count
      acc.manualCount += evaluation.manual_count
      acc.aiCount += evaluation.ai_count
      if (evaluation.manual_count > 0 && evaluation.missed_count === 0 && evaluation.extra_count === 0) {
        acc.exactItemCount += 1
      }
      return acc
    },
    {
      hitCount: 0,
      missedCount: 0,
      extraCount: 0,
      manualCount: 0,
      aiCount: 0,
      exactItemCount: 0,
    },
  )

  return {
    ...totals,
    evaluatedItemCount: evaluatedResults.length,
    totalItems,
    hitRate: totals.manualCount > 0 ? totals.hitCount / totals.manualCount : null,
  }
}

function formatPercent(value: number | null) {
  if (value == null) return '-'
  return `${(value * 100).toFixed(1)}%`
}

function confidenceLabel(confidence?: string) {
  if (confidence === 'high') return '高'
  if (confidence === 'medium') return '中'
  if (confidence === 'low') return '低'
  return '-'
}

function formatNullableNumber(value?: number | null) {
  if (value == null) return '-'
  return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
}

function ComboAdjustmentRules({
  rules,
  compact = false,
  preview = false,
}: {
  rules?: NonNullable<PricingTaskConversionCheck['items'][number]['adjustment_rules']>
  compact?: boolean
  preview?: boolean
}) {
  if (!rules || rules.length === 0) {
    return (
      <div className="rounded border border-dashed border-gray-200 bg-gray-50 px-3 py-3 text-xs text-gray-500">
        该定额无组合换算规则。
      </div>
    )
  }
  return (
    <div className="space-y-2">
      {rules.map(rule => (
        <div key={`${rule.rule_index}-${rule.combo_code}`} className="rounded border border-cyan-100 bg-white px-3 py-2 text-xs">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono font-semibold text-cyan-800">{rule.combo_code || '-'}</span>
                <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">规则 {rule.rule_index}</span>
              </div>
              <div className="mt-0.5 font-medium text-gray-900">{rule.combo_name || '-'}</div>
            </div>
            <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${preview ? 'bg-cyan-100 text-cyan-700' : rule.matched && (rule.calculated_times ?? 0) > 0 ? 'bg-amber-100 text-amber-700' : rule.matched ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-500'}`}>
              {preview ? '待识别' : rule.matched ? `次数 ${formatNullableNumber(rule.calculated_times)}` : '未匹配'}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-gray-500">
            <span>单位：{rule.combo_unit || '-'}</span>
            <span>基础值：{formatNullableNumber(rule.base_value)}</span>
            <span>增减单位：{formatNullableNumber(rule.increment_unit)}</span>
            {!preview && <span>特征值：{formatNullableNumber(rule.feature_value)}</span>}
            {rule.requires_manual_review && <span className="font-semibold text-amber-700">需人工复核</span>}
          </div>
          {rule.prompt && <div className="mt-1 text-gray-600">提示：{rule.prompt}</div>}
          {!preview && rule.matched_feature && <div className="mt-1 text-cyan-800">命中特征：{rule.matched_feature}</div>}
          {!preview && rule.reason && <div className="mt-1 text-gray-600">{rule.reason}</div>}
          {!compact && rule.combo_work_content && (
            <div className="mt-1 text-gray-500">工作内容：{rule.combo_work_content}</div>
          )}
          {!compact && (
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-gray-400">
              <span>人工费：{formatNullableNumber(rule.combo_labor_cost)}</span>
              <span>材料费：{formatNullableNumber(rule.combo_material_cost)}</span>
              <span>机械费：{formatNullableNumber(rule.combo_machine_cost)}</span>
              <span>置信度：{confidenceLabel(rule.confidence)}</span>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function ComboConversionList({
  items,
  compact = false,
  preview = false,
}: {
  items: PricingTaskConversionCheck['items']
  compact?: boolean
  preview?: boolean
}) {
  if (items.length === 0) {
    return <ResultEmptyState title="暂无组合换算结果" description="确认定额后会展示组合定额、特征值和计算次数。" />
  }
  return (
    <div className="space-y-2">
      {items.map((conversion, index) => (
        <div key={`${conversion.dekid}-${conversion.dezmid}-${index}`} className="rounded border border-cyan-100 bg-cyan-50/50 px-3 py-2 text-xs">
          <div className="flex items-start gap-2">
            <div className="min-w-0 flex-1">
              <div className="font-mono font-semibold text-cyan-800">{conversion.quota_code || '-'}</div>
              <div className="font-medium text-gray-900">{conversion.quota_name || '-'}</div>
            </div>
            <span className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium ${preview ? 'bg-cyan-100 text-cyan-700' : conversion.needs_conversion ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`}>
              {preview ? '组合定额已列出' : conversion.needs_conversion ? '有组合次数' : '无组合次数'}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-gray-500">
            <span>组合规则：{conversion.adjustment_rules?.length ?? 0} 条</span>
            <span>命中：{(conversion.adjustment_rules ?? []).filter(rule => rule.matched).length} 条</span>
            {!preview && conversion.requires_manual_review && <span className="font-medium text-amber-700">需人工复核</span>}
            {!preview && <span>置信度：{confidenceLabel(conversion.confidence)}</span>}
          </div>
          {!preview && conversion.reason && <div className="mt-1 text-gray-600">{conversion.reason}</div>}
          {!preview && conversion.missing_inputs.length > 0 && (
            <div className="mt-1 text-amber-700">缺失信息：{conversion.missing_inputs.join('、')}</div>
          )}
          <div className="mt-2">
            <ComboAdjustmentRules rules={conversion.adjustment_rules} compact={compact} preview={preview} />
          </div>
        </div>
      ))}
    </div>
  )
}

function ComboQuotaOnlyList({
  items,
  preview = false,
}: {
  items: PricingTaskConversionCheck['items']
  preview?: boolean
}) {
  const rules = items.flatMap(item =>
    (item.adjustment_rules ?? []).map(rule => ({
      ...rule,
      base_quota_code: item.quota_code,
      base_quota_name: item.quota_name,
    })),
  )
  if (rules.length === 0) {
    return <ResultEmptyState title="暂无组合定额" description="该清单确认定额后未查询到组合定额规则。" />
  }
  return (
    <div className="space-y-2">
      {rules.map(rule => (
        <div key={`${rule.base_quota_code}-${rule.rule_index}-${rule.combo_code}`} className="rounded border border-cyan-100 bg-cyan-50/50 px-3 py-2 text-xs">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono font-semibold text-cyan-800">{rule.combo_code || '-'}</span>
                <span className="rounded bg-white px-1.5 py-0.5 text-[10px] text-gray-500">来源 {rule.base_quota_code || '-'}</span>
              </div>
              <div className="mt-0.5 font-medium text-gray-900">{rule.combo_name || '-'}</div>
            </div>
            <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${preview ? 'bg-cyan-100 text-cyan-700' : rule.matched && (rule.calculated_times ?? 0) > 0 ? 'bg-amber-100 text-amber-700' : rule.matched ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-500'}`}>
              {preview ? '待识别' : rule.matched ? `次数 ${formatNullableNumber(rule.calculated_times)}` : '未匹配'}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-gray-500">
            <span>单位：{rule.combo_unit || '-'}</span>
            <span>基础值：{formatNullableNumber(rule.base_value)}</span>
            <span>增减单位：{formatNullableNumber(rule.increment_unit)}</span>
            {!preview && <span>特征值：{formatNullableNumber(rule.feature_value)}</span>}
            {rule.requires_manual_review && <span className="font-semibold text-amber-700">需人工复核</span>}
          </div>
          {rule.prompt && <div className="mt-1 text-gray-600">提示：{rule.prompt}</div>}
          {!preview && rule.matched_feature && <div className="mt-1 text-cyan-800">命中特征：{rule.matched_feature}</div>}
          {!preview && rule.reason && <div className="mt-1 text-gray-600">{rule.reason}</div>}
        </div>
      ))}
    </div>
  )
}

function CoefficientCheckList({
  items,
  preview = false,
}: {
  items: PricingTaskCoefficientCheck['items']
  preview?: boolean
}) {
  if (items.length === 0) {
    return <ResultEmptyState title="暂无系数换算说明" description="该清单定额未查询到 tdek_tznhs 换算说明。" />
  }
  return (
    <div className="space-y-2">
      {items.map(item => {
        const matchedCount = preview ? 0 : item.coefficient_rules.filter(rule => rule.matched).length
        return (
        <details key={item.quota_key} className="group rounded border border-violet-100 bg-white px-3 py-2 text-xs">
          <summary className="flex cursor-pointer list-none items-start justify-between gap-2 [&::-webkit-details-marker]:hidden">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono font-semibold text-violet-800">{item.quota_code || '-'}</span>
                <span className="rounded bg-violet-50 px-1.5 py-0.5 text-[10px] text-violet-700">
                  {item.source_type === 'combo' ? '组合定额' : '基础定额'}
                </span>
                <span className="text-[11px] text-gray-500">
                  {item.coefficient_rules.length} 条说明，{preview ? '待识别' : `命中 ${matchedCount} 条`}
                </span>
              </div>
              <div className="mt-0.5 truncate font-medium text-gray-900">{item.quota_name || '-'}</div>
            </div>
            <span className="shrink-0 text-[11px] text-violet-700 group-open:hidden">展开</span>
            <span className="hidden shrink-0 text-[11px] text-violet-700 group-open:inline">收起</span>
          </summary>
          {item.coefficient_rules.length === 0 ? (
            <div className="mt-2 rounded border border-dashed border-gray-200 bg-gray-50 px-2 py-2 text-gray-500">该定额无系数换算说明。</div>
          ) : (
            <div className="mt-2 space-y-1.5">
              {item.coefficient_rules.map(rule => (
                <div key={rule.rule_index} className="rounded border border-violet-100 bg-violet-50/60 px-2 py-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded bg-white px-1.5 py-0.5 text-[10px] text-gray-500">规则 {rule.rule_index}</span>
                    <span className={`font-medium ${!preview && rule.matched ? 'text-amber-700' : 'text-gray-600'}`}>
                      {preview ? '待识别' : rule.matched ? `系数 ×${formatNullableNumber(rule.factor)}` : '未命中'}
                    </span>
                    {!preview && rule.target_resource_types.length > 0 && (
                      <span className="text-gray-500">对象：{rule.target_resource_types.join('/')}</span>
                    )}
                  </div>
                  {rule.tsxx && <div className="mt-1 text-gray-500">提示：{rule.tsxx}</div>}
                  <div className="mt-1 text-gray-700">{rule.hssm}</div>
                  {!preview && rule.matched_feature && <div className="mt-1 text-violet-800">命中特征：{rule.matched_feature}</div>}
                  {!preview && rule.reason && <div className="mt-1 text-gray-500">{rule.reason}</div>}
                </div>
              ))}
            </div>
          )}
        </details>
        )
      })}
    </div>
  )
}

function ResultEmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded border border-dashed border-gray-200 bg-gray-50 px-4 py-8 text-center">
      <div className="text-sm font-medium text-gray-700">{title}</div>
      <div className="mt-1 text-xs text-gray-500">{description}</div>
    </div>
  )
}

function coefficientRulesForResource(resource: PricingTaskConversionResource, rules?: PricingTaskCoefficientCheck['items'][number]['coefficient_rules']) {
  return (rules ?? []).filter(rule => {
    if (!rule.matched) return false
    if (rule.target_resource_types.includes('all')) return true
    return resource.type != null && rule.target_resource_types.includes(String(resource.type) as '1' | '2' | '3')
  })
}

function coefficientNoteForResource(resource: PricingTaskConversionResource, rules?: PricingTaskCoefficientCheck['items'][number]['coefficient_rules']) {
  const matched = coefficientRulesForResource(resource, rules)
  if (matched.length === 0) return ''
  return matched
    .map(rule => {
      const basis = [rule.matched_feature, rule.hssm].filter(Boolean).join('；')
      return `系数 ×${formatNullableNumber(rule.factor)}${basis ? `（${basis}）` : ''}`
    })
    .join('；')
}

function ResourceTable({
  resources,
  coefficientRules,
}: {
  resources: PricingTaskConversionResource[]
  coefficientRules?: PricingTaskCoefficientCheck['items'][number]['coefficient_rules']
}) {
  if (resources.length === 0) {
    return <ResultEmptyState title="暂无工料机明细" description="确认定额并完成组合换算后，这里会展示工料机信息。" />
  }
  return (
    <div className="overflow-x-auto rounded border border-gray-200">
      <table className="min-w-[760px] w-full text-left text-xs">
        <thead className="bg-gray-50 text-gray-500">
          <tr>
            <th className="px-3 py-2 font-medium">类别</th>
            <th className="px-3 py-2 font-medium">编码</th>
            <th className="px-3 py-2 font-medium">名称</th>
            <th className="px-3 py-2 font-medium">单位</th>
            <th className="px-3 py-2 text-right font-medium">含量</th>
            <th className="px-3 py-2 font-medium">说明</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {resources.map((resource, index) => {
            const matchedRules = coefficientRulesForResource(resource, coefficientRules)
            const hasCoefficient = matchedRules.length > 0
            return (
              <tr key={`${resource.code}-${resource.name}-${index}`} className={hasCoefficient ? 'bg-amber-50/70' : undefined}>
                <td className="px-3 py-2 text-gray-500">{resourceTypeLabel(resource.type)}</td>
                <td className="px-3 py-2 font-mono text-gray-600">{resource.code || '-'}</td>
                <td className="px-3 py-2 text-gray-900">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span>{resource.name || '-'}</span>
                    {hasCoefficient && <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">系数换算</span>}
                  </div>
                </td>
                <td className="px-3 py-2 text-gray-500">{resource.unit || '-'}</td>
                <td className="px-3 py-2 text-right text-gray-700">
                  <div className="flex flex-col items-end gap-1">
                    <span>{resource.confirmed_quantity ?? resource.quantity ?? resource.original_quantity ?? '-'}</span>
                    {matchedRules.map(rule => (
                      <span key={rule.rule_index} className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">
                        x{formatNullableNumber(rule.factor)}
                      </span>
                    ))}
                  </div>
                </td>
                <td className={`px-3 py-2 ${hasCoefficient ? 'text-amber-700' : 'text-gray-500'}`}>
                  {coefficientNoteForResource(resource, coefficientRules) || resource.adjustment_note || '-'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

interface ResourceGroup {
  key: string
  quotaCode: string
  quotaName: string
  qtyFactor?: number
  sourceLabel?: string
  timesLabel?: string
  resources: PricingTaskConversionResource[]
  coefficientRules?: PricingTaskCoefficientCheck['items'][number]['coefficient_rules']
}

function ResourceGroups({ groups }: { groups: ResourceGroup[] }) {
  const resourceCount = groups.reduce((sum, group) => sum + group.resources.length, 0)
  if (resourceCount === 0) {
    return <ResultEmptyState title="暂无工料机明细" description="确认定额并完成组合换算后，这里会展示工料机信息。" />
  }
  return (
    <div className="space-y-3">
      {groups.map(group => (
        <div key={group.key} className="overflow-hidden rounded border border-gray-200 bg-white">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 bg-gray-50 px-3 py-2 text-xs">
            <div className="min-w-0">
              <span className="font-mono font-semibold text-gray-700">{group.quotaCode || '-'}</span>
              <span className="ml-2 font-medium text-gray-900">{group.quotaName || '-'}</span>
            </div>
            <div className="flex items-center gap-3 text-gray-500">
              {group.qtyFactor != null && <span>系数 {group.qtyFactor}</span>}
              <span>{group.resources.length} 条工料机</span>
            </div>
          </div>
          <ResourceTable resources={group.resources} coefficientRules={group.coefficientRules} />
        </div>
      ))}
    </div>
  )
}

function SelectedItemResultPanel({
  item,
  result,
}: {
  item?: BoqItem
  result?: ItemResult
}) {
  const conversionItems = result?.conversionCheck?.items ?? result?.comboAdjustmentPreview ?? []
  const hasFinalConversion = Boolean(result?.conversionCheck)
  const coefficientByKey = new Map((result?.coefficientCheck?.items ?? []).map(item => [item.quota_key, item.coefficient_rules]))
  const coefficientByCode = new Map((result?.coefficientCheck?.items ?? []).map(item => [item.quota_code, item.coefficient_rules]))
  const resourceGroups: ResourceGroup[] = conversionItems.flatMap(row => {
    const baseGroup: ResourceGroup = {
      key: `${row.dekid}-${row.dezmid}`,
      quotaCode: row.quota_code,
      quotaName: row.quota_name,
      resources: row.resources ?? [],
      coefficientRules: coefficientByKey.get(`base:${row.dekid}:${row.dezmid}`) ?? coefficientByCode.get(row.quota_code),
    }
    const comboGroups: ResourceGroup[] = (row.adjustment_rules ?? []).map(rule => ({
      key: `${row.dekid}-${row.dezmid}-${rule.rule_index}-${rule.combo_code}`,
      quotaCode: rule.combo_code,
      quotaName: `${rule.combo_name || '-'}（来源 ${row.quota_code || '-'}；次数 ${formatNullableNumber(rule.calculated_times)}）`,
      resources: rule.combo_resources ?? [],
      coefficientRules: coefficientByKey.get(`combo:${row.dekid}:${rule.combo_dezmid}:${rule.combo_code}`) ?? coefficientByCode.get(rule.combo_code),
    }))
    return [baseGroup, ...comboGroups]
  })
  const resourceCount = resourceGroups.reduce((sum, group) => sum + group.resources.length, 0)

  return (
    <section className="rounded-lg border border-gray-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-gray-200 px-4 py-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-gray-900">完整组价结果</div>
          {item ? (
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
              <span className="font-mono">{item.item_code || '-'}</span>
              <span className="max-w-xl truncate" title={item.item_name}>{item.item_name}</span>
              <span className="max-w-2xl truncate" title={item.item_description || '未填写'}>
                项目特征：{item.item_description || '未填写'}
              </span>
              <span>单位：{item.unit || '-'}</span>
              <span>工程量：{item.quantity ?? '-'}</span>
            </div>
          ) : (
            <div className="mt-1 text-xs text-gray-500">点击左侧清单后查看结果。</div>
          )}
        </div>
        {result?.status && (
          <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${statusClassName(result.status)}`}>
            {statusLabel(result.status)}
          </span>
        )}
      </div>

      <div className="max-h-[360px] overflow-y-auto px-4 py-4">
        {!item ? (
          <ResultEmptyState title="未选择清单" description="从左侧选择一条清单后，这里会展示定额、换算和工料机结果。" />
        ) : !result ? (
          <ResultEmptyState title="尚未运行" description="执行单条组价后，这里会展示该清单的结果摘要。" />
        ) : result.phase === 'error' ? (
          <ResultEmptyState title="执行失败" description={result.error || '请重新执行单条组价。'} />
        ) : (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)]">
            <div className="space-y-4">
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <h4 className="text-xs font-semibold text-gray-900">定额结果</h4>
                  {result.quotaMatch && <span className="text-xs text-gray-500">{result.quotaMatch.matches.length} 条</span>}
                </div>
                {!result.quotaMatch ? (
                  <ResultEmptyState title="暂无定额结果" description="套定额完成后会展示匹配定额。" />
                ) : result.quotaMatch.matches.length === 0 ? (
                  <ResultEmptyState title="未匹配到定额" description={result.quotaMatch.issues.join('；') || '候选为空或模型未选择定额。'} />
                ) : (
                  <div className="space-y-2">
                    {result.quotaMatch.matches.map((match, index) => (
                      <div key={`${match.dekid}-${match.dezmid}-${index}`} className="rounded border border-emerald-100 bg-emerald-50/50 px-3 py-2 text-xs">
                        <div className="flex items-start gap-2">
                          <div className="min-w-0 flex-1">
                            <div className="font-mono font-semibold text-emerald-800">{match.zmbh || '-'}</div>
                            <div className="mt-0.5 font-medium text-gray-900">{match.zmmc || '-'}</div>
                          </div>
                          <span className="shrink-0 rounded bg-white px-1.5 py-0.5 text-[11px] text-gray-600">
                            置信度 {confidenceLabel(match.confidence)}
                          </span>
                        </div>
                        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-gray-500">
                          <span>单位：{match.dw || '-'}</span>
                          <span>系数：{match.qty_factor}</span>
                          {match.library_name && <span>{match.library_name}</span>}
                        </div>
                        {match.match_reason && <div className="mt-1 text-gray-600">{match.match_reason}</div>}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <h4 className="mb-2 text-xs font-semibold text-gray-900">组合换算</h4>
                {result.conversionChecking && conversionItems.length === 0 ? (
                  <ResultEmptyState title="组合换算中" description="正在根据已确认定额查询组合定额规则并识别数量特征。" />
                ) : conversionItems.length === 0 ? (
                  <ResultEmptyState title="待组合换算" description="确认定额后会展示组合定额、特征值和计算次数。" />
                ) : (
                  <div className="space-y-2">
                    {result.conversionChecking && !hasFinalConversion && (
                      <div className="rounded border border-cyan-100 bg-cyan-50 px-3 py-2 text-xs text-cyan-800">
                        已查询组合定额，正在识别项目特征数量。
                      </div>
                    )}
                    <ComboQuotaOnlyList items={conversionItems} preview={!hasFinalConversion} />
                  </div>
                )}
              </div>
            </div>

            <div className="space-y-4">
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <h4 className="text-xs font-semibold text-gray-900">工料机明细</h4>
                  <span className="text-xs text-gray-500">{resourceGroups.length} 个定额 / {resourceCount} 条</span>
                </div>
                <ResourceGroups groups={resourceGroups} />
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}

async function fetchLatestRunsFallback(taskId: number, boqItems: BoqItem[]) {
  const entries: Array<[number, ItemResult]> = []
  const batchSize = 12

  for (let i = 0; i < boqItems.length; i += batchSize) {
    const batch = boqItems.slice(i, i + batchSize)
    const results = await Promise.all(
      batch.map(async item => {
        try {
          const runs = await fetchPricingTaskItemRuns(taskId, item.id)
          return runs.length > 0 ? ([item.id, runToResult(runs[0])] as [number, ItemResult]) : null
        } catch {
          return null
        }
      }),
    )
    for (const result of results) {
      if (result) entries.push(result)
    }
  }

  return entries
}

function AccuracyReportPanel({
  report,
  error,
  dark = false,
}: {
  report: PricingTask['accuracy_report']
  error?: string
  dark?: boolean
}) {
  if (!report && !error) return null

  const metrics = report?.metrics
  const shell = dark
    ? 'border-cyan-300/15 bg-slate-950/70 text-slate-200 shadow-[0_18px_60px_rgba(8,47,73,0.25)]'
    : 'border-gray-200 bg-white text-gray-700 shadow-sm'
  const muted = dark ? 'text-slate-400' : 'text-gray-500'
  const heading = dark ? 'text-slate-100' : 'text-gray-900'
  const chip = dark
    ? 'border-cyan-300/20 bg-cyan-400/10 text-cyan-100'
    : 'border-blue-100 bg-blue-50 text-blue-700'
  const section = dark ? 'border-slate-700/70 bg-slate-900/70' : 'border-gray-100 bg-gray-50'

  const list = (title: string, values?: string[]) => (
    values && values.length > 0 ? (
      <div className={`rounded-md border p-3 ${section}`}>
        <div className={`mb-2 text-xs font-semibold ${heading}`}>{title}</div>
        <ul className="space-y-1 text-xs leading-5">
          {values.map((item, index) => <li key={index}>• {item}</li>)}
        </ul>
      </div>
    ) : null
  )

  return (
    <div className={`rounded-lg border p-4 ${shell}`}>
      {error && (
        <div className={`mb-3 rounded border px-3 py-2 text-xs ${dark ? 'border-rose-400/30 bg-rose-500/10 text-rose-100' : 'border-red-200 bg-red-50 text-red-700'}`}>
          {error}
        </div>
      )}
      {report && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className={`text-sm font-semibold ${heading}`}>智能组价对比一致性分析报告</div>
              <p className={`mt-1 max-w-4xl text-xs leading-5 ${muted}`}>{report.summary}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className={`rounded-full border px-2.5 py-1 font-semibold ${chip}`}>等级：{report.accuracy_level}</span>
              {report.accuracy_rate != null && (
                <span className={`rounded-full border px-2.5 py-1 font-semibold ${chip}`}>对比一致率 {formatPercent(report.accuracy_rate)}</span>
              )}
            </div>
          </div>

          {metrics && (
            <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-4 lg:grid-cols-8">
              {[
                ['已评估', `${metrics.evaluated_item_count ?? 0}/${metrics.total_items ?? 0}`],
                ['人工定额', metrics.manual_count],
                ['AI 定额', metrics.ai_count],
                ['双方一致', metrics.hit_count],
                ['仅人工', metrics.missed_count],
                ['仅AI', metrics.extra_count],
                ['完全一致', metrics.exact_item_count ?? 0],
                ['生成时间', report.generated_at ? new Date(report.generated_at).toLocaleString() : '-'],
              ].map(([label, value]) => (
                <div key={String(label)} className={`rounded-md border px-3 py-2 ${section}`}>
                  <div className={muted}>{label}</div>
                  <div className={`mt-1 font-semibold ${heading}`}>{value}</div>
                </div>
              ))}
            </div>
          )}

          <div className="grid gap-3 lg:grid-cols-2">
            {list('关键发现', report.key_findings)}
            {list('风险清单类型', report.risk_items)}
            {list('代表性样例', report.representative_examples)}
            {list('复核与优化建议', report.business_recommendations)}
          </div>

          <div className="grid gap-3 text-xs leading-5 lg:grid-cols-3">
            {report.matched_analysis && <div className={`rounded-md border p-3 ${section}`}><span className={`font-semibold ${heading}`}>一致项分析：</span>{report.matched_analysis}</div>}
            {report.missed_analysis && <div className={`rounded-md border p-3 ${section}`}><span className={`font-semibold ${heading}`}>仅人工差异：</span>{report.missed_analysis}</div>}
            {report.extra_analysis && <div className={`rounded-md border p-3 ${section}`}><span className={`font-semibold ${heading}`}>仅AI差异：</span>{report.extra_analysis}</div>}
          </div>

          {report.conclusion && (
            <div className={`rounded-md border p-3 text-xs leading-5 ${section}`}>
              <span className={`font-semibold ${heading}`}>总体结论：</span>{report.conclusion}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function DetailReportPanel({ report }: { report: PricingTaskDetailReport }) {
  const metrics = report.metrics
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')

  async function downloadExcel() {
    setExporting(true)
    setExportError('')
    try {
      const blob = await exportPricingTaskDetailReportExcel(report.task.id)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `单条组价明细报表-${report.task.id}.xlsx`
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setExportError(err instanceof Error ? err.message : 'Excel导出失败')
    } finally {
      setExporting(false)
    }
  }

  const quotaList = (items: Array<{ code: string; name: string; analysis: string; in_manual?: boolean; in_ai?: boolean }>, empty: string) => (
    items.length === 0 ? (
      <div className="rounded border border-gray-100 bg-gray-50 px-3 py-2 text-xs text-gray-400">{empty}</div>
    ) : (
      <div className="space-y-1.5">
        {items.map((item, index) => {
          const hit = item.in_manual ?? item.in_ai
          return (
            <div key={`${item.code}-${index}`} className="rounded border border-gray-100 bg-white px-3 py-2 text-xs">
              <div className="flex items-start gap-2">
                <span className="font-mono font-semibold text-gray-800">{item.code || '-'}</span>
                <span className="min-w-0 flex-1 text-gray-900">{item.name || '-'}</span>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${hit ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
                  {hit ? '命中' : '差异'}
                </span>
              </div>
              <div className="mt-1 text-gray-500">{item.analysis}</div>
            </div>
          )
        })}
      </div>
    )
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-gray-900">单条组价明细报表</div>
          <div className="mt-1 text-xs text-gray-500">
            {report.task.name} · {report.generated_at ? new Date(report.generated_at).toLocaleString() : '-'}
          </div>
        </div>
        <button
          type="button"
          onClick={() => void downloadExcel()}
          disabled={exporting}
          className="rounded border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-600 hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
        >
          {exporting ? '导出中...' : '导出 Excel'}
        </button>
      </div>

      {exportError && (
        <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {exportError}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-6">
        {[
          ['清单数', metrics.total_items],
          ['已对比', metrics.evaluated_item_count],
          ['一致', metrics.consistent_item_count],
          ['部分一致', metrics.partial_item_count],
          ['不一致', metrics.inconsistent_item_count],
          ['对比一致率', formatPercent(metrics.hit_rate)],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded border border-gray-100 bg-gray-50 px-3 py-2">
            <div className="text-gray-500">{label}</div>
            <div className="mt-1 font-semibold text-gray-900">{value}</div>
          </div>
        ))}
      </div>

      <div className="space-y-4">
        {report.items.map(item => (
          <section key={item.run_id} className="rounded-lg border border-gray-200 bg-white">
            <div className="border-b border-gray-100 px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-mono text-xs text-gray-500">{item.item.item_code}</div>
                  <div className="mt-0.5 font-semibold text-gray-900">{item.item.item_name}</div>
                  {item.item.item_description && (
                    <div className="mt-1 line-clamp-2 text-xs text-gray-500">{item.item.item_description}</div>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className={`rounded-full px-2.5 py-1 font-semibold ${
                    item.consistency.status === '一致'
                      ? 'bg-emerald-50 text-emerald-700'
                      : item.consistency.status === '部分一致'
                        ? 'bg-amber-50 text-amber-700'
                        : 'bg-rose-50 text-rose-700'
                  }`}>
                    {item.consistency.status}
                  </span>
                  <span className="rounded-full bg-gray-50 px-2.5 py-1 text-gray-500">
                    双方一致 {item.consistency.hit_count} / 仅人工 {item.consistency.missed_count} / 仅AI {item.consistency.extra_count}
                  </span>
                </div>
              </div>
              <div className="mt-2 text-xs text-gray-600">{item.consistency.summary}</div>
            </div>

            <div className="grid gap-4 p-4 lg:grid-cols-2">
              <div>
                <div className="mb-2 text-xs font-semibold text-gray-700">AI套定额结果</div>
                {quotaList(item.ai_quota_results, '暂无AI套定额结果')}
              </div>
              <div>
                <div className="mb-2 text-xs font-semibold text-gray-700">人工套定额结果</div>
                {quotaList(item.manual_quota_results, '暂无人工套定额结果')}
              </div>
            </div>

            <div className="border-t border-gray-100 px-4 py-3">
              <div className="mb-2 text-xs font-semibold text-gray-700">每轮结果</div>
              <div className="space-y-2">
                {item.rounds.map(round => (
                  <details key={round.step_no} className="rounded border border-gray-100 bg-gray-50 px-3 py-2 text-xs">
                    <summary className="cursor-pointer font-medium text-gray-700">
                      {round.step_no}. {round.name}
                      {round.duration_ms != null && <span className="ml-2 text-gray-400">{formatDuration(round.duration_ms)}</span>}
                    </summary>
                    <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded bg-white p-2 text-[11px] leading-5 text-gray-600">
                      {JSON.stringify(round.data ?? {}, null, 2)}
                    </pre>
                  </details>
                ))}
              </div>
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}

export default function PricingTaskDetailPage() {
  const params = useParams()
  const taskId = Number(params.tid)

  const [task, setTask] = useState<PricingTask | null>(null)
  const [items, setItems] = useState<BoqItem[]>([])
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null)
  const [expandedItemId, setExpandedItemId] = useState<number | null>(null)
  const [quotaCandidatesExpanded, setQuotaCandidatesExpanded] = useState(false)
  const [loading, setLoading] = useState(true)
  const [itemResults, setItemResults] = useState<Map<number, ItemResult>>(new Map())
  const [actionBusy, setActionBusy] = useState(false)
  const [editingFeatureItem, setEditingFeatureItem] = useState<BoqItem | null>(null)
  const [editingFeatureText, setEditingFeatureText] = useState('')
  const [featureSaving, setFeatureSaving] = useState(false)
  const [featureEditError, setFeatureEditError] = useState('')
  const [featureImages, setFeatureImages] = useState<Array<{ url: string; name: string; size: number }>>([])
  const [accuracyReportGenerating, setAccuracyReportGenerating] = useState(false)
  const [accuracyReportError, setAccuracyReportError] = useState('')
  const [showAccuracyReportModal, setShowAccuracyReportModal] = useState(false)
  const [showManualComparisonModal, setShowManualComparisonModal] = useState(false)
  const [detailReport, setDetailReport] = useState<PricingTaskDetailReport | null>(null)
  const [detailReportLoading, setDetailReportLoading] = useState(false)
  const [detailReportError, setDetailReportError] = useState('')
  const [showDetailReportModal, setShowDetailReportModal] = useState(false)
  const reasoningRef = useRef<HTMLDivElement>(null)

  const currentResult = selectedItemId ? itemResults.get(selectedItemId) : undefined
  const selectedItem = selectedItemId ? items.find(item => item.id === selectedItemId) : undefined
  const isRunning = Boolean(
    currentResult?.phase === 'reasoning'
      || currentResult?.autoConfirming
      || currentResult?.conversionChecking
      || currentResult?.coefficientChecking,
  )

  useEffect(() => {
    if (!Number.isFinite(taskId)) return
    void bootstrap()
  }, [taskId])

  useEffect(() => {
    if (reasoningRef.current) {
      reasoningRef.current.scrollTop = reasoningRef.current.scrollHeight
    }
  }, [currentResult?.reasoning])

  useEffect(() => {
    setQuotaCandidatesExpanded(false)
  }, [selectedItemId])

  useEffect(() => {
    return () => {
      featureImages.forEach(image => URL.revokeObjectURL(image.url))
    }
  }, [featureImages])

  async function bootstrap() {
    setLoading(true)
    try {
      const taskData = await fetchPricingTask(taskId)
      setTask(taskData)
      const boqItems = await fetchAllBoqItems(taskData.project_id)
      setItems(boqItems)
      try {
        const latestRuns = await fetchPricingTaskLatestRuns(taskData.id)
        setItemResults(() => {
          const next = new Map<number, ItemResult>()
          for (const itemRun of latestRuns) {
            next.set(itemRun.boq_item_id, runToResult(itemRun.run))
          }
          return next
        })
      } catch (err) {
        console.warn('加载最新组价状态失败', err)
        const fallbackRuns = await fetchLatestRunsFallback(taskData.id, boqItems)
        if (fallbackRuns.length > 0) {
          setItemResults(new Map(fallbackRuns))
        }
      }
    } finally {
      setLoading(false)
    }
  }

  function updateResult(itemId: number, updater: (prev: ItemResult) => ItemResult) {
    setItemResults(m => {
      const prev = m.get(itemId) ?? { phase: 'reasoning', reasoning: '' }
      return new Map(m).set(itemId, updater(prev))
    })
  }

  function handleManualComparisonUpdated(evaluation: PricingTaskEvaluation) {
    if (selectedItemId == null) return
    updateResult(selectedItemId, current => ({ ...current, evaluation }))
    setTask(current => current ? { ...current, accuracy_report: null } : current)
  }

  function openFeatureEditor(item: BoqItem) {
    setEditingFeatureItem(item)
    setEditingFeatureText(item.item_description ?? '')
    setFeatureEditError('')
    clearFeatureImages()
  }

  function closeFeatureEditor() {
    setEditingFeatureItem(null)
    setFeatureEditError('')
    clearFeatureImages()
  }

  function clearFeatureImages() {
    setFeatureImages(current => {
      current.forEach(image => URL.revokeObjectURL(image.url))
      return []
    })
  }

  function removeFeatureImage(index: number) {
    setFeatureImages(current => {
      const image = current[index]
      if (image) URL.revokeObjectURL(image.url)
      return current.filter((_, i) => i !== index)
    })
  }

  function handleFeatureImageUpload(files: FileList | null) {
    if (!files || files.length === 0) return
    const next = Array.from(files).map(file => ({
      url: URL.createObjectURL(file),
      name: file.name,
      size: file.size,
    }))
    setFeatureImages(current => [...current, ...next])
  }

  async function saveFeatureEditor() {
    if (!editingFeatureItem) return
    setFeatureSaving(true)
    setFeatureEditError('')
    try {
      const updated = await updateBoqItemDescription(editingFeatureItem.id, editingFeatureText.trim() || null)
      setItems(prev => prev.map(item => item.id === updated.id ? updated : item))
      setEditingFeatureItem(updated)
      closeFeatureEditor()
      setEditingFeatureText('')
    } catch (err) {
      setFeatureEditError(err instanceof Error ? err.message : '保存项目特征失败')
    } finally {
      setFeatureSaving(false)
    }
  }

  async function loadLatestRun(itemId: number) {
    const existing = itemResults.get(itemId)
    if (existing?.phase === 'reasoning' || existing?.runId) return

    try {
      const runs = await fetchPricingTaskItemRuns(taskId, itemId)
      if (runs.length > 0) {
        setItemResults(m => new Map(m).set(itemId, runToResult(runs[0])))
      }
    } catch (err) {
      console.error('加载历史组价结果失败', err)
    }
  }

  async function autoConfirmAndContinue(runId: number, itemId: number, matches: QuotaMatch[]) {
    updateResult(itemId, s => ({
      ...s,
      autoConfirming: true,
      status: 'running',
      reasoning: `${s.reasoning}${s.reasoning ? '\n\n' : ''}【自动确认】已完成套定额，正在确认全部匹配定额并继续后续换算。\n`,
    }))
    try {
      await confirmPricingTaskRun(runId, matches)
      updateResult(itemId, s => ({ ...s, autoConfirming: false, phase: 'done', status: 'confirmed' }))
      await runConversionCheck(runId, itemId)
      await runCoefficientCheck(runId, itemId)
    } catch (err) {
      updateResult(itemId, s => ({
        ...s,
        autoConfirming: false,
        phase: 'error',
        status: 'failed',
        error: `自动确认定额失败：${err instanceof Error ? err.message : '未知错误'}`,
      }))
    }
  }

  async function handleMatch(itemId: number) {
    if (!task || isRunning) return
    setSelectedItemId(itemId)
    setItemResults(m => new Map(m).set(itemId, { phase: 'reasoning', reasoning: '', status: 'running', stepTimings: {} }))
    let streamRunId: number | null = null
    let matchedResults: QuotaMatch[] = []
    let streamCompleted = false

    try {
      await streamPricingTaskRunItem(task.id, itemId, (evt: PricingTaskEvent) => {
        if (evt.type === 'run_started') {
          streamRunId = evt.run_id
          updateResult(itemId, s => ({ ...s, runId: evt.run_id, status: 'running' }))
        } else if (evt.type === 'reasoning_token') {
          updateResult(itemId, s => ({ ...s, reasoning: s.reasoning + evt.token }))
        } else if (evt.type === 'code_check') {
          updateResult(itemId, s => ({
            ...s,
            codeCheck: {
              item_code: evt.item_code,
              item_name: evt.item_name,
              base_code: evt.base_code,
              standard_name: evt.standard_name,
              found: evt.found,
              is_consistent: evt.is_consistent,
            },
          }))
        } else if (evt.type === 'judgment') {
          updateResult(itemId, s => ({
            ...s,
            judgment: { is_consistent: evt.is_consistent, reasoning: evt.reasoning },
          }))
        } else if (evt.type === 'feature_check') {
          updateResult(itemId, s => ({
            ...s,
            featureCheck: {
              is_complete: evt.is_complete,
              missing_features: evt.missing_features,
              analysis: evt.analysis,
              original_description: evt.original_description,
              normalized_description: evt.normalized_description,
              effective_description: evt.effective_description ?? evt.normalized_description,
              default_fills: evt.default_fills ?? [],
              description_updated: false,
              schema_kb_version_id: evt.schema_kb_version_id,
              feature_schema: evt.feature_schema ?? [],
              default_candidates: evt.default_candidates ?? [],
              unresolved_features: evt.unresolved_features ?? [],
            },
          }))
        } else if (evt.type === 'chapter_rule_check') {
          updateResult(itemId, s => ({
            ...s,
            chapterRuleCheck: {
              available: evt.available,
              base_code: evt.base_code,
              kb_version_id: evt.kb_version_id,
              chapters: evt.chapters ?? [],
              project_items_checked: evt.project_items_checked ?? 0,
              rules: evt.rules ?? [],
              issues: evt.issues ?? [],
              validation: evt.validation ?? { status: 'pending', validations: [], issues: [] },
            },
          }))
        } else if (evt.type === 'quota_candidates') {
          updateResult(itemId, s => ({
            ...s,
            quotaCandidates: { item_code: evt.item_code, base_code: evt.base_code, candidates: evt.candidates, total: evt.total },
          }))
        } else if (evt.type === 'quota_match') {
          matchedResults = evt.matches
          updateResult(itemId, s => ({
            ...s,
            quotaMatch: { matches: evt.matches, issues: evt.issues },
          }))
        } else if (evt.type === 'evaluation') {
          updateResult(itemId, s => ({ ...s, evaluation: evt.evaluation }))
        } else if (evt.type === 'step_timing') {
          updateResult(itemId, s => ({
            ...s,
            stepTimings: { ...(s.stepTimings ?? {}), [String(evt.step_no)]: evt },
          }))
        } else if (evt.type === 'done') {
          streamRunId = evt.run_id ?? streamRunId
          streamCompleted = true
          updateResult(itemId, s => ({ ...s, phase: 'done', status: matchedResults.length > 0 ? 'running' : 'completed', runId: streamRunId ?? s.runId }))
        } else if (evt.type === 'error') {
          updateResult(itemId, s => ({ ...s, phase: 'error', status: 'failed', error: evt.error }))
        }
      })
      if (streamCompleted && streamRunId && matchedResults.length > 0) {
        await autoConfirmAndContinue(streamRunId, itemId, matchedResults)
      }
    } catch (err) {
      updateResult(itemId, s => ({
        ...s,
        phase: 'error',
        status: 'failed',
        error: err instanceof Error ? err.message : '未知错误',
      }))
    }
  }

  async function runConversionCheck(runId: number, itemId: number) {
    updateResult(itemId, s => ({ ...s, conversionChecking: true, conversionError: undefined }))
    try {
      await streamPricingTaskConversionCheck(runId, (evt: PricingTaskEvent) => {
        if (evt.type === 'conversion_check_start') {
          updateResult(itemId, s => ({
            ...s,
            conversionChecking: true,
            conversionError: undefined,
            reasoning: `${s.reasoning}${s.reasoning ? '\n\n' : ''}【第七轮 组合换算】\n`,
          }))
        } else if (evt.type === 'combo_adjustment_rules') {
          updateResult(itemId, s => ({
            ...s,
            comboAdjustmentPreview: evt.items,
            conversionChecking: true,
            reasoning: `${s.reasoning}${s.reasoning.endsWith('\n') || !s.reasoning ? '' : '\n'}已查询组合定额，正在识别项目特征数量。\n`,
          }))
        } else if (evt.type === 'reasoning_token') {
          updateResult(itemId, s => ({ ...s, reasoning: s.reasoning + evt.token }))
        } else if (evt.type === 'conversion_check') {
          updateResult(itemId, s => ({ ...s, conversionCheck: evt.conversion_check, comboAdjustmentPreview: evt.conversion_check.items, conversionChecking: false }))
        } else if (evt.type === 'step_timing') {
          updateResult(itemId, s => ({
            ...s,
            stepTimings: { ...(s.stepTimings ?? {}), [String(evt.step_no)]: evt },
          }))
        } else if (evt.type === 'done') {
          updateResult(itemId, s => ({ ...s, conversionChecking: false }))
        } else if (evt.type === 'error') {
          updateResult(itemId, s => ({
            ...s,
            conversionChecking: false,
            conversionError: evt.error,
          }))
        }
      })
    } catch (err) {
      updateResult(itemId, s => ({
        ...s,
        conversionChecking: false,
        conversionError: err instanceof Error ? err.message : '组合换算失败',
      }))
    }
  }

  async function runCoefficientCheck(runId: number, itemId: number) {
    updateResult(itemId, s => ({ ...s, coefficientChecking: true, coefficientError: undefined }))
    try {
      await streamPricingTaskCoefficientCheck(runId, (evt: PricingTaskEvent) => {
        if (evt.type === 'coefficient_check_start') {
          updateResult(itemId, s => ({
            ...s,
            coefficientChecking: true,
            coefficientError: undefined,
            reasoning: `${s.reasoning}${s.reasoning ? '\n\n' : ''}【第八轮 系数换算】\n`,
          }))
        } else if (evt.type === 'coefficient_rules') {
          updateResult(itemId, s => ({
            ...s,
            coefficientPreview: evt.items,
            coefficientChecking: true,
          }))
        } else if (evt.type === 'reasoning_token') {
          updateResult(itemId, s => ({ ...s, reasoning: s.reasoning + evt.token }))
        } else if (evt.type === 'coefficient_check') {
          updateResult(itemId, s => ({ ...s, coefficientCheck: evt.coefficient_check, coefficientPreview: evt.coefficient_check.items, coefficientChecking: false }))
        } else if (evt.type === 'step_timing') {
          updateResult(itemId, s => ({
            ...s,
            stepTimings: { ...(s.stepTimings ?? {}), [String(evt.step_no)]: evt },
          }))
        } else if (evt.type === 'done') {
          updateResult(itemId, s => ({ ...s, coefficientChecking: false }))
        } else if (evt.type === 'error') {
          updateResult(itemId, s => ({
            ...s,
            coefficientChecking: false,
            coefficientError: evt.error,
          }))
        }
      })
    } catch (err) {
      updateResult(itemId, s => ({
        ...s,
        coefficientChecking: false,
        coefficientError: err instanceof Error ? err.message : '系数换算失败',
      }))
    }
  }

  async function handleGenerateAccuracyReport() {
    if (!task) return
    setAccuracyReportGenerating(true)
    setAccuracyReportError('')
    setShowAccuracyReportModal(true)
    try {
      const report = await generatePricingTaskAccuracyReport(task.id)
      setTask({ ...task, accuracy_report: report })
    } catch (err) {
      setAccuracyReportError(err instanceof Error ? err.message : '准确性分析报告生成失败')
    } finally {
      setAccuracyReportGenerating(false)
    }
  }

  function handleOpenAccuracyReport() {
    setAccuracyReportError('')
    if (task?.accuracy_report) {
      setShowAccuracyReportModal(true)
      return
    }
    void handleGenerateAccuracyReport()
  }

  async function handleOpenDetailReport() {
    if (!task) return
    setShowDetailReportModal(true)
    setDetailReportError('')
    setDetailReportLoading(true)
    try {
      const report = await fetchPricingTaskDetailReport(task.id)
      setDetailReport(report)
    } catch (err) {
      setDetailReportError(err instanceof Error ? err.message : '明细报表加载失败')
    } finally {
      setDetailReportLoading(false)
    }
  }

  async function handleReject() {
    if (!selectedItemId || !currentResult?.runId) return
    setActionBusy(true)
    try {
      await rejectPricingTaskRun(currentResult.runId)
      updateResult(selectedItemId, s => ({ ...s, status: 'rejected' }))
    } finally {
      setActionBusy(false)
    }
  }

  if (loading || !task) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-500">加载中...</div>
      </div>
    )
  }

  const libraryNames = task.quota_library_names.length > 0 ? task.quota_library_names.join('、') : '全部定额库'
  const canReject = currentResult?.phase === 'done' && currentResult.runId && currentResult.status !== 'rejected' && !currentResult.autoConfirming && !currentResult.conversionChecking && !currentResult.coefficientChecking
  const currentActiveStepNo = activeStepNo(currentResult)
  const currentActiveStep = currentActiveStepNo == null
    ? undefined
    : stepBadges(currentResult).find(step => step.no === currentActiveStepNo)
  const isCurrentStepRunning = Boolean(
    currentResult?.phase === 'reasoning'
      || currentResult?.conversionChecking
      || currentResult?.coefficientChecking,
  )
  const quotaHitStats = buildQuotaHitStats(itemResults, items.length)

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200 px-6 py-3">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center gap-3">
              <Link href="/pricing-task" className="shrink-0 rounded border border-gray-300 px-2.5 py-1 text-xs text-gray-600 hover:bg-gray-50">
                返回单条列表
              </Link>
              <div className="truncate text-sm font-semibold text-gray-900" title={task.name}>
                {task.name}
              </div>
              <span className="shrink-0 rounded border border-sky-200 bg-sky-50 px-2 py-0.5 font-mono text-[11px] font-semibold text-sky-700">
                {'\u77e5\u8bc6\u5e93\u7248\u672c\uff1a'}{task.kb_version_id ?? '-'}
              </span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
              <span className="min-w-0 max-w-full truncate" title={task.project_name}>
                组价工程：{task.project_name}
              </span>
              <span className="min-w-0 max-w-full truncate" title={libraryNames}>
                定额库：{libraryNames}
              </span>
              {task.manual_project_id && (
                <span
                  className="min-w-0 max-w-full truncate"
                  title={task.manual_project_name || `#${task.manual_project_id}`}
                >
                  对比工程：{(task.manual_project_name || `#${task.manual_project_id}`).replace(/^工程名称[:：]\s*/, '')}
                </span>
              )}
            </div>
          </div>

          <div className="w-full lg:w-auto lg:flex-none">
            <div className="flex flex-wrap items-center gap-2 rounded-md border border-gray-200 bg-white px-2.5 py-2 shadow-sm shadow-gray-100/70 lg:justify-end">
              <div className="mr-1 min-w-24 rounded bg-gray-50 px-2.5 py-1.5">
                <div className="text-[11px] text-gray-500">对比一致率</div>
                <div className="mt-0.5 text-xs font-semibold leading-none text-gray-900">{formatPercent(quotaHitStats.hitRate)}</div>
              </div>
              <div className="flex items-center gap-3 text-xs text-gray-500">
                <span>
                  已评估 <span className="font-medium text-gray-800">{quotaHitStats.evaluatedItemCount}/{quotaHitStats.totalItems}</span>
                </span>
                <span>
                  人工 <span className="font-medium text-gray-800">{quotaHitStats.manualCount}</span>
                </span>
                <span>
                  双方一致 <span className="font-medium text-gray-800">{quotaHitStats.hitCount}</span>
                </span>
                <span>
                  仅人工 <span className="font-medium text-amber-700">{quotaHitStats.missedCount}</span>
                </span>
                <span>
                  仅AI <span className="font-medium text-rose-700">{quotaHitStats.extraCount}</span>
                </span>
                <span>
                  一致 <span className="font-medium text-gray-800">{quotaHitStats.exactItemCount}</span>
                </span>
              </div>
            </div>
            {quotaHitStats.manualCount === 0 && (
              <div className="mt-1 text-right text-xs text-gray-400">暂无人工套定额对比数据</div>
            )}
            <div className="mt-2 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => void handleOpenDetailReport()}
                disabled={detailReportLoading || quotaHitStats.evaluatedItemCount === 0}
                className="rounded border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {detailReportLoading ? '加载中...' : '组价明细报表'}
              </button>
              <button
                type="button"
                onClick={handleOpenAccuracyReport}
                disabled={accuracyReportGenerating || quotaHitStats.evaluatedItemCount === 0 || quotaHitStats.manualCount === 0}
                className="rounded border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {accuracyReportGenerating ? '生成中...' : task.accuracy_report ? '查看对比分析报告' : '生成准确性报告'}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto space-y-4 px-6 py-6">
        <div className="flex h-[calc(100vh-430px)] min-h-[420px] gap-6">
          <div className="w-80 bg-white rounded-lg shadow flex flex-col">
            <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-gray-900">清单项</h3>
                <div className="mt-1 flex items-center gap-1 text-[10px] text-gray-500">
                  <span>1编码</span>
                  <span>2特征</span>
                  <span>3工序</span>
                  <span>4候选</span>
                  <span>5结果</span>
                  <span>6对比</span>
                  <span>7组合</span>
                </div>
              </div>
              <span className="text-xs text-gray-500">{items.length} 条</span>
            </div>
            <div className="flex-1 overflow-y-auto">
              {items.length === 0 ? (
                <div className="p-4 text-center text-gray-500 text-sm">暂无清单项</div>
              ) : (
                <div className="divide-y divide-gray-200">
                  {items.map(item => {
                    const result = itemResults.get(item.id)
                    const selected = selectedItemId === item.id
                    const activeStep = activeStepNo(result)
                    const quotaHit = quotaHitBadge(result)
                    return (
                      <div
                        key={item.id}
                        className={`cursor-pointer transition-colors ${selected ? 'border-l-2 border-blue-700 bg-blue-50' : 'hover:bg-gray-50'}`}
                      >
                        <div
                          onClick={() => {
                            setSelectedItemId(item.id)
                            setExpandedItemId(expandedItemId === item.id ? null : item.id)
                            void loadLatestRun(item.id)
                          }}
                          className="px-4 py-3"
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-start gap-2">
                              <div className="flex-1 min-w-0">
                                <div className="font-mono text-xs text-gray-600">{item.item_code}</div>
                                <div className="text-sm font-medium text-gray-900 truncate">{item.item_name}</div>
                              </div>
                              {quotaHit && (
                                <span
                                  title={quotaHit.title}
                                  className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${quotaHit.className}`}
                                >
                                  {quotaHit.label}
                                </span>
                              )}
                            </div>
                            <div className="mt-2 flex items-center justify-between gap-2">
                              <div className="flex items-center gap-1">
                                {stepBadges(result).map(step => (
                                  <button
                                    type="button"
                                    key={step.no}
                                    title={`${step.no === 2 ? '点击编辑项目特征' : `${step.no}. ${step.title}`}${stepTiming(result, step.no) ? `，耗时 ${formatDuration(stepTiming(result, step.no)?.duration_ms)}` : ''}`}
                                    onClick={event => {
                                      event.stopPropagation()
                                      if (step.no === 2) openFeatureEditor(item)
                                    }}
                                    className={`inline-flex h-4 w-4 items-center justify-center rounded-full border text-[10px] font-bold ${stepBadgeClass(step.tone)} ${activeStep === step.no ? 'animate-pulse ring-2 ring-amber-300 ring-offset-1' : ''} ${step.no === 2 ? 'cursor-pointer hover:scale-110 hover:ring-2 hover:ring-blue-200' : 'cursor-default'}`}
                                  >
                                    {step.no}
                                  </button>
                                ))}
                              </div>
                              {result?.status && (
                                <div className="flex items-center gap-1.5 text-[11px]">
                                  <span className={`inline-flex items-center rounded-full border px-2 py-0.5 font-semibold ${statusClassName(result.status)}`}>
                                    {statusLabel(result.status)}
                                  </span>
                                  {result.quotaMatch && <span className="text-gray-500">{matchCountLabel(result)}</span>}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>

                        {expandedItemId === item.id && (
                          <div className="px-4 py-3 bg-gray-50 border-t border-gray-200 text-xs text-gray-700 space-y-2">
                            {item.item_description && <p><span className="font-medium">特征：</span>{item.item_description}</p>}
                            <p><span className="font-medium">单位：</span>{item.unit || '-'}</p>
                            {item.quantity && <p><span className="font-medium">工程量：</span>{item.quantity}</p>}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {selectedItemId && (
              <div className="px-4 py-4 border-t border-gray-200 bg-gray-50">
                <button
                  onClick={() => handleMatch(selectedItemId)}
                  disabled={isRunning}
                  className="w-full px-3 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors disabled:opacity-50"
                >
                  {isRunning ? '组价中...' : '执行单条组价'}
                </button>
              </div>
            )}
          </div>

          <div className="flex-1 bg-white rounded-lg shadow flex flex-col overflow-hidden">
            {!currentResult ? (
              <div className="flex-1 flex items-center justify-center text-gray-400 text-center">
                <div>
                  <p className="text-lg mb-2">请选择清单项</p>
                  <p className="text-sm">执行组价后会保存运行记录，结果需要人工确认后才生效。</p>
                </div>
              </div>
            ) : currentResult.phase === 'error' ? (
              <div className="flex-1 flex items-center justify-center p-6">
                <div className="text-center max-w-xl">
                  <p className="text-red-600 font-semibold mb-2">执行失败</p>
                  <p className="text-sm text-red-500 whitespace-pre-wrap">{currentResult.error}</p>
                </div>
              </div>
            ) : (
              <div className="flex-1 flex overflow-hidden">
                <div className="flex-1 flex flex-col overflow-hidden border-r border-gray-200">
                  <div className="px-4 py-3 border-b bg-amber-50 flex items-center justify-between flex-shrink-0">
                    <div className="text-amber-700 font-semibold text-sm">
                      AI 推理过程
                    </div>
                    {isCurrentStepRunning ? (
                      <div className="flex items-center gap-2 text-xs font-medium text-amber-700">
                        <span
                          className="inline-block h-4 w-4 rounded-full border-2 border-amber-200 border-t-amber-600 animate-spin"
                          title={currentActiveStep ? `第 ${currentActiveStep.no} 步：${currentActiveStep.title}` : '运行中'}
                        />
                        <span>
                          {currentActiveStep
                            ? `第 ${currentActiveStep.no} 步：${currentActiveStep.title}`
                            : '正在处理'}
                        </span>
                      </div>
                    ) : (
                      <span className="text-xs text-gray-500">{statusLabel(currentResult.status)}</span>
                    )}
                  </div>
                  <div ref={reasoningRef} className="flex-1 overflow-y-auto">
                    <div className="px-4 py-3 text-xs text-gray-600 whitespace-pre-wrap font-mono">
                      {currentResult.reasoning || (currentResult.phase === 'reasoning' ? '等待模型流式输出...' : '本轮没有流式推理文本，结果见右侧结构化卡片。')}
                    </div>
                  </div>
                </div>

                <div className="w-96 flex-shrink-0 overflow-y-auto">
                  {currentResult.codeCheck && (
                    <section className={`px-4 py-3 border-b ${currentResult.codeCheck.is_consistent ? 'bg-green-50 border-green-200' : 'bg-orange-50 border-orange-200'}`}>
                      <h4 className={`font-semibold text-sm mb-2 ${currentResult.codeCheck.is_consistent ? 'text-green-900' : 'text-orange-900'}`}>
                        1. 编码核查：{currentResult.codeCheck.is_consistent ? '名称一致' : '名称不一致'}
                        <StepDuration result={currentResult} stepNo={1} />
                      </h4>
                      <div className="space-y-1.5 text-xs">
                        <div className="grid grid-cols-[3rem_minmax(0,1fr)] items-start gap-2">
                          <span className="text-right text-gray-500">清单</span>
                          <div className="min-w-0">
                            <span className="font-medium text-gray-900">{currentResult.codeCheck.item_name || '-'}</span>
                            <span className="ml-2 font-mono font-semibold text-gray-700">{currentResult.codeCheck.item_code}</span>
                          </div>
                        </div>
                        <div className="grid grid-cols-[3rem_minmax(0,1fr)] items-start gap-2">
                          <span className="text-right text-gray-500">标准</span>
                          <div className="min-w-0">
                            {currentResult.codeCheck.found ? (
                              <span className="font-medium text-gray-900">{currentResult.codeCheck.standard_name || '-'}</span>
                            ) : (
                              <span className="text-orange-600">未找到</span>
                            )}
                            <span className="ml-2 font-mono text-gray-700">{currentResult.codeCheck.base_code}</span>
                          </div>
                        </div>
                        <div className="grid grid-cols-[3rem_minmax(0,1fr)] items-start gap-2">
                          <span className="text-right text-gray-500">结论</span>
                          <div className="leading-5">
                            <span className={`text-xs font-normal ${currentResult.codeCheck.is_consistent ? 'text-green-700' : 'text-orange-700'}`}>
                              {currentResult.codeCheck.is_consistent ? '编码与名称一致' : '编码与名称不一致或标准库未找到'}
                            </span>
                          </div>
                        </div>
                      </div>
                      <div className="hidden">
                        <div><span className="text-gray-600">原始编码：</span><span className="font-mono font-semibold">{currentResult.codeCheck.item_code}</span></div>
                        <div><span className="text-gray-600">基准编码：</span><span className="font-mono">{currentResult.codeCheck.base_code}</span></div>
                        <div><span className="text-gray-600">清单名称：</span>{currentResult.codeCheck.item_name}</div>
                        <div>
                          <span className="text-gray-600">标准名称：</span>
                          {currentResult.codeCheck.found ? currentResult.codeCheck.standard_name : <span className="text-orange-600">未找到</span>}
                        </div>
                        <div>
                          <span className="text-gray-600">核查结论：</span>
                          <span className={currentResult.codeCheck.is_consistent ? 'text-green-700 font-medium' : 'text-orange-700 font-medium'}>
                            {currentResult.codeCheck.is_consistent ? '清单编码与名称一致' : '清单编码与名称不一致或标准库未找到'}
                          </span>
                        </div>
                      </div>
                    </section>
                  )}

                  {currentResult.featureCheck && (
                    <section className={`px-4 py-4 border-b ${currentResult.featureCheck.is_complete ? 'bg-green-50 border-green-200' : 'bg-orange-50 border-orange-200'}`}>
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <h4 className={`font-semibold text-sm ${currentResult.featureCheck.is_complete ? 'text-green-900' : 'text-orange-900'}`}>
                          2. {currentResult.featureCheck.is_complete ? '项目特征完整' : '项目特征不完整'}
                          <StepDuration result={currentResult} stepNo={2} />
                        </h4>
                        {!currentResult.featureCheck.is_complete && selectedItem && (
                          <button
                            type="button"
                            onClick={() => openFeatureEditor(selectedItem)}
                            className="shrink-0 rounded border border-orange-200 bg-white px-2 py-1 text-xs font-medium text-orange-700 hover:bg-orange-50"
                          >
                            编辑项目特征
                          </button>
                        )}
                      </div>
                      {currentResult.featureCheck.missing_features.length > 0 && (
                        <ul className="text-xs text-orange-800 space-y-1 list-disc list-inside mb-2">
                          {currentResult.featureCheck.missing_features.map((f, i) => <li key={i}>{f}</li>)}
                        </ul>
                      )}
                      {(currentResult.featureCheck.feature_schema?.length ?? 0) > 0 && (
                        <details className="group mb-2 rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
                          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-slate-700 [&::-webkit-details-marker]:hidden">
                            <span className="font-medium">标准项目特征结构（{currentResult.featureCheck.feature_schema?.length ?? 0}）</span>
                            <span className="text-slate-500 group-open:hidden">展开</span>
                            <span className="hidden text-slate-500 group-open:inline">收起</span>
                          </summary>
                          <div className="mt-2 space-y-1.5">
                            {currentResult.featureCheck.feature_schema?.map((feature, i) => (
                              <div key={`${feature.feature_name}-${i}`} className="flex flex-wrap gap-x-2 gap-y-1 rounded bg-white px-2 py-1 text-slate-600">
                                <span className="font-medium text-slate-800">{feature.feature_name}</span>
                                <span>{feature.native_default_value ? `原生默认值：${feature.native_default_value}` : '未配置原生默认值'}</span>
                                <span className="text-slate-400">TQDK_TQDXMTZ</span>
                              </div>
                            ))}
                          </div>
                        </details>
                      )}
                      {(currentResult.featureCheck.default_candidates?.length ?? 0) > 0 && (
                        <details className="group mb-2 rounded border border-gray-200 bg-white px-3 py-2 text-xs">
                          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-gray-700 [&::-webkit-details-marker]:hidden">
                            <span className="font-medium">综合考虑默认值候选（{currentResult.featureCheck.default_candidates?.length ?? 0}）</span>
                            <span className="text-gray-500 group-open:hidden">展开</span>
                            <span className="hidden text-gray-500 group-open:inline">收起</span>
                          </summary>
                          <div className="mt-2 space-y-1.5">
                            {currentResult.featureCheck.default_candidates?.map(candidate => (
                              <div key={candidate.candidate_id} className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded bg-gray-50 px-2 py-1 text-gray-600">
                                <span className="font-medium text-gray-800">{candidate.feature_name}</span>
                                <span>{candidate.feature_value || '综合考虑'} → {candidate.default_value}</span>
                                <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${candidate.source === 'TQDK_TQDXMTZ' ? 'bg-emerald-100 text-emerald-700' : 'bg-blue-100 text-blue-700'}`}>
                                  {candidate.source === 'TQDK_TQDXMTZ' ? '原生默认值' : '补充默认值'}
                                </span>
                                {candidate.blocked_by_native_default && <span className="text-amber-700">同名特征已有原生默认值，不参与补全</span>}
                              </div>
                            ))}
                          </div>
                        </details>
                      )}
                      {(currentResult.featureCheck.default_fills?.length ?? 0) > 0 && (
                        <div className="mb-2 rounded border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-900">
                          <div className="mb-1 font-semibold">已生成本次组价有效特征，原始清单未修改</div>
                          <div className="space-y-1">
                            {currentResult.featureCheck.default_fills?.map(fill => (
                              <div key={fill.candidate_id} className="flex flex-wrap gap-x-2 gap-y-1">
                                <span className="font-medium">{fill.target_feature_name}</span>
                                <span>{fill.original_value || '综合考虑'} → {fill.default_value}</span>
                                <span className="text-blue-600">来源：{fill.source === 'TQDK_TQDXMTZ' ? 'TQDK_TQDXMTZ' : 'tqdk_tzhkl'}</span>
                              </div>
                            ))}
                          </div>
                          {currentResult.featureCheck.effective_description && (
                            <div className="mt-2 whitespace-pre-wrap rounded bg-white/70 px-2 py-1 text-blue-800">
                              {currentResult.featureCheck.effective_description}
                            </div>
                          )}
                        </div>
                      )}
                      {(currentResult.featureCheck.unresolved_features?.length ?? 0) > 0 && (
                        <div className="mb-2 text-xs text-amber-800">未补全特征：{currentResult.featureCheck.unresolved_features?.join('、')}</div>
                      )}
                      <p className="text-xs text-gray-600">{currentResult.featureCheck.analysis}</p>
                    </section>
                  )}

                  {currentResult.chapterRuleCheck && (
                    <section className={`px-4 py-4 border-b ${currentResult.chapterRuleCheck.validation?.status === 'failed' ? 'bg-red-50 border-red-200' : currentResult.chapterRuleCheck.validation?.status === 'manual_review' ? 'bg-amber-50 border-amber-200' : 'bg-sky-50 border-sky-200'}`}>
                      <h4 className="font-semibold text-sm text-sky-900 mb-2">
                        3. 章节规则校验<StepDuration result={currentResult} stepNo={3} />
                      </h4>
                      {!currentResult.chapterRuleCheck.available ? (
                        <p className="text-xs text-slate-600">未找到该清单对应的章节说明规则。</p>
                      ) : (
                        <>
                          <p className="mb-2 text-xs text-sky-800">章节：{currentResult.chapterRuleCheck.chapters.map(chapter => chapter.chapter_name).join(' / ')}</p>
                          {currentResult.chapterRuleCheck.project_items_checked > 0 && <p className="mb-2 text-xs text-sky-700">已核查全工程清单索引：{currentResult.chapterRuleCheck.project_items_checked} 条</p>}
                          {currentResult.chapterRuleCheck.rules.length === 0 ? (
                            <p className="text-xs text-slate-600">章节规则均未命中。</p>
                          ) : (
                            <div className="space-y-2 text-xs">
                              {currentResult.chapterRuleCheck.rules.map((rule, index) => (
                                <div key={`${rule.chapter_id}-${rule.rule_reference}-${index}`} className={`rounded border bg-white px-3 py-2 ${rule.matched ? 'border-sky-200' : 'border-slate-200'}`}>
                                  <div className="flex items-center gap-2">
                                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${rule.matched ? 'bg-sky-100 text-sky-700' : 'bg-slate-100 text-slate-600'}`}>{rule.matched ? '已命中' : '未命中'}</span>
                                    <span className="font-medium text-slate-900">{rule.rule_reference || '章节规则'}</span>
                                  </div>
                                  <p className="mt-1 whitespace-pre-wrap text-slate-600">{rule.rule_text}</p>
                                  <p className="mt-1 text-slate-700">{rule.action}</p>
                                  {rule.evidence && <p className="mt-1 text-slate-500">依据：{rule.evidence}</p>}
                                </div>
                              ))}
                            </div>
                          )}
                          {currentResult.chapterRuleCheck.validation?.validations.length > 0 && (
                            <div className="mt-3 space-y-1 text-xs">
                              {currentResult.chapterRuleCheck.validation.validations.map((validation, index) => (
                                <p key={`${validation.rule_index}-${index}`} className={validation.status === 'failed' ? 'text-red-700' : validation.status === 'passed' ? 'text-green-700' : 'text-amber-700'}>
                                  {validation.status === 'passed' ? '已落实' : validation.status === 'failed' ? '未通过' : '需复核'}：{validation.message || validation.evidence}
                                </p>
                              ))}
                            </div>
                          )}
                        </>
                      )}
                      {(currentResult.chapterRuleCheck.issues?.length ?? 0) > 0 && <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-amber-700">{currentResult.chapterRuleCheck.issues.map((issue, index) => <li key={index}>{issue}</li>)}</ul>}
                    </section>
                  )}

                  {currentResult.quotaCandidates && (
                    <section className="px-4 py-4 border-b bg-slate-50 border-slate-200">
                      <button
                        type="button"
                        onClick={() => setQuotaCandidatesExpanded(v => !v)}
                        className="w-full flex items-center justify-between text-left"
                      >
                        <h4 className="font-semibold text-sm text-slate-900">
                          4. 定额候选子目 <span className="text-xs font-normal text-slate-500">共 {currentResult.quotaCandidates.total} 条</span>
                          <StepDuration result={currentResult} stepNo={4} />
                        </h4>
                        <span className="text-xs text-slate-500">{quotaCandidatesExpanded ? '收起' : '展开'}</span>
                      </button>
                      {quotaCandidatesExpanded && (
                        <div className="mt-2">
                          {currentResult.quotaCandidates.total === 0 ? (
                            <p className="text-xs text-slate-400">未找到候选定额子目</p>
                          ) : (
                            <div className="space-y-1 text-xs">
                              {currentResult.quotaCandidates.candidates.map((c, i) => (
                                <div key={`${c.dezmid ?? c.zmbh}-${i}`} className="bg-white border border-slate-200 rounded px-3 py-2">
                                  <div className="flex items-center gap-2 mb-0.5">
                                    <span className="font-mono text-slate-500">{c.zmbh}</span>
                                    <span className="font-medium text-slate-900">{c.zmmc}</span>
                                    <span className="text-slate-400 ml-auto flex-shrink-0">{c.dw}</span>
                                  </div>
                                  {c.library_name && <div className="text-slate-400">{c.library_name}{c.chapter_name ? ` / ${c.chapter_name}` : ''}</div>}
                                  {c.gznr && <div className="text-slate-500 line-clamp-2">{c.gznr}</div>}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </section>
                  )}

                  {currentResult.quotaMatch && (
                    <section className="px-4 py-4 border-b bg-emerald-50 border-emerald-200">
                      <h4 className="font-semibold text-sm text-emerald-900 mb-3">
                        5. 套定额结果 <span className="text-xs font-normal text-emerald-600">{currentResult.quotaMatch.matches.length} 条匹配</span>
                        <StepDuration result={currentResult} stepNo={5} />
                      </h4>
                      {currentResult.quotaMatch.matches.length === 0 ? (
                        <p className="text-xs text-gray-400">未找到匹配定额</p>
                      ) : (
                        <div className="space-y-2 text-xs mb-3">
                          {currentResult.quotaMatch.matches.map((m, i) => {
                            const confColor = m.confidence === 'high' ? 'bg-green-100 text-green-800' : m.confidence === 'medium' ? 'bg-amber-100 text-amber-800' : 'bg-red-100 text-red-800'
                            const confLabel = m.confidence === 'high' ? '高' : m.confidence === 'medium' ? '中' : '低'
                            return (
                              <div key={`${m.dezmid ?? m.zmbh}-${i}`} className="bg-white border border-emerald-200 rounded px-3 py-2">
                                <div className="flex items-center gap-2 mb-1">
                                  <span className="font-mono text-emerald-700 font-semibold">{m.zmbh}</span>
                                  <span className="font-medium text-gray-900">{m.zmmc}</span>
                                  {m.qty_factor !== 1 && <span className="text-gray-500 ml-1">x{m.qty_factor}</span>}
                                  <span className={`ml-auto px-1.5 py-0.5 rounded text-[10px] font-bold flex-shrink-0 ${confColor}`}>{confLabel}</span>
                                </div>
                                {m.library_name && <p className="text-gray-400 mb-1">{m.library_name}{m.chapter_name ? ` / ${m.chapter_name}` : ''}</p>}
                                <p className="text-gray-500">{m.match_reason}</p>
                              </div>
                            )
                          })}
                        </div>
                      )}
                      {currentResult.quotaMatch.issues.length > 0 && (
                        <div className="mt-2">
                          <div className="text-xs font-semibold text-amber-700 mb-1">模型提示的问题</div>
                          <ul className="text-xs text-amber-700 space-y-0.5 list-disc list-inside">
                            {currentResult.quotaMatch.issues.map((issue, i) => <li key={i}>{issue}</li>)}
                          </ul>
                        </div>
                      )}
                    </section>
                  )}

                  {currentResult.evaluation && (
                    <section className="px-4 py-4 border-b bg-purple-50 border-purple-200">
                      <h4 className="font-semibold text-sm text-purple-900 mb-2">6. 人工对比一致性<StepDuration result={currentResult} stepNo={6} /></h4>
                      <div className="grid grid-cols-3 gap-2 text-xs mb-2">
                        <div className="bg-white rounded p-2 text-center"><div className="font-semibold">{currentResult.evaluation.hit_count}</div><div className="text-gray-500">双方一致</div></div>
                        <div className="bg-white rounded p-2 text-center"><div className="font-semibold">{currentResult.evaluation.missed_count}</div><div className="text-gray-500">仅人工</div></div>
                        <div className="bg-white rounded p-2 text-center"><div className="font-semibold">{currentResult.evaluation.extra_count}</div><div className="text-gray-500">仅AI</div></div>
                      </div>
                      {currentResult.evaluation.missed_codes.length > 0 && (
                        <p className="text-xs text-purple-700">仅人工：{currentResult.evaluation.missed_codes.join('、')}</p>
                      )}
                      {task.manual_project_id && currentResult.runId && currentResult.quotaMatch
                        && (currentResult.evaluation.missed_count > 0 || currentResult.evaluation.extra_count > 0) && (
                        <button
                          type="button"
                          onClick={() => setShowManualComparisonModal(true)}
                          className="mt-3 rounded border border-purple-300 bg-white px-3 py-1.5 text-xs font-medium text-purple-700 hover:border-purple-400 hover:bg-purple-100"
                        >
                          复核差异并修正人工工程
                        </button>
                      )}
                      <div className="mt-3">
                        <div className="text-xs font-semibold text-purple-900 mb-2">
                          人工套定额明细
                          <span className="ml-1 font-normal text-purple-500">
                            {currentResult.evaluation.manual_quotas.length} 条
                          </span>
                        </div>
                        {currentResult.evaluation.manual_quotas.length === 0 ? (
                          <p className="text-xs text-purple-500">未找到人工套定额明细</p>
                        ) : (
                          <div className="space-y-2">
                            {currentResult.evaluation.manual_quotas.map((q, i) => {
                              const manualCode = q.quota_code || ''
                              const isHit = currentResult.evaluation!.hit_codes.some(aiCode => manualCode.includes(aiCode))
                              return (
                                <div key={`${manualCode}-${i}`} className="bg-white border border-purple-100 rounded px-3 py-2 text-xs">
                                  <div className="flex items-center gap-2 mb-1">
                                    <span className="font-mono font-semibold text-purple-800">{manualCode || '-'}</span>
                                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${isHit ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                                      {isHit ? '双方一致' : '仅人工'}
                                    </span>
                                  </div>
                                  <div className="font-medium text-gray-900 break-words">{q.quota_name || '-'}</div>
                                  <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-gray-500">
                                    <span>单位：{q.quota_unit || '-'}</span>
                                    <span>工程量：{q.quantity ?? '-'}</span>
                                    <span>系数：{q.qty_factor ?? '-'}</span>
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        )}
                      </div>
                    </section>
                  )}

                  {(currentResult.conversionChecking || currentResult.conversionCheck || currentResult.conversionError) && (
                    <section className="px-4 py-4 border-b bg-cyan-50 border-cyan-200">
                      <div className="mb-3 flex items-center justify-between">
                        <h4 className="font-semibold text-sm text-cyan-900">7. 组合换算<StepDuration result={currentResult} stepNo={7} /></h4>
                        {currentResult.conversionChecking && (
                          <span className="inline-block h-4 w-4 rounded-full border-2 border-cyan-200 border-t-cyan-700 animate-spin" title="组合换算运行中" />
                        )}
                      </div>
                      {currentResult.conversionError && (
                        <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                          组合换算失败：{currentResult.conversionError}
                        </div>
                      )}
                      {currentResult.conversionChecking && !currentResult.conversionCheck && (
                        <p className="text-xs text-cyan-700">
                          {currentResult.comboAdjustmentPreview ? '已查询组合定额，正在识别项目特征数量。' : '正在根据已确认定额查询组合定额规则...'}
                        </p>
                      )}
                      {(currentResult.conversionCheck || currentResult.comboAdjustmentPreview) && (
                        <div className="space-y-3 text-xs">
                          {currentResult.comboAdjustmentPreview && !currentResult.conversionCheck && (
                            <div>
                              <div className="mb-2 font-semibold text-cyan-900">组合定额列表</div>
                              <ComboConversionList items={currentResult.comboAdjustmentPreview} preview />
                            </div>
                          )}
                          {currentResult.conversionCheck && (
                            <>
                          <div className="grid grid-cols-2 gap-2">
                            <div className="rounded bg-white p-2 text-center">
                              <div className="font-semibold text-amber-700">{currentResult.conversionCheck.items.filter(item => item.needs_conversion).length}</div>
                              <div className="text-gray-500">有组合次数</div>
                            </div>
                            <div className="rounded bg-white p-2 text-center">
                              <div className="font-semibold text-emerald-700">{currentResult.conversionCheck.items.filter(item => !item.needs_conversion).length}</div>
                              <div className="text-gray-500">无组合次数</div>
                            </div>
                          </div>

                          {currentResult.conversionCheck.issues.length > 0 && (
                            <ul className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-amber-700 space-y-1 list-disc list-inside">
                              {currentResult.conversionCheck.issues.map((issue, i) => <li key={i}>{issue}</li>)}
                            </ul>
                          )}

                          <ComboConversionList items={currentResult.conversionCheck.items} />
                            </>
                          )}
                        </div>
                      )}
                    </section>
                  )}

                  {(currentResult.coefficientChecking || currentResult.coefficientCheck || currentResult.coefficientPreview || currentResult.coefficientError) && (
                    <section className="px-4 py-4 border-b bg-violet-50 border-violet-200">
                      <div className="mb-3 flex items-center justify-between">
                        <h4 className="font-semibold text-sm text-violet-900">8. 系数换算<StepDuration result={currentResult} stepNo={8} /></h4>
                        {currentResult.coefficientChecking && (
                          <span className="inline-block h-4 w-4 rounded-full border-2 border-violet-200 border-t-violet-700 animate-spin" title="系数换算运行中" />
                        )}
                      </div>
                      {currentResult.coefficientError && (
                        <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                          系数换算失败：{currentResult.coefficientError}
                        </div>
                      )}
                      {currentResult.coefficientChecking && !currentResult.coefficientCheck && (
                        <p className="mb-3 text-xs text-violet-700">已查询系数换算说明，正在识别项目特征和作用对象。</p>
                      )}
                      <CoefficientCheckList
                        items={currentResult.coefficientCheck?.items ?? currentResult.coefficientPreview ?? []}
                        preview={!currentResult.coefficientCheck}
                      />
                      {currentResult.coefficientCheck?.issues.length ? (
                        <ul className="mt-2 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 space-y-1 list-disc list-inside">
                          {currentResult.coefficientCheck.issues.map((issue, i) => <li key={i}>{issue}</li>)}
                        </ul>
                      ) : null}
                    </section>
                  )}

                  <section className="px-4 py-4 bg-white">
                    <div className="text-xs text-gray-500 mb-3">当前状态：{statusLabel(currentResult.status)}</div>
                    <div className="flex gap-2">
                      <div className="flex-1 rounded border border-emerald-200 bg-emerald-50 px-3 py-2">
                        <div className="text-xs font-semibold text-emerald-800">自动确认已启用</div>
                        <div className="mt-0.5 text-[11px] leading-4 text-emerald-700">
                          {currentResult.autoConfirming ? '正在自动确认全部匹配定额...' : currentResult.status === 'confirmed' ? '已自动确认全部定额，并连续执行后续换算。' : currentResult.phase === 'reasoning' || currentResult.quotaMatch?.matches.length ? '套定额完成后将自动确认并继续后续换算。' : '未匹配到可自动确认的定额，后续换算未执行。'}
                        </div>
                      </div>
                      <button
                        onClick={handleReject}
                        disabled={!canReject || actionBusy}
                        className="flex-1 px-3 py-2 bg-gray-600 text-white text-sm rounded hover:bg-gray-700 disabled:opacity-50"
                      >
                        驳回
                      </button>
                    </div>
                  </section>
                </div>
              </div>
            )}
          </div>
        </div>
        <SelectedItemResultPanel item={selectedItem} result={currentResult} />
      </div>
      {showManualComparisonModal && selectedItem && currentResult?.runId && currentResult.evaluation && currentResult.quotaMatch && (
        <ManualComparisonReviewModal
          key={currentResult.runId}
          open
          item={selectedItem}
          evaluation={currentResult.evaluation}
          matches={currentResult.quotaMatch.matches}
          submitReview={input => updatePricingTaskManualComparison(currentResult.runId!, input)}
          loadHistory={() => fetchPricingTaskManualComparisonHistory(currentResult.runId!)}
          onClose={() => setShowManualComparisonModal(false)}
          onUpdated={handleManualComparisonUpdated}
        />
      )}
      {showAccuracyReportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 py-6">
          <div className="flex max-h-[88vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl">
            <div className="flex items-center justify-between gap-3 border-b border-gray-200 px-5 py-4">
              <div>
                <div className="text-base font-semibold text-gray-900">智能组价对比一致性分析报告</div>
                <div className="mt-0.5 text-xs text-gray-500">基于当前任务最新组价结果与已复核人工基准生成。</div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void handleGenerateAccuracyReport()}
                  disabled={accuracyReportGenerating}
                  className="rounded border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-600 hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700 disabled:opacity-50"
                >
                  {accuracyReportGenerating ? '生成中...' : '重新生成'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowAccuracyReportModal(false)}
                  className="rounded border border-gray-200 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
                >
                  关闭
                </button>
              </div>
            </div>
            <div className="overflow-y-auto p-5">
              {accuracyReportGenerating && !task.accuracy_report ? (
                <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-10 text-center text-sm text-gray-500">
                  正在生成任务全集对比一致性分析报告...
                </div>
              ) : (
                <AccuracyReportPanel report={task.accuracy_report} error={accuracyReportError} />
              )}
            </div>
          </div>
        </div>
      )}

      {showDetailReportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 py-6">
          <div className="flex max-h-[88vh] w-full max-w-7xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl">
            <div className="flex items-center justify-between gap-3 border-b border-gray-200 px-5 py-4">
              <div>
                <div className="text-base font-semibold text-gray-900">单条组价明细报表</div>
                <div className="mt-0.5 text-xs text-gray-500">输出每条清单的每轮结果、AI套定额、人工套定额和一致性分析。</div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void handleOpenDetailReport()}
                  disabled={detailReportLoading}
                  className="rounded border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-600 hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700 disabled:opacity-50"
                >
                  {detailReportLoading ? '加载中...' : '刷新'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowDetailReportModal(false)}
                  className="rounded border border-gray-200 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
                >
                  关闭
                </button>
              </div>
            </div>
            <div className="overflow-y-auto p-5">
              {detailReportError && (
                <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                  {detailReportError}
                </div>
              )}
              {detailReportLoading && !detailReport ? (
                <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-10 text-center text-sm text-gray-500">
                  正在加载单条组价明细报表...
                </div>
              ) : detailReport ? (
                <DetailReportPanel report={detailReport} />
              ) : (
                <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-10 text-center text-sm text-gray-500">
                  暂无报表数据
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {editingFeatureItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/40 px-4" onClick={() => !featureSaving && closeFeatureEditor()}>
          <div className="w-full max-w-5xl rounded-lg bg-white shadow-2xl" onClick={event => event.stopPropagation()}>
            <div className="border-b border-gray-200 px-5 py-4">
              <div className="text-base font-semibold text-gray-900">编辑项目特征</div>
              <div className="mt-1 text-xs text-gray-500">
                {editingFeatureItem.item_code} {editingFeatureItem.item_name}
              </div>
            </div>
            <div className="grid gap-4 px-5 py-4 lg:grid-cols-[minmax(0,1fr)_360px]">
              <div>
                <label className="mb-2 block text-xs font-semibold text-gray-600">项目特征信息</label>
                <textarea
                  value={editingFeatureText}
                  onChange={event => setEditingFeatureText(event.target.value)}
                  disabled={featureSaving}
                  rows={14}
                  className="w-full resize-y rounded border border-gray-300 px-3 py-2 text-sm leading-6 text-gray-800 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:bg-gray-50"
                  placeholder="请输入项目特征信息"
                />
              </div>
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <label className="block text-xs font-semibold text-gray-600">图纸截图</label>
                  {featureImages.length > 0 && (
                    <button
                      type="button"
                      onClick={clearFeatureImages}
                      disabled={featureSaving}
                      className="text-xs text-red-600 hover:text-red-700 disabled:opacity-50"
                    >
                      清空图片
                    </button>
                  )}
                </div>
                <label className="flex cursor-pointer flex-col items-center justify-center rounded border border-dashed border-gray-300 bg-gray-50 px-4 py-6 text-center hover:border-blue-300 hover:bg-blue-50/50">
                  <input
                    type="file"
                    accept="image/*"
                    multiple
                    className="hidden"
                    disabled={featureSaving}
                    onChange={event => {
                      handleFeatureImageUpload(event.target.files)
                      event.currentTarget.value = ''
                    }}
                  />
                  <span className="text-sm font-medium text-gray-700">上传图片</span>
                  <span className="mt-1 text-xs text-gray-500">支持多张图纸截图，当前仅本地预览</span>
                </label>
                {featureImages.length > 0 ? (
                  <div className="mt-3 max-h-96 space-y-3 overflow-y-auto pr-1">
                    {featureImages.map((image, index) => (
                      <div key={`${image.url}-${index}`} className="overflow-hidden rounded border border-gray-200 bg-white">
                        <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2 text-xs">
                          <div className="min-w-0">
                            <div className="truncate font-medium text-gray-700">{index + 1}. {image.name}</div>
                            <div className="text-gray-500">{(image.size / 1024).toFixed(1)} KB</div>
                          </div>
                          <button
                            type="button"
                            onClick={() => removeFeatureImage(index)}
                            disabled={featureSaving}
                            className="ml-2 shrink-0 rounded border border-red-200 px-2 py-1 text-red-600 hover:bg-red-50 disabled:opacity-50"
                          >
                            移除
                          </button>
                        </div>
                        <img src={image.url} alt={image.name} className="max-h-72 w-full object-contain bg-gray-100" />
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-3 rounded border border-gray-200 bg-white px-3 py-8 text-center text-xs text-gray-400">
                    暂未上传图片
                  </div>
                )}
              </div>
              {featureEditError && (
                <div className="lg:col-span-2 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {featureEditError}
                </div>
              )}
            </div>
            <div className="flex items-center justify-between gap-3 border-t border-gray-200 bg-gray-50 px-5 py-4">
              <button
                type="button"
                onClick={() => setEditingFeatureText('')}
                disabled={featureSaving}
                className="rounded border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50"
              >
                清空
              </button>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={closeFeatureEditor}
                  disabled={featureSaving}
                  className="rounded border border-gray-300 bg-white px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => void saveFeatureEditor()}
                  disabled={featureSaving}
                  className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {featureSaving ? '保存中...' : '保存'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
