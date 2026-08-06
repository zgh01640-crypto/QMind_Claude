'use client'

import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  BoqItem,
  PricingTaskEvaluation,
  PricingTaskManualComparisonInput,
  PricingTaskManualComparisonResult,
  PricingTaskManualComparisonReview,
  QuotaMatch,
} from '@/lib/api'

interface Props {
  open: boolean
  item: BoqItem
  evaluation: PricingTaskEvaluation
  matches: QuotaMatch[]
  dark?: boolean
  submitReview: (input: PricingTaskManualComparisonInput) => Promise<PricingTaskManualComparisonResult>
  loadHistory: () => Promise<PricingTaskManualComparisonReview[]>
  onClose: () => void
  onUpdated: (evaluation: PricingTaskEvaluation) => void
}

function manualMatchesAi(manualCode: string, matches: QuotaMatch[]) {
  return matches.some(match => match.zmbh && manualCode.includes(match.zmbh))
}

export default function ManualComparisonReviewModal({
  open,
  item,
  evaluation,
  matches,
  dark = false,
  submitReview,
  loadHistory,
  onClose,
  onUpdated,
}: Props) {
  const sharedManual = useMemo(
    () => evaluation.manual_quotas.filter(quota => manualMatchesAi(quota.quota_code || '', matches)),
    [evaluation.manual_quotas, matches],
  )
  const manualOnly = useMemo(
    () => evaluation.manual_quotas.filter(quota => !manualMatchesAi(quota.quota_code || '', matches)),
    [evaluation.manual_quotas, matches],
  )
  const aiOnly = useMemo(
    () => matches.filter(match => !evaluation.manual_quotas.some(quota => match.zmbh && (quota.quota_code || '').includes(match.zmbh))),
    [evaluation.manual_quotas, matches],
  )
  const [selectedManualIds, setSelectedManualIds] = useState<number[]>([])
  const [selectedAiKeys, setSelectedAiKeys] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [history, setHistory] = useState<PricingTaskManualComparisonReview[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState('')

  useEffect(() => {
    if (!open) return
    setSelectedManualIds(evaluation.manual_quotas.flatMap(quota => quota.id == null ? [] : [quota.id]))
    setSelectedAiKeys([])
    setError('')
  }, [open, evaluation])

  useEffect(() => {
    if (!open) return
    let active = true
    setHistory([])
    setHistoryError('')
    setHistoryLoading(true)
    void loadHistory()
      .then(rows => {
        if (active) setHistory(rows)
      })
      .catch(err => {
        if (active) setHistoryError(err instanceof Error ? err.message : '复核记录加载失败')
      })
      .finally(() => {
        if (active) setHistoryLoading(false)
      })
    return () => {
      active = false
    }
    // Load once whenever this run's modal is opened.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  if (!open) return null

  const aiKey = (match: QuotaMatch) => `${match.dekid}:${match.dezmid}`
  const finalCount = selectedManualIds.length + selectedAiKeys.length
  const panel = dark ? 'border-slate-700 bg-slate-950 text-slate-100' : 'border-gray-200 bg-white text-gray-900'
  const section = dark ? 'border-slate-700 bg-slate-900/80' : 'border-gray-200 bg-gray-50'
  const muted = dark ? 'text-slate-400' : 'text-gray-500'

  function toggleManual(id: number) {
    setSelectedManualIds(current => current.includes(id) ? current.filter(value => value !== id) : [...current, id])
  }

  function toggleAi(key: string) {
    setSelectedAiKeys(current => current.includes(key) ? current.filter(value => value !== key) : [...current, key])
  }

  async function submit() {
    if (finalCount === 0) {
      setError('最终定额集合至少保留一条定额。')
      return
    }
    setSaving(true)
    setError('')
    try {
      const accepted = aiOnly
        .filter(match => selectedAiKeys.includes(aiKey(match)))
        .flatMap(match => match.dekid == null || match.dezmid == null ? [] : [{ dekid: match.dekid, dezmid: match.dezmid }])
      if (accepted.length !== selectedAiKeys.length) {
        throw new Error('部分 AI 定额缺少库内标识，无法写入人工工程。')
      }
      const result = await submitReview({
        retained_manual_quota_ids: selectedManualIds,
        accepted_ai_quotas: accepted,
      })
      onUpdated(result.evaluation)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : '人工对比工程修正失败')
    } finally {
      setSaving(false)
    }
  }

  return createPortal(
    <div className='fixed inset-0 flex items-center justify-center bg-black/60 px-4 py-6' style={{ zIndex: 110 }}>
      <div className={`flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-lg border shadow-2xl ${panel}`}>
        <header className={`flex items-start justify-between gap-4 border-b px-5 py-4 ${dark ? 'border-slate-700' : 'border-gray-200'}`}>
          <div>
            <h3 className='text-base font-semibold'>人工对比差异复核</h3>
            <p className={`mt-1 text-xs ${muted}`}>
              {item.item_code} · {item.item_name} · 选择复核后的最终定额集合
            </p>
          </div>
          <button type='button' onClick={onClose} disabled={saving} className={`text-sm ${dark ? 'text-slate-400 hover:text-white' : 'text-gray-500 hover:text-gray-900'}`}>
            关闭
          </button>
        </header>

        <div className='overflow-y-auto px-5 py-4'>
          <section className={`mb-4 rounded-md border px-4 py-3 ${dark ? 'border-cyan-900/70 bg-cyan-950/20' : 'border-sky-200 bg-sky-50/70'}`}>
            <div className='flex items-center justify-between gap-3'>
              <h4 className={`text-xs font-semibold ${dark ? 'text-cyan-300' : 'text-sky-800'}`}>{'\u6e05\u5355\u9879\u76ee\u7279\u5f81'}</h4>
              <span className={`text-[11px] ${muted}`}>
                {item.unit || '\u65e0\u5355\u4f4d'} {'\u00b7 \u5de5\u7a0b\u91cf'} {item.quantity ?? '-'}
              </span>
            </div>
            <div className={`mt-2 max-h-32 overflow-y-auto whitespace-pre-wrap break-words rounded border px-3 py-2 text-xs leading-5 ${dark ? 'border-slate-700 bg-slate-950/60 text-slate-200' : 'border-sky-100 bg-white text-gray-700'}`}>
              {item.item_description?.trim() || '\u672a\u586b\u5199\u9879\u76ee\u7279\u5f81'}
            </div>
          </section>

          <div className={`mb-4 rounded-md border px-4 py-3 text-xs ${dark ? 'border-amber-800/70 bg-amber-950/30 text-amber-200' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
            本操作会直接修改人工对比工程，复核前后的差异与选择会保留在历史记录中。双方一致的定额已锁定；请判断其余差异应保留人工结果，还是采纳 AI 结果。
          </div>

          <div className='grid gap-4 lg:grid-cols-3'>
            <section className={`rounded-md border p-3 ${section}`}>
              <div className='mb-3 flex items-center justify-between'>
                <h4 className='text-sm font-semibold text-emerald-500'>双方一致</h4>
                <span className={`text-xs ${muted}`}>{sharedManual.length} 条 · 已锁定</span>
              </div>
              <div className='space-y-2'>
                {sharedManual.length === 0 && <p className={`py-5 text-center text-xs ${muted}`}>暂无一致定额</p>}
                {sharedManual.map(quota => (
                  <label key={quota.id ?? quota.quota_code} className={`block rounded border p-3 ${dark ? 'border-emerald-900/70 bg-emerald-950/20' : 'border-emerald-200 bg-white'}`}>
                    <div className='flex items-start gap-2'>
                      <input type='checkbox' checked readOnly className='mt-0.5 accent-emerald-600' />
                      <div className='min-w-0'>
                        <div className='font-mono text-xs font-semibold text-emerald-500'>{quota.quota_code}</div>
                        <div className='mt-1 text-xs leading-5'>{quota.quota_name || '-'}</div>
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            </section>

            <section className={`rounded-md border p-3 ${section}`}>
              <div className='mb-3 flex items-center justify-between'>
                <h4 className='text-sm font-semibold text-amber-500'>仅人工存在</h4>
                <span className={`text-xs ${muted}`}>{manualOnly.length} 条 · 默认保留</span>
              </div>
              <div className='space-y-2'>
                {manualOnly.length === 0 && <p className={`py-5 text-center text-xs ${muted}`}>暂无仅人工定额</p>}
                {manualOnly.map(quota => (
                  <label key={quota.id ?? quota.quota_code} className={`block rounded border p-3 ${dark ? 'border-slate-700 bg-slate-950/60' : 'border-gray-200 bg-white'} ${quota.id == null ? 'opacity-60' : 'cursor-pointer'}`}>
                    <div className='flex items-start gap-2'>
                      <input
                        type='checkbox'
                        checked={quota.id != null && selectedManualIds.includes(quota.id)}
                        disabled={quota.id == null}
                        onChange={() => quota.id != null && toggleManual(quota.id)}
                        className='mt-0.5 accent-amber-500'
                      />
                      <div className='min-w-0'>
                        <div className='font-mono text-xs font-semibold text-amber-500'>{quota.quota_code}</div>
                        <div className='mt-1 text-xs leading-5'>{quota.quota_name || '-'}</div>
                        <div className={`mt-1 text-[11px] ${muted}`}>{quota.quota_unit || '-'} · 系数 {quota.qty_factor ?? '-'}</div>
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            </section>

            <section className={`rounded-md border p-3 ${section}`}>
              <div className='mb-3 flex items-center justify-between'>
                <h4 className='text-sm font-semibold text-cyan-500'>仅 AI 存在</h4>
                <span className={`text-xs ${muted}`}>{aiOnly.length} 条 · 默认不采纳</span>
              </div>
              <div className='space-y-2'>
                {aiOnly.length === 0 && <p className={`py-5 text-center text-xs ${muted}`}>暂无仅 AI 定额</p>}
                {aiOnly.map(match => {
                  const key = aiKey(match)
                  const canAccept = match.dekid != null && match.dezmid != null
                  return (
                    <label key={key} className={`block rounded border p-3 ${dark ? 'border-slate-700 bg-slate-950/60' : 'border-gray-200 bg-white'} ${canAccept ? 'cursor-pointer' : 'opacity-60'}`}>
                      <div className='flex items-start gap-2'>
                        <input
                          type='checkbox'
                          checked={canAccept && selectedAiKeys.includes(key)}
                          disabled={!canAccept}
                          onChange={() => canAccept && toggleAi(key)}
                          className='mt-0.5 accent-cyan-500'
                        />
                        <div className='min-w-0'>
                          <div className='font-mono text-xs font-semibold text-cyan-500'>{match.zmbh}</div>
                          <div className='mt-1 text-xs leading-5'>{match.zmmc}</div>
                          <div className={`mt-1 text-[11px] ${muted}`}>{match.dw || '-'} · 系数 {match.qty_factor}</div>
                          {match.match_reason && <p className={`mt-2 text-[11px] leading-4 ${muted}`}>{match.match_reason}</p>}
                        </div>
                      </div>
                    </label>
                  )
                })}
              </div>
            </section>
          </div>

          <details className={`mt-4 overflow-hidden rounded-md border ${section}`}>
            <summary className='flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-semibold'>
              <span>复核记录</span>
              <span className={`text-xs font-normal ${muted}`}>{historyLoading ? '加载中…' : `${history.length} 次`}</span>
            </summary>
            <div className={`border-t px-4 py-3 ${dark ? 'border-slate-700' : 'border-gray-200'}`}>
              {historyError && <div className={`rounded border px-3 py-2 text-xs ${dark ? 'border-red-900 bg-red-950/40 text-red-300' : 'border-red-200 bg-red-50 text-red-700'}`}>{historyError}</div>}
              {!historyLoading && !historyError && history.length === 0 && (
                <p className={`py-3 text-center text-xs ${muted}`}>暂无复核记录</p>
              )}
              <div className='space-y-2'>
                {history.map(review => (
                  <div key={review.id} className={`rounded border px-3 py-2.5 ${dark ? 'border-slate-700 bg-slate-950/50' : 'border-gray-200 bg-white'}`}>
                    <div className='flex flex-wrap items-center justify-between gap-2 text-xs'>
                      <span className='font-medium'>{new Date(review.created_at).toLocaleString()}</span>
                      <span className={muted}>{review.operator_name || '系统'}</span>
                    </div>
                    <div className={`mt-2 flex flex-wrap items-center gap-2 text-[11px] ${muted}`}>
                      <span>复核前：命中 {review.before_evaluation.hit_count} / 遗漏 {review.before_evaluation.missed_count} / 额外 {review.before_evaluation.extra_count}</span>
                      <span aria-hidden>→</span>
                      <span className={review.after_evaluation.missed_count === 0 && review.after_evaluation.extra_count === 0 ? 'font-semibold text-emerald-500' : 'font-semibold text-amber-500'}>
                        复核后：命中 {review.after_evaluation.hit_count} / 遗漏 {review.after_evaluation.missed_count} / 额外 {review.after_evaluation.extra_count}
                      </span>
                    </div>
                    <div className={`mt-2 space-y-1 text-[11px] ${muted}`}>
                      <div>复核前差异：仅人工 {review.before_evaluation.missed_codes.join('、') || '-'}；仅 AI {review.before_evaluation.extra_codes.join('、') || '-'}</div>
                      <div>复核后差异：仅人工 {review.after_evaluation.missed_codes.join('、') || '-'}；仅 AI {review.after_evaluation.extra_codes.join('、') || '-'}</div>
                      <div>人工工程：{review.before_manual_quotas.map(quota => quota.quota_code).filter(Boolean).join('、') || '-'} → {review.after_manual_quotas.map(quota => quota.quota_code).filter(Boolean).join('、') || '-'}</div>
                    </div>
                    <div className={`mt-1 text-[11px] ${muted}`}>
                      保留人工 {review.retained_manual_quota_ids.length} 条 · 采纳 AI {review.accepted_ai_quotas.length} 条
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </details>

          {error && <div className={`mt-4 rounded border px-3 py-2 text-xs ${dark ? 'border-red-900 bg-red-950/40 text-red-300' : 'border-red-200 bg-red-50 text-red-700'}`}>{error}</div>}
        </div>

        <footer className={`flex items-center justify-between gap-4 border-t px-5 py-4 ${dark ? 'border-slate-700 bg-slate-950' : 'border-gray-200 bg-gray-50'}`}>
          <div className={`text-xs ${muted}`}>最终保留 <span className={`text-sm font-semibold ${dark ? 'text-white' : 'text-gray-900'}`}>{finalCount}</span> 条定额</div>
          <div className='flex items-center gap-2'>
            <button type='button' onClick={onClose} disabled={saving} className={`rounded border px-4 py-2 text-sm ${dark ? 'border-slate-600 text-slate-300 hover:bg-slate-800' : 'border-gray-300 text-gray-600 hover:bg-white'}`}>取消</button>
            <button type='button' onClick={() => void submit()} disabled={saving || finalCount === 0} className='rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50'>
              {saving ? '正在修改…' : '确认并修改人工工程'}
            </button>
          </div>
        </footer>
      </div>
    </div>,
    document.body,
  )
}