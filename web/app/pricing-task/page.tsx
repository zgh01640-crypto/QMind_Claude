'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { fetchBoqProjects, BoqProject, fetchManualBoqProjects, ManualBoqProject } from '@/lib/api'

interface PricingTask {
  id: string
  name: string
  project_id: number
  project_name: string
  chapter_ids: number[]
  chapter_names: string[]
  manual_project_id: number | null
  manual_project_name: string | null
  created_at: string
}

interface BS2024Chapter {
  id: number
  chapter_no: number
  title: string
  subitem_count: number
}

export default function PricingTaskPage() {
  const [tasks, setTasks] = useState<PricingTask[]>([])
  const [showModal, setShowModal] = useState(false)

  // Modal 状态
  const [projects, setProjects] = useState<BoqProject[]>([])
  const [chapters, setChapters] = useState<BS2024Chapter[]>([])
  const [manualProjects, setManualProjects] = useState<ManualBoqProject[]>([])

  const [selectedProject, setSelectedProject] = useState<number | null>(null)
  const [taskName, setTaskName] = useState('')
  const [selectedChapters, setSelectedChapters] = useState<Set<number>>(new Set())
  const [selectedManualProject, setSelectedManualProject] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)

  // 初始化：加载 tasks 和 API 数据
  useEffect(() => {
    const stored = localStorage.getItem('pricing_tasks')
    if (stored) setTasks(JSON.parse(stored))
  }, [])

  // Modal 打开时加载数据
  const handleOpenModal = async () => {
    setShowModal(true)
    setLoading(true)
    try {
      const [projectsRes, chaptersRes, manualRes] = await Promise.all([
        fetchBoqProjects(),
        fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/bs2024-match/chapters`).then(r => r.json()),
        fetchManualBoqProjects(),
      ])
      setProjects(projectsRes)
      setChapters(chaptersRes)
      setManualProjects(manualRes)
    } catch (err) {
      console.error('加载数据失败', err)
    } finally {
      setLoading(false)
    }
  }

  const handleCreateTask = () => {
    if (!selectedProject || !taskName.trim() || selectedChapters.size === 0) {
      alert('请填写必填字段')
      return
    }

    const project = projects.find(p => p.id === selectedProject)
    const selectedChapterObjs = chapters.filter(c => selectedChapters.has(c.id))
    const manualProject = manualProjects.find(p => p.id === selectedManualProject)

    const newTask: PricingTask = {
      id: `task_${Date.now()}`,
      name: taskName,
      project_id: selectedProject,
      project_name: project?.project_name || '',
      chapter_ids: Array.from(selectedChapters),
      chapter_names: selectedChapterObjs.map(c => c.title),
      manual_project_id: selectedManualProject,
      manual_project_name: manualProject?.project_name || null,
      created_at: new Date().toISOString(),
    }

    const updatedTasks = [newTask, ...tasks]
    setTasks(updatedTasks)
    localStorage.setItem('pricing_tasks', JSON.stringify(updatedTasks))

    // 重置 modal
    setShowModal(false)
    setSelectedProject(null)
    setTaskName('')
    setSelectedChapters(new Set())
    setSelectedManualProject(null)
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto px-6 py-8">
        {/* 页面头 */}
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold text-gray-900">单条组价</h1>
          <button
            onClick={handleOpenModal}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            新增组价任务
          </button>
        </div>

        {/* 任务列表 */}
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
                    <h3 className="font-semibold text-lg text-gray-900 mb-2">{task.name}</h3>
                    <div className="text-sm text-gray-600 space-y-1">
                      <p>工程：{task.project_name}</p>
                      <p>定额库：{task.chapter_names.join('、')}</p>
                      {task.manual_project_name && (
                        <p>对比工程：{task.manual_project_name}</p>
                      )}
                      <p className="text-xs text-gray-400 mt-2">
                        创建于 {new Date(task.created_at).toLocaleString()}
                      </p>
                    </div>
                  </div>
                  <Link href={`/pricing-task/${task.id}`}>
                    <button className="px-4 py-2 ml-4 bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors whitespace-nowrap">
                      进入
                    </button>
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 创建任务 Modal */}
        {showModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
              <h2 className="text-xl font-bold mb-6">新增组价任务</h2>

              {loading ? (
                <div className="text-center py-8">加载中...</div>
              ) : (
                <div className="space-y-4">
                  {/* 工程 */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      工程 <span className="text-red-500">*</span>
                    </label>
                    <select
                      value={selectedProject || ''}
                      onChange={e => setSelectedProject(e.target.value ? Number(e.target.value) : null)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    >
                      <option value="">请选择工程</option>
                      {projects.map(p => (
                        <option key={p.id} value={p.id}>
                          {p.project_name}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* 任务名称 */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      任务名称 <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={taskName}
                      onChange={e => setTaskName(e.target.value)}
                      placeholder="输入任务名称"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                  </div>

                  {/* 定额专业 */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      定额专业 <span className="text-red-500">*</span>
                    </label>
                    <div className="max-h-48 overflow-y-auto border border-gray-300 rounded-lg p-3 space-y-2">
                      {chapters.map(ch => (
                        <label key={ch.id} className="flex items-center">
                          <input
                            type="checkbox"
                            checked={selectedChapters.has(ch.id)}
                            onChange={e => {
                              const newSet = new Set(selectedChapters)
                              if (e.target.checked) {
                                newSet.add(ch.id)
                              } else {
                                newSet.delete(ch.id)
                              }
                              setSelectedChapters(newSet)
                            }}
                            className="rounded"
                          />
                          <span className="ml-2 text-sm">{ch.title}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* 对比工程 */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      对比工程 <span className="text-gray-400">(可选)</span>
                    </label>
                    <select
                      value={selectedManualProject || ''}
                      onChange={e => setSelectedManualProject(e.target.value ? Number(e.target.value) : null)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    >
                      <option value="">不对比</option>
                      {manualProjects.map(p => (
                        <option key={p.id} value={p.id}>
                          {p.project_name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              {/* 按钮 */}
              <div className="flex gap-3 mt-6">
                <button
                  onClick={() => setShowModal(false)}
                  className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={handleCreateTask}
                  disabled={loading}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
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
