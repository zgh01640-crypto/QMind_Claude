'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import {
  fetchDebugBatches, createDebugBatch, deleteDebugBatch,
  fetchBoqProjects, fetchQuotaStandards, fetchManualBoqProjects,
  DebugBatch, BoqProject, QuotaStandard, ManualBoqProject,
} from '@/lib/api'

// ── 定额标准选择器 ─────────────────────────────────────────────────────────────

function StandardSelector({
  standards, selected, onChange,
}: {
  standards: QuotaStandard[]
  selected: number[]
  onChange: (ids: number[]) => void
}) {
  const byRegion = standards.reduce<Record<string, QuotaStandard[]>>((acc, s) => {
    const r = s.region || '其他'
    ;(acc[r] = acc[r] || []).push(s)
    return acc
  }, {})

  return (
    <div className="flex flex-wrap gap-2">
      {Object.entries(byRegion).map(([region, stds]) => {
        const ids = stds.map(s => s.id)
        const allSel = ids.every(id => selected.includes(id))
        return (
          <div key={region} className="flex items-center gap-1.5 border rounded-lg px-2.5 py-1">
            <button
              type="button"
              onClick={() => onChange(allSel ? selected.filter(id => !ids.includes(id)) : Array.from(new Set([...selected, ...ids])))}
              className={`text-xs font-semibold px-1.5 py-0.5 rounded transition ${allSel ? 'bg-indigo-600 text-white' : 'bg-white text-gray-600 border border-gray-300 hover:border-indigo-400'}`}
            >
              {region}（全部）
            </button>
            {stds.map(s => {
              const checked = selected.includes(s.id)
              return (
                <label key={s.id} className="flex items-center gap-1 text-xs cursor-pointer">
                  <input type="checkbox" checked={checked}
                    onChange={() => onChange(checked ? selected.filter(id => id !== s.id) : [...selected, s.id])}
                    className="accent-indigo-600" />
                  <span className="text-gray-700">{s.standard_code}</span>
                </label>
              )
            })}
          </div>
        )
      })}
    </div>
  )
}

// ── 新建批次弹窗 ───────────────────────────────────────────────────────────────

function CreateBatchModal({
  projects, standards, manualProjects, onClose, onCreate,
}: {
  projects: BoqProject[]
  standards: QuotaStandard[]
  manualProjects: ManualBoqProject[]
  onClose: () => void
  onCreate: (id: number) => void
}) {
  const [projId, setProjId] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [stdIds, setStdIds] = useState<number[]>(standards.map(s => s.id))
  const [manualId, setManualId] = useState<number | null>(
    manualProjects.length > 0 ? manualProjects[0].id : null
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // standards 异步加载时同步初始选中状态
  useEffect(() => {
    if (stdIds.length === 0 && standards.length > 0) setStdIds(standards.map(s => s.id))
  }, [standards])  // eslint-disable-line react-hooks/exhaustive-deps

  // manualProjects 异步加载时设默认值
  useEffect(() => {
    if (manualId === null && manualProjects.length > 0) setManualId(manualProjects[0].id)
  }, [manualProjects])  // eslint-disable-line react-hooks/exhaustive-deps

  function handleProjectChange(id: number | null) {
    setProjId(id)
    if (id) {
      const p = projects.find(p => p.id === id)
      if (p) setName(p.project_name + (p.bid_section ? ` · ${p.bid_section}` : ''))
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!projId) { setError('请选择工程'); return }
    if (!name.trim()) { setError('批次名不能为空'); return }
    if (stdIds.length === 0) { setError('请至少选择一个定额标准'); return }
    setSaving(true)
    try {
      const { id } = await createDebugBatch({
        name: name.trim(),
        boq_project_id: projId,
        manual_project_id: manualId,
        standard_ids: stdIds,
      })
      onCreate(id)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '创建失败')
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg p-6 space-y-5 max-h-[90vh] overflow-y-auto">
        <h2 className="text-base font-semibold text-gray-800">新建调试批次</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* 工程选择 */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">BOQ 工程 *</label>
            <select
              className="w-full border border-gray-200 rounded px-2 py-1.5 text-sm"
              value={projId ?? ''}
              onChange={e => handleProjectChange(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">-- 请选择工程 --</option>
              {projects.map(p => (
                <option key={p.id} value={p.id}>
                  {p.project_name}{p.bid_section ? ` · ${p.bid_section}` : ''}
                </option>
              ))}
            </select>
          </div>

          {/* 批次名 */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">批次名称 *</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="输入批次名称…"
              className="w-full border border-gray-200 rounded px-2 py-1.5 text-sm"
            />
          </div>

          {/* 定额标准 */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">定额标准 *</label>
            <StandardSelector standards={standards} selected={stdIds} onChange={setStdIds} />
          </div>

          {/* 人工标准工程 */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">人工标准工程（可选）</label>
            <select
              className="w-full border border-gray-200 rounded px-2 py-1.5 text-sm"
              value={manualId ?? ''}
              onChange={e => setManualId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">-- 不对比人工标准 --</option>
              {manualProjects.map(p => (
                <option key={p.id} value={p.id}>{p.project_name}</option>
              ))}
            </select>
          </div>

          {error && <p className="text-xs text-red-500">{error}</p>}

          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose}
              className="px-4 py-1.5 text-sm rounded border border-gray-200 hover:bg-gray-50">
              取消
            </button>
            <button type="submit" disabled={saving}
              className="px-4 py-1.5 text-sm rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50">
              {saving ? '创建中…' : '创建并进入'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── 主页面 ─────────────────────────────────────────────────────────────────────

export default function DebugBatchListPage() {
  const router = useRouter()
  const [batches, setBatches] = useState<DebugBatch[]>([])
  const [projects, setProjects] = useState<BoqProject[]>([])
  const [standards, setStandards] = useState<QuotaStandard[]>([])
  const [manualProjects, setManualProjects] = useState<ManualBoqProject[]>([])
  const [showModal, setShowModal] = useState(false)
  const [deleting, setDeleting] = useState<number | null>(null)

  useEffect(() => {
    fetchDebugBatches().then(setBatches).catch(() => {})
    Promise.all([
      fetchBoqProjects(),
      fetchQuotaStandards(),
      fetchManualBoqProjects(),
    ]).then(([p, s, m]) => {
      setProjects(p)
      setStandards(s)
      setManualProjects(m)
    }).catch(() => {})
  }, [])

  async function handleDelete(id: number) {
    if (!confirm('确定删除该批次及其所有推理结果？')) return
    setDeleting(id)
    try {
      await deleteDebugBatch(id)
      setBatches(prev => prev.filter(b => b.id !== id))
    } finally {
      setDeleting(null)
    }
  }

  function handleCreated(id: number) {
    router.push(`/boq/debug/${id}`)
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-6">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-gray-800">套定额调试</h1>
          <p className="text-sm text-gray-500 mt-0.5">按批次管理调试会话，推理结果自动保存。</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700"
        >
          + 新建批次
        </button>
      </div>

      {batches.length === 0 ? (
        <div className="text-center py-20 text-gray-400">
          <p className="text-4xl mb-3">🗂</p>
          <p className="text-sm">暂无调试批次</p>
          <button onClick={() => setShowModal(true)}
            className="mt-4 px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700">
            新建第一个批次
          </button>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium">批次名称</th>
                <th className="text-left px-4 py-2.5 font-medium">工程</th>
                <th className="text-left px-4 py-2.5 font-medium">已推理</th>
                <th className="text-left px-4 py-2.5 font-medium">创建时间</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {batches.map(b => (
                <tr key={b.id} className="hover:bg-gray-50 transition">
                  <td className="px-4 py-3 font-medium text-gray-800">{b.name}</td>
                  <td className="px-4 py-3 text-gray-600 text-xs">{b.project_name}</td>
                  <td className="px-4 py-3">
                    {b.result_count > 0
                      ? <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">{b.result_count} 条</span>
                      : <span className="text-xs text-gray-400">未推理</span>
                    }
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-400">
                    {new Date(b.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => router.push(`/boq/debug/${b.id}`)}
                        className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                      >
                        进入
                      </button>
                      <button
                        onClick={() => handleDelete(b.id)}
                        disabled={deleting === b.id}
                        className="text-xs text-gray-400 hover:text-red-500 disabled:opacity-40"
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showModal && (
        <CreateBatchModal
          projects={projects}
          standards={standards}
          manualProjects={manualProjects}
          onClose={() => setShowModal(false)}
          onCreate={handleCreated}
        />
      )}
    </div>
  )
}
