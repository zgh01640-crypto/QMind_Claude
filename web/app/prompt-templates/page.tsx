'use client'
import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Template {
  id: number
  name: string
  description: string | null
  is_active: boolean
  created_at: string
  updated_at: string
  content_len: number
  content?: string
}

// 内置默认模板（代码硬编码，作为参考/初始化用）
const DEFAULT_TEMPLATE = `你是专业的建筑工程造价工程师，精通深圳市建筑工程消耗量标准（SJG 171-2024）。
你的任务是将招标工程量清单（BOQ）中的清单项与{chapter_name}专业定额子目进行匹配（套定额）。
【重要】请全程使用中文进行推理和分析。
【重要】推理过程（thinking/reasoning）必须使用中文输出，不得使用英文。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【推理步骤】

Step 1: 解析清单项目特征，识别材料品种/规格/施工工艺
Step 2: 将项目特征拆解为 1-3 条施工工序
Step 3: 对每条工序从定额子目列表中找最匹配的子目
Step 4: 计算 qty_factor（纯单位换算）
  清单m³ ÷ 定额10m³ = 0.1
  清单m³ ÷ 定额100m³ = 0.01
  清单m² ÷ 定额100m² = 0.01
  清单m ÷ 定额100m = 0.01
  单位相同 = 1.0
Step 5: 调用 submit_matches 输出结果

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【变体选择优先级】

1. 材料品种/规格完全匹配
2. 施工工艺匹配（湿拌 vs 干混；泵送 vs 非泵送）
3. 尺寸规格区间覆盖清单值
4. 单位相同或可换算

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【置信度标准】

- high：项目特征完整，与定额完全对应
- medium：主要特征匹配，但有次要特征未明确
- low：关键特征缺失，只能猜测

medium/low 时 missing_info 必须说明缺少哪些特征。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【返回空数组的情形】

- 该清单项不属于 {chapter_name} 专业范围
- 所有候选定额置信度均为 low 且工作内容匹配度低
- 清单单位无法与定额换算`

export default function PromptTemplatesPage() {
  const [templates, setTemplates] = useState<Template[]>([])
  const [selected, setSelected] = useState<Template | null>(null)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [editContent, setEditContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ text: string; type: 'ok' | 'err' } | null>(null)
  const [creating, setCreating] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const loadList = () =>
    fetch(`${API}/api/prompt-templates`).then(r => r.json())
      .then(d => setTemplates(Array.isArray(d) ? d : []))
      .catch(() => {})

  useEffect(() => { loadList() }, [])

  const selectTemplate = async (t: Template) => {
    if (t.content) { applyToEditor(t); return }
    const d = await fetch(`${API}/api/prompt-templates/${t.id}`).then(r => r.json())
    applyToEditor({ ...t, ...d })
  }

  const applyToEditor = (t: Template) => {
    setSelected(t)
    setEditName(t.name)
    setEditDesc(t.description || '')
    setEditContent(t.content || '')
    setCreating(false)
  }

  const flash = (text: string, type: 'ok' | 'err' = 'ok') => {
    setMsg({ text, type })
    setTimeout(() => setMsg(null), 3000)
  }

  const handleSave = async () => {
    if (!editName.trim() || !editContent.trim()) return
    setSaving(true)
    try {
      if (creating || !selected) {
        // 创建新模板
        const r = await fetch(`${API}/api/prompt-templates`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: editName.trim(), description: editDesc.trim() || null, content: editContent }),
        }).then(r => r.json())
        if (r.id) {
          flash('模板已创建')
          await loadList()
          // 选中新建的
          const detail = await fetch(`${API}/api/prompt-templates/${r.id}`).then(r => r.json())
          applyToEditor(detail)
          setCreating(false)
        } else { flash('创建失败', 'err') }
      } else {
        // 更新现有模板
        await fetch(`${API}/api/prompt-templates/${selected.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: editName.trim(), description: editDesc.trim() || null, content: editContent }),
        })
        flash('已保存')
        await loadList()
      }
    } finally { setSaving(false) }
  }

  const handleActivate = async () => {
    if (!selected) return
    await fetch(`${API}/api/prompt-templates/${selected.id}/activate`, { method: 'POST' })
    flash(`「${selected.name}」已激活，后续套定额将使用此模板`)
    await loadList()
    setSelected(prev => prev ? { ...prev, is_active: true } : prev)
  }

  const handleDeactivate = async () => {
    await fetch(`${API}/api/prompt-templates/deactivate-all`, { method: 'POST' })
    flash('已取消激活，将使用系统内置提示词')
    await loadList()
  }

  const handleDelete = async () => {
    if (!selected) return
    if (!confirm(`确认删除模板「${selected.name}」？`)) return
    const r = await fetch(`${API}/api/prompt-templates/${selected.id}`, { method: 'DELETE' }).then(r => r.json())
    if (r.ok) {
      flash('已删除')
      setSelected(null); setEditName(''); setEditDesc(''); setEditContent('')
      await loadList()
    } else { flash(r.detail || '删除失败', 'err') }
  }

  const startCreate = (fromDefault = false) => {
    setCreating(true)
    setSelected(null)
    setEditName('新建模板')
    setEditDesc('')
    setEditContent(fromDefault ? DEFAULT_TEMPLATE : '')
    setTimeout(() => textareaRef.current?.focus(), 100)
  }

  const activeTemplate = templates.find(t => t.is_active)

  return (
    <div className="flex gap-4 h-[calc(100vh-80px)]">
      {/* 左侧：模板列表 */}
      <div className="w-64 shrink-0 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold text-gray-700">提示词模板</div>
          <div className="flex gap-1">
            <button onClick={() => startCreate(true)} title="从默认模板创建"
              className="text-xs px-2 py-1 rounded border border-gray-300 text-gray-600 hover:bg-gray-50">
              从默认创建
            </button>
            <button onClick={() => startCreate(false)} title="空白创建"
              className="text-xs px-2 py-1 rounded bg-indigo-600 text-white hover:bg-indigo-700">
              + 新建
            </button>
          </div>
        </div>

        {/* 当前状态提示 */}
        <div className={`text-xs px-3 py-2 rounded-lg border ${
          activeTemplate
            ? 'bg-green-50 border-green-200 text-green-700'
            : 'bg-gray-50 border-gray-200 text-gray-500'
        }`}>
          {activeTemplate
            ? <>✓ 当前使用：<span className="font-medium">{activeTemplate.name}</span></>
            : '当前使用系统内置提示词'}
        </div>

        {/* 模板列表 */}
        <div className="flex-1 overflow-y-auto space-y-1">
          {templates.length === 0 && (
            <div className="text-xs text-gray-400 text-center py-6">
              暂无保存的模板<br />
              <button onClick={() => startCreate(true)} className="mt-2 text-indigo-600 hover:underline">
                从默认模板开始编辑
              </button>
            </div>
          )}
          {templates.map(t => (
            <div
              key={t.id}
              onClick={() => selectTemplate(t)}
              className={`px-3 py-2.5 rounded-lg cursor-pointer border transition-colors text-sm ${
                selected?.id === t.id && !creating
                  ? 'bg-indigo-50 border-indigo-300'
                  : 'bg-white border-gray-200 hover:border-indigo-200 hover:bg-gray-50'
              }`}
            >
              <div className="flex items-center gap-2">
                {t.is_active && <span className="w-2 h-2 rounded-full bg-green-500 shrink-0" />}
                <span className="font-medium text-gray-800 truncate flex-1">{t.name}</span>
              </div>
              <div className="text-xs text-gray-400 mt-0.5 flex justify-between">
                <span>{(t.content_len / 1000).toFixed(1)}k 字符</span>
                <span>{new Date(t.updated_at).toLocaleDateString('zh-CN')}</span>
              </div>
              {t.description && (
                <div className="text-xs text-gray-500 mt-0.5 truncate">{t.description}</div>
              )}
            </div>
          ))}
        </div>

        {/* 内置默认说明 */}
        <div className="text-xs text-gray-400 px-1 pb-1">
          <div className="font-medium text-gray-500 mb-1">💡 可用占位符</div>
          <code className="bg-gray-100 px-1 rounded">{'{chapter_name}'}</code> — 当前专业名称（自动替换）
        </div>
      </div>

      {/* 右侧：编辑区 */}
      <div className="flex-1 flex flex-col gap-3 min-w-0">
        {/* 顶部操作栏 */}
        <div className="flex items-center gap-3 flex-wrap">
          <input
            type="text"
            value={editName}
            onChange={e => setEditName(e.target.value)}
            placeholder="模板名称"
            className="border border-gray-300 rounded px-3 py-1.5 text-sm w-48 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
          <input
            type="text"
            value={editDesc}
            onChange={e => setEditDesc(e.target.value)}
            placeholder="描述（可选）"
            className="border border-gray-300 rounded px-3 py-1.5 text-sm flex-1 min-w-32 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
          <button
            onClick={handleSave}
            disabled={saving || !editName.trim() || !editContent.trim()}
            className="px-4 py-1.5 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-700 disabled:opacity-40 font-medium shrink-0"
          >
            {saving ? '保存中…' : creating || !selected ? '创建' : '保存'}
          </button>
          {selected && !creating && (
            <>
              {selected.is_active ? (
                <button onClick={handleDeactivate}
                  className="px-3 py-1.5 border border-gray-300 text-gray-600 text-sm rounded hover:bg-gray-50 shrink-0">
                  取消激活
                </button>
              ) : (
                <button onClick={handleActivate}
                  className="px-3 py-1.5 bg-green-600 text-white text-sm rounded hover:bg-green-700 font-medium shrink-0">
                  ✓ 激活使用
                </button>
              )}
              <button onClick={handleDelete}
                className="px-3 py-1.5 border border-red-300 text-red-600 text-sm rounded hover:bg-red-50 shrink-0">
                删除
              </button>
            </>
          )}
          {msg && (
            <span className={`text-xs px-2 py-1 rounded ${msg.type === 'ok' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
              {msg.text}
            </span>
          )}
        </div>

        {/* 编辑器区域 */}
        {(selected || creating) ? (
          <div className="flex-1 flex flex-col">
            <div className="text-xs text-gray-400 mb-1 flex items-center justify-between">
              <span>
                {creating ? '新建模板' : `编辑：${selected?.name}`}
                {selected?.is_active && <span className="ml-2 text-green-600 font-medium">● 当前激活</span>}
              </span>
              <span>{editContent.length.toLocaleString()} 字符</span>
            </div>
            <textarea
              ref={textareaRef}
              value={editContent}
              onChange={e => setEditContent(e.target.value)}
              spellCheck={false}
              className="flex-1 w-full border border-gray-300 rounded-lg px-4 py-3 text-sm font-mono leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"
              placeholder="在此输入提示词内容，使用 {chapter_name} 作为专业名称占位符…"
            />
            <div className="mt-2 text-xs text-gray-400">
              保存后系统自动追加专业说明、工程量计算规则和定额子目列表（不需要手动写入）
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-400">
            <div className="text-center">
              <div className="text-4xl mb-3">📝</div>
              <div className="text-sm">选择左侧模板进行编辑，或新建一个模板</div>
              <button onClick={() => startCreate(true)}
                className="mt-3 text-indigo-600 text-sm hover:underline">
                从系统默认提示词开始 →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
