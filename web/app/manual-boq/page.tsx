'use client'
import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import {
  fetchManualBoqProjects, uploadManualBoqFile, deleteManualBoqProject, ManualBoqProject
} from '@/lib/api'

export default function ManualBoqListPage() {
  const router = useRouter()
  const [projects, setProjects] = useState<ManualBoqProject[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [drag, setDrag] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetchManualBoqProjects()
      .then(setProjects)
      .finally(() => setLoading(false))
  }, [])

  const doUpload = async (file: File, force = false) => {
    if (!file.name.endsWith('.xlsx')) {
      setUploadError('请上传 .xlsx 格式的工程量清单文件')
      return
    }
    setUploading(true); setUploadError('')
    try {
      const proj = await uploadManualBoqFile(file, force)
      setProjects(prev => [proj, ...prev.filter(p => p.id !== proj.id)])
      router.push(`/manual-boq/${proj.id}`)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.includes('409') || msg.includes('已存在')) {
        if (confirm('该文件已导入过，是否强制重新导入？')) {
          await doUpload(file, true)
        }
      } else {
        setUploadError(msg)
      }
    } finally {
      setUploading(false)
    }
  }

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) doUpload(f)
    e.target.value = ''
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDrag(false)
    const f = e.dataTransfer.files?.[0]
    if (f) doUpload(f)
  }

  const handleDelete = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation()
    if (!confirm('确认删除该工程及所有套定额数据？')) return
    await deleteManualBoqProject(id)
    setProjects(prev => prev.filter(p => p.id !== id))
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
            <button
              onClick={e => handleDelete(e, p.id)}
              className="absolute top-3 right-3 text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity text-sm"
              title="删除工程"
            >✕</button>
            <div className="flex items-start gap-2 mb-2 pr-5">
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
    </div>
  )
}
