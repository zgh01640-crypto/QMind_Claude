'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function PromptTemplatePage() {
  const [roleDesc, setRoleDesc] = useState('')
  const [toolSchema, setToolSchema] = useState('')
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState<'role' | 'tool' | null>(null)

  useEffect(() => {
    fetch(`${API}/api/boq/prompt-template`)
      .then(r => r.json())
      .then(data => {
        setRoleDesc(data.role_desc ?? '')
        setToolSchema(JSON.stringify(data.tool_schema, null, 2))
        setLoading(false)
      })
  }, [])

  const copy = (text: string, which: 'role' | 'tool') => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(which)
      setTimeout(() => setCopied(null), 1500)
    })
  }

  return (
    <div className="max-w-4xl mx-auto py-6 px-4">
      <div className="flex items-center gap-1.5 text-sm text-gray-500 mb-6">
        <Link href="/boq" className="hover:text-blue-600">工程管理</Link>
        <span>/</span>
        <span className="text-gray-800 font-medium">提示词模板</span>
      </div>

      {loading ? (
        <div className="text-center py-16 text-gray-400 text-sm">加载中…</div>
      ) : (
        <div className="space-y-6">
          <Section
            title="推理指令（_ROLE_DESC）"
            content={roleDesc}
            onCopy={() => copy(roleDesc, 'role')}
            copied={copied === 'role'}
          />
          <Section
            title="工具定义（_MATCH_TOOL）"
            content={toolSchema}
            onCopy={() => copy(toolSchema, 'tool')}
            copied={copied === 'tool'}
          />
        </div>
      )}
    </div>
  )
}

function Section({ title, content, onCopy, copied }: {
  title: string
  content: string
  onCopy: () => void
  copied: boolean
}) {
  return (
    <div className="bg-white rounded-lg shadow overflow-hidden">
      <div className="px-4 py-3 border-b flex items-center justify-between">
        <span className="font-medium text-gray-700 text-sm">{title}</span>
        <button
          onClick={onCopy}
          className="text-xs px-2.5 py-1 border rounded text-gray-500 hover:bg-gray-50"
        >
          {copied ? '已复制 ✓' : '复制'}
        </button>
      </div>
      <pre className="text-xs leading-relaxed text-gray-800 p-4 overflow-x-auto whitespace-pre-wrap font-mono bg-gray-50 max-h-[60vh] overflow-y-auto">
        {content}
      </pre>
    </div>
  )
}
