const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface Period {
  id: number
  year: number
  month: number
  version: number
  source_file: string | null
  imported_at: string
  item_count: number | null
}

export interface Category {
  id: number
  sheet_index: number
  sheet_name: string
  category_group: string
}

export interface PriceItem {
  id: number
  sequence_no: number | null
  material_code: string | null
  material_name: string
  specification: string | null
  unit: string | null
  price_yuan: number | null
  coefficient: number | null
  calculation_formula: string | null
  remarks: string | null
}

export interface PriceItemList {
  total: number
  items: PriceItem[]
}

export interface TrendPoint {
  year: number
  month: number
  version: number
  price_yuan: number | null
  label: string
}

export interface ImportResult {
  period_id: number
  year: number
  month: number
  version: number
  categories: number
  items: number
}

// ── 消耗量标准 ──────────────────────────────────────────

export interface QuotaStandard {
  id: number
  standard_code: string
  name: string
  region: string | null
  base_date: string | null
  source_file: string | null
  imported_at: string
  item_count: number | null
}

export interface QuotaChapter {
  id: number
  code: string | null
  name: string
  level: number
  parent_id: number | null
  sort_order: number
}

export interface QuotaResource {
  id: number
  resource_type: string
  resource_name: string
  unit: string | null
  quantity: number | null
  ref_price: number | null
}

export interface QuotaItem {
  id: number
  chapter_id: number | null
  chapter_name: string | null
  item_code: string
  item_name: string
  variant_desc: string | null
  unit: string | null
  work_content: string | null
  total_unit_price: number | null
  unit_price: number | null
  labor_cost: number | null
  material_cost: number | null
  machine_cost: number | null
  management_fee: number | null
  profit: number | null
  safety_fee: number | null
  statutory_fee: number | null
  tax: number | null
  source_row: number | null
  resources: QuotaResource[]
}

export interface QuotaItemList {
  total: number
  items: QuotaItem[]
}

// ── 通用请求 ──────────────────────────────────────────

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, init)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `请求失败 ${res.status}`)
  }
  return res.json()
}

// ── 信息价接口 ──────────────────────────────────────────

export const fetchPeriods = () => req<Period[]>('/api/periods')
export const fetchCategories = () => req<Category[]>('/api/categories')

export function fetchItems(params: {
  period_id: number
  category_id?: number | null
  search?: string
  page?: number
  page_size?: number
}) {
  const q = new URLSearchParams({ period_id: String(params.period_id) })
  if (params.category_id) q.set('category_id', String(params.category_id))
  if (params.search) q.set('search', params.search)
  if (params.page) q.set('page', String(params.page))
  if (params.page_size) q.set('page_size', String(params.page_size))
  return req<PriceItemList>(`/api/items?${q}`)
}

export function fetchTrend(materialName: string, specification?: string) {
  const q = new URLSearchParams({ material_name: materialName })
  if (specification) q.set('specification', specification)
  return req<TrendPoint[]>(`/api/items/trend?${q}`)
}

export async function uploadFile(file: File, force = false): Promise<ImportResult> {
  const form = new FormData()
  form.append('file', file)
  return req<ImportResult>(`/api/upload?force=${force}`, { method: 'POST', body: form })
}

export async function deletePeriod(id: number) {
  return req<{ ok: boolean }>(`/api/periods/${id}`, { method: 'DELETE' })
}

// ── 消耗量标准接口 ──────────────────────────────────────────

export const fetchQuotaStandards = () => req<QuotaStandard[]>('/api/quota/standards')

export const fetchQuotaChapters = (standardId: number) =>
  req<QuotaChapter[]>(`/api/quota/chapters?standard_id=${standardId}`)

export function fetchQuotaItems(params: {
  standard_id: number
  chapter_id?: number | null
  search?: string
  page?: number
  page_size?: number
}) {
  const q = new URLSearchParams({ standard_id: String(params.standard_id) })
  if (params.chapter_id) q.set('chapter_id', String(params.chapter_id))
  if (params.search) q.set('search', params.search)
  if (params.page) q.set('page', String(params.page))
  if (params.page_size) q.set('page_size', String(params.page_size))
  return req<QuotaItemList>(`/api/quota/items?${q}`)
}

export const fetchAllQuotaItems = (standardId: number) =>
  req<QuotaItem[]>(`/api/quota/all-items?standard_id=${standardId}`)

// ── 国标清单（工程量计算标准）─────────────────────────────

export interface MeasureStandard {
  id: number
  name: string
  source_file: string | null
  imported_at: string
  item_count: number | null
}

export interface MeasureSection {
  id: number
  code: string | null
  name: string
  level: number
  parent_id: number | null
  sort_order: number
  num_code?: string | null
  description?: string | null
}

export interface MeasureItem {
  id: number
  section_id: number | null
  section_name: string | null
  item_code: string
  item_name: string
  item_features: string | null
  unit: string | null
  calc_rule: string | null
  work_content: string | null
}

export interface MeasureItemList {
  total: number
  items: MeasureItem[]
}

export const fetchMeasureStandards = () =>
  req<MeasureStandard[]>('/api/measure/standards')

export const fetchMeasureSections = (standardId: number) =>
  req<MeasureSection[]>(`/api/measure/sections?standard_id=${standardId}`)

export const fetchAllMeasureItems = (standardId: number) =>
  req<MeasureItem[]>(`/api/measure/all-items?standard_id=${standardId}`)

export function fetchMeasureItems(params: {
  standard_id: number
  section_id?: number | null
  search?: string
  page?: number
  page_size?: number
}) {
  const q = new URLSearchParams({ standard_id: String(params.standard_id) })
  if (params.section_id) q.set('section_id', String(params.section_id))
  if (params.search) q.set('search', params.search)
  if (params.page) q.set('page', String(params.page))
  if (params.page_size) q.set('page_size', String(params.page_size))
  return req<MeasureItemList>(`/api/measure/items?${q}`)
}

// ── 工程量清单（分部分项）────────────────────────────────

export interface BoqProject {
  id: number
  project_name: string
  bid_section: string | null
  source_file: string | null
  tag: string | null
  imported_at: string
  item_count: number | null
}

export interface BoqSection {
  id: number
  seq: number
  section_name: string
}

export interface BoqItem {
  id: number
  section_id: number | null
  section_name: string | null
  item_seq: number
  item_code: string
  item_name: string
  item_description: string | null
  unit: string | null
  quantity: number | null
  unit_price: number | null
  total_price: number | null
  provisional_price: number | null
}

export interface BoqItemList {
  total: number
  items: BoqItem[]
}

export const fetchBoqProjects = () => req<BoqProject[]>('/api/boq/projects')

export const fetchBoqSections = (projectId: number) =>
  req<BoqSection[]>(`/api/boq/sections?project_id=${projectId}`)

export const fetchAllBoqItems = (projectId: number) =>
  req<BoqItem[]>(`/api/boq/all-items?project_id=${projectId}`)

export function fetchBoqItems(params: {
  project_id: number
  section_id?: number | null
  search?: string
  page?: number
  page_size?: number
}) {
  const q = new URLSearchParams({ project_id: String(params.project_id) })
  if (params.section_id) q.set('section_id', String(params.section_id))
  if (params.search) q.set('search', params.search)
  if (params.page) q.set('page', String(params.page))
  if (params.page_size) q.set('page_size', String(params.page_size))
  return req<BoqItemList>(`/api/boq/items?${q}`)
}

// ── BOQ 套定额匹配 ──────────────────────────────────────

export interface BoqMatchResult {
  id: number
  boq_item_id: number
  quota_item_id: number
  qty_factor: number
  ai_reasoning: string | null
  reasoning_chain: string | null
  confidence: string | null
  status: string  // ai / confirmed / rejected
  confirmed_at: string | null

  // 工序和换算说明
  work_procedure: string | null
  factor_explanation: string | null

  // 定额基本信息
  quota_item_code: string
  quota_item_name: string
  quota_variant_desc: string | null
  quota_unit: string | null
  quota_work_content: string | null

  // 定额价格构成
  quota_total_unit_price: number | null
  quota_unit_price: number | null
  quota_labor_cost: number | null
  quota_material_cost: number | null
  quota_machine_cost: number | null
  quota_management_fee: number | null
  quota_profit: number | null
  quota_safety_fee: number | null
  quota_statutory_fee: number | null
  quota_tax: number | null

  // 工料机
  quota_resources: QuotaResource[]
}

export interface BoqSummaryItem {
  boq_item_id: number
  item_seq: number
  item_code: string
  item_name: string
  unit: string | null
  quantity: number | null
  unit_price: number | null
  total_price: number | null
  match_count: number
  match_status: string  // none / partial / all_confirmed
}

export interface BoqResourceSummary {
  resource_type: string
  resource_name: string
  unit: string | null
  total_quantity: number
}

export interface BoqSummaryResponse {
  items: BoqSummaryItem[]
  resources: BoqResourceSummary[]
}

export interface BoqMatchRun {
  id: number
  project_id: number
  standard_id: number
  standard_code: string | null
  run_name: string | null
  standard_ids: string | null   // JSON 数组字符串如 "[1,2]"
  status: string  // running / done / error
  total_items: number
  matched_items: number
  created_at: string
  finished_at: string | null
}

export const uploadBoqFile = (file: File, force = false, projectName?: string): Promise<BoqProject> => {
  const form = new FormData()
  form.append('file', file)
  if (projectName) form.append('project_name', projectName)
  return req<BoqProject>(`/api/boq/upload?force=${force}`, { method: 'POST', body: form })
}

export const fetchBoqRuns = (project_id: number) =>
  req<BoqMatchRun[]>(`/api/boq/runs?project_id=${project_id}`)

// ── 流式套定额 ──────────────────────────────────────────

export interface StreamMatch {
  quota_item_id: number
  quota_item_code: string
  quota_item_name: string
  quota_variant_desc: string | null
  quota_unit: string | null
  qty_factor: number
  confidence: string
  reasoning: string
}

export type StreamEvent =
  | { type: 'run_start'; run_id: number; total: number }
  | { type: 'item_start'; index: number; total: number; boq_item_id: number; item_name: string }
  | { type: 'reasoning_token'; token: string }
  | { type: 'item_done'; boq_item_id: number; matches: StreamMatch[] }
  | { type: 'item_error'; boq_item_id: number; error: string }
  | { type: 'run_done'; run_id: number; total: number; matched: number }
  | { type: 'run_error'; error: string }

export async function streamMatchBoqProject(
  project_id: number,
  standard_ids: number[],
  run_name: string,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  const res = await fetch(`${API}/api/boq/match-project-stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id, standard_ids, run_name }),
  })
  if (!res.ok) throw new Error(`请求失败 ${res.status}`)
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try { onEvent(JSON.parse(line.slice(6)) as StreamEvent) } catch { /* skip */ }
      }
    }
  }
}

// ── 消耗量标准 2024 接口 ────────────────────────────────────────────

export interface Quota2024Standard {
  id: number
  standard_code: string
  name: string
  region: string | null
  base_date: string | null
  source_file: string | null
  imported_at: string
}

export interface Quota2024Chapter {
  id: number
  chapter_no: number
  code: string | null
  name: string
  sort_order: number
}

export interface Quota2024Section {
  id: number
  section_type: 'intro' | 'rules' | 'items'
  section_code: string | null
  title: string
  content_md: string | null
  page_start: number | null
  page_end: number | null
}

export interface Quota2024Resource {
  id: number
  resource_type: string
  resource_name: string
  unit: string | null
  quantity: number | null
  ref_price: number | null
}

export interface Quota2024SubItem {
  id: number
  subitem_code: string
  subitem_name: string | null
  variant_desc: string | null
  unit: string | null
  name_path: string[]
  total_unit_price: number | null
  unit_price: number | null
  labor_cost: number | null
  material_cost: number | null
  machine_cost: number | null
  management_fee: number | null
  profit: number | null
  safety_fee: number | null
  statutory_fee: number | null
  tax: number | null
  resources: Quota2024Resource[]
}

export interface Quota2024Item {
  id: number
  item_no: number | null
  item_name: string
  work_content: string | null
  unit: string | null
  subitems: Quota2024SubItem[]
}

export interface Quota2024Group {
  id: number
  group_code: string | null
  group_name: string
  sort_order: number
  items: Quota2024Item[]
}

export interface Quota2024ChapterDetail {
  chapter: Quota2024Chapter
  sections: Quota2024Section[]
}

export const fetchQuota2024Standards = () => req<Quota2024Standard[]>('/api/quota2024/standards')

export const fetchQuota2024Chapters = (standardId: number) =>
  req<Quota2024Chapter[]>(`/api/quota2024/chapters?standard_id=${standardId}`)

export const fetchQuota2024ChapterSections = (chapterId: number) =>
  req<Quota2024ChapterDetail>(`/api/quota2024/chapters/${chapterId}/sections`)

export const fetchQuota2024Groups = (sectionId: number) =>
  req<Quota2024Group[]>(`/api/quota2024/sections/${sectionId}/groups`)

export const fetchQuota2024Items = (groupId: number) =>
  req<Quota2024Group>(`/api/quota2024/groups/${groupId}/items`)

export const fetchQuota2024SubItem = (subitemId: number) =>
  req<Quota2024SubItem>(`/api/quota2024/subitems/${subitemId}`)

export function searchQuota2024(q: string, standardId: number) {
  return req<Array<{ id: number; code: string; item_name: string; variant_desc: string | null }>>(
    `/api/quota2024/search?q=${encodeURIComponent(q)}&standard_id=${standardId}`
  )
}

export const matchBoqItem = (boq_item_id: number, standard_id: number) =>
  req<BoqMatchResult[]>('/api/boq/match-item', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ boq_item_id, standard_id }),
  })

// ── 并行套定额 ──────────────────────────────────────────

export type ParallelStreamEvent =
  | { type: 'run_start'; run_id: number; total: number; slots: number }
  | { type: 'slot_start'; slot: number; boq_item_id: number; item_name: string }
  | { type: 'slot_done'; slot: number; boq_item_id: number; item_name: string; matches: StreamMatch[]; elapsed_ms: number }
  | { type: 'slot_error'; slot: number; boq_item_id: number; item_name: string; error: string }
  | { type: 'run_done'; run_id: number; total: number; matched: number }
  | { type: 'run_error'; error: string }

export async function streamMatchBoqProjectParallel(
  project_id: number,
  standard_ids: number[],
  run_name: string,
  concurrency: number,
  onEvent: (e: ParallelStreamEvent) => void,
): Promise<void> {
  const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  const res = await fetch(`${API}/api/boq/match-project-parallel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id, standard_ids, run_name, concurrency }),
  })
  if (!res.ok) throw new Error(`请求失败 ${res.status}`)
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try { onEvent(JSON.parse(line.slice(6)) as ParallelStreamEvent) } catch { /* skip */ }
      }
    }
  }
}

export const startMatchBoqProject = (project_id: number, standard_id: number) =>
  req<{ run_id: number; status: string; total: number }>('/api/boq/match-project', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id, standard_id }),
  })

export const fetchBoqMatches = (run_id: number) =>
  req<BoqMatchResult[]>(`/api/boq/matches?run_id=${run_id}`)

export const updateBoqMatch = (id: number, status: string) =>
  req<BoqMatchResult>(`/api/boq/matches/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })

export const deleteBoqMatch = (id: number) =>
  req<{ ok: boolean }>(`/api/boq/matches/${id}`, { method: 'DELETE' })

export const fetchBoqSummary = (run_id: number) =>
  req<BoqSummaryResponse>(`/api/boq/summary?run_id=${run_id}`)

// ── 人工套定额工程 ──────────────────────────────────────

export interface ManualBoqProject {
  id: number
  project_name: string
  bid_section: string | null
  source_file: string | null
  tag: string | null
  imported_at: string
  item_count: number | null
}

export interface ManualBoqQuota {
  id: number
  boq_item_id: number
  quota_code: string | null
  quota_name: string | null
  quota_unit: string | null
  quantity: number | null
  unit_price: number | null
  total_price: number | null
  qty_factor: number | null
  quota_item_id: number | null
  // 关联定额库价格
  qi_total_unit_price: number | null
  qi_unit_price: number | null
  qi_labor_cost: number | null
  qi_material_cost: number | null
  qi_machine_cost: number | null
  qi_management_fee: number | null
  qi_profit: number | null
  qi_safety_fee: number | null
  qi_statutory_fee: number | null
  qi_tax: number | null
  qi_work_content: string | null
  qi_variant_desc: string | null
  qi_unit: string | null
}

export interface ManualBoqItem {
  id: number
  section_id: number | null
  section_name: string | null
  item_seq: number | null
  item_code: string | null
  item_name: string | null
  item_description: string | null
  unit: string | null
  quantity: number | null
  unit_price: number | null
  total_price: number | null
  quotas: ManualBoqQuota[]
}

export interface ManualBoqSection {
  id: number
  seq: number | null
  section_name: string
}

export interface ManualBoqProjectDetail {
  project: ManualBoqProject
  sections: ManualBoqSection[]
  items: ManualBoqItem[]
}

export const fetchManualBoqProjects = () =>
  req<ManualBoqProject[]>('/api/manual-boq/projects')

export const fetchManualBoqProject = (id: number) =>
  req<ManualBoqProjectDetail>(`/api/manual-boq/projects/${id}`)

export const uploadManualBoqFile = (file: File, force = false, tag?: string): Promise<ManualBoqProject> => {
  const form = new FormData()
  form.append('file', file)
  const q = new URLSearchParams({ force: String(force) })
  if (tag) q.set('tag', tag)
  return req<ManualBoqProject>(`/api/manual-boq/upload?${q}`, { method: 'POST', body: form })
}

export const deleteManualBoqProject = (id: number) =>
  req<{ ok: boolean }>(`/api/manual-boq/projects/${id}`, { method: 'DELETE' })

// ── 定额比较 ──────────────────────────────────────────

export interface CompareRunInfo {
  run_id: number
  run_name: string | null
  standard_code: string | null
  project_id: number
  project_name: string
}

export interface CompareQuota {
  quota_item_id: number | null
  quota_item_code: string
  quota_item_name: string
  qty_factor: number
  confidence: string | null
  work_procedure: string | null
}

export interface CompareBoqItem {
  item_code: string
  item_name: string
  unit: string | null
  quantity: number | null
  quotas_a: CompareQuota[]
  quotas_b: CompareQuota[]
  consistent: boolean
}

export interface CompareSummary {
  total: number
  consistent: number
  different: number
  only_a: number
  only_b: number
  both_empty: number
}

export interface CompareResult {
  run_a: CompareRunInfo
  run_b: CompareRunInfo
  items: CompareBoqItem[]
  summary: CompareSummary
}

export const fetchBoqCompare = (
  run_a: number, run_b: number,
  run_a_type = 'run', run_b_type = 'run',
) =>
  req<CompareResult>(`/api/boq/compare?run_a=${run_a}&run_b=${run_b}&run_a_type=${run_a_type}&run_b_type=${run_b_type}`)

// ── 深圳市建筑工程消耗量标准 2024（新解析表族）────────────────────────────

export interface BS2024Document {
  id: number
  standard_code: string
  name: string
  region: string | null
  source_file: string
  source_sha256: string
  page_count: number
  publish_date: string | null
  effective_date: string | null
  imported_at: string
  latest_run_status: string | null
  latest_run_stats: Record<string, unknown>
  chapter_count: number
  subitem_count: number
  issue_count: number
}

export interface BS2024SectionNode {
  id: number
  section_type: 'intro' | 'rules' | 'items' | 'directory' | 'other'
  section_code: string | null
  title: string
  page_start: number | null
  page_end: number | null
}

export interface BS2024ChapterNode {
  id: number
  chapter_no: number
  code: string | null
  title: string
  page_start: number | null
  page_end: number | null
  sections: BS2024SectionNode[]
}

export interface BS2024SectionDetail extends BS2024SectionNode {
  document_id: number
  chapter_id: number
  content_md: string | null
}

export interface BS2024Resource {
  id: number
  resource_type: string
  resource_name: string
  unit: string | null
  quantity: number | null
  ref_price: number | null
  page_no: number | null
}

export interface BS2024Subitem {
  id: number
  subitem_code: string
  subitem_name: string | null
  variant_desc: string | null
  unit: string | null
  name_path: string[]
  total_unit_price: number | null
  unit_price: number | null
  labor_cost: number | null
  material_cost: number | null
  machine_cost: number | null
  management_fee: number | null
  profit: number | null
  safety_fee: number | null
  statutory_fee: number | null
  tax: number | null
  page_no: number | null
  confidence: number | null
  resources: BS2024Resource[]
}

export interface BS2024Item {
  id: number
  item_no: number | null
  item_name: string
  work_content: string | null
  unit: string | null
  page_no: number | null
  subitems: BS2024Subitem[]
}

export interface BS2024Group {
  id: number
  group_code: string | null
  group_name: string
  page_start: number | null
  page_end: number | null
  sort_order: number
  item_count: number
  items: BS2024Item[]
}

export interface BS2024Issue {
  id: number
  page_no: number | null
  severity: string
  issue_type: string
  message: string
  context_json: Record<string, unknown>
  created_at: string
}

export interface BS2024SearchResult {
  id: number
  subitem_code: string
  name: string
  variant_desc: string | null
  unit: string | null
  group_code: string | null
  group_name: string
  chapter_no: number
  chapter_title: string
}

export const fetchBS2024Documents = () =>
  req<BS2024Document[]>('/api/building-standard-2024/documents')

export const fetchBS2024Tree = (documentId: number) =>
  req<BS2024ChapterNode[]>(`/api/building-standard-2024/documents/${documentId}/tree`)

export const fetchBS2024Section = (sectionId: number) =>
  req<BS2024SectionDetail>(`/api/building-standard-2024/sections/${sectionId}`)

export const fetchBS2024Groups = (sectionId: number) =>
  req<BS2024Group[]>(`/api/building-standard-2024/groups?section_id=${sectionId}`)

export const fetchBS2024GroupItems = (groupId: number) =>
  req<BS2024Group>(`/api/building-standard-2024/groups/${groupId}/items`)

export const searchBS2024 = (documentId: number, q: string) =>
  req<BS2024SearchResult[]>(`/api/building-standard-2024/search?document_id=${documentId}&q=${encodeURIComponent(q)}`)

export const fetchBS2024Issues = (documentId: number) =>
  req<BS2024Issue[]>(`/api/building-standard-2024/parse-issues?document_id=${documentId}`)

// ── 调试批次 ──────────────────────────────────────────────────────────────────

export interface DebugBatch {
  id: number
  name: string
  boq_project_id: number
  project_name: string
  manual_project_id: number | null
  standard_ids: number[]
  created_at: string
  result_count: number
}

export interface DebugBatchDetail extends DebugBatch {
  standards: { id: number; standard_code: string; name: string }[]
}

export interface DebugItemResult {
  reasoning_chain: string | null
  result: {
    matches: DebugMatchQuota[]
    missed: (DebugManualQuota & { missed_by_ai: boolean })[]
    manual_quotas: DebugManualQuota[]
  }
  ran_at: string
}

export const fetchDebugBatches = () => req<DebugBatch[]>('/api/debug-batches')

export const fetchDebugBatch = (id: number) => req<DebugBatchDetail>(`/api/debug-batches/${id}`)

export const fetchBatchResults = (batchId: number) =>
  req<Record<string, DebugItemResult>>(`/api/debug-batches/${batchId}/results`)

export async function createDebugBatch(body: {
  name: string
  boq_project_id: number
  manual_project_id: number | null
  standard_ids: number[]
}): Promise<{ id: number; created_at: string }> {
  const res = await fetch(`${API}/api/debug-batches`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`创建失败 ${res.status}`)
  return res.json()
}

export async function renameDebugBatch(id: number, name: string): Promise<void> {
  const res = await fetch(`${API}/api/debug-batches/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error(`重命名失败 ${res.status}`)
}

export async function deleteDebugBatch(id: number): Promise<void> {
  const res = await fetch(`${API}/api/debug-batches/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`删除失败 ${res.status}`)
}

// ── 单条调试套定额 ────────────────────────────────────────────────────────────

export interface DebugManualQuota {
  quota_code: string
  quota_name: string | null
  quota_unit: string | null
  quantity: number | null
  qty_factor: number | null
  quota_item_id: number | null
  is_formula: boolean
}

export interface DebugMatchQuota {
  quota_item_id: number
  quota_item_code: string
  quota_item_name: string
  quota_variant_desc: string | null
  quota_unit: string | null
  total_unit_price: number | null
  labor_cost: number | null
  material_cost: number | null
  machine_cost: number | null
  qty_factor: number
  confidence: string | null
  work_procedure: string | null
  factor_explanation: string | null
  reasoning: string | null
  missing_info: string | null  // 缺少的项目特征（low/medium 时非空）
  in_manual: boolean    // AI 匹配的，人工也有 → ✅
}

export type DebugMatchEvent =
  | { type: 'item_info'; item: BoqItem; manual_quotas: DebugManualQuota[]; system_prompt?: string; system_prompt_len?: number; user_message?: string }
  | { type: 'reasoning_token'; token: string }
  | { type: 'result'; matches: DebugMatchQuota[]; missed: (DebugManualQuota & { missed_by_ai: boolean })[] }
  | { type: 'done' }
  | { type: 'error'; error: string }

export async function streamDebugMatch(
  boq_item_id: number,
  standard_ids: number[],
  manual_project_id: number | null,
  onEvent: (e: DebugMatchEvent) => void,
  batch_id?: number,
  item_description_override?: string | null,
): Promise<void> {
  const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  const res = await fetch(`${API}/api/boq/match-item-debug`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ boq_item_id, standard_ids, manual_project_id, batch_id, item_description_override: item_description_override ?? null }),
  })
  if (!res.ok) throw new Error(`请求失败 ${res.status}`)
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try { onEvent(JSON.parse(line.slice(6)) as DebugMatchEvent) } catch { /* skip */ }
      }
    }
  }
}
