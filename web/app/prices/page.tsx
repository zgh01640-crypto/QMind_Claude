'use client'
import { useState, useEffect, useCallback } from 'react'
import { fetchPeriods, fetchCategories, fetchItems, Period, Category, PriceItem } from '@/lib/api'

const PAGE_SIZE = 20

export default function PricesPage() {
  const [periods, setPeriods] = useState<Period[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [periodId, setPeriodId] = useState<number | null>(null)
  const [categoryId, setCategoryId] = useState<number | null>(null)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [items, setItems] = useState<PriceItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetchPeriods().then(data => {
      setPeriods(data)
      if (data.length > 0) setPeriodId(data[0].id)
    })
    fetchCategories().then(setCategories)
  }, [])

  const load = useCallback(async () => {
    if (!periodId) return
    setLoading(true)
    try {
      const res = await fetchItems({ period_id: periodId, category_id: categoryId, search: search || undefined, page, page_size: PAGE_SIZE })
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [periodId, categoryId, search, page])

  useEffect(() => { load() }, [load])

  const doSearch = () => { setSearch(searchInput); setPage(1) }

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const groups = Array.from(new Set(categories.map(c => c.category_group)))

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-800 mb-4">价格查询</h1>

      <div className="bg-white rounded-lg shadow p-4 mb-4 flex flex-wrap gap-3 items-end">
        <div>
          <label className="text-xs text-gray-500 block mb-1">期次</label>
          <select
            className="border rounded px-3 py-1.5 text-sm min-w-[200px]"
            value={periodId ?? ''}
            onChange={e => { setPeriodId(Number(e.target.value)); setPage(1) }}
          >
            {periods.map(p => (
              <option key={p.id} value={p.id}>
                {p.year}年{String(p.month).padStart(2, '0')}月 第{p.version}版（{p.item_count} 条）
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs text-gray-500 block mb-1">分类</label>
          <select
            className="border rounded px-3 py-1.5 text-sm min-w-[220px]"
            value={categoryId ?? ''}
            onChange={e => { setCategoryId(e.target.value ? Number(e.target.value) : null); setPage(1) }}
          >
            <option value="">全部分类</option>
            {groups.map(g => (
              <optgroup key={g} label={g}>
                {categories.filter(c => c.category_group === g).map(c => (
                  <option key={c.id} value={c.id}>
                    {c.sheet_name.includes('.') ? c.sheet_name.split('.').slice(1).join('.') : c.sheet_name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>

        <div className="flex-1 min-w-[220px]">
          <label className="text-xs text-gray-500 block mb-1">搜索名称 / 规格</label>
          <div className="flex gap-2">
            <input
              className="border rounded px-3 py-1.5 text-sm flex-1"
              placeholder="输入关键词…"
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && doSearch()}
            />
            <button onClick={doSearch} className="bg-blue-600 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-700">
              搜索
            </button>
            {(search || categoryId) && (
              <button
                onClick={() => { setSearch(''); setSearchInput(''); setCategoryId(null); setPage(1) }}
                className="border px-3 py-1.5 rounded text-sm text-gray-600 hover:bg-gray-50"
              >
                清除
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="px-4 py-2 border-b text-sm text-gray-500">
          共 <span className="font-semibold text-gray-800">{total.toLocaleString()}</span> 条
          {loading && <span className="ml-2 text-blue-500 animate-pulse">加载中…</span>}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wide">
              <tr>
                <th className="px-4 py-2.5 text-left">序号</th>
                <th className="px-4 py-2.5 text-left">材料名称</th>
                <th className="px-4 py-2.5 text-left">型号规格</th>
                <th className="px-4 py-2.5 text-left">单位</th>
                <th className="px-4 py-2.5 text-right">价格（元）</th>
                <th className="px-4 py-2.5 text-left">备注</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {!loading && items.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-10 text-center text-gray-400">暂无数据</td></tr>
              )}
              {items.map((item, i) => (
                <tr key={item.id} className={i % 2 === 1 ? 'bg-gray-50/40' : ''}>
                  <td className="px-4 py-2 text-gray-400">{item.sequence_no}</td>
                  <td className="px-4 py-2 font-medium text-gray-900">{item.material_name}</td>
                  <td className="px-4 py-2 text-gray-600">{item.specification ?? '-'}</td>
                  <td className="px-4 py-2 text-gray-600">{item.unit ?? '-'}</td>
                  <td className="px-4 py-2 text-right font-semibold text-blue-700">
                    {item.price_yuan != null ? item.price_yuan.toLocaleString() : '-'}
                  </td>
                  <td className="px-4 py-2 text-gray-400 text-xs">{item.remarks ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="px-4 py-3 border-t flex items-center justify-between text-sm text-gray-600">
            <span>第 {page} / {totalPages} 页</span>
            <div className="flex gap-1">
              {[['«', 1], ['‹ 上一页', page - 1], ['下一页 ›', page + 1], ['»', totalPages]].map(([label, target]) => (
                <button
                  key={label}
                  onClick={() => setPage(Number(target))}
                  disabled={Number(target) < 1 || Number(target) > totalPages || Number(target) === page}
                  className="px-3 py-1 rounded border disabled:opacity-40 hover:bg-gray-50 disabled:cursor-not-allowed"
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
