'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  BoqProject,
  ManualBoqProject,
  PricingKbLibrary,
  PricingTaskBatch,
  createNewPricingTaskBatch,
  deleteNewPricingTaskBatch,
  fetchBoqProjects,
  fetchManualBoqProjects,
  fetchPricingKbLibraries,
  fetchNewPricingTaskBatches,
} from '@/lib/api'

export default function PricingTaskBatchListPage() {
  const router = useRouter()
  const [batches, setBatches] = useState<PricingTaskBatch[]>([])
  const [projects, setProjects] = useState<BoqProject[]>([])
  const [libraries, setLibraries] = useState<PricingKbLibrary[]>([])
  const [manualProjects, setManualProjects] = useState<ManualBoqProject[]>([])
  const [showModal, setShowModal] = useState(false)
  const [batchName, setBatchName] = useState('')
  const [selectedProject, setSelectedProject] = useState<number | null>(null)
  const [selectedLibraries, setSelectedLibraries] = useState<Set<number>>(new Set())
  const [selectedManualProject, setSelectedManualProject] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [modalLoading, setModalLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    void bootstrap()
  }, [])

  async function bootstrap() {
    setLoading(true)
    try {
      setBatches(await fetchNewPricingTaskBatches())
    } finally {
      setLoading(false)
    }
  }

  async function openModal() {
    setShowModal(true)
    setModalLoading(true)
    try {
      const [projectRows, libraryRows, manualRows] = await Promise.all([
        fetchBoqProjects(),
        fetchPricingKbLibraries(),
        fetchManualBoqProjects(),
      ])
      setProjects(projectRows)
      setLibraries(libraryRows)
      setManualProjects(manualRows)
      if (!batchName) setBatchName(`新批量组价 ${new Date().toLocaleString()}`)
    } finally {
      setModalLoading(false)
    }
  }

  async function createBatch() {
    if (!batchName.trim() || !selectedProject || !selectedManualProject) {
      alert('请填写批次名称，并选择工程和人工对比工程')
      return
    }
    setSaving(true)
    try {
      const created = await createNewPricingTaskBatch({
        name: batchName.trim(),
        boq_project_id: selectedProject,
        quota_library_ids: Array.from(selectedLibraries),
        manual_project_id: selectedManualProject,
      })
      setShowModal(false)
      router.push(`/pricing-task/new-batch/${created.id}`)
    } finally {
      setSaving(false)
    }
  }

  async function removeBatch(id: number) {
    if (!confirm('确定删除该批量组价批次？')) return
    await deleteNewPricingTaskBatch(id)
    await bootstrap()
  }

  if (loading) {
    return <div className="min-h-screen bg-gray-50 flex items-center justify-center text-gray-500">加载中...</div>
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">新批量组价</h1>
            <p className="mt-2 text-sm text-gray-500">按批次执行并独立保存过程与结果。</p>
          </div>
          <button onClick={openModal} className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
            新建批次
          </button>
        </div>

        {batches.length === 0 ? (
          <div className="rounded-lg bg-white py-16 text-center shadow">
            <p className="text-sm text-gray-500">暂无批量组价批次，创建后可按批次执行并回看过程与结果。</p>
            <button onClick={openModal} className="mt-4 rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
              新建第一个批次
            </button>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg bg-white shadow">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">批次</th>
                  <th className="px-4 py-3 text-left font-medium">工程</th>
                  <th className="px-4 py-3 text-left font-medium">定额库</th>
                  <th className="px-4 py-3 text-left font-medium">对比工程</th>
                  <th className="px-4 py-3 text-left font-medium">进度</th>
                  <th className="px-4 py-3 text-left font-medium">创建时间</th>
                  <th className="px-4 py-3 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {batches.map(batch => (
                  <tr key={batch.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-900">{batch.name}</div>
                      <span className="mt-1 inline-flex rounded border border-sky-200 bg-sky-50 px-2 py-0.5 font-mono text-[11px] font-semibold text-sky-700">
                        {'\u77e5\u8bc6\u5e93\u7248\u672c\uff1a'}{batch.kb_version_id ?? '-'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-700">{batch.project_name}</td>
                    <td className="px-4 py-3 text-gray-600">
                      {batch.quota_library_names.length > 0 ? batch.quota_library_names.join('、') : '全部定额库'}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {batch.manual_project_id ? batch.manual_project_name || `#${batch.manual_project_id}` : '不对比'}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {batch.completed_count}/{batch.selected_count}
                      {batch.failed_count > 0 ? `，失败 ${batch.failed_count}` : ''}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">{new Date(batch.created_at).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right">
                      <Link href={`/pricing-task/new-batch/${batch.id}`} className="mr-3 text-blue-600 hover:text-blue-700">
                        进入
                      </Link>
                      <button onClick={() => removeBatch(batch.id)} className="text-gray-400 hover:text-red-600">
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {showModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="mx-4 w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
              <h2 className="mb-6 text-xl font-bold text-gray-900">新建精简批量组价批次</h2>
              {modalLoading ? (
                <div className="py-8 text-center text-sm text-gray-500">加载中...</div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <label className="mb-2 block text-sm font-medium text-gray-700">批次名称 *</label>
                    <input
                      value={batchName}
                      onChange={event => setBatchName(event.target.value)}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2"
                      placeholder="输入批次名称"
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-gray-700">工程 *</label>
                    <select
                      value={selectedProject || ''}
                      onChange={event => setSelectedProject(event.target.value ? Number(event.target.value) : null)}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2"
                    >
                      <option value="">请选择工程</option>
                      {projects.map(project => (
                        <option key={project.id} value={project.id}>{project.project_name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-gray-700">
                      定额库 <span className="text-gray-400">(不选表示全部)</span>
                    </label>
                    <div className="max-h-48 space-y-2 overflow-y-auto rounded-lg border border-gray-300 p-3">
                      {libraries.map(library => (
                        <label key={library.id} className="flex items-start text-sm">
                          <input
                            type="checkbox"
                            checked={selectedLibraries.has(library.id)}
                            onChange={event => {
                              const next = new Set(selectedLibraries)
                              if (event.target.checked) next.add(library.id)
                              else next.delete(library.id)
                              setSelectedLibraries(next)
                            }}
                            className="mt-1"
                          />
                          <span className="ml-2">
                            {library.name}
                            <span className="ml-1 text-xs text-gray-400">({library.quota_count} 条)</span>
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-gray-700">
                      对比工程 <span className="text-red-500">*</span>
                      <span className="ml-1 text-gray-400">用于准确率评测与差异复核</span>
                    </label>
                    <select
                      value={selectedManualProject || ''}
                      onChange={event => setSelectedManualProject(event.target.value ? Number(event.target.value) : null)}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2"
                    >
                      <option value="">请选择人工对比工程</option>
                      {manualProjects.map(project => (
                        <option key={project.id} value={project.id}>{project.project_name}</option>
                      ))}
                    </select>
                  </div>
                </div>
              )}
              <div className="mt-6 flex gap-3">
                <button
                  onClick={() => setShowModal(false)}
                  className="flex-1 rounded-lg border border-gray-300 px-4 py-2 text-gray-700 hover:bg-gray-50"
                >
                  取消
                </button>
                <button
                  onClick={createBatch}
                  disabled={modalLoading || saving || !batchName.trim() || !selectedProject || !selectedManualProject}
                  className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
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
