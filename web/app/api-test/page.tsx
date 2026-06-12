'use client'

import { useEffect, useState } from 'react'

export default function ApiTest() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState<string>('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function test() {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
        console.log('API URL:', apiUrl)
        setData(prev => ({ ...prev, apiUrl }))

        const res = await fetch(`${apiUrl}/api/quota2024/standards`)
        const json = await res.json()
        
        setData({
          apiUrl,
          status: res.status,
          standards: json,
        })
      } catch (e: any) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }

    test()
  }, [])

  return (
    <div style={{ padding: '20px', fontFamily: 'monospace' }}>
      <h1>API 诊断</h1>
      
      {loading && <p>加载中...</p>}
      {error && <p style={{ color: 'red' }}>❌ 错误: {error}</p>}
      
      {data && (
        <div>
          <p>✅ API URL: {data.apiUrl}</p>
          <p>✅ HTTP 状态: {data.status}</p>
          <p>✅ 获取到 {data.standards?.length || 0} 条标准：</p>
          <pre>{JSON.stringify(data.standards, null, 2)}</pre>
        </div>
      )}
    </div>
  )
}
