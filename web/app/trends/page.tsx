'use client'
import { useState, useEffect } from 'react'
import { fetchItems, fetchTrend, fetchPeriods, Period, TrendPoint } from '@/lib/api'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'

export default function TrendsPage() {
  const [periods, setPeriods] = useState<Period[]>([])
  const [nameInput, setNameInput] = useState('')
  const [queriedName, setQueriedName] = useState('')
  const [specs, setSpecs] = useState<string[]>([])
  const [selectedSpec, setSelectedSpec] = useState('')
  const [trendData, setTrendData] = useState<TrendPoint[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { fetchPeriods().then(setPeriods) }, [])

  const handleSearch = async () => {
    const name = nameInput.trim()
    if (!name) return
    setLoading(true)
    setError('')
    setTrendData([])
    setSpecs([])
    setSelectedSpec('')
    setQueriedName(name)
    try {
      // First get all matching specs from the latest period
      if (periods.length > 0) {
        const res = await fetchItems({ period_id: periods[0].id, search: name, page_size: 200 })
        const matchedSpecs = Array.from(
          new Set(
            res.items
              .filter(i => i.material_name === name && i.specification)
              .map(i => i.specification as string)
          )
        )
        setSpecs(matchedSpecs)
        const spec = matchedSpecs[0] || ''
        setSelectedSpec(spec)
        const trend = await fetchTrend(name, spec || undefined)
        setTrendData(trend)
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '查询失败')
    } finally {
      setLoading(false)
    }
  }

  const handleSpecChange = async (spec: string) => {
    setSelectedSpec(spec)
    if (!queriedName) return
    setLoading(true)
    try {
      const trend = await fetchTrend(queriedName, spec || undefined)
      setTrendData(trend)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '查询失败')
    } finally {
      setLoading(false)
    }
  }

  const hasData = trendData.length > 0
  const minPrice = hasData ? Math.min(...trendData.filter(d => d.price_yuan != null).map(d => d.price_yuan!)) : 0
  const maxPrice = hasData ? Math.max(...trendData.filter(d => d.price_yuan != null).map(d => d.price_yuan!)) : 0
  const priceDiff = hasData && trendData.length > 1
    ? (trendData[trendData.length - 1].price_yuan ?? 0) - (trendData[0].price_yuan ?? 0)
    : null

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-800 mb-4">价格趋势</h1>

      <div className="bg-white rounded-lg shadow p-4 mb-4 flex flex-wrap gap-3 items-end">
        <div className="flex-1 min-w-[260px]">
          <label className="text-xs text-gray-500 block mb-1">材料名称（精确匹配）</label>
          <div className="flex gap-2">
            <input
              className="border rounded px-3 py-1.5 text-sm flex-1"
              placeholder="例：热轧光圆钢筋 HPB300"
              value={nameInput}
              onChange={e => setNameInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
            />
            <button
              onClick={handleSearch}
              disabled={loading}
              className="bg-blue-600 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              查询
            </button>
          </div>
        </div>

        {specs.length > 1 && (
          <div>
            <label className="text-xs text-gray-500 block mb-1">规格</label>
            <select
              className="border rounded px-3 py-1.5 text-sm min-w-[180px]"
              value={selectedSpec}
              onChange={e => handleSpecChange(e.target.value)}
            >
              <option value="">不限规格</option>
              {specs.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        )}
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4 text-sm">{error}</div>}

      {loading && (
        <div className="bg-white rounded-lg shadow p-12 text-center text-gray-400">加载中…</div>
      )}

      {!loading && hasData && (
        <>
          <div className="grid grid-cols-3 gap-4 mb-4">
            {[
              { label: '数据期数', value: `${trendData.length} 期` },
              { label: '价格区间', value: `${minPrice.toLocaleString()} ~ ${maxPrice.toLocaleString()} 元` },
              {
                label: '首末差价',
                value: priceDiff != null
                  ? `${priceDiff >= 0 ? '+' : ''}${priceDiff.toLocaleString()} 元`
                  : '-',
                color: priceDiff != null ? (priceDiff >= 0 ? 'text-red-600' : 'text-green-600') : '',
              },
            ].map(card => (
              <div key={card.label} className="bg-white rounded-lg shadow p-4">
                <div className="text-xs text-gray-500 mb-1">{card.label}</div>
                <div className={`text-lg font-semibold ${card.color || 'text-gray-800'}`}>{card.value}</div>
              </div>
            ))}
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-sm font-medium text-gray-700 mb-1">
              {queriedName}{selectedSpec ? ` · ${selectedSpec}` : ''}
            </h2>
            <p className="text-xs text-gray-400 mb-4">价格（元/{trendData[0] ? (
              // get unit from data - not available here, skip
              ''
            ) : ''}）走势图</p>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={trendData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                <YAxis
                  tick={{ fontSize: 12 }}
                  domain={['auto', 'auto']}
                  tickFormatter={v => v.toLocaleString()}
                />
                <Tooltip
                  formatter={(value: number) => [`${value.toLocaleString()} 元`, '价格']}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="price_yuan"
                  name="价格（元）"
                  stroke="#2563eb"
                  strokeWidth={2}
                  dot={{ r: 4 }}
                  activeDot={{ r: 6 }}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}

      {!loading && !hasData && queriedName && (
        <div className="bg-white rounded-lg shadow p-12 text-center text-gray-400">
          未找到"{queriedName}"的历史价格数据
        </div>
      )}

      {!loading && !queriedName && (
        <div className="bg-white rounded-lg shadow p-12 text-center text-gray-400">
          输入材料名称后点击查询，查看各月价格趋势
        </div>
      )}
    </div>
  )
}
