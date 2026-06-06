'use client'
import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import {
  fetchBoqProjects, fetchQuotaStandards,
  BoqProject, QuotaStandard, ParallelStreamEvent,
  streamMatchBoqProjectParallel,
} from '@/lib/api'

interface SlotItem {
  boq_item_id: number
  name: string
  status: 'done' | 'error'
  matchCount: number
  elapsed_ms: number
  errorMsg?: string
}

interface SlotState {
  current: { boq_item_id: number; name: string } | null
  history: SlotItem[]
}

interface RunState {
  phase: 'idle' | 'running' | 'done' | 'error'
  runId: number | null
  total: number
  done: number
  slots: SlotState[]
}

const emptySlots = (n: number): SlotState[] =>
  Array.from({ length: n }, () => ({ current: null, history: [] }))

export default function ParallelPage() {
  const { id: projectId } = useParams<{ id: string }>()

  const [project, setProject] = useState<BoqProject | null>(null)
  const [standards, setStandards] = useState<QuotaStandard[]>([])
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [concurrency, setConcurrency] = useState(4)
  const [runName, setRunName] = useState('')
  const [runState, setRunState] = useState<RunState>({
    phase: 'idle', runId: null, total: 0, done: 0, slots: emptySlots(4),
  })
  const [error, setError] = useState('')

  useEffect(() => {
    fetchBoqProjects().then(ps => {
      const p = ps.find(p => p.id === Number(projectId))
      if (p) setProject(p)
    })
    fetchQuotaStandards().then(setStandards)
  }, [projectId])

  const running = runState.phase === 'running'

  const handleStart = async () => {
    if (!selectedIds.length) { setError('请至少选择一个定额标准'); return }
    if (!runName.trim()) { setError('请填写本次名称'); return }
    setError('')
    setRunState({ phase: 'running', runId: null, total: 0, done: 0, slots: emptySlots(concurrency) })

    try {
      await streamMatchBoqProjectParallel(
        Number(projectId), selectedIds, runName, concurrency,
        (e: ParallelStreamEvent) => {
          if (e.type === 'run_start') {
            setRunState(s => ({ ...s, total: e.total, slots: emptySlots(e.slots) }))
          } else if (e.type === 'slot_start') {
            setRunState(s => {
              const slots = s.slots.map((sl, i) =>
                i === e.slot ? { ...sl, current: { boq_item_id: e.boq_item_id, name: e.item_name } } : sl
              )
              return { ...s, slots }
            })
          } else if (e.type === 'slot_done') {
            setRunState(s => {
              const slots = s.slots.map((sl, i) => {
                if (i !== e.slot) return sl
                return {
                  current: null,
                  history: [...sl.history, {
                    boq_item_id: e.boq_item_id, name: e.item_name,
                    status: 'done' as const, matchCount: e.matches.length, elapsed_ms: e.elapsed_ms,
                  }],
                }
              })
              return { ...s, done: s.done + 1, slots }
            })
          } else if (e.type === 'slot_error') {
            setRunState(s => {
              const slots = s.slots.map((sl, i) => {
                if (i !== e.slot) return sl
                return {
                  current: null,
                  history: [...sl.history, {
                    boq_item_id: e.boq_item_id, name: e.item_name,
                    status: 'error' as const, matchCount: 0, elapsed_ms: 0, errorMsg: e.error,
                  }],
                }
              })
              return { ...s, done: s.done + 1, slots }
            })
          } else if (e.type === 'run_done') {
            setRunState(s => ({ ...s, phase: 'done', runId: e.run_id }))
          } else if (e.type === 'run_error') {
            setRunState(s => ({ ...s, phase: 'error' }))
            setError(e.error)
          }
        },
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : '套定额失败')
      setRunState(s => ({ ...s, phase: 'error' }))
    }
  }

  const pct = runState.total > 0 ? (runState.done / runState.total) * 100 : 0

  return (
    <div className="max-w-6xl mx-auto py-6 px-4">
      {/* 面包屑 */}
      <div className="flex items-center gap-1.5 text-sm text-gray-500 mb-6">
        <Link href="/boq" className="hover:text-blue-600">工程管理</Link>
        <span>/</span>
        <Link href={`/boq/${projectId}`} className="hover:text-blue-600">
          {project?.project_name ?? '…'}
        </Link>
        <span>/</span>
        <span className="text-gray-800 font-medium">⚡ 并行套定额</span>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4 text-sm">{error}</div>
      )}

      {/* 配置行 */}
      <div className="bg-white rounded-lg shadow p-4 mb-4">
        <div className="flex flex-wrap gap-4 items-end">
          {/* 定额标准 */}
          <div className="flex-1 min-w-[220px]">
            <label className="block text-xs text-gray-500 mb-1.5">定额标准</label>
            <div className="flex flex-wrap gap-3">
              {standards.map(s => (
                <label key={s.id} className="flex items-center gap-1.5 text-sm text-gray-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(s.id)}
                    disabled={running}
                    onChange={e => {
                      if (e.target.checked) setSelectedIds(ids => [...ids, s.id])
                      else setSelectedIds(ids => ids.filter(i => i !== s.id))
                    }}
                  />
                  {s.name}
                </label>
              ))}
            </div>
          </div>

          {/* 并发数 */}
          <div>
            <label className="block text-xs text-gray-500 mb-1.5">并发槽数</label>
            <select
              value={concurrency}
              disabled={running}
              onChange={e => setConcurrency(Number(e.target.value))}
              className="border rounded px-2 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-1 focus:ring-indigo-400 disabled:opacity-50"
            >
              <option value={2}>2 个槽</option>
              <option value={4}>4 个槽</option>
              <option value={8}>8 个槽</option>
            </select>
          </div>

          {/* 名称 */}
          <div className="flex-1 min-w-[180px]">
            <label className="block text-xs text-gray-500 mb-1.5">本次名称</label>
            <input
              type="text"
              value={runName}
              disabled={running}
              onChange={e => setRunName(e.target.value)}
              placeholder="例：并行第1轮"
              className="w-full border rounded px-2 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-1 focus:ring-indigo-400 disabled:opacity-50"
            />
          </div>

          {/* 开始按钮 */}
          <button
            onClick={handleStart}
            disabled={running || !selectedIds.length || !runName.trim()}
            className="px-5 py-1.5 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2 shrink-0"
          >
            {running
              ? <><span className="animate-spin inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full" />运行中…</>
              : '⚡ 开始'}
          </button>
        </div>
      </div>

      {/* 进度条 + 完成按钮 */}
      {runState.phase !== 'idle' && (
        <div className="bg-white rounded-lg shadow px-4 py-3 mb-4 flex items-center gap-4">
          <div className="flex-1">
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>
                {runState.phase === 'done' ? '全部完成' : runState.phase === 'running' ? '进行中' : '出错'}
                {' '}{runState.done} / {runState.total}
              </span>
              <span>{pct.toFixed(0)}%</span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all duration-300 ${runState.phase === 'done' ? 'bg-green-500' : 'bg-indigo-500'}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
          {runState.phase === 'done' && runState.runId && (
            <Link
              href={`/boq/${projectId}/run/${runState.runId}`}
              className="px-4 py-1.5 bg-green-600 text-white text-sm rounded hover:bg-green-700 shrink-0"
            >
              查看结果 →
            </Link>
          )}
        </div>
      )}

      {/* 槽卡片区 */}
      {runState.slots.length > 0 && (
        <div
          className="grid gap-3"
          style={{ gridTemplateColumns: `repeat(${Math.min(runState.slots.length, 4)}, minmax(0, 1fr))` }}
        >
          {runState.slots.map((slot, idx) => (
            <SlotCard key={idx} slot={idx} state={slot} phase={runState.phase} />
          ))}
        </div>
      )}
    </div>
  )
}

function SlotCard({ slot, state, phase }: {
  slot: number
  state: SlotState
  phase: RunState['phase']
}) {
  const idle = phase !== 'running' && state.current === null

  return (
    <div className="bg-white rounded-lg shadow flex flex-col overflow-hidden">
      {/* 槽头 */}
      <div className={`px-3 py-2 flex items-center gap-2 text-xs font-semibold border-b ${
        state.current ? 'bg-indigo-50 border-indigo-100 text-indigo-700'
          : idle ? 'bg-gray-50 border-gray-100 text-gray-400'
          : 'bg-green-50 border-green-100 text-green-700'
      }`}>
        <span className={`inline-block w-2 h-2 rounded-full ${
          state.current ? 'bg-indigo-400 animate-pulse'
            : idle ? 'bg-gray-300'
            : 'bg-green-400'
        }`} />
        槽 {slot + 1}
        <span className="ml-auto font-normal text-[11px]">
          已完成 {state.history.length}
        </span>
      </div>

      {/* 当前正在处理的条目 */}
      <div className={`px-3 py-2.5 border-b min-h-[52px] flex items-center gap-2 ${
        state.current ? 'bg-indigo-50/40' : 'bg-gray-50/60'
      }`}>
        {state.current ? (
          <>
            <span className="animate-spin inline-block w-3.5 h-3.5 border-2 border-indigo-400 border-t-transparent rounded-full shrink-0" />
            <span className="text-xs text-indigo-800 font-medium line-clamp-2 leading-tight">
              {state.current.name}
            </span>
          </>
        ) : (
          <span className="text-xs text-gray-400 italic">
            {idle ? '空闲' : '已完成'}
          </span>
        )}
      </div>

      {/* 历史条目 */}
      <div className="flex-1 overflow-y-auto max-h-[360px] divide-y divide-gray-50">
        {state.history.length === 0 ? (
          <div className="px-3 py-4 text-center text-xs text-gray-300">等待结果…</div>
        ) : (
          [...state.history].reverse().map((item, i) => (
            <div key={i} className="px-3 py-2 flex items-start gap-2">
              <span className="shrink-0 text-sm leading-none mt-0.5">
                {item.status === 'done' ? '✅' : '❌'}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-xs text-gray-700 line-clamp-2 leading-tight">{item.name}</div>
                {item.status === 'done' ? (
                  <div className="text-[11px] text-gray-400 mt-0.5">
                    {item.matchCount > 0 ? `${item.matchCount} 条` : '无匹配'}
                    {' · '}{(item.elapsed_ms / 1000).toFixed(1)}s
                  </div>
                ) : (
                  <div className="text-[11px] text-red-500 mt-0.5 line-clamp-1">{item.errorMsg}</div>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
