'use client'

import { useEffect, useRef, useState } from 'react'
import { useParams } from 'next/navigation'
import {
  BoqItem,
  PricingTask,
  PricingTaskConversionCheck,
  PricingTaskEvaluation,
  PricingTaskEvent,
  PricingTaskRun,
  PricingTaskStepTiming,
  QuotaCandidate,
  QuotaMatch,
  confirmPricingTaskRun,
  fetchAllBoqItems,
  fetchPricingTaskLatestRuns,
  fetchPricingTask,
  fetchPricingTaskItemRuns,
  rejectPricingTaskRun,
  streamPricingTaskConversionCheck,
  streamPricingTaskRunItem,
  updateBoqItemDescription,
} from '@/lib/api'

interface CodeCheck {
  item_code: string
  item_name: string
  base_code: string
  standard_name: string
  found: boolean
  is_consistent: boolean
}

interface ItemResult {
  phase: 'reasoning' | 'done' | 'error'
  reasoning: string
  runId?: number
  status?: string
  codeCheck?: CodeCheck
  judgment?: { is_consistent: boolean; reasoning: string }
  featureCheck?: { is_complete: boolean; missing_features: string[]; analysis: string }
  workProcedures?: string[]
  workProcedureText?: string
  quotaCandidates?: { item_code: string; base_code: string; candidates: QuotaCandidate[]; total: number }
  quotaMatch?: { matches: QuotaMatch[]; issues: string[] }
  evaluation?: PricingTaskEvaluation
  conversionCheck?: PricingTaskConversionCheck
  conversionChecking?: boolean
  conversionError?: string
  stepTimings?: Record<string, PricingTaskStepTiming>
  error?: string
}

function runToResult(run: PricingTaskRun): ItemResult {
  const workProcedures = run.work_procedures as { procedures?: string[]; procedure_text?: string } | undefined
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
    workProcedures: workProcedures?.procedures,
    workProcedureText: workProcedures?.procedure_text,
    quotaCandidates: run.quota_candidates as ItemResult['quotaCandidates'],
    quotaMatch: run.quota_match as ItemResult['quotaMatch'],
    evaluation: run.evaluation ?? undefined,
    conversionCheck: run.conversion_check ?? undefined,
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
      title: '标准工序',
      tone: !result?.workProcedures ? 'pending' : result.workProcedures.length > 0 ? 'success' : 'warning',
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
      title: '换算判断',
      tone: result?.conversionChecking
        ? 'pending'
        : !result?.conversionCheck
          ? 'pending'
          : result.conversionCheck.items.some(item => item.needs_conversion)
            ? 'warning'
            : 'success',
    },
  ] as const
}

function activeStepNo(result?: ItemResult) {
  if (result?.conversionChecking) return 7
  if (!result || result.phase !== 'reasoning') return null
  if (!result.codeCheck) return 1
  if (!result.featureCheck) return 2
  if (!result.workProcedures) return 3
  if (!result.quotaCandidates) return 4
  if (!result.quotaMatch) return 5
  if (!result.evaluation) return 6
  return null
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
  const reasoningRef = useRef<HTMLDivElement>(null)

  const currentResult = selectedItemId ? itemResults.get(selectedItemId) : undefined
  const isRunning = currentResult?.phase === 'reasoning'

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

  async function handleMatch(itemId: number) {
    if (!task || isRunning) return
    setSelectedItemId(itemId)
    setItemResults(m => new Map(m).set(itemId, { phase: 'reasoning', reasoning: '', status: 'running', stepTimings: {} }))

    try {
      await streamPricingTaskRunItem(task.id, itemId, (evt: PricingTaskEvent) => {
        if (evt.type === 'run_started') {
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
            featureCheck: { is_complete: evt.is_complete, missing_features: evt.missing_features, analysis: evt.analysis },
          }))
        } else if (evt.type === 'work_procedures') {
          updateResult(itemId, s => ({ ...s, workProcedures: evt.procedures, workProcedureText: evt.procedure_text }))
        } else if (evt.type === 'quota_candidates') {
          updateResult(itemId, s => ({
            ...s,
            quotaCandidates: { item_code: evt.item_code, base_code: evt.base_code, candidates: evt.candidates, total: evt.total },
          }))
        } else if (evt.type === 'quota_match') {
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
          updateResult(itemId, s => ({ ...s, phase: 'done', status: 'completed', runId: evt.run_id ?? s.runId }))
        } else if (evt.type === 'error') {
          updateResult(itemId, s => ({ ...s, phase: 'error', status: 'failed', error: evt.error }))
        }
      })
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
            reasoning: `${s.reasoning}${s.reasoning ? '\n\n' : ''}【第七轮 换算判断】\n`,
          }))
        } else if (evt.type === 'reasoning_token') {
          updateResult(itemId, s => ({ ...s, reasoning: s.reasoning + evt.token }))
        } else if (evt.type === 'conversion_check') {
          updateResult(itemId, s => ({ ...s, conversionCheck: evt.conversion_check, conversionChecking: false }))
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
        conversionError: err instanceof Error ? err.message : '换算判断失败',
      }))
    }
  }

  async function handleConfirm() {
    if (!selectedItemId || !currentResult?.runId) return
    const itemId = selectedItemId
    const runId = currentResult.runId
    setActionBusy(true)
    try {
      await confirmPricingTaskRun(runId, currentResult.quotaMatch?.matches)
      updateResult(itemId, s => ({ ...s, status: 'confirmed' }))
    } finally {
      setActionBusy(false)
    }
    void runConversionCheck(runId, itemId)
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
  const canConfirm = currentResult?.phase === 'done' && currentResult.runId && currentResult.status !== 'confirmed'
  const canReject = currentResult?.phase === 'done' && currentResult.runId && currentResult.status !== 'rejected'

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-7xl mx-auto text-sm text-gray-700">
          <span className="font-semibold">任务：</span>{task.name}
          <span className="ml-4 font-semibold">工程：</span>{task.project_name}
          <span className="ml-4 font-semibold">定额库：</span>{libraryNames}
          {task.manual_project_id && (
            <span className="ml-4 text-gray-500">人工对比工程 #{task.manual_project_id}</span>
          )}
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="flex gap-6 h-[calc(100vh-200px)]">
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
                  <span>7换算</span>
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
                              {result?.quotaMatch && (
                                <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${statusClassName(result.status)}`}>
                                  已套
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
                    {currentResult.phase === 'reasoning' ? (
                      <span className="inline-block h-4 w-4 rounded-full border-2 border-amber-200 border-t-amber-600 animate-spin" title="运行中" />
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
                    <section className={`px-4 py-4 border-b ${currentResult.codeCheck.is_consistent ? 'bg-green-50 border-green-200' : 'bg-orange-50 border-orange-200'}`}>
                      <h4 className={`font-semibold text-sm mb-3 ${currentResult.codeCheck.is_consistent ? 'text-green-900' : 'text-orange-900'}`}>
                        1. 编码核查：{currentResult.codeCheck.is_consistent ? '名称一致' : '名称不一致'}
                        <StepDuration result={currentResult} stepNo={1} />
                      </h4>
                      <div className="space-y-2 text-xs">
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
                      <h4 className={`font-semibold text-sm mb-2 ${currentResult.featureCheck.is_complete ? 'text-green-900' : 'text-orange-900'}`}>
                        2. {currentResult.featureCheck.is_complete ? '项目特征完整' : '项目特征不完整'}
                        <StepDuration result={currentResult} stepNo={2} />
                      </h4>
                      {currentResult.featureCheck.missing_features.length > 0 && (
                        <ul className="text-xs text-orange-800 space-y-1 list-disc list-inside mb-2">
                          {currentResult.featureCheck.missing_features.map((f, i) => <li key={i}>{f}</li>)}
                        </ul>
                      )}
                      <p className="text-xs text-gray-600">{currentResult.featureCheck.analysis}</p>
                    </section>
                  )}

                  {(currentResult.workProcedureText || currentResult.workProcedures) && (
                    <section className="px-4 py-4 border-b bg-indigo-50 border-indigo-200">
                      <h4 className="font-semibold text-sm text-indigo-900 mb-3">3. 标准工序<StepDuration result={currentResult} stepNo={3} /></h4>
                      {currentResult.workProcedureText ? (
                        <div className="rounded border border-indigo-200 bg-white px-3 py-2 text-xs leading-6 text-indigo-900">
                          {currentResult.workProcedureText}
                        </div>
                      ) : (
                        <div className="flex flex-wrap gap-1 text-xs">
                          {currentResult.workProcedures?.map((p, i) => (
                            <span key={i} className="bg-indigo-100 text-indigo-800 px-2 py-0.5 rounded font-medium">
                              {i + 1}. {p}
                            </span>
                          ))}
                        </div>
                      )}
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
                      <h4 className="font-semibold text-sm text-purple-900 mb-2">6. 人工对比评估<StepDuration result={currentResult} stepNo={6} /></h4>
                      <div className="grid grid-cols-3 gap-2 text-xs mb-2">
                        <div className="bg-white rounded p-2 text-center"><div className="font-semibold">{currentResult.evaluation.hit_count}</div><div className="text-gray-500">命中</div></div>
                        <div className="bg-white rounded p-2 text-center"><div className="font-semibold">{currentResult.evaluation.missed_count}</div><div className="text-gray-500">遗漏</div></div>
                        <div className="bg-white rounded p-2 text-center"><div className="font-semibold">{currentResult.evaluation.extra_count}</div><div className="text-gray-500">额外</div></div>
                      </div>
                      {currentResult.evaluation.missed_codes.length > 0 && (
                        <p className="text-xs text-purple-700">遗漏：{currentResult.evaluation.missed_codes.join('、')}</p>
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
                                      {isHit ? '命中' : '未命中'}
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
                        <h4 className="font-semibold text-sm text-cyan-900">7. 换算判断<StepDuration result={currentResult} stepNo={7} /></h4>
                        {currentResult.conversionChecking && (
                          <span className="inline-block h-4 w-4 rounded-full border-2 border-cyan-200 border-t-cyan-700 animate-spin" title="换算判断运行中" />
                        )}
                      </div>
                      {currentResult.conversionError && (
                        <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                          换算判断失败：{currentResult.conversionError}
                        </div>
                      )}
                      {currentResult.conversionChecking && !currentResult.conversionCheck && (
                        <p className="text-xs text-cyan-700">正在根据已确认定额查询换算说明并判断...</p>
                      )}
                      {currentResult.conversionCheck && (
                        <div className="space-y-3 text-xs">
                          <div className="grid grid-cols-2 gap-2">
                            <div className="rounded bg-white p-2 text-center">
                              <div className="font-semibold text-amber-700">{currentResult.conversionCheck.items.filter(item => item.needs_conversion).length}</div>
                              <div className="text-gray-500">建议换算</div>
                            </div>
                            <div className="rounded bg-white p-2 text-center">
                              <div className="font-semibold text-emerald-700">{currentResult.conversionCheck.items.filter(item => !item.needs_conversion).length}</div>
                              <div className="text-gray-500">不建议换算</div>
                            </div>
                          </div>

                          {currentResult.conversionCheck.issues.length > 0 && (
                            <ul className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-amber-700 space-y-1 list-disc list-inside">
                              {currentResult.conversionCheck.issues.map((issue, i) => <li key={i}>{issue}</li>)}
                            </ul>
                          )}

                          <div className="space-y-2">
                            {currentResult.conversionCheck.items.map((item, i) => (
                              <div key={`${item.dekid}-${item.dezmid}-${i}`} className="rounded border border-cyan-100 bg-white px-3 py-2">
                                <div className="mb-1 flex items-start gap-2">
                                  <div className="min-w-0 flex-1">
                                    <div className="font-mono font-semibold text-cyan-800">{item.quota_code || '-'}</div>
                                    <div className="font-medium text-gray-900 break-words">{item.quota_name || '-'}</div>
                                  </div>
                                  <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${item.needs_conversion ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`}>
                                    {item.needs_conversion ? '建议换算' : '不换算'}
                                  </span>
                                </div>
                                <div className="mb-1 flex flex-wrap gap-x-3 gap-y-1 text-gray-500">
                                  <span>建议系数：{item.suggested_qty_factor}</span>
                                  <span>置信度：{item.confidence}</span>
                                </div>
                                <p className="text-gray-600">{item.reason || '未给出判断理由'}</p>
                                {item.matched_rules.length > 0 && (
                                  <div className="mt-2 rounded bg-cyan-50 px-2 py-1">
                                    <div className="mb-1 font-semibold text-cyan-900">命中的换算说明</div>
                                    <ul className="space-y-1">
                                      {item.matched_rules.map((rule, idx) => (
                                        <li key={idx}>
                                          <span className="text-cyan-800">{rule.prompt || '-'}</span>
                                          {rule.description && <span className="text-gray-500">：{rule.description}</span>}
                                          {rule.group_no ? <span className="ml-1 text-gray-400">#{rule.group_no}</span> : null}
                                        </li>
                                      ))}
                                    </ul>
                                  </div>
                                )}
                                {item.missing_inputs.length > 0 && (
                                  <div className="mt-2 text-amber-700">
                                    缺失实际值信息：{item.missing_inputs.join('、')}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </section>
                  )}

                  <section className="px-4 py-4 bg-white">
                    <div className="text-xs text-gray-500 mb-3">当前状态：{statusLabel(currentResult.status)}</div>
                    <div className="flex gap-2">
                      <button
                        onClick={handleConfirm}
                        disabled={!canConfirm || actionBusy}
                        className="flex-1 px-3 py-2 bg-emerald-600 text-white text-sm rounded hover:bg-emerald-700 disabled:opacity-50"
                      >
                        确认结果
                      </button>
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
      </div>
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
