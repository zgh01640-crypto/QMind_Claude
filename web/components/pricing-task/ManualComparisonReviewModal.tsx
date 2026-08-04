'use client'

import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  BoqItem,
  PricingTaskEvaluation,
  QuotaMatch,
  updatePricingTaskManualComparison,
} from '@/lib/api'

interface Props {
  open: boolean
  runId: number
  item: BoqItem
  evaluation: PricingTaskEvaluation
  matches: QuotaMatch[]
  dark?: boolean
  onClose: () => void
  onUpdated: (evaluation: PricingTaskEvaluation) => void
}

function manualMatchesAi(manualCode: string, matches: QuotaMatch[]) {
  return matches.some(match => match.zmbh && manualCode.includes(match.zmbh))
}

export default function ManualComparisonReviewModal({
  open,
  runId,
  item,
  evaluation,
  matches,
  dark = false,
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

  useEffect(() => {
    if (!open) return
    setSelectedManualIds(evaluation.manual_quotas.flatMap(quota => quota.id == null ? [] : [quota.id]))
    setSelectedAiKeys([])
    setError('')
  }, [open, evaluation])

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
      const result = await updatePricingTaskManualComparison(runId, {
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
    <div className='fixed inset-0 flex items-center justify-center bg-black/60 px-4 py-6' style={{ zIndex: 100 }}>
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
          <div className={`mb-4 rounded-md border px-4 py-3 text-xs ${dark ? 'border-amber-800/70 bg-amber-950/30 text-amber-200' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
            本操作会直接修改人工对比工程，不保留版本历史。双方一致的定额已锁定；请判断其余差异应保留人工结果，还是采纳 AI 结果。
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