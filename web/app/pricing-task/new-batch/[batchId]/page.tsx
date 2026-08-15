'use client'

import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import {
  BoqItem,
  PricingTaskBatch,
  PricingTaskBatchItemRun,
  PricingTaskCoefficientCheck,
  PricingTaskChapterRuleCheck,
  PricingTaskConversionCheck,
  PricingTaskEvaluation,
  PricingTaskEvent,
  PricingTaskStepTiming,
  QuotaCandidate,
  QuotaMatch,
  exportNewPricingTaskBatchDetailReportExcel,
  fetchPricingTaskBatchDetail,
  fetchPricingTaskBatchManualComparisonHistory,
  streamPricingTaskBatchCoefficientCheck,
  streamPricingTaskBatchConversionCheck,
  streamPricingTaskBatchItemRun,
  updatePricingTaskBatchManualComparison,
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

interface FeatureCheck {
  is_complete: boolean
  missing_features: string[]
  analysis: string
  normalized_description?: string
  default_fills?: Array<{ feature_name: string; original_value: string; default_value: string; source_code: string; reason: string }>
  default_candidates?: Array<{ source_code: string; feature_name: string; feature_value: string; default_value: string; source_rowid?: number }>
  description_updated?: boolean
}

type ToolActivityStatus = 'running' | 'success' | 'error'

interface ToolActivity {
  id: string
  name: string
  status: ToolActivityStatus
  output?: string
  rows?: string[]
  durationMs?: number
}

interface ItemResult {
  phase: 'idle' | 'queued' | 'reasoning' | 'done' | 'error'
  toolActivities: ToolActivity[]
  runId?: number
  status?: string
  codeCheck?: CodeCheck
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
  coefficientError?: string
  stepTimings?: Record<string, PricingTaskStepTiming>
  error?: string
}

type BatchState = 'idle' | 'queued' | 'running' | 'succeeded' | 'failed'

type ResourceRow = NonNullable<PricingTaskConversionCheck['items'][number]['resources']>[number]
type CoefficientRules = PricingTaskCoefficientCheck['items'][number]['coefficient_rules']

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

const TOOL_NAMES: Record<string, string> = {
  code_check: 'check_item_code',
  feature_check: 'submit_feature_analysis',
  chapter_rule_check: 'submit_chapter_rule_check',
  quota_candidates: 'fetch_quota_candidates',
  quota_match: 'submit_quota_match',
  evaluation: 'evaluate_manual_comparison',
  conversion_check: 'check_combo_conversion',
  coefficient_check: 'check_resource_coefficient',
  execution: 'batch_pricing',
}

const TOOL_LABELS: Record<string, string> = {
  code_check: '编码核查',
  feature_check: '项目特征分析',
  chapter_rule_check: '章节规则校验',
  quota_candidates: '定额候选检索',
  quota_match: '定额匹配',
  evaluation: '人工对比评测',
  conversion_check: '组合定额换算',
  coefficient_check: '资源系数换算',
  execution: '批量组价执行',
}

const STEP_TOOL_IDS: Record<number, string> = {
  1: 'code_check',
  2: 'feature_check',
  3: 'chapter_rule_check',
  4: 'quota_candidates',
  5: 'quota_match',
  6: 'evaluation',
  7: 'conversion_check',
  8: 'coefficient_check',
}

type ToolActivityPatch = {
  id: string
  name?: string
  status?: ToolActivityStatus
  output?: string
  rows?: string[]
  durationMs?: number
}

function mergeToolActivities(current: ToolActivity[], ...patches: ToolActivityPatch[]) {
  const next = [...current]
  for (const patch of patches) {
    const index = next.findIndex(activity => activity.id === patch.id)
    const existing = index >= 0 ? next[index] : undefined
    const activity: ToolActivity = {
      id: patch.id,
      name: patch.name ?? existing?.name ?? TOOL_NAMES[patch.id] ?? patch.id,
      status: patch.status ?? existing?.status ?? 'running',
      output: patch.output ?? existing?.output,
      rows: patch.rows ?? existing?.rows,
      durationMs: patch.durationMs ?? existing?.durationMs,
    }
    if (index >= 0) next[index] = activity
    else next.push(activity)
  }
  return next
}

function withToolActivities(result: ItemResult, ...patches: ToolActivityPatch[]): ItemResult {
  return { ...result, toolActivities: mergeToolActivities(result.toolActivities, ...patches) }
}

function codeCheckOutput(check: CodeCheck) {
  if (!check.found) return '未找到对应的标准清单编码'
  return `${check.is_consistent ? '编码与名称一致' : '编码存在但名称不一致'}；标准名称：${check.standard_name || '-'}`
}

function featureCheckOutput(check: FeatureCheck) {
  const fills = check.default_fills?.length ?? 0
  const summary = check.is_complete
    ? '项目特征完整'
    : `缺少：${check.missing_features.join('、') || '未明确'}`
  return `${summary}${fills > 0 ? `；已补全 ${fills} 个“综合考虑”特征` : ''}${check.analysis ? `；${check.analysis}` : ''}`
}

function quotaMatchRows(matches: QuotaMatch[]) {
  return matches.map(match => `${match.zmbh || '-'}  ${match.zmmc || '-'}  × ${match.qty_factor ?? 1}`)
}

function evaluationOutput(evaluation: PricingTaskEvaluation) {
  const accuracy = evaluation.manual_count > 0
    ? `${((evaluation.hit_count / evaluation.manual_count) * 100).toFixed(1)}%`
    : '-'
  return `人工 ${evaluation.manual_count} 条，AI ${evaluation.ai_count} 条；命中 ${evaluation.hit_count}，遗漏 ${evaluation.missed_count}，额外 ${evaluation.extra_count}；准确率 ${accuracy}`
}

function conversionOutput(check: PricingTaskConversionCheck) {
  const ruleCount = check.items.reduce((sum, item) => sum + (item.adjustment_rules?.length ?? 0), 0)
  return `完成 ${check.items.length} 条定额检查，输出 ${ruleCount} 条组合换算规则`
}

function coefficientOutput(check: PricingTaskCoefficientCheck) {
  const ruleCount = check.items.reduce((sum, item) => sum + item.coefficient_rules.filter(rule => rule.matched).length, 0)
  return `完成 ${check.items.length} 条定额检查，命中 ${ruleCount} 条系数规则`
}

function restoredToolActivities(run: PricingTaskBatchItemRun['run']) {
  let result: ItemResult = {
    phase: run.status === 'failed' ? 'error' : 'done',
    toolActivities: [],
  }
  const timings = run.step_timings ?? {}
  const duration = (step: number) => timings[String(step)]?.duration_ms
  const codeCheck = run.code_check as CodeCheck | undefined
  const featureCheck = run.feature_check as FeatureCheck | undefined
  const chapterRuleCheck = run.chapter_rule_check ?? undefined
  const quotaCandidates = run.quota_candidates as ItemResult['quotaCandidates']
  const quotaMatch = run.quota_match as ItemResult['quotaMatch']
  const evaluation = run.evaluation ?? undefined

  if (codeCheck) result = withToolActivities(result, { id: 'code_check', status: 'success', output: codeCheckOutput(codeCheck), durationMs: duration(1) })
  if (featureCheck) result = withToolActivities(result, { id: 'feature_check', status: 'success', output: featureCheckOutput(featureCheck), durationMs: duration(2) })
  if (chapterRuleCheck) result = withToolActivities(result, { id: 'chapter_rule_check', status: chapterRuleCheck.validation?.status === 'failed' ? 'error' : 'success', output: `命中 ${chapterRuleCheck.rules.filter(rule => rule.matched).length} 条章节规则`, durationMs: duration(3) })
  if (quotaCandidates) result = withToolActivities(result, { id: 'quota_candidates', status: 'success', output: `检索到 ${quotaCandidates.total} 条候选定额`, durationMs: duration(4) })
  if (quotaMatch) {
    result = withToolActivities(result, {
      id: 'quota_match',
      status: 'success',
      output: `输出 ${quotaMatch.matches.length} 条定额${quotaMatch.issues.length > 0 ? `；提示 ${quotaMatch.issues.length} 条` : ''}`,
      rows: quotaMatchRows(quotaMatch.matches),
      durationMs: duration(5),
    })
  }
  if (evaluation) result = withToolActivities(result, { id: 'evaluation', status: 'success', output: evaluationOutput(evaluation), durationMs: duration(6) })
  if (run.conversion_check) result = withToolActivities(result, { id: 'conversion_check', status: 'success', output: conversionOutput(run.conversion_check), durationMs: duration(7) })
  if (run.coefficient_check) result = withToolActivities(result, { id: 'coefficient_check', status: 'success', output: coefficientOutput(run.coefficient_check), durationMs: duration(8) })

  if (run.status === 'running') {
    const sequence = ['code_check', 'feature_check', 'chapter_rule_check', 'quota_candidates', 'quota_match', 'evaluation']
    const nextId = sequence.find(id => !result.toolActivities.some(activity => activity.id === id))
    if (nextId) result = withToolActivities(result, { id: nextId, status: 'running' })
  }
  if (run.error_message) {
    result = withToolActivities(result, { id: 'execution', status: 'error', output: run.error_message })
  }
  return result.toolActivities
}

function runToResult(run: PricingTaskBatchItemRun['run']): ItemResult {
  return {
    phase: run.status === 'failed' ? 'error' : 'done',
    toolActivities: restoredToolActivities(run),
    runId: run.id,
    status: run.status,
    codeCheck: run.code_check as CodeCheck | undefined,
    featureCheck: run.feature_check as FeatureCheck | undefined,
    chapterRuleCheck: run.chapter_rule_check ?? undefined,
    quotaCandidates: run.quota_candidates as ItemResult['quotaCandidates'],
    quotaMatch: run.quota_match as ItemResult['quotaMatch'],
    evaluation: run.evaluation ?? undefined,
    conversionCheck: run.conversion_check ?? undefined,
    coefficientCheck: run.coefficient_check ?? undefined,
    stepTimings: run.step_timings ?? undefined,
    error: run.error_message || undefined,
  }
}

function batchStateLabel(state?: BatchState) {
  if (state === 'running') return '处理中'
  if (state === 'succeeded') return '成功'
  if (state === 'failed') return '失败'
  return '等待'
}

function batchStateClass(state?: BatchState) {
  if (state === 'succeeded') return 'bg-emerald-100 text-emerald-700 border-emerald-200'
  if (state === 'running') return 'bg-amber-100 text-amber-700 border-amber-200'
  if (state === 'failed') return 'bg-red-100 text-red-700 border-red-200'
  if (state === 'queued') return 'bg-blue-100 text-blue-700 border-blue-200'
  return 'bg-slate-100 text-slate-500 border-slate-200'
}

function hasReviewDifferences(result?: ItemResult) {
  return Boolean(result?.runId && result.phase === 'done' && !result.error
    && !result.conversionChecking && !result.coefficientChecking
    && result.evaluation && result.quotaMatch
    && (result.evaluation.missed_count > 0 || result.evaluation.extra_count > 0))
}

function ConsistencyBadge({ evaluation, compact = false }: { evaluation?: PricingTaskEvaluation; compact?: boolean }) {
  if (!evaluation) return null

  const exact = evaluation.missed_count === 0 && evaluation.extra_count === 0
  const partial = !exact && evaluation.hit_count > 0
  const label = exact ? '完全一致' : partial ? '部分一致' : '不一致'
  const className = exact
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : partial
      ? 'border-amber-200 bg-amber-50 text-amber-700'
      : 'border-rose-200 bg-rose-50 text-rose-700'

  const sizeClass = compact ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-[11px]'

  return (
    <span className={`shrink-0 rounded-full border font-semibold ${sizeClass} ${className}`}>
      {label}
    </span>
  )
}

function ManualComparisonStep({ result }: { result: ItemResult }) {
  const evaluation = result.evaluation
  if (!evaluation) return null

  const matches = result.quotaMatch?.matches ?? []
  const hitCodes = new Set(evaluation.hit_codes ?? evaluation.consistent_codes ?? [])
  const missedCodes = new Set(evaluation.missed_codes ?? evaluation.manual_only_codes ?? [])
  const extraCodes = new Set(evaluation.extra_codes ?? evaluation.ai_only_codes ?? [])
  const consistentManualQuotas = evaluation.manual_quotas.filter(quota =>
    Array.from(hitCodes).some(aiCode => quota.quota_code.includes(aiCode)),
  )
  const manualOnlyQuotas = evaluation.manual_quotas.filter(quota => missedCodes.has(quota.quota_code))
  const aiOnlyMatches = matches.filter(match => extraCodes.has(match.zmbh))

  return (
    <section className="rounded-lg border border-purple-200 bg-purple-50 px-3 py-3 text-xs">
      <div className="flex items-center justify-between gap-2">
        <div className="font-semibold text-purple-900">6. 人工对比一致性</div>
        <ConsistencyBadge evaluation={evaluation} compact />
      </div>
      <div className="mt-2 grid grid-cols-3 gap-1.5">
        {[
          { label: '双方一致', count: evaluation.hit_count, color: 'text-emerald-700' },
          { label: '仅人工', count: evaluation.missed_count, color: 'text-amber-700' },
          { label: '仅 AI', count: evaluation.extra_count, color: 'text-cyan-700' },
        ].map(item => (
          <div key={item.label} className="rounded-md border border-purple-100 bg-white px-1.5 py-2 text-center">
            <div className={'text-sm font-semibold tabular-nums ' + item.color}>{item.count}</div>
            <div className="mt-0.5 text-[10px] text-slate-500">{item.label}</div>
          </div>
        ))}
      </div>

      <div className="mt-3 space-y-2">
        <div className="rounded-md border border-emerald-200 bg-emerald-50/70 p-2">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="font-semibold text-emerald-800">双方一致</span>
            <span className="text-[10px] text-emerald-600">{evaluation.hit_count} 条</span>
          </div>
          {consistentManualQuotas.length === 0 ? (
            <div className="rounded bg-white/70 px-2 py-1.5 text-slate-400">无</div>
          ) : (
            <div className="space-y-1.5">
              {consistentManualQuotas.map((quota, index) => (
                <div key={quota.quota_code + '-' + (quota.id ?? index)} className="rounded border border-emerald-100 bg-white px-2 py-1.5">
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-mono font-semibold text-emerald-800">{quota.quota_code || '-'}</span>
                    <span className="shrink-0 text-[10px] text-slate-400">{quota.quota_unit || '-'}</span>
                  </div>
                  <div className="mt-0.5 break-words text-slate-800">{quota.quota_name || '-'}</div>
                  <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-slate-500">
                    <span>工程量：{quota.quantity ?? '-'}</span>
                    <span>系数：{quota.qty_factor ?? '-'}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-md border border-amber-200 bg-amber-50/70 p-2">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="font-semibold text-amber-800">仅人工存在</span>
            <span className="text-[10px] text-amber-600">{evaluation.missed_count} 条</span>
          </div>
          {manualOnlyQuotas.length === 0 ? (
            <div className="rounded bg-white/70 px-2 py-1.5 text-slate-400">无</div>
          ) : (
            <div className="space-y-1.5">
              {manualOnlyQuotas.map((quota, index) => (
                <div key={quota.quota_code + '-' + (quota.id ?? index)} className="rounded border border-amber-100 bg-white px-2 py-1.5">
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-mono font-semibold text-amber-800">{quota.quota_code || '-'}</span>
                    <span className="shrink-0 text-[10px] text-slate-400">{quota.quota_unit || '-'}</span>
                  </div>
                  <div className="mt-0.5 break-words text-slate-800">{quota.quota_name || '-'}</div>
                  <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-slate-500">
                    <span>工程量：{quota.quantity ?? '-'}</span>
                    <span>系数：{quota.qty_factor ?? '-'}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-md border border-cyan-200 bg-cyan-50/70 p-2">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="font-semibold text-cyan-800">仅 AI 存在</span>
            <span className="text-[10px] text-cyan-600">{evaluation.extra_count} 条</span>
          </div>
          {aiOnlyMatches.length === 0 ? (
            <div className="rounded bg-white/70 px-2 py-1.5 text-slate-400">无</div>
          ) : (
            <div className="space-y-1.5">
              {aiOnlyMatches.map((match, index) => (
                <div key={match.zmbh + '-' + index} className="rounded border border-cyan-100 bg-white px-2 py-1.5">
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-mono font-semibold text-cyan-800">{match.zmbh || '-'}</span>
                    <span className="shrink-0 text-[10px] text-slate-400">{match.dw || '-'}</span>
                  </div>
                  <div className="mt-0.5 break-words text-slate-800">{match.zmmc || '-'}</div>
                  <div className="mt-1 text-[10px] text-slate-500">AI 系数：{match.qty_factor ?? '-'}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  )
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

function totalDuration(result?: ItemResult) {
  const timings = Object.values(result?.stepTimings ?? {})
  if (timings.length === 0) return null
  return timings.reduce((sum, timing) => sum + (timing.duration_ms ?? 0), 0)
}

function updateResultFromEvent(prev: ItemResult, evt: PricingTaskEvent): ItemResult {
  if (evt.type === 'run_started') {
    return withToolActivities(
      { ...prev, runId: evt.run_id, status: 'running' },
      { id: 'code_check', status: 'running' },
    )
  }
  if (evt.type === 'reasoning_token' || evt.type === 'judgment' || evt.type === 'item_info') return prev
  if (evt.type === 'code_check') {
    const codeCheck: CodeCheck = {
      item_code: evt.item_code,
      item_name: evt.item_name,
      base_code: evt.base_code,
      standard_name: evt.standard_name,
      found: evt.found,
      is_consistent: evt.is_consistent,
    }
    return withToolActivities(
      { ...prev, codeCheck },
      { id: 'code_check', status: 'success', output: codeCheckOutput(codeCheck) },
      { id: 'feature_check', status: 'running' },
    )
  }
  if (evt.type === 'feature_check') {
    const featureCheck: FeatureCheck = {
      is_complete: evt.is_complete,
      missing_features: evt.missing_features,
      analysis: evt.analysis,
      normalized_description: evt.normalized_description,
      default_fills: evt.default_fills ?? [],
      default_candidates: evt.default_candidates ?? [],
      description_updated: evt.description_updated,
    }
    return withToolActivities(
      { ...prev, featureCheck },
      { id: 'feature_check', status: 'success', output: featureCheckOutput(featureCheck) },
      { id: 'chapter_rule_check', status: 'running' },
    )
  }
  if (evt.type === 'chapter_rule_check') {
    const chapterRuleCheck: PricingTaskChapterRuleCheck = {
      available: evt.available,
      base_code: evt.base_code,
      kb_version_id: evt.kb_version_id,
      chapters: evt.chapters ?? [],
      project_items_checked: evt.project_items_checked ?? 0,
      rules: evt.rules ?? [],
      issues: evt.issues ?? [],
      validation: evt.validation ?? { status: 'pending', validations: [], issues: [] },
    }
    return withToolActivities(
      { ...prev, chapterRuleCheck },
      { id: 'chapter_rule_check', status: chapterRuleCheck.validation.status === 'failed' ? 'error' : 'success', output: `命中 ${chapterRuleCheck.rules.filter(rule => rule.matched).length} 条章节规则` },
      { id: 'quota_candidates', status: 'running' },
    )
  }
  if (evt.type === 'quota_candidates') {
    return withToolActivities(
      { ...prev, quotaCandidates: { item_code: evt.item_code, base_code: evt.base_code, candidates: evt.candidates, total: evt.total } },
      { id: 'quota_candidates', status: 'success', output: `检索到 ${evt.total} 条候选定额` },
      { id: 'quota_match', status: 'running' },
    )
  }
  if (evt.type === 'quota_match') {
    return withToolActivities(
      { ...prev, quotaMatch: { matches: evt.matches, issues: evt.issues } },
      {
        id: 'quota_match',
        status: 'success',
        output: `输出 ${evt.matches.length} 条定额${evt.issues.length > 0 ? `；提示 ${evt.issues.length} 条` : ''}`,
        rows: quotaMatchRows(evt.matches),
      },
      { id: 'evaluation', status: 'running' },
    )
  }
  if (evt.type === 'evaluation') {
    return withToolActivities(
      { ...prev, evaluation: evt.evaluation },
      { id: 'evaluation', status: 'success', output: evaluationOutput(evt.evaluation) },
    )
  }
  if (evt.type === 'step_timing') {
    const result = { ...prev, stepTimings: { ...(prev.stepTimings ?? {}), [String(evt.step_no)]: evt } }
    const toolId = STEP_TOOL_IDS[evt.step_no]
    return toolId ? withToolActivities(result, { id: toolId, durationMs: evt.duration_ms }) : result
  }
  if (evt.type === 'error') {
    const active = [...prev.toolActivities].reverse().find(activity => activity.status === 'running')
    return withToolActivities(
      { ...prev, phase: 'error', status: 'failed', error: evt.error },
      { id: active?.id ?? 'execution', name: active?.name, status: 'error', output: evt.error },
    )
  }
  return prev
}

function ToolActivityFeed({ result }: { result?: ItemResult }) {
  if (!result) return <div className="px-5 py-10 text-sm text-slate-400">选择清单后查看工具调用与输出。</div>
  if (result.toolActivities.length === 0) return <div className="px-5 py-10 text-sm text-slate-400">等待启动工具调用...</div>

  return (
    <div className="space-y-3 px-4 py-4">
      {result.toolActivities.map((activity, index) => {
        const running = activity.status === 'running'
        const failed = activity.status === 'error'
        return (
          <article
            key={activity.id}
            className={`rounded-lg border px-3.5 py-3 ${failed
              ? 'border-rose-200 bg-rose-50/70'
              : running
                ? 'border-blue-200 bg-blue-50/60'
                : 'border-slate-200 bg-white'}`}
          >
            <div className="flex items-center gap-2.5">
              <div className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] font-bold ${failed
                ? 'bg-rose-600 text-white'
                : running
                  ? 'bg-blue-600 text-white'
                  : 'bg-emerald-600 text-white'}`}>
                {failed ? '!' : running ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" /> : '✓'}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">
                    TOOL {String(index + 1).padStart(2, '0')}
                  </span>
                  {activity.durationMs != null && <span className="text-[10px] tabular-nums text-slate-400">{formatDuration(activity.durationMs)}</span>}
                </div>
                <div className="mt-0.5 flex min-w-0 items-baseline gap-2">
                  <span className="shrink-0 text-sm font-semibold text-slate-800">{TOOL_LABELS[activity.id] ?? '工具调用'}</span>
                  <span className="truncate font-mono text-[11px] text-slate-500">{activity.name}</span>
                </div>
              </div>
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${failed
                ? 'bg-rose-100 text-rose-700'
                : running
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-emerald-100 text-emerald-700'}`}>
                {failed ? '失败' : running ? '调用中' : '已返回'}
              </span>
            </div>
            <div className="ml-9 mt-2 border-l-2 border-slate-200 pl-3">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">输出</div>
              <div className={`mt-1 whitespace-pre-wrap text-xs leading-5 ${failed ? 'text-rose-700' : 'text-slate-700'}`}>
                {activity.output || (running ? '等待工具返回结果...' : '执行完成')}
              </div>
              {(activity.rows?.length ?? 0) > 0 && (
                <div className="mt-2 space-y-1">
                  {activity.rows?.map((row, rowIndex) => (
                    <div key={`${activity.id}-${rowIndex}`} className="rounded bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-700">
                      {row}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </article>
        )
      })}
    </div>
  )
}

function StepCards({ result }: { result?: ItemResult }) {
  if (!result) return <div className="text-sm text-gray-400">选择清单后查看过程卡片</div>
  return (
    <div className="space-y-3">
      {result.codeCheck && (
        <section className="rounded border border-green-200 bg-green-50 px-3 py-2 text-xs">
          <div className="font-semibold text-green-900">1. 编码核查</div>
          <div className="mt-1 text-green-800">{result.codeCheck.standard_name || '未找到标准名称'}</div>
        </section>
      )}
      {result.featureCheck && (
        <section className="rounded border border-orange-200 bg-orange-50 px-3 py-2 text-xs">
          <div className="font-semibold text-orange-900">2. 项目特征{result.featureCheck.is_complete ? '完整' : '不完整'}</div>
          {(result.featureCheck.default_fills?.length ?? 0) > 0 && (
            <div className="mt-2 rounded bg-white/80 px-2 py-1 text-orange-800">
              已补全 {result.featureCheck.default_fills?.length} 个综合考虑特征
            </div>
          )}
          <div className="mt-1 text-orange-800">{result.featureCheck.analysis}</div>
        </section>
      )}
      {result.chapterRuleCheck && (
        <section className="rounded border border-sky-200 bg-sky-50 px-3 py-2 text-xs">
          <div className="font-semibold text-sky-900">3. 章节规则校验</div>
          <div className="mt-1 text-sky-800">{result.chapterRuleCheck.chapters.map(chapter => chapter.chapter_name).join(' / ') || '未找到章节规则'}</div>
          {result.chapterRuleCheck.rules.filter(rule => rule.matched).map((rule, index) => <div key={`${rule.chapter_id}-${index}`} className="mt-1 rounded bg-white px-2 py-1 text-slate-700">{rule.rule_reference || rule.rule_text}：{rule.action}</div>)}
        </section>
      )}
      {result.quotaCandidates && (
        <section className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
          <div className="font-semibold text-slate-900">4. 定额候选：{result.quotaCandidates.total} 条</div>
        </section>
      )}
      {result.quotaMatch && (
        <section className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs">
          <div className="font-semibold text-emerald-900">5. 套定额结果：{result.quotaMatch.matches.length} 条</div>
          <div className="mt-2 space-y-1">
            {result.quotaMatch.matches.map((match, index) => (
              <div key={`${match.zmbh}-${index}`} className="rounded bg-white px-2 py-1">
                <span className="font-mono text-emerald-800">{match.zmbh}</span>
                <span className="ml-2 text-gray-800">{match.zmmc}</span>
              </div>
            ))}
          </div>
        </section>
      )}
      {result.evaluation && <ManualComparisonStep result={result} />}
      {(result.conversionChecking || result.conversionCheck || result.comboAdjustmentPreview || result.conversionError) && (
        <section className="rounded border border-cyan-200 bg-cyan-50 px-3 py-2 text-xs">
          <div className="font-semibold text-cyan-900">7. 组合换算</div>
          {result.conversionChecking && <div className="mt-1 text-cyan-700">运行中...</div>}
          {result.conversionError && <div className="mt-1 text-red-700">{result.conversionError}</div>}
          {(result.conversionCheck || result.comboAdjustmentPreview) && (
            <div className="mt-1 text-cyan-800">
              定额 {result.conversionCheck?.items.length ?? result.comboAdjustmentPreview?.length ?? 0} 条
            </div>
          )}
          {(result.conversionCheck || result.comboAdjustmentPreview) && (
            <div className="mt-2 space-y-1.5">
              {(result.conversionCheck?.items ?? result.comboAdjustmentPreview ?? []).map(item => (
                <div key={`${item.dekid}-${item.dezmid}`} className="rounded bg-white px-2 py-1.5">
                  <div>
                    <span className="font-mono text-cyan-800">{item.quota_code}</span>
                    <span className="ml-2 text-gray-800">{item.quota_name}</span>
                  </div>
                  {(item.adjustment_rules ?? []).length === 0 ? (
                    <div className="mt-1 text-gray-500">该定额无组合换算规则</div>
                  ) : (
                    <div className="mt-1 space-y-1">
                      {(item.adjustment_rules ?? []).map(rule => (
                        <div key={`${rule.rule_index}-${rule.combo_code}`} className="rounded bg-cyan-50 px-2 py-1 text-cyan-900">
                          <span className="font-mono">{rule.combo_code || '-'}</span>
                          <span className="ml-2">{rule.combo_name || '-'}</span>
                          <span className="ml-2 text-cyan-700">次数 {rule.calculated_times ?? '-'}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}
      {(result.coefficientChecking || result.coefficientCheck || result.coefficientPreview || result.coefficientError) && (
        <section className="rounded border border-violet-200 bg-violet-50 px-3 py-2 text-xs">
          <div className="font-semibold text-violet-900">8. 系数换算</div>
          {result.coefficientChecking && <div className="mt-1 text-violet-700">运行中...</div>}
          {result.coefficientError && <div className="mt-1 text-red-700">{result.coefficientError}</div>}
          {(result.coefficientCheck || result.coefficientPreview) && (
            <div className="mt-1 text-violet-800">
              说明 {result.coefficientCheck?.items.reduce((sum, item) => sum + item.coefficient_rules.length, 0) ?? result.coefficientPreview?.reduce((sum, item) => sum + item.coefficient_rules.length, 0) ?? 0} 条
            </div>
          )}
          {(result.coefficientCheck || result.coefficientPreview) && (
            <div className="mt-2 space-y-1.5">
              {(result.coefficientCheck?.items ?? result.coefficientPreview ?? []).map(item => {
                const matchedRules = item.coefficient_rules.filter(rule => rule.matched)
                return (
                  <div key={item.quota_key} className="rounded bg-white px-2 py-1.5">
                    <div>
                      <span className="font-mono text-violet-800">{item.quota_code}</span>
                      <span className="ml-2 text-gray-800">{item.quota_name}</span>
                    </div>
                    {item.coefficient_rules.length === 0 ? (
                      <div className="mt-1 text-gray-500">该定额无系数换算说明</div>
                    ) : (
                      <div className="mt-1 space-y-1">
                        {item.coefficient_rules.map(rule => (
                          <div key={rule.rule_index} className={`rounded px-2 py-1 ${rule.matched ? 'bg-amber-50 text-amber-800' : 'bg-violet-50 text-violet-900'}`}>
                            <span>规则 {rule.rule_index}</span>
                            <span className="ml-2">{rule.matched ? `系数 x${rule.factor}` : '未命中'}</span>
                            {rule.matched_feature && <span className="ml-2">{rule.matched_feature}</span>}
                          </div>
                        ))}
                      </div>
                    )}
                    {matchedRules.length > 0 && <div className="mt-1 text-amber-700">命中 {matchedRules.length} 条</div>}
                  </div>
                )
              })}
            </div>
          )}
        </section>
      )}
    </div>
  )
}

export default function PricingTaskBatchPage() {
  const params = useParams()
  const batchId = Number(params.batchId)
  const [batch, setBatch] = useState<PricingTaskBatch | null>(null)
  const [items, setItems] = useState<BoqItem[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [focusedItemId, setFocusedItemId] = useState<number | null>(null)
  const [expandedItemId, setExpandedItemId] = useState<number | null>(null)
  const [itemResults, setItemResults] = useState<Map<number, ItemResult>>(new Map())
  const [batchStates, setBatchStates] = useState<Map<number, BatchState>>(new Map())
  const [running, setRunning] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [currentItemId, setCurrentItemId] = useState<number | null>(null)
  const [detailItemId, setDetailItemId] = useState<number | null>(null)
  const [reviewItemId, setReviewItemId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [exportingExcel, setExportingExcel] = useState(false)
  const [exportExcelError, setExportExcelError] = useState('')
  const stopRef = useRef(false)
  const toolFeedRef = useRef<HTMLDivElement>(null)

  const focusedItem = focusedItemId ? items.find(item => item.id === focusedItemId) : undefined
  const focusedResult = focusedItemId ? itemResults.get(focusedItemId) : undefined
  const detailItem = detailItemId ? items.find(item => item.id === detailItemId) : undefined
  const detailResult = detailItemId ? itemResults.get(detailItemId) : undefined
  const reviewItem = reviewItemId ? items.find(item => item.id === reviewItemId) : undefined
  const reviewResult = reviewItemId ? itemResults.get(reviewItemId) : undefined
  const selectedCount = selectedIds.size
  const succeededCount = Array.from(batchStates.values()).filter(state => state === 'succeeded').length
  const failedCount = Array.from(batchStates.values()).filter(state => state === 'failed').length
  const doneCount = succeededCount + failedCount
  const completedItems = items
    .map(item => ({ item, result: itemResults.get(item.id), state: batchStates.get(item.id) }))
    .filter(row => Boolean(row.result?.evaluation))
  const quotaHitStats = buildQuotaHitStats(itemResults, items.length)

  useEffect(() => {
    if (!Number.isFinite(batchId)) return
    void bootstrap()
  }, [batchId])

  useEffect(() => {
    if (toolFeedRef.current) toolFeedRef.current.scrollTop = toolFeedRef.current.scrollHeight
  }, [focusedResult?.toolActivities])

  async function bootstrap() {
    setLoading(true)
    try {
      const detail = await fetchPricingTaskBatchDetail(batchId)
      setBatch(detail.batch)
      setItems(detail.items)
      if (detail.items[0]) {
        setFocusedItemId(detail.items[0].id)
        setExpandedItemId(detail.items[0].id)
      }
      setItemResults(() => {
        const next = new Map<number, ItemResult>()
        for (const itemRun of detail.runs) next.set(itemRun.boq_item_id, runToResult(itemRun.run))
        return next
      })
      setBatchStates(() => {
        const next = new Map<number, BatchState>()
        for (const itemRun of detail.runs) {
          if (['confirmed', 'completed', 'no_match'].includes(itemRun.run.status)) next.set(itemRun.boq_item_id, 'succeeded')
          else if (itemRun.run.status === 'failed') next.set(itemRun.boq_item_id, 'failed')
          else if (itemRun.run.status === 'running') next.set(itemRun.boq_item_id, 'running')
        }
        return next
      })
    } finally {
      setLoading(false)
    }
  }

  async function downloadBatchExcel() {
    if (!batch || completedItems.length === 0 || exportingExcel) return
    setExportingExcel(true)
    setExportExcelError('')
    try {
      const blob = await exportNewPricingTaskBatchDetailReportExcel(batch.id)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      const safeName = batch.name.replace(/[\\/:*?"<>|]+/g, '_').trim() || String(batch.id)
      link.href = url
      link.download = `新批量组价明细报表-${safeName}.xlsx`
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setExportExcelError(err instanceof Error ? err.message : 'Excel导出失败')
    } finally {
      setExportingExcel(false)
    }
  }

  function setResult(itemId: number, updater: (prev: ItemResult) => ItemResult) {
    setItemResults(prev => {
      const current = prev.get(itemId) ?? { phase: 'idle', toolActivities: [] }
      return new Map(prev).set(itemId, updater(current))
    })
  }

  function setBatchState(itemId: number, state: BatchState) {
    setBatchStates(prev => new Map(prev).set(itemId, state))
  }

  function applySnapshot(itemId: number, snapshot: ItemResult) {
    setItemResults(prev => new Map(prev).set(itemId, snapshot))
  }

  function toggleSelected(itemId: number, checked: boolean) {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (checked) next.add(itemId)
      else next.delete(itemId)
      return next
    })
  }

  async function runConversionAndCoefficient(itemId: number, runId: number, initial: ItemResult) {
    let snapshot = withToolActivities(
      { ...initial, conversionChecking: true },
      { id: 'conversion_check', status: 'running', output: `正在检查 ${initial.quotaMatch?.matches.length ?? 0} 条定额` },
    )
    applySnapshot(itemId, snapshot)
    await streamPricingTaskBatchConversionCheck(runId, (evt: PricingTaskEvent) => {
      if (evt.type === 'reasoning_token') return
      if (evt.type === 'conversion_check_start') {
        snapshot = withToolActivities(
          { ...snapshot, conversionChecking: true, conversionError: undefined },
          { id: 'conversion_check', status: 'running', output: `正在检查 ${evt.total} 条定额` },
        )
      } else if (evt.type === 'combo_adjustment_rules') {
        snapshot = withToolActivities(
          { ...snapshot, comboAdjustmentPreview: evt.items, conversionChecking: true },
          { id: 'conversion_check', status: 'running', output: `已读取 ${evt.items.length} 条定额的组合规则，正在计算换算结果` },
        )
      } else if (evt.type === 'conversion_check') {
        snapshot = withToolActivities(
          { ...snapshot, conversionCheck: evt.conversion_check, comboAdjustmentPreview: evt.conversion_check.items, conversionChecking: false },
          { id: 'conversion_check', status: 'success', output: conversionOutput(evt.conversion_check) },
        )
      } else if (evt.type === 'step_timing') {
        snapshot = updateResultFromEvent(snapshot, evt)
      } else if (evt.type === 'error') {
        snapshot = withToolActivities(
          { ...snapshot, conversionChecking: false, conversionError: evt.error, error: evt.error },
          { id: 'conversion_check', status: 'error', output: evt.error },
        )
      } else if (evt.type === 'done') {
        snapshot = { ...snapshot, conversionChecking: false }
      }
      applySnapshot(itemId, snapshot)
    })
    if (snapshot.conversionError) throw new Error(snapshot.conversionError)

    snapshot = withToolActivities(
      { ...snapshot, coefficientChecking: true },
      { id: 'coefficient_check', status: 'running', output: `正在检查 ${snapshot.conversionCheck?.items.length ?? snapshot.quotaMatch?.matches.length ?? 0} 条定额` },
    )
    applySnapshot(itemId, snapshot)
    await streamPricingTaskBatchCoefficientCheck(runId, (evt: PricingTaskEvent) => {
      if (evt.type === 'reasoning_token') return
      if (evt.type === 'coefficient_check_start') {
        snapshot = withToolActivities(
          { ...snapshot, coefficientChecking: true, coefficientError: undefined },
          { id: 'coefficient_check', status: 'running', output: `正在检查 ${evt.total} 条定额` },
        )
      } else if (evt.type === 'coefficient_rules') {
        const ruleCount = evt.items.reduce((sum, item) => sum + item.coefficient_rules.length, 0)
        snapshot = withToolActivities(
          { ...snapshot, coefficientPreview: evt.items, coefficientChecking: true },
          { id: 'coefficient_check', status: 'running', output: `已读取 ${ruleCount} 条系数规则，正在计算应用结果` },
        )
      } else if (evt.type === 'coefficient_check') {
        snapshot = withToolActivities(
          { ...snapshot, coefficientCheck: evt.coefficient_check, coefficientPreview: evt.coefficient_check.items, coefficientChecking: false },
          { id: 'coefficient_check', status: 'success', output: coefficientOutput(evt.coefficient_check) },
        )
      } else if (evt.type === 'step_timing') {
        snapshot = updateResultFromEvent(snapshot, evt)
      } else if (evt.type === 'error') {
        snapshot = withToolActivities(
          { ...snapshot, coefficientChecking: false, coefficientError: evt.error, error: evt.error },
          { id: 'coefficient_check', status: 'error', output: evt.error },
        )
      } else if (evt.type === 'done') {
        snapshot = { ...snapshot, coefficientChecking: false }
      }
      applySnapshot(itemId, snapshot)
    })
    if (snapshot.coefficientError) throw new Error(snapshot.coefficientError)
    return snapshot
  }

  async function runOne(item: BoqItem) {
    setCurrentItemId(item.id)
    setFocusedItemId(item.id)
    setExpandedItemId(item.id)
    setBatchState(item.id, 'running')
    let snapshot: ItemResult = { phase: 'reasoning', toolActivities: [], status: 'running', stepTimings: {} }
    setItemResults(prev => new Map(prev).set(item.id, snapshot))

    try {
      await streamPricingTaskBatchItemRun(batch!.id, item.id, (evt: PricingTaskEvent) => {
        if (evt.type === 'reasoning_token' || evt.type === 'judgment') return
        snapshot = updateResultFromEvent(snapshot, evt)
        if (evt.type === 'done') snapshot = { ...snapshot, phase: 'done', status: 'completed' }
        setItemResults(prev => new Map(prev).set(item.id, snapshot))
        if (evt.type === 'feature_check' && evt.description_updated && evt.normalized_description) {
          setItems(prev => prev.map(row => row.id === item.id ? { ...row, item_description: evt.normalized_description || row.item_description } : row))
        }
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : '批量组价请求失败'
      setResult(item.id, prev => ({ ...prev, phase: 'error', status: 'failed', error: message }))
      setBatchState(item.id, 'failed')
      return
    }

    if (snapshot.error) {
      setBatchState(item.id, 'failed')
      return
    }
    if (!snapshot.runId) {
      setResult(item.id, prev => ({ ...prev, phase: 'error', status: 'failed', error: '未获取运行编号' }))
      setBatchState(item.id, 'failed')
      return
    }
    const runId = snapshot.runId
    const matches = snapshot.quotaMatch?.matches ?? []
    if (matches.length === 0) {
      setResult(item.id, prev => ({ ...prev, phase: 'done', status: 'completed' }))
      setBatchState(item.id, 'succeeded')
      return
    }
    try {
      snapshot = { ...snapshot, phase: 'done', status: 'confirmed' }
      applySnapshot(item.id, snapshot)
      snapshot = await runConversionAndCoefficient(item.id, runId, snapshot)
      setResult(item.id, prev => ({ ...prev, ...snapshot, phase: 'done', status: 'confirmed' }))
      setBatchState(item.id, 'succeeded')
    } catch (err) {
      setResult(item.id, prev => ({ ...prev, phase: 'error', status: 'failed', error: err instanceof Error ? err.message : '自动确认失败' }))
      setBatchState(item.id, 'failed')
    }
  }

  async function startBatch() {
    if (!batch || running || selectedIds.size === 0) return
    stopRef.current = false
    setStopping(false)
    setRunning(true)
    const queue = items.filter(item => selectedIds.has(item.id))
    setBatchStates(prev => {
      const next = new Map(prev)
      queue.forEach(item => next.set(item.id, 'queued'))
      return next
    })
    let cursor = 0
    const workerCount = Math.min(4, queue.length)
    async function worker() {
      while (!stopRef.current) {
        const index = cursor
        cursor += 1
        if (index >= queue.length) return
        await runOne(queue[index])
      }
    }
    await Promise.all(Array.from({ length: workerCount }, () => worker()))
    setBatchStates(prev => {
      const next = new Map(prev)
      queue.forEach(item => {
        if (next.get(item.id) === 'queued') next.set(item.id, 'idle')
      })
      return next
    })
    setCurrentItemId(null)
    setRunning(false)
    setStopping(false)
  }

  function stopBatch() {
    stopRef.current = true
    setStopping(true)
  }

  if (loading || !batch) {
    return <div className="min-h-screen bg-gray-50 flex items-center justify-center text-gray-500">加载中...</div>
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="border-b border-gray-200 bg-white px-6 py-3">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <div className="text-sm font-semibold text-gray-900">{batch.name}</div>
              <span className="rounded border border-sky-200 bg-sky-50 px-2 py-0.5 font-mono text-[11px] font-semibold text-sky-700">
                {'\u77e5\u8bc6\u5e93\u7248\u672c\uff1a'}{batch.kb_version_id ?? '-'}
              </span>
            </div>
            <div className="mt-1 text-xs text-gray-500">
              新批量组价 · {batch.project_name} · {batch.quota_library_names.length > 0 ? batch.quota_library_names.join('、') : '全部定额库'}
              {batch.manual_project_id ? ` · 对比工程：${batch.manual_project_name || `#${batch.manual_project_id}`}` : ''}
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-3">
            <div className="flex flex-wrap items-center gap-2 rounded-md border border-gray-200 bg-white px-2.5 py-2 shadow-sm shadow-gray-100/70">
              <div className="mr-1 min-w-24 rounded bg-gray-50 px-2.5 py-1.5">
                <div className="text-[11px] text-gray-500">命中率</div>
                <div className="mt-0.5 text-xs font-semibold leading-none text-gray-900">{formatPercent(quotaHitStats.hitRate)}</div>
              </div>
              <div className="flex items-center gap-3 text-xs text-gray-500">
                <span>已评估 <span className="font-medium text-gray-800">{quotaHitStats.evaluatedItemCount}/{quotaHitStats.totalItems}</span></span>
                <span>人工 <span className="font-medium text-gray-800">{quotaHitStats.manualCount}</span></span>
                <span>命中 <span className="font-medium text-gray-800">{quotaHitStats.hitCount}</span></span>
                <span>遗漏 <span className="font-medium text-amber-700">{quotaHitStats.missedCount}</span></span>
                <span>额外 <span className="font-medium text-rose-700">{quotaHitStats.extraCount}</span></span>
                <span>一致 <span className="font-medium text-gray-800">{quotaHitStats.exactItemCount}</span></span>
              </div>
            </div>
            <Link href="/pricing-task/new-batch" className="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50">
              返回新批量列表
            </Link>
            <button
              type="button"
              onClick={running ? stopBatch : startBatch}
              disabled={!running && selectedCount === 0}
              className={`rounded px-4 py-1.5 text-xs font-semibold text-white disabled:opacity-50 ${running ? 'bg-rose-600 hover:bg-rose-700' : 'bg-blue-600 hover:bg-blue-700'}`}
            >
              {running ? (stopping ? '停止中...' : '停止') : `开始批量组价（${selectedCount}）`}
            </button>
          </div>
        </div>
      </div>

      <div className="mx-auto grid max-w-7xl grid-cols-[22rem_minmax(0,1fr)] gap-4 px-6 py-6">
        <aside className="flex h-[calc(100vh-330px)] min-h-[420px] flex-col rounded-lg bg-white shadow">
          <div className="border-b border-gray-200 px-4 py-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-900">清单选择</h2>
              <span className="text-xs text-gray-500">{selectedCount}/{items.length}</span>
            </div>
            <div className="mt-2 flex gap-2">
              <button type="button" disabled={running} onClick={() => setSelectedIds(new Set(items.map(item => item.id)))} className="rounded border px-2 py-1 text-xs disabled:opacity-50">全选</button>
              <button type="button" disabled={running} onClick={() => setSelectedIds(new Set())} className="rounded border px-2 py-1 text-xs disabled:opacity-50">清空</button>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto divide-y divide-gray-100">
            {items.map(item => {
              const state = batchStates.get(item.id)
              const result = itemResults.get(item.id)
              const focused = focusedItemId === item.id
              const expanded = expandedItemId === item.id
              const duration = totalDuration(result)
              return (
                <div
                  key={item.id}
                  onClick={() => {
                    setFocusedItemId(item.id)
                    setExpandedItemId(expanded ? null : item.id)
                  }}
                  className={`cursor-pointer px-3 py-3 ${focused ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                >
                  <div className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(item.id)}
                      disabled={running}
                      onClick={event => event.stopPropagation()}
                      onChange={event => toggleSelected(item.id, event.target.checked)}
                      className="mt-1"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="font-mono text-xs text-gray-500">{item.item_code}</div>
                      <div className="flex min-w-0 items-center justify-between gap-3">
                        <div className="truncate text-sm font-medium text-gray-900">{item.item_name}</div>
                        {duration != null && <div className="shrink-0 text-[11px] text-gray-400">{formatDuration(duration)}</div>}
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${batchStateClass(state)}`}>{batchStateLabel(state)}</span>
                        <ConsistencyBadge evaluation={result?.evaluation} compact />
                        {result?.quotaMatch && <span className="text-[11px] text-gray-500">{result.quotaMatch.matches.length} 条</span>}
                      </div>
                    </div>
                  </div>
                  {expanded && (
                    <div className="mt-3 rounded border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-600">
                      <div className="whitespace-pre-wrap leading-5">
                        <span className="font-semibold text-gray-700">项目特征：</span>
                        {item.item_description || '未填写'}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                        <span><span className="font-semibold text-gray-700">单位：</span>{item.unit || '-'}</span>
                        <span><span className="font-semibold text-gray-700">工程量：</span>{item.quantity ?? '-'}</span>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </aside>

        <main className="flex h-[calc(100vh-330px)] min-h-[420px] overflow-hidden rounded-lg bg-white shadow">
          <div className="flex min-w-0 flex-1 flex-col border-r border-gray-200">
            <div className="border-b border-gray-200 px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-gray-900">{focusedItem?.item_name || '未选择清单'}</div>
                  <div className="mt-1 font-mono text-xs text-gray-500">{focusedItem?.item_code || '-'}</div>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="rounded bg-gray-50 px-2 py-1 text-gray-600">已选 {selectedCount}</span>
                  <span className="rounded bg-gray-50 px-2 py-1 text-gray-600">已结束 {doneCount}</span>
                  <span className="rounded bg-emerald-50 px-2 py-1 font-semibold text-emerald-700">成功 {succeededCount}</span>
                  <span className="rounded bg-red-50 px-2 py-1 font-semibold text-red-700">失败 {failedCount}</span>
                </div>
              </div>
              <div className="mt-2 truncate text-xs text-gray-500">
                当前项：{currentItemId ? items.find(item => item.id === currentItemId)?.item_name : '无'}
              </div>
            </div>
            <div ref={toolFeedRef} className="flex-1 overflow-y-auto bg-slate-50/50">
              <ToolActivityFeed result={focusedResult} />
            </div>
          </div>

          <aside className="w-[24rem] shrink-0 overflow-y-auto bg-gray-50/60 p-4">
            <h2 className="mb-3 text-xs font-semibold text-gray-700">过程卡片</h2>
            <StepCards result={focusedResult} />
          </aside>
        </main>
      </div>
      <section className="mx-auto max-w-7xl px-6 pb-6">
        <div className="rounded-lg bg-white shadow">
          <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">清单套定额结果</h2>
              <div className="mt-1 text-xs text-gray-500">已完成套定额的清单会在这里汇总，点击查看详情。</div>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-500">{completedItems.length} 条</span>
              <button
                type="button"
                onClick={() => void downloadBatchExcel()}
                disabled={exportingExcel || completedItems.length === 0}
                className="rounded border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700 hover:border-emerald-300 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {exportingExcel ? '导出中...' : '导出 Excel'}
              </button>
            </div>
          </div>
          {exportExcelError && (
            <div className="border-b border-rose-100 bg-rose-50 px-4 py-2 text-xs text-rose-700">
              {exportExcelError}
            </div>
          )}
          {completedItems.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-gray-400">暂无套定额结果</div>
          ) : (
            <div className="max-h-56 overflow-y-auto divide-y divide-gray-100">
              {completedItems.map(({ item, result, state }) => (
                <div key={item.id} className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50">
                  <button type="button" onClick={() => setDetailItemId(item.id)} className="min-w-0 flex-1 text-left">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs text-gray-500">{item.item_code}</span>
                      <span className="truncate text-sm font-medium text-gray-900">{item.item_name}</span>
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      {(result?.quotaMatch?.matches.length ?? 0)} 条定额
                      {result?.evaluation ? ` · 命中 ${result.evaluation.hit_count} / 遗漏 ${result.evaluation.missed_count} / 额外 ${result.evaluation.extra_count}` : ''}
                    </div>
                  </button>
                  <ConsistencyBadge evaluation={result?.evaluation} />
                  {hasReviewDifferences(result) && (
                    <button
                      type="button"
                      onClick={() => setReviewItemId(item.id)}
                      className="shrink-0 rounded border border-amber-300 bg-amber-50 px-2.5 py-1.5 text-xs font-medium text-amber-700 hover:border-amber-400 hover:bg-amber-100"
                    >
                      复核差异
                    </button>
                  )}
                  <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${batchStateClass(state)}`}>
                    {batchStateLabel(state)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {detailItem && detailResult?.quotaMatch && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/40 px-4" onClick={() => setDetailItemId(null)}>
          <div className="max-h-[86vh] w-full max-w-4xl overflow-hidden rounded-lg bg-white shadow-xl" onClick={event => event.stopPropagation()}>
            <div className="flex items-start justify-between gap-4 border-b border-gray-200 px-5 py-4">
              <div className="min-w-0">
                <div className="font-mono text-xs text-gray-500">{detailItem.item_code}</div>
                <h3 className="mt-1 truncate text-base font-semibold text-gray-900">{detailItem.item_name}</h3>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <ConsistencyBadge evaluation={detailResult.evaluation} />
                {hasReviewDifferences(detailResult) && (
                  <button
                    type="button"
                    onClick={() => {
                      setReviewItemId(detailItem.id)
                      setDetailItemId(null)
                    }}
                    className="rounded border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 hover:border-amber-400 hover:bg-amber-100"
                  >
                    复核差异并修正人工工程
                  </button>
                )}
                <button type="button" onClick={() => setDetailItemId(null)} className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50">
                  关闭
                </button>
              </div>
            </div>
            <div className="max-h-[calc(86vh-72px)] overflow-y-auto px-5 py-4">
              <div className="mb-4 rounded border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-600">
                <div className="whitespace-pre-wrap"><span className="font-semibold text-gray-700">项目特征：</span>{detailItem.item_description || '未填写'}</div>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                  <span><span className="font-semibold text-gray-700">单位：</span>{detailItem.unit || '-'}</span>
                  <span><span className="font-semibold text-gray-700">工程量：</span>{detailItem.quantity ?? '-'}</span>
                </div>
              </div>

              <div className="space-y-2">
                <h4 className="text-sm font-semibold text-gray-900">套定额结果</h4>
                {detailResult.quotaMatch.matches.map((match, index) => (
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

              {detailResult.conversionCheck && (
                <div className="mt-5 space-y-2">
                  <h4 className="text-sm font-semibold text-gray-900">组合换算结果</h4>
                  {detailResult.conversionCheck.items.map(item => (
                    <div key={`${item.dekid}-${item.dezmid}`} className="rounded border border-cyan-200 bg-cyan-50 px-3 py-2 text-xs">
                      <div><span className="font-mono text-cyan-800">{item.quota_code}</span><span className="ml-2 text-gray-900">{item.quota_name}</span></div>
                      {(item.adjustment_rules ?? []).map(rule => (
                        <div key={`${rule.rule_index}-${rule.combo_code}`} className="mt-1 rounded bg-white px-2 py-1 text-cyan-900">
                          <span className="font-mono">{rule.combo_code}</span>
                          <span className="ml-2">{rule.combo_name}</span>
                          <span className="ml-2">次数 {rule.calculated_times ?? '-'}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}

              {detailResult.conversionCheck && (
                <div className="mt-5 space-y-3">
                  <h4 className="text-sm font-semibold text-gray-900">工料机明细</h4>
                  {detailResult.conversionCheck.items.flatMap(item => {
                    const coefficientByKey = new Map((detailResult.coefficientCheck?.items ?? []).map(coefficientItem => [coefficientItem.quota_key, coefficientItem.coefficient_rules]))
                    const coefficientByCode = new Map((detailResult.coefficientCheck?.items ?? []).map(coefficientItem => [coefficientItem.quota_code, coefficientItem.coefficient_rules]))
                    const groups = [
                      {
                        key: `base-${item.dekid}-${item.dezmid}`,
                        code: item.quota_code,
                        name: item.quota_name,
                        resources: item.resources ?? [],
                        rules: coefficientByKey.get(`base:${item.dekid}:${item.dezmid}`) ?? coefficientByCode.get(item.quota_code),
                      },
                      ...((item.adjustment_rules ?? []).map(rule => ({
                        key: `combo-${item.dekid}-${rule.combo_dezmid}-${rule.combo_code}`,
                        code: rule.combo_code,
                        name: `${rule.combo_name || '-'}（来源 ${item.quota_code || '-'}；次数 ${rule.calculated_times ?? '-'}）`,
                        resources: rule.combo_resources ?? [],
                        rules: coefficientByKey.get(`combo:${item.dekid}:${rule.combo_dezmid}:${rule.combo_code}`) ?? coefficientByCode.get(rule.combo_code),
                      }))),
                    ]
                    return groups.map(group => (
                      <div key={group.key} className="overflow-hidden rounded border border-gray-200">
                        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 bg-gray-50 px-3 py-2 text-xs">
                          <div className="min-w-0">
                            <span className="font-mono font-semibold text-gray-700">{group.code || '-'}</span>
                            <span className="ml-2 font-medium text-gray-900">{group.name || '-'}</span>
                          </div>
                          <span className="text-gray-500">{group.resources.length} 条工料机</span>
                        </div>
                        {group.resources.length === 0 ? (
                          <div className="px-3 py-4 text-center text-xs text-gray-400">暂无工料机明细</div>
                        ) : (
                          <div className="overflow-x-auto">
                            <table className="min-w-[720px] w-full text-left text-xs">
                              <thead className="bg-white text-gray-500">
                                <tr>
                                  <th className="px-3 py-2 font-medium">类别</th>
                                  <th className="px-3 py-2 font-medium">编码</th>
                                  <th className="px-3 py-2 font-medium">名称</th>
                                  <th className="px-3 py-2 font-medium">单位</th>
                                  <th className="px-3 py-2 text-right font-medium">含量</th>
                                  <th className="px-3 py-2 font-medium">换算</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-gray-100 bg-white">
                                {group.resources.map((resource, index) => {
                                  const matchedRules = coefficientRulesForResource(resource, group.rules)
                                  return (
                                    <tr key={`${resource.code}-${resource.name}-${index}`} className={matchedRules.length > 0 ? 'bg-amber-50/70' : undefined}>
                                      <td className="px-3 py-2 text-gray-500">{resourceTypeLabel(resource.type)}</td>
                                      <td className="px-3 py-2 font-mono text-gray-600">{resource.code || '-'}</td>
                                      <td className="px-3 py-2 text-gray-900">{resource.name || '-'}</td>
                                      <td className="px-3 py-2 text-gray-500">{resource.unit || '-'}</td>
                                      <td className="px-3 py-2 text-right text-gray-700">{resource.confirmed_quantity ?? resource.quantity ?? resource.original_quantity ?? '-'}</td>
                                      <td className="px-3 py-2 text-gray-500">
                                        {matchedRules.length === 0 ? '-' : (
                                          <div className="flex flex-wrap gap-1">
                                            {matchedRules.map(rule => (
                                              <span key={rule.rule_index} className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">
                                                系数 x{rule.factor}
                                              </span>
                                            ))}
                                          </div>
                                        )}
                                      </td>
                                    </tr>
                                  )
                                })}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    ))
                  })}
                </div>
              )}

              {detailResult.coefficientCheck && (
                <div className="mt-5 space-y-2">
                  <h4 className="text-sm font-semibold text-gray-900">系数换算结果</h4>
                  {detailResult.coefficientCheck.items.map(item => (
                    <div key={item.quota_key} className="rounded border border-violet-200 bg-violet-50 px-3 py-2 text-xs">
                      <div><span className="font-mono text-violet-800">{item.quota_code}</span><span className="ml-2 text-gray-900">{item.quota_name}</span></div>
                      {item.coefficient_rules.map(rule => (
                        <div key={rule.rule_index} className={`mt-1 rounded px-2 py-1 ${rule.matched ? 'bg-amber-50 text-amber-800' : 'bg-white text-violet-900'}`}>
                          <span>规则 {rule.rule_index}</span>
                          <span className="ml-2">{rule.matched ? `系数 x${rule.factor}` : '未命中'}</span>
                          {rule.matched_feature && <span className="ml-2">{rule.matched_feature}</span>}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {reviewItem && reviewResult?.runId && reviewResult.evaluation && reviewResult.quotaMatch && hasReviewDifferences(reviewResult) && (
        <ManualComparisonReviewModal
          key={reviewResult.runId}
          open
          item={reviewItem}
          evaluation={reviewResult.evaluation}
          matches={reviewResult.quotaMatch.matches}
          submitReview={input => updatePricingTaskBatchManualComparison(reviewResult.runId!, input)}
          loadHistory={() => fetchPricingTaskBatchManualComparisonHistory(reviewResult.runId!)}
          onClose={() => setReviewItemId(null)}
          onUpdated={evaluation => setResult(reviewItem.id, current => ({ ...current, evaluation }))}
        />
      )}
    </div>
  )
}
