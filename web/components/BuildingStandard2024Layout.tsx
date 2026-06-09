'use client'

import Link from 'next/link'
import { ReactNode } from 'react'
import {
  BS2024ChapterNode,
  BS2024Document,
} from '@/lib/api'

export function pageRange(start: number | null, end: number | null) {
  if (!start && !end) return '—'
  if (start === end || !end) return `P${start}`
  return `P${start}-${end}`
}

export function StandardStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="min-w-28 rounded border border-gray-200 bg-white px-3 py-2">
      <div className="text-xs text-gray-400">{label}</div>
      <div className="mt-0.5 text-sm font-semibold text-gray-800 tabular-nums">{value}</div>
    </div>
  )
}

export function BuildingStandardHeader({
  documents,
  documentId,
  onDocumentChange,
  stats,
  error,
}: {
  documents: BS2024Document[]
  documentId: number | null
  onDocumentChange: (documentId: number) => void
  stats: ReactNode
  error?: string
}) {
  return (
    <div className="border-b border-gray-200 bg-white px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900">建筑消耗量标准2024</h1>
          <p className="mt-1 text-sm text-gray-500">本地 OCR 解析入库，保留页源、层级、说明规则和子目表结构。</p>
        </div>
        <select
          value={documentId ?? ''}
          onChange={event => onDocumentChange(Number(event.target.value))}
          className="rounded border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700"
        >
          {documents.map(document => (
            <option key={document.id} value={document.id}>
              {document.standard_code} - {document.name}
            </option>
          ))}
        </select>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">{stats}</div>
      {error && (
        <div className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}
    </div>
  )
}

export function BuildingStandardSidebar({
  tree,
  selectedChapterId,
  appendixActive,
  topContent,
  onChapterClick,
  renderChapterDetails,
}: {
  tree: BS2024ChapterNode[]
  selectedChapterId: number | null
  appendixActive?: boolean
  topContent?: ReactNode
  onChapterClick?: (chapter: BS2024ChapterNode) => void
  renderChapterDetails?: (chapter: BS2024ChapterNode) => ReactNode
}) {
  return (
    <aside className="border-b border-gray-200 bg-white lg:border-b-0 lg:border-r">
      {topContent}
      <div className="max-h-[42vh] overflow-y-auto py-2 lg:max-h-[calc(100vh-260px)]">
        {tree.map(chapter => (
          <div key={chapter.id}>
            <button
              onClick={() => onChapterClick?.(chapter)}
              className={`w-full px-4 py-2.5 text-left text-sm transition ${
                selectedChapterId === chapter.id && !appendixActive
                  ? 'border-l-2 border-blue-700 bg-blue-50 text-blue-700'
                  : 'border-l-2 border-transparent text-gray-700 hover:bg-gray-50'
              }`}
            >
              <div className="font-medium">第{chapter.chapter_no}章 {chapter.title}</div>
              <div className="mt-0.5 text-xs text-gray-400">{pageRange(chapter.page_start, chapter.page_end)}</div>
            </button>
            {selectedChapterId === chapter.id && !appendixActive && renderChapterDetails?.(chapter)}
          </div>
        ))}

        <div className="mx-4 mt-2 border-t border-gray-200 pt-2">
          <Link
            href="/building-standard-2024/appendix-a"
            className={`block border-l-2 px-3 py-2.5 text-sm transition ${
              appendixActive
                ? 'border-blue-700 bg-blue-50 text-blue-700'
                : 'border-transparent text-gray-700 hover:bg-gray-50'
            }`}
          >
            <div className="font-medium">附录A</div>
            <div className="mt-0.5 text-xs text-gray-400">材料、机械台班参考价格表 · P268-277</div>
          </Link>
        </div>
      </div>
    </aside>
  )
}

