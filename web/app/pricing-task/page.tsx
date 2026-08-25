'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import {
  BoqProject,
  ManualBoqProject,
  PricingKbLibrary,
  PricingTask,
  createPricingTask,
  deletePricingTask,
  fetchBoqProjects,
  fetchManualBoqProjects,
  fetchPricingKbLibraries,
  fetchPricingTasks,
  importLocalPricingTasks,
  createPricingTaskV2,
  deletePricingTaskV2,
  fetchPricingTaskV2Tasks,
} from '@/lib/api'

export default function PricingTaskPage() {
  const router = useRouter()
  const pathname = usePathname()
  const v2 = pathname.startsWith('/pricing-task-v2')
  const [tasks, setTasks] = useState<PricingTask[]>([])
  const [showModal, setShowModal] = useState(false)
  const [projects, setProjects] = useState<BoqProject[]>([])
  const [libraries, setLibraries] = useState<PricingKbLibrary[]>([])
  const [manualProjects, setManualProjects] = useState<ManualBoqProject[]>([])
  const [selectedProject, setSelectedProject] = useState<number | null>(null)
  const [taskName, setTaskName] = useState('')
  const [selectedLibraries, setSelectedLibraries] = useState<Set<number>>(new Set())
  const [selectedManualProject, setSelectedManualProject] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [modalLoading, setModalLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [createError, setCreateError] = useState('')

  useEffect(() => {
    bootstrap()
  }, [])

  const bootstrap = async () => {
    setLoading(true)
    try {
      if (!v2) await migrateLocalTasks()
      const data = await (v2 ? fetchPricingTaskV2Tasks() : fetchPricingTasks())
      setTasks(data)
    } finally {
      setLoading(false)
    }
  }

  const migrateLocalTasks = async () => {
    if (typeof window === 'undefined') return
    if (localStorage.getItem('pricing_tasks_migrated_v1') === '1') return
    const raw = localStorage.getItem('pricing_tasks')
    if (!raw) {
      localStorage.setItem('pricing_tasks_migrated_v1', '1')
      return
    }
    try {
      const localTasks = JSON.parse(raw)
      if (Array.isArray(localTasks) && localTasks.length > 0) {
        await importLocalPricingTasks(localTasks)
      }
      localStorage.setItem('pricing_tasks_migrated_v1', '1')
    } catch (err) {
      console.warn('旧任务迁移失败', err)
    }
  }

  const handleOpenModal = async () => {
    setCreateError('')
    setShowModal(true)
    setModalLoading(true)
    try {
      const [projectsRes, libsRes, manualRes] = await Promise.all([
        fetchBoqProjects(),
        fetchPricingKbLibraries(),
        fetchManualBoqProjects(),
      ])
      setProjects(projectsRes)
      setLibraries(libsRes)
      setManualProjects(manualRes)
      if (!taskName) setTaskName(`${v2 ? '新版单条组价' : '单条组价'} ${new Date().toLocaleString()}`)
    } finally {
      setModalLoading(false)
    }
  }

  const handleCreateTask = async () => {
    if (!selectedProject || !taskName.trim()) {
      alert('请填写工程和任务名称')
      return
    }
    setCreateError('')
    setSaving(true)
    try {
      const created = await (v2 ? createPricingTaskV2 : createPricingTask)({
        name: taskName.trim(),
        boq_project_id: selectedProject,
        quota_library_ids: Array.from(selectedLibraries),
        manual_project_id: selectedManualProject,
      })
      setShowModal(false)
      router.push(`/${v2 ? 'pricing-task-v2' : 'pricing-task'}/${created.id}`)
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : '创建任务失败，请稍后重试')
    } finally {
      setSaving(false)
    }
  }

  const removeTask = async (id: number) => {
    if (!confirm('确定删除该单条组价任务？')) return
    await (v2 ? deletePricingTaskV2 : deletePricingTask)(id)
    await bootstrap()
  }

  if (loading) {
    return <div className="min-h-screen bg-gray-50 flex items-center justify-center text-gray-500">加载中...</div>
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">{v2 ? '新版单条组价' : '单条组价'}</h1>
            <p className="mt-2 text-sm text-gray-500">{v2 ? '独立试验A/B合并后的第五步，不影响原单条和批量组价。' : '用于单条验证、Prompt/步骤调试和人工确认。'}</p>
          </div>
          <button
            onClick={handleOpenModal}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            新增组价任务
          </button>
        </div>

        {tasks.length === 0 ? (
          <div className="rounded-lg bg-white py-16 text-center shadow">
            <p className="text-sm text-gray-500">暂无单条组价任务，创建后可逐条调试并回看结果。</p>
            <button onClick={handleOpenModal} className="mt-4 rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
              新建第一个任务
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg bg-white shadow">
            <table className="w-full min-w-[1100px] text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">任务</th>
                  <th className="px-4 py-3 text-left font-medium">工程</th>
                  <th className="px-4 py-3 text-left font-medium">定额库</th>
                  <th className="px-4 py-3 text-left font-medium">对比工程</th>
                  <th className="px-4 py-3 text-left font-medium">运行次数</th>
                  <th className="px-4 py-3 text-left font-medium">组价一致率</th>
                  <th className="px-4 py-3 text-left font-medium">创建时间</th>
                  <th className="px-4 py-3 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {tasks.map(task => {
                  const consistencyRate = task.consistency_rate
                  return (
                    <tr key={task.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <div className="font-medium text-gray-900">{task.name}</div>
                        <span className="mt-1 inline-flex rounded border border-sky-200 bg-sky-50 px-2 py-0.5 font-mono text-[11px] font-semibold text-sky-700">
                          {'\u77e5\u8bc6\u5e93\u7248\u672c\uff1a'}{task.kb_version_id ?? '-'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-700">{task.project_name}</td>
                      <td className="px-4 py-3 text-gray-600">
                        {task.quota_library_names.length > 0 ? task.quota_library_names.join('、') : '全部定额库'}
                      </td>
                      <td className="px-4 py-3 text-gray-600">
                        {task.manual_project_id ? task.manual_project_name || `#${task.manual_project_id}` : '不对比'}
                      </td>
                      <td className="px-4 py-3 text-gray-600 tabular-nums">{task.latest_run_count}</td>
                      <td className="px-4 py-3">
                        {consistencyRate == null ? (
                          <span className="text-xs text-gray-400">待计算</span>
                        ) : (
                          <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold tabular-nums ${
                            consistencyRate >= 0.9
                              ? 'bg-emerald-50 text-emerald-700'
                              : consistencyRate >= 0.6
                                ? 'bg-amber-50 text-amber-700'
                                : 'bg-rose-50 text-rose-700'
                          }`}>
                            {(consistencyRate * 100).toFixed(1)}%
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-500">{new Date(task.created_at).toLocaleString()}</td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <Link href={`/${v2 ? 'pricing-task-v2' : 'pricing-task'}/${task.id}`} className="mr-3 text-blue-600 hover:text-blue-700">进入</Link>
                        <Link href={`/${v2 ? 'pricing-task-v2' : 'pricing-task'}/${task.id}/preview`} className="mr-3 text-cyan-600 hover:text-cyan-700">预览</Link>
                        <button onClick={() => removeTask(task.id)} className="text-gray-400 hover:text-red-600">删除</button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {showModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-xl max-w-lg w-full mx-4 p-6">
              <h2 className="text-xl font-bold mb-6">新增组价任务</h2>

              {modalLoading ? (
                <div className="text-center py-8">加载中...</div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">工程 *</label>
                    <select
                      value={selectedProject || ''}
                      onChange={e => setSelectedProject(e.target.value ? Number(e.target.value) : null)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    >
                      <option value="">请选择工程</option>
                      {projects.map(p => (
                        <option key={p.id} value={p.id}>{p.project_name}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">任务名称 *</label>
                    <input
                      type="text"
                      value={taskName}
                      onChange={e => setTaskName(e.target.value)}
                      placeholder="输入任务名称"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      定额库 <span className="text-gray-400">(不选表示全部)</span>
                    </label>
                    <div className="max-h-52 overflow-y-auto border border-gray-300 rounded-lg p-3 space-y-2">
                      {libraries.map(lib => (
                        <label key={lib.id} className="flex items-start">
                          <input
                            type="checkbox"
                            checked={selectedLibraries.has(lib.id)}
                            onChange={e => {
                              const next = new Set(selectedLibraries)
                              if (e.target.checked) next.add(lib.id)
                              else next.delete(lib.id)
                              setSelectedLibraries(next)
                            }}
                            className="rounded mt-1"
                          />
                          <span className="ml-2 text-sm">
                            {lib.name}
                            <span className="ml-1 text-xs text-gray-400">({lib.quota_count} 条)</span>
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      对比工程 <span className="text-gray-400">(仅用于评测)</span>
                    </label>
                    <select
                      value={selectedManualProject || ''}
                      onChange={e => setSelectedManualProject(e.target.value ? Number(e.target.value) : null)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    >
                      <option value="">不对比</option>
                      {manualProjects.map(p => (
                        <option key={p.id} value={p.id}>{p.project_name}</option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              {createError && (
                <p className="mt-5 text-sm text-red-600" role="alert">{createError}</p>
              )}
              <div className="flex gap-3 mt-6">
                <button
                  onClick={() => setShowModal(false)}
                  className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50"
                >
                  取消
                </button>
                <button
                  onClick={handleCreateTask}
                  disabled={modalLoading || saving || !taskName.trim() || !selectedProject}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  {saving ? '创建中...' : '创建并进入'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
