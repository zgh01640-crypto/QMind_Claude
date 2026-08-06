'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  BoqProject,
  ManualBoqProject,
  PricingKbLibrary,
  PricingTask,
  createPricingTask,
  fetchBoqProjects,
  fetchManualBoqProjects,
  fetchPricingKbLibraries,
  fetchPricingTasks,
  importLocalPricingTasks,
} from '@/lib/api'

export default function PricingTaskPage() {
  const router = useRouter()
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

  useEffect(() => {
    bootstrap()
  }, [])

  const bootstrap = async () => {
    setLoading(true)
    try {
      await migrateLocalTasks()
      const data = await fetchPricingTasks()
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
    } finally {
      setModalLoading(false)
    }
  }

  const handleCreateTask = async () => {
    if (!selectedProject || !taskName.trim()) {
      alert('请填写工程和任务名称')
      return
    }
    const created = await createPricingTask({
      name: taskName.trim(),
      boq_project_id: selectedProject,
      quota_library_ids: Array.from(selectedLibraries),
      manual_project_id: selectedManualProject,
    })
    setShowModal(false)
    router.push(`/pricing-task/${created.id}`)
  }

  if (loading) {
    return <div className="min-h-screen bg-gray-50 flex items-center justify-center text-gray-500">加载中...</div>
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">单条组价</h1>
            <p className="mt-2 text-sm text-gray-500">用于单条验证、Prompt/步骤调试和人工确认。</p>
          </div>
          <button
            onClick={handleOpenModal}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            新增组价任务
          </button>
        </div>

        {tasks.length === 0 ? (
          <div className="text-center py-16">
            <p className="text-gray-500 text-lg mb-4">暂无任务，点击新增开始</p>
          </div>
        ) : (
          <div className="grid gap-4">
            {tasks.map(task => (
              <div key={task.id} className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <h3 className="text-lg font-semibold text-gray-900">{task.name}</h3>
                      <span className="rounded border border-sky-200 bg-sky-50 px-2 py-0.5 font-mono text-[11px] font-semibold text-sky-700">
                        {'\u77e5\u8bc6\u5e93\u7248\u672c\uff1a'}{task.kb_version_id ?? '-'}
                      </span>
                    </div>
                    <div className="text-sm text-gray-600 space-y-1">
                      <p>工程：{task.project_name}</p>
                      <p>
                        定额库：
                        {task.quota_library_names.length > 0 ? task.quota_library_names.join('、') : '全部定额库'}
                      </p>
                      {task.manual_project_id && (
                        <p>对比工程：{task.manual_project_name || `#${task.manual_project_id}`}</p>
                      )}
                      <p className="text-xs text-gray-400 mt-2">
                        创建于 {new Date(task.created_at).toLocaleString()} · 运行 {task.latest_run_count} 次
                      </p>
                    </div>
                  </div>
                  <div className="ml-4 flex shrink-0 flex-col items-end gap-2">
                    <Link href={`/pricing-task/${task.id}`}>
                      <button className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors whitespace-nowrap">
                        进入
                      </button>
                    </Link>
                    <Link href={`/pricing-task/${task.id}/preview`} className="text-xs text-cyan-600 hover:text-cyan-700">
                      试行皮肤
                    </Link>
                  </div>
                </div>
              </div>
            ))}
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

              <div className="flex gap-3 mt-6">
                <button
                  onClick={() => setShowModal(false)}
                  className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50"
                >
                  取消
                </button>
                <button
                  onClick={handleCreateTask}
                  disabled={modalLoading}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  创建并进入
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
