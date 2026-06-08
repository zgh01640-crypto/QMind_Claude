'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { fetchBoqProjects, BoqProject } from '@/lib/api'

export default function NewBoqListPage() {
  const router = useRouter()
  const [projects, setProjects] = useState<BoqProject[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchBoqProjects()
      .then(setProjects)
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">新工程管理</h1>
          <p className="text-sm text-gray-500 mt-1">基于深圳建筑消耗量标准2024（SJG 171-2024）套定额</p>
        </div>
      </div>

      {loading && (
        <div className="text-center text-gray-400 py-16 animate-pulse">加载中…</div>
      )}

      {!loading && projects.length === 0 && (
        <div className="text-center text-gray-400 py-16">
          <div className="text-4xl mb-3">📋</div>
          <div className="text-sm">暂无工程，请先在「工程管理」中上传工程清单</div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {projects.map(p => (
          <div
            key={p.id}
            onClick={() => router.push(`/new-boq/${p.id}`)}
            className="bg-white rounded-lg shadow hover:shadow-md cursor-pointer transition-shadow p-5 border border-transparent hover:border-indigo-200"
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="font-semibold text-gray-800 text-sm leading-snug">{p.project_name}</div>
              {p.tag && (
                <span className="text-xs bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded shrink-0">{p.tag}</span>
              )}
            </div>
            {p.bid_section && (
              <div className="text-xs text-gray-500 mb-2 truncate">{p.bid_section}</div>
            )}
            <div className="flex items-center justify-between text-xs text-gray-400 mt-3 pt-3 border-t border-gray-100">
              <span>{p.item_count?.toLocaleString() ?? '—'} 个清单项</span>
              <span>{new Date(p.imported_at).toLocaleDateString('zh-CN')}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
