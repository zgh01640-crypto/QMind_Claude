'use client'
import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchPeriods, uploadFile, deletePeriod, Period, ImportResult } from '@/lib/api'

export default function ImportPage() {
  const [periods, setPeriods] = useState<Period[]>([])
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState('')
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const reload = useCallback(() => fetchPeriods().then(setPeriods), [])
  useEffect(() => { reload() }, [reload])

  const handleFile = async (file: File) => {
    if (!file.name.endsWith('.xlsx')) {
      setError('只支持 .xlsx 格式文件')
      return
    }
    setUploading(true)
    setError('')
    setResult(null)
    try {
      const res = await uploadFile(file, false)
      setResult(res)
      await reload()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '上传失败'
      // If conflict, offer force
      if (msg.includes('已存在')) {
        if (confirm(`${msg}\n\n是否覆盖重新导入？`)) {
          try {
            const res = await uploadFile(file, true)
            setResult(res)
            await reload()
          } catch (e2: unknown) {
            setError(e2 instanceof Error ? e2.message : '覆盖导入失败')
          }
        }
      } else {
        setError(msg)
      }
    } finally {
      setUploading(false)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确认删除该期数据？此操作不可撤销。')) return
    setDeleteId(id)
    try {
      await deletePeriod(id)
      await reload()
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : '删除失败')
    } finally {
      setDeleteId(null)
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-800 mb-4">导入管理</h1>

      {/* Upload Area */}
      <div
        className={`border-2 border-dashed rounded-xl p-10 text-center mb-6 transition-colors cursor-pointer ${
          dragOver ? 'border-blue-400 bg-blue-50' : 'border-gray-300 bg-white hover:border-blue-300 hover:bg-gray-50'
        }`}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx"
          className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f); e.target.value = '' }}
        />
        {uploading ? (
          <div className="text-blue-600 font-medium animate-pulse">正在导入，请稍候…</div>
        ) : (
          <>
            <div className="text-4xl mb-3">📂</div>
            <p className="text-gray-600 font-medium">拖放 Excel 文件到此处，或点击选择文件</p>
            <p className="text-gray-400 text-sm mt-1">文件命名格式：YYYY-MM-版本深圳信息价.xlsx</p>
            <p className="text-gray-400 text-xs mt-1">例如：2026-05-0深圳信息价.xlsx</p>
          </>
        )}
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4 text-sm">
          {error}
        </div>
      )}

      {result && (
        <div className="bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded mb-4 text-sm">
          ✓ 导入成功：{result.year}年{String(result.month).padStart(2, '0')}月 第{result.version}版，
          共 <strong>{result.categories}</strong> 个分类，<strong>{result.items.toLocaleString()}</strong> 条记录
        </div>
      )}

      {/* History Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="px-4 py-3 border-b font-medium text-gray-700">历史导入记录</div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th className="px-4 py-2.5 text-left">期次</th>
              <th className="px-4 py-2.5 text-left">版本</th>
              <th className="px-4 py-2.5 text-right">记录数</th>
              <th className="px-4 py-2.5 text-left">源文件</th>
              <th className="px-4 py-2.5 text-left">导入时间</th>
              <th className="px-4 py-2.5 text-center">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {periods.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-400">暂无记录</td></tr>
            )}
            {periods.map(p => (
              <tr key={p.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-900">
                  {p.year}年{String(p.month).padStart(2, '0')}月
                </td>
                <td className="px-4 py-3 text-gray-600">第 {p.version} 版</td>
                <td className="px-4 py-3 text-right text-gray-700">
                  {p.item_count?.toLocaleString() ?? '-'}
                </td>
                <td className="px-4 py-3 text-gray-400 text-xs truncate max-w-[200px]">
                  {p.source_file ?? '-'}
                </td>
                <td className="px-4 py-3 text-gray-500 text-xs">
                  {new Date(p.imported_at).toLocaleString('zh-CN')}
                </td>
                <td className="px-4 py-3 text-center">
                  <button
                    onClick={() => handleDelete(p.id)}
                    disabled={deleteId === p.id}
                    className="text-red-500 hover:text-red-700 text-xs px-2 py-1 rounded hover:bg-red-50 disabled:opacity-40"
                  >
                    {deleteId === p.id ? '删除中…' : '删除'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
