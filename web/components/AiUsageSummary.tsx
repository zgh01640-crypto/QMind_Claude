'use client'

import { useEffect, useState } from 'react'

type Summary = { call_count: number; unknown_usage_count: number; coverage_rate: number; total_tokens: number; known_cost_yuan: number }

export default function AiUsageSummary({ taskId, batchId }: { taskId?: number; batchId?: number }) {
  const [data, setData] = useState<Summary | null>(null)
  useEffect(() => {
    const query = taskId != null ? `task_id=${taskId}` : `batch_id=${batchId}`
    fetch(`/api/ai-usage/summary?${query}`, { cache: 'no-store' }).then(response => response.ok ? response.json() : null).then(setData).catch(() => undefined)
  }, [taskId, batchId])
  if (!data) return null
  return <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-600">
    <span className="rounded border border-violet-200 bg-violet-50 px-2 py-1">Token {Number(data.total_tokens).toLocaleString()}</span>
    <span className="rounded border border-emerald-200 bg-emerald-50 px-2 py-1">已知费用 ¥{Number(data.known_cost_yuan).toFixed(6)}</span>
    <span className={`rounded border px-2 py-1 ${data.unknown_usage_count ? 'border-amber-200 bg-amber-50 text-amber-700' : 'border-slate-200 bg-slate-50'}`}>计量 {(data.coverage_rate * 100).toFixed(1)}% · {data.call_count} 次</span>
  </div>
}
