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
  fetchPricingTaskBatchDetail,
  streamPricingTaskBatchCoefficientCheck,
  streamPricingTaskBatchConversionCheck,
  streamPricingTaskBatchItemRun,
} from '@/lib/api'

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
  original_description?: string
  normalized_description?: string
  effective_description?: string
  schema_kb_version_id?: number
  feature_schema?: Array<{ feature_name: string; native_default_value?: string; source: 'TQDK_TQDXMTZ'; source_rowid?: number }>
  default_fills?: Array<{
    candidate_id: string
    feature_name: string
    target_feature_name: string
    original_value: string
    default_value: string
    source: 'TQDK_TQDXMTZ' | 'tqdk_tzhkl'
    source_code: string
    match_state?: 'comprehensive' | 'vague' | 'missing'
    original_feature_text?: string
    reason: string
    confidence: 'high' | 'medium' | 'low'
  }>
  default_review_items?: Array<{
    candidate_id: string
    feature_name: string
    target_feature_name: string
    original_value: string
    default_value: string
    source: 'TQDK_TQDXMTZ' | 'tqdk_tzhkl'
    source_code: string
    match_state?: 'comprehensive' | 'vague' | 'missing'
    original_feature_text?: string
    reason: string
    confidence: 'low'
  }>
  default_candidates?: Array<{
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
  }>
  unresolved_features?: string[]
  description_updated?: boolean
}
interface ItemResult {
  phase: 'idle' | 'queued' | 'reasoning' | 'done' | 'error'
  reasoning: string
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

type BatchState = 'idle' | 'queued' | 'running' | 'confirmed' | 'no_match' | 'failed' | 'stopped'

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

function runToResult(run: PricingTaskBatchItemRun['run']): ItemResult {
  return {
    phase: run.status === 'failed' ? 'error' : 'done',
    reasoning: run.reasoning_text || '',
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

function statusLabel(status?: string) {
  if (status === 'confirmed') return '已确认'
  if (status === 'completed') return '待确认'
  if (status === 'failed') return '失败'
  if (status === 'running') return '运行中'
  return '未运行'
}

function batchStateLabel(state?: BatchState) {
  if (state === 'queued') return '等待'
  if (state === 'running') return '运行中'
  if (state === 'confirmed') return '已确认'
  if (state === 'no_match') return '无匹配'
  if (state === 'failed') return '失败'
  if (state === 'stopped') return '已停止'
  return '未开始'
}

function batchStateClass(state?: BatchState) {
  if (state === 'confirmed') return 'bg-emerald-100 text-emerald-700 border-emerald-200'
  if (state === 'running') return 'bg-amber-100 text-amber-700 border-amber-200'
  if (state === 'failed') return 'bg-red-100 text-red-700 border-red-200'
  if (state === 'no_match') return 'bg-orange-100 text-orange-700 border-orange-200'
  if (state === 'queued') return 'bg-blue-100 text-blue-700 border-blue-200'
  if (state === 'stopped') return 'bg-gray-100 text-gray-600 border-gray-200'
  return 'bg-slate-100 text-slate-500 border-slate-200'
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
  if (evt.type === 'run_started') return { ...prev, runId: evt.run_id, status: 'running' }
  if (evt.type === 'reasoning_token') return { ...prev, reasoning: prev.reasoning + evt.token }
  if (evt.type === 'code_check') {
    return {
      ...prev,
      codeCheck: {
        item_code: evt.item_code,
        item_name: evt.item_name,
        base_code: evt.base_code,
        standard_name: evt.standard_name,
        found: evt.found,
        is_consistent: evt.is_consistent,
      },
    }
  }
  if (evt.type === 'feature_check') {
    return {
      ...prev,
      featureCheck: {
        is_complete: evt.is_complete,
        missing_features: evt.missing_features,
        analysis: evt.analysis,
        original_description: evt.original_description,
        normalized_description: evt.normalized_description,
        effective_description: evt.effective_description ?? evt.normalized_description,
        schema_kb_version_id: evt.schema_kb_version_id,
        feature_schema: evt.feature_schema ?? [],
        default_fills: evt.default_fills ?? [],
        default_review_items: evt.default_review_items ?? [],
        default_candidates: evt.default_candidates ?? [],
        unresolved_features: evt.unresolved_features ?? [],
        description_updated: false,
      },
    }
  }  if (evt.type === 'quota_candidates') {
    return { ...prev, quotaCandidates: { item_code: evt.item_code, base_code: evt.base_code, candidates: evt.candidates, total: evt.total } }
  }
  if (evt.type === 'chapter_rule_check') {
    return {
      ...prev,
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
    }
  }
  if (evt.type === 'quota_match') return { ...prev, quotaMatch: { matches: evt.matches, issues: evt.issues } }
  if (evt.type === 'evaluation') return { ...prev, evaluation: evt.evaluation }
  if (evt.type === 'step_timing') return { ...prev, stepTimings: { ...(prev.stepTimings ?? {}), [String(evt.step_no)]: evt } }
  if (evt.type === 'error') return { ...prev, phase: 'error', status: 'failed', error: evt.error }
  return prev
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
          {(result.featureCheck.feature_schema?.length ?? 0) > 0 && (
            <details className="mt-2 rounded border border-orange-200 bg-white/80 px-2 py-1.5">
              <summary className="cursor-pointer font-medium text-orange-900">
                标准特征结构 {result.featureCheck.feature_schema?.length} 个
                {result.featureCheck.schema_kb_version_id ? ` / V${result.featureCheck.schema_kb_version_id}` : ''}
              </summary>
              <div className="mt-2 space-y-1 text-gray-700">
                {result.featureCheck.feature_schema?.map((feature, index) => (
                  <div key={`${feature.feature_name}-${index}`} className="flex flex-wrap gap-x-2 rounded bg-orange-50 px-2 py-1">
                    <span className="font-medium">{feature.feature_name}</span>
                    <span className="text-gray-500">{feature.native_default_value ? `默认值：${feature.native_default_value}` : '未配置原生默认值'}</span>
                  </div>
                ))}
              </div>
            </details>
          )}
          {(result.featureCheck.default_candidates?.length ?? 0) > 0 && (
            <details className="mt-2 rounded border border-orange-200 bg-white/80 px-2 py-1.5">
              <summary className="cursor-pointer font-medium text-orange-900">原生默认值候选 {result.featureCheck.default_candidates?.length} 个</summary>
              <div className="mt-2 space-y-1 text-gray-700">
                {result.featureCheck.default_candidates?.map(candidate => (
                  <div key={candidate.candidate_id} className="flex flex-wrap items-center gap-x-2 rounded bg-orange-50 px-2 py-1">
                    <span className="font-medium">{candidate.feature_name}</span>
                    <span>默认：{candidate.default_value}</span>
                    <span className="text-gray-500">{candidate.source}</span>
                  </div>
                ))}
              </div>
            </details>
          )}
          {(result.featureCheck.default_fills?.length ?? 0) > 0 && (
            <div className="mt-2 rounded border border-blue-200 bg-blue-50 px-2 py-2 text-blue-900">
              <div className="font-semibold">本次组价已补全 {result.featureCheck.default_fills?.length} 个特征，原清单未修改</div>
              <div className="mt-1 space-y-1">
                {result.featureCheck.default_fills?.map(fill => (
                  <div key={fill.candidate_id} className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="font-medium">{fill.target_feature_name}</span>
                    <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-medium text-blue-700">
                      {fill.match_state === 'vague' ? '模糊补全' : fill.match_state === 'missing' ? '缺失补全' : '综合考虑替换'}
                    </span>
                    <span>{fill.original_value || '未明确'} → {fill.default_value}（{fill.source}）</span>
                  </div>
                ))}
              </div>
              {result.featureCheck.effective_description && (
                <div className="mt-2 whitespace-pre-wrap rounded bg-white/80 px-2 py-1 text-blue-800">{result.featureCheck.effective_description}</div>
              )}
            </div>
          )}
          {(result.featureCheck.default_review_items?.length ?? 0) > 0 && (
            <div className="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-2 text-amber-900">
              <div className="font-semibold">原生默认值待人工复核，不参与本次组价</div>
              <div className="mt-1 space-y-1">
                {result.featureCheck.default_review_items?.map(fill => (
                  <div key={fill.candidate_id}>
                    <span className="font-medium">{fill.target_feature_name}</span>
                    <span>：建议 {fill.default_value}</span>
                    {fill.reason && <span className="text-amber-700">（{fill.reason}）</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
          {(result.featureCheck.unresolved_features?.length ?? 0) > 0 && (
            <div className="mt-2 text-amber-800">未补全：{result.featureCheck.unresolved_features?.join('、')}</div>
          )}
          <div className="mt-1 text-orange-800">{result.featureCheck.analysis}</div>
        </section>
      )}
      {result.chapterRuleCheck && (
        <section className="rounded border border-sky-200 bg-sky-50 px-3 py-2 text-xs">
          <div className="font-semibold text-sky-900">3. 章节规则校验</div>
          <div className="mt-1 text-sky-800">{result.chapterRuleCheck.chapters.map(chapter => chapter.chapter_name).join(' / ') || '未找到章节规则'}</div>
          {result.chapterRuleCheck.rules.filter(rule => rule.matched).map((rule, index) => (
            <div key={`${rule.chapter_id}-${index}`} className="mt-1 rounded bg-white px-2 py-1 text-slate-700">已命中：{rule.rule_reference || rule.rule_text}；{rule.action}</div>
          ))}
          {result.chapterRuleCheck.validation?.status === 'failed' && <div className="mt-1 text-red-700">规则校验未通过，需复核定额结果。</div>}
        </section>
      )}
      {result.quotaCandidates && (
        <section className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
          <div className="font-semibold text-slate-900">4. 定额候选：{result.quotaCandidates.total} 条</div>
          {result.quotaCandidates.candidates.some(candidate => candidate.source_tables?.includes('TQDK_TQDZY_SPECIAL')) && (
            <div className="mt-1 text-violet-600">已合并典型组价候选</div>
          )}
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
      {result.evaluation && (
        <section className="rounded border border-purple-200 bg-purple-50 px-3 py-2 text-xs">
          <div className="font-semibold text-purple-900">6. 人工对比</div>
          <div className="mt-1 text-purple-800">
            命中 {result.evaluation.hit_count}，遗漏 {result.evaluation.missed_count}，额外 {result.evaluation.extra_count}
          </div>
        </section>
      )}
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
  const [loading, setLoading] = useState(true)
  const stopRef = useRef(false)
  const reasoningRef = useRef<HTMLDivElement>(null)

  const focusedItem = focusedItemId ? items.find(item => item.id === focusedItemId) : undefined
  const focusedResult = focusedItemId ? itemResults.get(focusedItemId) : undefined
  const detailItem = detailItemId ? items.find(item => item.id === detailItemId) : undefined
  const detailResult = detailItemId ? itemResults.get(detailItemId) : undefined
  const selectedCount = selectedIds.size
  const confirmedCount = Array.from(batchStates.values()).filter(state => state === 'confirmed').length
  const failedCount = Array.from(batchStates.values()).filter(state => state === 'failed').length
  const doneCount = Array.from(batchStates.values()).filter(state => ['confirmed', 'failed', 'no_match', 'stopped'].includes(state)).length
  const pricedItems = items
    .map(item => ({ item, result: itemResults.get(item.id), state: batchStates.get(item.id) }))
    .filter(row => (row.result?.quotaMatch?.matches.length ?? 0) > 0)
  const quotaHitStats = buildQuotaHitStats(itemResults, items.length)

  useEffect(() => {
    if (!Number.isFinite(batchId)) return
    void bootstrap()
  }, [batchId])

  useEffect(() => {
    if (reasoningRef.current) reasoningRef.current.scrollTop = reasoningRef.current.scrollHeight
  }, [focusedResult?.reasoning])

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
          if (itemRun.run.status === 'confirmed') next.set(itemRun.boq_item_id, 'confirmed')
          else if (itemRun.run.status === 'failed') next.set(itemRun.boq_item_id, 'failed')
          else if (itemRun.run.status === 'no_match') next.set(itemRun.boq_item_id, 'no_match')
          else if (itemRun.run.status === 'running') next.set(itemRun.boq_item_id, 'running')
        }
        return next
      })
    } finally {
      setLoading(false)
    }
  }

  function setResult(itemId: number, updater: (prev: ItemResult) => ItemResult) {
    setItemResults(prev => {
      const current = prev.get(itemId) ?? { phase: 'idle', reasoning: '' }
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
    let snapshot = initial
    snapshot = {
      ...snapshot,
      conversionChecking: true,
      reasoning: `${snapshot.reasoning}${snapshot.reasoning ? '\n\n' : ''}【第六轮 组合换算】\n`,
    }
    applySnapshot(itemId, snapshot)
    await streamPricingTaskBatchConversionCheck(runId, (evt: PricingTaskEvent) => {
      if (evt.type === 'conversion_check_start') {
        snapshot = { ...snapshot, conversionChecking: true, conversionError: undefined }
      } else if (evt.type === 'combo_adjustment_rules') {
        snapshot = {
          ...snapshot,
          comboAdjustmentPreview: evt.items,
          conversionChecking: true,
          reasoning: `${snapshot.reasoning}${snapshot.reasoning.endsWith('\n') || !snapshot.reasoning ? '' : '\n'}已查询组合定额，正在识别项目特征数量。\n`,
        }
      } else if (evt.type === 'reasoning_token') {
        snapshot = { ...snapshot, reasoning: snapshot.reasoning + evt.token }
      } else if (evt.type === 'conversion_check') {
        snapshot = { ...snapshot, conversionCheck: evt.conversion_check, comboAdjustmentPreview: evt.conversion_check.items, conversionChecking: false }
      } else if (evt.type === 'step_timing') {
        snapshot = { ...snapshot, stepTimings: { ...(snapshot.stepTimings ?? {}), [String(evt.step_no)]: evt } }
      } else if (evt.type === 'error') {
        snapshot = { ...snapshot, conversionChecking: false, conversionError: evt.error, error: evt.error }
      } else if (evt.type === 'done') {
        snapshot = { ...snapshot, conversionChecking: false }
      }
      applySnapshot(itemId, snapshot)
    })
    if (snapshot.conversionError) throw new Error(snapshot.conversionError)

    snapshot = {
      ...snapshot,
      coefficientChecking: true,
      reasoning: `${snapshot.reasoning}${snapshot.reasoning ? '\n\n' : ''}【第七轮 系数换算】\n`,
    }
    applySnapshot(itemId, snapshot)
    await streamPricingTaskBatchCoefficientCheck(runId, (evt: PricingTaskEvent) => {
      if (evt.type === 'coefficient_check_start') {
        snapshot = { ...snapshot, coefficientChecking: true, coefficientError: undefined }
      } else if (evt.type === 'coefficient_rules') {
        snapshot = { ...snapshot, coefficientPreview: evt.items, coefficientChecking: true }
      } else if (evt.type === 'reasoning_token') {
        snapshot = { ...snapshot, reasoning: snapshot.reasoning + evt.token }
      } else if (evt.type === 'coefficient_check') {
        snapshot = { ...snapshot, coefficientCheck: evt.coefficient_check, coefficientPreview: evt.coefficient_check.items, coefficientChecking: false }
      } else if (evt.type === 'step_timing') {
        snapshot = { ...snapshot, stepTimings: { ...(snapshot.stepTimings ?? {}), [String(evt.step_no)]: evt } }
      } else if (evt.type === 'error') {
        snapshot = { ...snapshot, coefficientChecking: false, coefficientError: evt.error, error: evt.error }
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
    let snapshot: ItemResult = { phase: 'reasoning', reasoning: '', status: 'running', stepTimings: {} }
    setItemResults(prev => new Map(prev).set(item.id, snapshot))

    await streamPricingTaskBatchItemRun(batch!.id, item.id, (evt: PricingTaskEvent) => {
      snapshot = updateResultFromEvent(snapshot, evt)
      if (evt.type === 'done') snapshot = { ...snapshot, phase: 'done', status: 'completed' }
      setItemResults(prev => new Map(prev).set(item.id, snapshot))

    })

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
      setBatchState(item.id, 'no_match')
      return
    }
    try {
      snapshot = { ...snapshot, phase: 'done', status: 'confirmed' }
      applySnapshot(item.id, snapshot)
      snapshot = await runConversionAndCoefficient(item.id, runId, snapshot)
      setResult(item.id, prev => ({ ...prev, ...snapshot, phase: 'done', status: 'confirmed' }))
      setBatchState(item.id, 'confirmed')
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
    for (const item of queue) {
      if (stopRef.current) {
        setBatchState(item.id, 'stopped')
        continue
      }
      await runOne(item)
    }
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
            <div className="text-sm font-semibold text-gray-900">{batch.name}</div>
            <div className="mt-1 text-xs text-gray-500">
              批量组价 · {batch.project_name} · {batch.quota_library_names.length > 0 ? batch.quota_library_names.join('、') : '全部定额库'}
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
            <Link href="/pricing-task/batch" className="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50">
              返回批量列表
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
                        {result?.status && <span className="text-[11px] text-gray-500">{statusLabel(result.status)}</span>}
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
                  <span className="rounded bg-emerald-50 px-2 py-1 font-semibold text-emerald-700">已确认 {confirmedCount}</span>
                  <span className="rounded bg-red-50 px-2 py-1 font-semibold text-red-700">失败 {failedCount}</span>
                </div>
              </div>
              <div className="mt-2 truncate text-xs text-gray-500">
                当前项：{currentItemId ? items.find(item => item.id === currentItemId)?.item_name : '无'}
              </div>
            </div>
            <div ref={reasoningRef} className="flex-1 overflow-y-auto">
              <pre className="whitespace-pre-wrap px-4 py-3 font-mono text-xs leading-5 text-gray-700">
                {focusedResult?.reasoning || (focusedResult?.phase === 'reasoning' ? '等待模型流式输出...' : '选择清单后查看流式输出。')}
              </pre>
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
            <span className="text-xs text-gray-500">{pricedItems.length} 条</span>
          </div>
          {pricedItems.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-gray-400">暂无套定额结果</div>
          ) : (
            <div className="max-h-56 overflow-y-auto divide-y divide-gray-100">
              {pricedItems.map(({ item, result, state }) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setDetailItemId(item.id)}
                  className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-gray-50"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs text-gray-500">{item.item_code}</span>
                      <span className="truncate text-sm font-medium text-gray-900">{item.item_name}</span>
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      {(result?.quotaMatch?.matches.length ?? 0)} 条定额
                      {result?.evaluation ? ` · 命中 ${result.evaluation.hit_count} / 遗漏 ${result.evaluation.missed_count} / 额外 ${result.evaluation.extra_count}` : ''}
                    </div>
                  </div>
                  <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${batchStateClass(state)}`}>
                    {batchStateLabel(state)}
                  </span>
                </button>
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
              <button type="button" onClick={() => setDetailItemId(null)} className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50">
                关闭
              </button>
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
    </div>
  )
}
