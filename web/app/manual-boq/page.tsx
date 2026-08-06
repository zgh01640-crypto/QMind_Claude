'use client'
import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import {
  fetchManualBoqProjects, uploadManualBoqFile, renameManualBoqProject, deleteManualBoqProject, ManualBoqProject
} from '@/lib/api'

export default function ManualBoqListPage() {
  const router = useRouter()
  const [projects, setProjects] = useState<ManualBoqProject[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [drag, setDrag] = useState(false)
  const [showUploadDialog, setShowUploadDialog] = useState(false)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [projectName, setProjectName] = useState('')
  const [renamingProject, setRenamingProject] = useState<ManualBoqProject | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [renameError, setRenameError] = useState('')
  const [renaming, setRenaming] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const nameInputRef = useRef<HTMLInputElement>(null)
  const renameInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetchManualBoqProjects()
      .then(setProjects)
      .finally(() => setLoading(false))
  }, [])

  const openUploadDialog = (file: File) => {
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
      setUploadError('请上传 .xlsx 格式的工程量清单文件')
      return
    }
    setPendingFile(file)
    setProjectName(file.name.replace(/\.xlsx$/i, ''))
    setUploadError('')
    setShowUploadDialog(true)
    setTimeout(() => nameInputRef.current?.select(), 0)
  }

  const closeUploadDialog = () => {
    if (uploading) return
    setShowUploadDialog(false)
    setPendingFile(null)
    setProjectName('')
    setUploadError('')
  }

  const doUpload = async () => {
    if (!pendingFile || !projectName.trim()) return
    setUploading(true); setUploadError('')
    try {
      const proj = await uploadManualBoqFile(pendingFile, projectName.trim())
      setProjects(prev => [proj, ...prev])
      setShowUploadDialog(false)
      setPendingFile(null)
      setProjectName('')
      router.push(`/manual-boq/${proj.id}`)
    } catch (e: unknown) {
      setUploadError(e instanceof Error ? e.message : String(e))
    } finally {
      setUploading(false)
    }
  }

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) openUploadDialog(file)
    e.target.value = ''
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDrag(false)
    const file = e.dataTransfer.files?.[0]
    if (file) openUploadDialog(file)
  }
  const handleDelete = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation()
    if (!confirm('确认删除该工程及所有套定额数据？')) return
    await deleteManualBoqProject(id)
    setProjects(prev => prev.filter(p => p.id !== id))
  }

  const openRenameDialog = (e: React.MouseEvent, project: ManualBoqProject) => {
    e.stopPropagation()
    setRenamingProject(project)
    setRenameValue(project.project_name)
    setRenameError('')
    setTimeout(() => renameInputRef.current?.select(), 0)
  }

  const closeRenameDialog = () => {
    if (renaming) return
    setRenamingProject(null)
    setRenameValue('')
    setRenameError('')
  }

  const doRename = async () => {
    if (!renamingProject || !renameValue.trim()) return
    setRenaming(true); setRenameError('')
    try {
      const updated = await renameManualBoqProject(renamingProject.id, renameValue.trim())
      setProjects(prev => prev.map(project => project.id === updated.id ? updated : project))
      setRenamingProject(null)
      setRenameValue('')
    } catch (e: unknown) {
      setRenameError(e instanceof Error ? e.message : String(e))
    } finally {
      setRenaming(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-800">工程管理（人工）</h1>
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="px-4 py-2 bg-blue-700 text-white text-sm rounded hover:bg-blue-800 disabled:opacity-50 flex items-center gap-2"
        >
          {uploading
            ? <><span className="animate-spin inline-block w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full" />上传中…</>
            : '+ 上传人工套定额清单'}
        </button>
        <input ref={fileRef} type="file" accept=".xlsx" className="hidden" onChange={onFile} />
      </div>

      {projects.length === 0 && !loading && (
        <div
          onDragOver={e => { e.preventDefault(); setDrag(true) }}
          onDragLeave={() => setDrag(false)}
          onDrop={onDrop}
          onClick={() => fileRef.current?.click()}
          className={`border-2 border-dashed rounded-xl py-20 text-center cursor-pointer transition-colors mb-6 ${
            drag ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-blue-300 hover:bg-gray-50'
          }`}
        >
          <div className="text-4xl mb-3">📋</div>
          <div className="text-gray-500 text-sm">拖拽含子定额的 Excel 清单到此处，或点击选择文件</div>
          <div className="text-gray-400 text-xs mt-1">支持分部分项工程项目清单计价表（含子定额）（.xlsx）</div>
        </div>
      )}

      {uploadError && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4 text-sm">{uploadError}</div>
      )}

      {loading && (
        <div className="text-center text-gray-400 py-16 animate-pulse">加载中…</div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {projects.map(p => (
          <div
            key={p.id}
            onClick={() => router.push(`/manual-boq/${p.id}`)}
            className="relative bg-white rounded-lg shadow hover:shadow-md cursor-pointer transition-shadow p-5 border border-transparent hover:border-blue-200 group"
          >
            <div className="absolute top-3 right-3 flex items-center gap-1 opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100 focus-within:opacity-100">
              <button
                onClick={e => openRenameDialog(e, p)}
                className="w-7 h-7 rounded-md bg-white/95 border border-gray-200 text-gray-400 hover:text-blue-600 hover:border-blue-200 shadow-sm"
                title="修改工程名称"
                aria-label={`修改 ${p.project_name} 的名称`}
              >✎</button>
              <button
                onClick={e => handleDelete(e, p.id)}
                className="w-7 h-7 rounded-md bg-white/95 border border-gray-200 text-gray-400 hover:text-red-500 hover:border-red-200 shadow-sm"
                title="删除工程"
                aria-label={`删除 ${p.project_name}`}
              >✕</button>
            </div>
            <div className="flex items-start gap-2 mb-2 pr-16">
              <div className="font-semibold text-gray-800 text-sm leading-snug">{p.project_name}</div>
              {p.tag && (
                <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded shrink-0">{p.tag}</span>
              )}
            </div>
            {p.bid_section && (
              <div className="text-xs text-gray-500 mb-2 truncate">{p.bid_section}</div>
            )}
            <div className="flex items-center gap-1 mb-1">
              <span className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">人工套定额</span>
            </div>
            <div className="flex items-center justify-between text-xs text-gray-400 mt-3 pt-3 border-t border-gray-100">
              <span>{p.item_count?.toLocaleString() ?? '—'} 个清单项</span>
              <span>{new Date(p.imported_at).toLocaleDateString('zh-CN')}</span>
            </div>
          </div>
        ))}
      </div>

      {projects.length > 0 && (
        <div
          onDragOver={e => { e.preventDefault(); setDrag(true) }}
          onDragLeave={() => setDrag(false)}
          onDrop={onDrop}
          className={`mt-6 border border-dashed rounded-lg py-4 text-center text-sm transition-colors ${
            drag ? 'border-blue-400 bg-blue-50 text-blue-600' : 'border-gray-200 text-gray-400'
          }`}
        >
          拖拽文件到此处导入新工程
        </div>
      )}

      {showUploadDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 px-4 backdrop-blur-[2px]">
          <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-2xl">
            <div className="mb-5">
              <h2 className="text-lg font-semibold text-gray-900">新增人工工程</h2>
              <p className="mt-1 text-xs text-gray-500">同一个 Excel 可以使用不同工程名称重复导入。</p>
            </div>
            <div className="mb-4 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-700">
              文件：<span className="font-mono">{pendingFile?.name}</span>
            </div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700">工程名称</label>
            <input
              ref={nameInputRef}
              type="text"
              value={projectName}
              maxLength={500}
              onChange={e => setProjectName(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && projectName.trim() && !uploading) doUpload()
                if (e.key === 'Escape') closeUploadDialog()
              }}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              placeholder="请输入工程名称"
            />
            {uploadError && (
              <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{uploadError}</div>
            )}
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={closeUploadDialog}
                disabled={uploading}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >取消</button>
              <button
                onClick={doUpload}
                disabled={uploading || !projectName.trim()}
                className="flex items-center gap-2 rounded-lg bg-blue-700 px-4 py-2 text-sm text-white hover:bg-blue-800 disabled:opacity-50"
              >
                {uploading
                  ? <><span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />导入中…</>
                  : '新增工程'}
              </button>
            </div>
          </div>
        </div>
      )}

      {renamingProject && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 px-4 backdrop-blur-[2px]">
          <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-2xl">
            <div className="mb-5">
              <h2 className="text-lg font-semibold text-gray-900">修改工程名称</h2>
              <p className="mt-1 truncate text-xs text-gray-500">源文件：{renamingProject.source_file || '未知'}</p>
            </div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700">工程名称</label>
            <input
              ref={renameInputRef}
              type="text"
              value={renameValue}
              maxLength={500}
              onChange={e => setRenameValue(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && renameValue.trim() && !renaming) doRename()
                if (e.key === 'Escape') closeRenameDialog()
              }}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              placeholder="请输入工程名称"
            />
            {renameError && (
              <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{renameError}</div>
            )}
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={closeRenameDialog}
                disabled={renaming}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >取消</button>
              <button
                onClick={doRename}
                disabled={renaming || !renameValue.trim() || renameValue.trim() === renamingProject.project_name}
                className="rounded-lg bg-blue-700 px-4 py-2 text-sm text-white hover:bg-blue-800 disabled:opacity-50"
              >{renaming ? '保存中…' : '保存名称'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
