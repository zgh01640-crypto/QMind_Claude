const API = process.env.NEXT_PUBLIC_API_URL || ''

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

export async function updateBoqItemDescription(itemId: number, item_description: string | null) {
  return req<BoqItem>(`/api/boq/items/${itemId}/description`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ item_description }),
  })
}

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
  const API = process.env.NEXT_PUBLIC_API_URL || ''
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
  const API = process.env.NEXT_PUBLIC_API_URL || ''
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
  item_description: string | null
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

export interface StandardReferencePrice {
  id: number
  document_id: number
  appendix_code: string
  sequence_no: number
  resource_type: '材料' | '机械'
  name: string
  unit: string
  price: number
  source_page_no: number
  source_page_id: number | null
  confidence: number | null
  raw_json: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface StandardReferencePriceList {
  total: number
  page: number
  page_size: number
  items: StandardReferencePrice[]
}

export interface StandardReferencePriceFilterOptions {
  total: number
  material_count: number
  machine_count: number
  units: string[]
}

export function fetchStandardReferencePrices(params: {
  document_id: number
  appendix_code?: string
  q?: string
  unit?: string
  resource_type?: '材料' | '机械' | ''
  page?: number
  page_size?: number
}) {
  const query = new URLSearchParams({
    document_id: String(params.document_id),
    appendix_code: params.appendix_code ?? 'A',
  })
  if (params.q) query.set('q', params.q)
  if (params.unit) query.set('unit', params.unit)
  if (params.resource_type) query.set('resource_type', params.resource_type)
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  return req<StandardReferencePriceList>(`/api/standard-reference-prices?${query}`)
}

export function fetchStandardReferencePriceFilterOptions(documentId: number, appendixCode = 'A') {
  const query = new URLSearchParams({
    document_id: String(documentId),
    appendix_code: appendixCode,
  })
  return req<StandardReferencePriceFilterOptions>(
    `/api/standard-reference-prices/filter-options?${query}`,
  )
}

// ── 组价知识库 ──────────────────────────────────────────────────────────────────

export interface PricingKbSummary {
  library_count: number
  chapter_count: number
  boq_item_count: number
  quota_item_count: number
  resource_count: number
  conversion_rule_count: number
  candidate_count: number
  target_link_count: number
  issue_count: number
  boq_with_candidates: number
  boq_without_candidates: number
  link_status_counts: Record<string, number>
  issue_type_counts: Record<string, number>
}

export interface PricingKbLibrary {
  id: number
  source_library_id: number
  name: string
  quota_count: number
  boq_count: number
}

export interface PricingKbBoqItem {
  id: number
  source_library_id: number
  library_name: string
  code: string | null
  name: string
  unit: string | null
  chapter_name: string | null
  chapter_path: string[]
  candidate_count: number
}

export interface BoqProcessAppendixSummary {
  appendix_code: string | null
  appendix_name: string | null
  process_count: number
  item_count: number
}

export interface BoqProcessItem {
  id: number
  qdkid: number
  library_name: string
  qdzmid: number | null
  zmbh: string
  zmmc: string
  unit: string | null
  chapter_name: string | null
  appendix_code: string | null
  appendix_name: string | null
  procedure_text: string
  source_sheet: string
  source_rowid: number
  linked: boolean
}

export interface BoqProcessList {
  total: number
  item_total: number
  page: number
  page_size: number
  appendices: BoqProcessAppendixSummary[]
  items: BoqProcessItem[]
}

export interface BoqFeatureDefaultFeature {
  id: number
  feature_name: string
  feature_value: string
  default_value: string
  source_sheet: string
  source_rowid: number
}

export interface BoqFeatureDefaultItem {
  id: number
  qdkid: number
  library_name: string
  qdzmid: number | null
  zmbh: string
  zmmc: string | null
  unit: string | null
  chapter_name: string | null
  linked: boolean
  features: BoqFeatureDefaultFeature[]
}

export interface BoqFeatureDefaultList {
  total: number
  item_total: number
  page: number
  page_size: number
  items: BoqFeatureDefaultItem[]
}

export interface PricingKbQuotaItem {
  id: number
  source_library_id: number
  library_name: string
  code: string | null
  name: string
  unit: string | null
  chapter_name: string | null
  link_status: string
  target_table: string | null
  target_item_id: number | null
}

export interface PricingKbResourceSummary {
  resource_type: string | null
  resource_code: string | null
  resource_name: string
  unit: string | null
  quantity: number | null
}

export interface PricingKbConversionRule {
  rule_type: string
  prompt: string | null
  description: string | null
  group_no: number | null
}

export interface QuotaCostBreakdown {
  dj: number | null
  rgf: number | null
  clf: number | null
  jxf: number | null
  zcf: number | null
  sbf: number | null
  glf: number | null
  lr: number | null
  aqwmsgf: number | null
  qtcsf: number | null
  gf: number | null
  sj: number | null
}

export interface QuotaInputPromptRule {
  prompt: string | null
  adjustment_code: string | null
  base_value: number | null
  increment_unit: number | null
}

export interface PricingKbCandidate {
  candidate_id: number
  quota_item: {
    id: number
    source_library_id: number
    library_name: string
    code: string | null
    name: string
    unit: string | null
    work_content: string | null
    chapter_name: string | null
    cost_breakdown: QuotaCostBreakdown
  }
  target_link: {
    link_status: string
    target_table: string | null
    target_item_id: number | null
    review_message: string | null
  }
  resource_summary: PricingKbResourceSummary[]
  resource_count: number
  conversion_rules: PricingKbConversionRule[]
  input_prompt_rules: QuotaInputPromptRule[]
}

export interface PricingKbCandidateResponse {
  boq_item: Omit<PricingKbBoqItem, 'candidate_count'>
  total: number
  candidates: PricingKbCandidate[]
}

export interface PricingKbImportRun {
  id: number
  source_file: string
  source_file_sha256: string
  status: string
  stats_json: Record<string, unknown>
  error_message: string | null
  created_at: string
  finished_at: string | null
  reasoning_text?: string | null
}

export interface PricingKbImportIssue {
  id: number
  run_id: number | null
  severity: string
  issue_type: string
  message: string
  source_table: string | null
  source_library_id: number | null
  source_record_id: number | null
  context_json: Record<string, unknown>
  created_at: string
}

export interface PricingKbSourceTableInspection {
  name: string
  known: boolean
  row_count: number
  column_count: number
  columns: { name: string; type: string; not_null: boolean; pk: boolean }[]
  schema_signature: string
  dependencies: string[]
}

export interface PricingKbUploadResult {
  id: number
  duplicate: boolean
  inspection: { quick_check: string; schema_signature: string; tables: PricingKbSourceTableInspection[] }
}

export interface PricingKbImportProfile {
  profile_id: string
  name: string
  description: string | null
  selected_tables: string[]
  required_tables: string[]
  is_system: boolean
}

export interface PricingKbImportJob {
  id: number
  upload_id: number
  profile_id: string | null
  parent_version_id: number | null
  version_id: number | null
  config: { selected_tables: string[]; unknown_tables: Record<string, string> }
  status: string
  current_table: string | null
  completed_tables: number
  total_tables: number
  processed_rows: number
  progress: Record<string, unknown>
  error_message: string | null
  attempts: number
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface PricingKbVersion {
  id: number
  source_file: string
  source_file_sha256: string
  status: string
  table_counts: Record<string, unknown>
  validation_report: Record<string, unknown>
  imported_at: string
  published_at: string | null
  published_by: string | null
  is_active: boolean
}

export interface PricingKbList<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

export interface BoqTreeCategory {
  id: number
  qdkid: number
  pid: number | null
  zjmc: string
  zjsm: string | null
  child_count: number
  item_count: number
  descendant_item_count?: number
  enabled?: boolean
}

export interface BoqTreeItem {
  id: number
  qdkid: number
  zmbh: string
  zmmc: string
  dw: string | null
  zjh: number
  chapter_name: string | null
  candidate_count: number
}

export interface BoqTreeChapterResponse {
  chapter: {
    id: number
    qdkid: number
    pid: number | null
    zjmc: string
    zjsm: string | null
    descendant_item_count?: number
  }
  children: BoqTreeCategory[]
  items: BoqTreeItem[]
}

export interface QuotaTreeCategory {
  id: number
  dekid: number
  pid: number | null
  zjmc: string
  zjsm: string | null
  child_count: number
  item_count: number
  quota_count?: number
}

export interface QuotaTreeItem {
  id: number
  dekid: number
  zmbh: string | null
  zmmc: string
  dw: string | null
  gznr: string | null
  zjh: number
  chapter_name: string | null
  resource_count: number
  conversion_rule_count: number
  input_prompt_count: number
  link_status: string
  target_table: string | null
  target_item_id: number | null
}

export interface QuotaTreeChapterResponse {
  chapter: {
    id: number
    dekid: number
    pid: number | null
    zjmc: string
    zjsm: string | null
  }
  children: QuotaTreeCategory[]
  items: QuotaTreeItem[]
}

export interface QuotaTreeResource {
  resource_type: string | null
  resource_code: string | null
  resource_name: string
  unit: string | null
  quantity: number | null
}

// ── 单条组价 — 新版接口 ────────────────────────────────────────────

export interface QuotaCandidate {
  id: number
  dezmid?: number
  dekid: number
  library_name?: string
  zmbh: string
  zmmc: string
  dw: string
  gznr: string
  chapter_name?: string | null
}

export interface QuotaMatch {
  dekid?: number
  dezmid?: number
  zmbh: string
  zmmc: string
  dw?: string | null
  library_name?: string | null
  chapter_name?: string | null
  qty_factor: number
  confidence: 'high' | 'medium' | 'low'
  match_reason: string
}

export interface PricingTask {
  id: number
  name: string
  boq_project_id: number
  project_id: number
  project_name: string
  manual_project_id: number | null
  manual_project_name?: string | null
  quota_library_ids: number[]
  quota_library_names: string[]
  legacy_local_id: string | null
  accuracy_report: PricingTaskAccuracyReport | null
  created_at: string
  latest_run_count: number
}

export interface PricingTaskBatch {
  id: number
  name: string
  boq_project_id: number
  project_id: number
  project_name: string
  manual_project_id: number | null
  manual_project_name?: string | null
  quota_library_ids: number[]
  quota_library_names: string[]
  status: string
  selected_count: number
  completed_count: number
  failed_count: number
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface PricingTaskRun {
  id: number
  status: string
  code_check: any
  feature_check: any
  work_procedures: { procedures?: string[]; procedure_text?: string; found?: boolean; base_code?: string } | null
  quota_candidates: { candidates?: QuotaCandidate[]; total?: number } | null
  quota_match: { matches?: QuotaMatch[]; issues?: string[] } | null
  evaluation: PricingTaskEvaluation | null
  conversion_check: PricingTaskConversionCheck | null
  coefficient_check: PricingTaskCoefficientCheck | null
  step_timings: Record<string, PricingTaskStepTiming> | null
  error_message: string | null
  created_at: string
  finished_at: string | null
  reasoning_text?: string | null
  confirmed_results?: PricingTaskConfirmedResult[]
}

export interface PricingTaskLatestRun {
  boq_item_id: number
  run: PricingTaskRun
}

export interface PricingTaskBatchItemRun {
  boq_item_id: number
  run: PricingTaskRun
}

export interface PricingTaskBatchDetail {
  batch: PricingTaskBatch
  items: BoqItem[]
  runs: PricingTaskBatchItemRun[]
}

export interface PricingTaskEvaluation {
  manual_quotas: DebugManualQuota[]
  hit_codes: string[]
  missed_codes: string[]
  extra_codes: string[]
  hit_count: number
  missed_count: number
  extra_count: number
  manual_count: number
  ai_count: number
}

export interface PricingTaskAccuracyReport {
  summary: string
  accuracy_level: '高' | '中' | '低' | '待复核'
  accuracy_rate: number | null
  metrics: {
    total_items?: number
    evaluated_item_count?: number
    exact_item_count?: number
    hit_count: number
    missed_count: number
    extra_count: number
    manual_count: number
    ai_count: number
    hit_rate?: number | null
  }
  key_findings: string[]
  matched_analysis: string
  missed_analysis: string
  extra_analysis: string
  risk_items?: string[]
  representative_examples?: string[]
  business_recommendations: string[]
  conclusion: string
  generated_at: string
}

export interface PricingTaskDetailReportQuota {
  code: string
  name: string
  unit?: string
  qty_factor?: number | null
  quantity?: number | null
  confidence?: string
  match_reason?: string
  in_manual?: boolean
  in_ai?: boolean
  analysis: string
}

export interface PricingTaskDetailReportRound {
  step_no: number
  name: string
  data: any
  duration_ms: number | null
  started_at: string | null
  finished_at: string | null
}

export interface PricingTaskDetailReportItem {
  run_id: number
  boq_item_id: number
  status: string
  created_at: string | null
  finished_at: string | null
  item: {
    id: number
    item_seq?: number | null
    item_code: string
    item_name: string
    item_description: string
    unit: string
    quantity: number | null
  }
  rounds: PricingTaskDetailReportRound[]
  ai_quota_results: PricingTaskDetailReportQuota[]
  manual_quota_results: PricingTaskDetailReportQuota[]
  consistency: {
    status: string
    summary: string
    hit_codes: string[]
    missed_codes: string[]
    extra_codes: string[]
    hit_count: number
    missed_count: number
    extra_count: number
    manual_count: number
    ai_count: number
    ai_results: PricingTaskDetailReportQuota[]
    manual_results: PricingTaskDetailReportQuota[]
  }
  reasoning_text: string
}

export interface PricingTaskDetailReport {
  task: {
    id: number
    name: string
    boq_project_id: number
    project_name: string
    manual_project_id: number | null
    manual_project_name?: string | null
    quota_library_ids: number[]
  }
  metrics: {
    total_items: number
    evaluated_item_count: number
    consistent_item_count: number
    partial_item_count: number
    inconsistent_item_count: number
    no_manual_item_count: number
    hit_count: number
    missed_count: number
    extra_count: number
    manual_count: number
    ai_count: number
    hit_rate: number | null
  }
  items: PricingTaskDetailReportItem[]
  generated_at: string
}

export interface PricingTaskStepTiming {
  step_no: number
  name: string
  duration_ms: number
  started_at: string
  finished_at: string
}

export interface PricingTaskConversionResource {
  code: string
  name: string
  unit: string
  type: number | null
  original_quantity?: number | null
  confirmed_quantity?: number | null
  quantity?: number | null
  adjustment_note?: string
}

export interface PricingTaskConversionResourceChange {
  resource_code: string
  resource_name: string
  resource_type: number | null
  field: string
  old_value: string | number | null
  new_value: string | number | null
  change_type: string
  basis: string
  note: string
}

export interface PricingTaskConfirmedResult {
  dekid: number
  dezmid: number
  subitem_code: string
  subitem_name: string
  qty_factor: number
  status: string
  conversion_confirmed: boolean
  conversion_note: string
  conversion_confirmed_at: string | null
  conversion_resources: PricingTaskConversionResource[]
  conversion_resource_changes: PricingTaskConversionResourceChange[]
}

export interface PricingTaskConversionItem {
  dekid: number
  dezmid: number
  quota_code: string
  quota_name: string
  needs_conversion: boolean
  reason: string
  requires_manual_review?: boolean
  resources?: PricingTaskConversionResource[]
  adjustment_rules?: PricingTaskComboAdjustmentRule[]
  missing_inputs: string[]
  confidence: 'high' | 'medium' | 'low'
}

export interface PricingTaskComboAdjustmentRule {
  rule_index: number
  prompt: string
  base_value: number
  increment_unit: number
  combo_dezmid: number
  combo_code: string
  combo_name: string
  combo_unit: string
  combo_work_content: string
  combo_labor_cost?: number
  combo_material_cost?: number
  combo_machine_cost?: number
  combo_resources?: PricingTaskConversionResource[]
  matched: boolean
  matched_feature: string
  feature_value: number | null
  calculated_times: number | null
  reason: string
  requires_manual_review: boolean
  confidence: 'high' | 'medium' | 'low'
}

export interface PricingTaskConversionCheck {
  items: PricingTaskConversionItem[]
  issues: string[]
}

export interface PricingTaskCoefficientRule {
  rule_index: number
  tsxx: string
  hssm: string
  group_no: number
  matched: boolean
  matched_feature: string
  feature_value: string
  factor: number
  target_resource_types: Array<'1' | '2' | '3' | 'all'>
  reason: string
  requires_manual_review: boolean
  confidence: 'high' | 'medium' | 'low'
}

export interface PricingTaskCoefficientItem {
  quota_key: string
  source_type: 'base' | 'combo'
  dekid: number
  dezmid: number
  quota_code: string
  quota_name: string
  resources?: PricingTaskConversionResource[]
  coefficient_rules: PricingTaskCoefficientRule[]
  missing_inputs: string[]
  confidence: 'high' | 'medium' | 'low'
}

export interface PricingTaskCoefficientCheck {
  items: PricingTaskCoefficientItem[]
  issues: string[]
}

export interface PricingTaskMatch {
  dezmid: number
  dekid: number
  subitem_code: string
  subitem_name: string
  qty_factor: number
  work_procedure: string
  confidence: 'high' | 'medium' | 'low'
  missing_info?: string
}

export type PricingTaskEvent =
  | { type: 'run_started'; run_id: number }
  | { type: 'item_info'; item: BoqItem }
  | { type: 'reasoning_token'; token: string }
  | { type: 'code_check'; item_code: string; item_name: string; base_code: string; standard_name: string; found: boolean; is_consistent: boolean }
  | { type: 'judgment'; is_consistent: boolean; reasoning: string }
  | {
      type: 'feature_check'
      is_complete: boolean
      missing_features: string[]
      analysis: string
      normalized_description?: string
      default_fills?: Array<{ feature_name: string; original_value: string; default_value: string; source_code: string; reason: string }>
      description_updated?: boolean
      default_candidates?: Array<{ source_code: string; feature_name: string; feature_value: string; default_value: string; source_rowid?: number }>
    }
  | { type: 'quota_candidates'; item_code: string; base_code: string; candidates: QuotaCandidate[]; total: number }
  | { type: 'quota_match'; matches: QuotaMatch[]; issues: string[] }
  | { type: 'evaluation'; evaluation: PricingTaskEvaluation }
  | { type: 'conversion_check_start'; run_id: number; total: number }
  | { type: 'combo_adjustment_rules'; items: PricingTaskConversionItem[] }
  | { type: 'conversion_check'; conversion_check: PricingTaskConversionCheck }
  | { type: 'coefficient_check_start'; run_id: number; total: number }
  | { type: 'coefficient_rules'; items: PricingTaskCoefficientItem[] }
  | { type: 'coefficient_check'; coefficient_check: PricingTaskCoefficientCheck }
  | { type: 'step_timing'; step_no: number; name: string; duration_ms: number; started_at: string; finished_at: string }
  | { type: 'done'; run_id?: number }
  | { type: 'error'; error: string }

export interface LocalPricingTask {
  id: string
  name: string
  project_id: number
  manual_project_id: number | null
  chapter_ids?: number[]
}

export const fetchPricingTasks = () => req<PricingTask[]>('/api/pricing-tasks')

export const fetchPricingTask = (id: number) => req<PricingTask>(`/api/pricing-tasks/${id}`)

export const fetchPricingTaskBatches = () => req<PricingTaskBatch[]>('/api/pricing-task-batches')

export const fetchPricingTaskBatch = (id: number) => req<PricingTaskBatch>(`/api/pricing-task-batches/${id}`)

export const fetchPricingTaskBatchDetail = (id: number) =>
  req<PricingTaskBatchDetail>(`/api/pricing-task-batches/${id}/items`)

export async function createPricingTaskBatch(body: {
  name: string
  boq_project_id: number
  quota_library_ids: number[]
  manual_project_id: number | null
}): Promise<{ id: number }> {
  return req<{ id: number }>('/api/pricing-task-batches', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function deletePricingTaskBatch(id: number) {
  const res = await fetch(`${API}/api/pricing-task-batches/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `请求失败 ${res.status}`)
  }
}

export async function createPricingTask(body: {
  name: string
  boq_project_id: number
  quota_library_ids: number[]
  manual_project_id: number | null
  legacy_local_id?: string | null
}): Promise<{ id: number }> {
  return req<{ id: number }>('/api/pricing-tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function importLocalPricingTasks(tasks: LocalPricingTask[]) {
  return req<{ imported: { legacy_local_id: string; id: number }[] }>('/api/pricing-tasks/import-local', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tasks }),
  })
}

export const fetchPricingTaskItemRuns = (taskId: number, itemId: number) =>
  req<PricingTaskRun[]>(`/api/pricing-tasks/${taskId}/items/${itemId}/runs`)

export const fetchPricingTaskLatestRuns = (taskId: number) =>
  req<PricingTaskLatestRun[]>(`/api/pricing-tasks/${taskId}/runs/latest`)

export async function confirmPricingTaskRun(runId: number, results?: QuotaMatch[]) {
  return req<{ ok: boolean }>(`/api/pricing-task-runs/${runId}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ results: results ?? null }),
  })
}

export async function rejectPricingTaskRun(runId: number) {
  return req<{ ok: boolean }>(`/api/pricing-task-runs/${runId}/reject`, { method: 'POST' })
}

export async function generatePricingTaskAccuracyReport(taskId: number) {
  return req<PricingTaskAccuracyReport>(`/api/pricing-tasks/${taskId}/accuracy-report`, { method: 'POST' })
}

export async function fetchPricingTaskDetailReport(taskId: number) {
  return req<PricingTaskDetailReport>(`/api/pricing-tasks/${taskId}/detail-report`)
}

export async function exportPricingTaskDetailReportExcel(taskId: number) {
  const response = await fetch(`${API}/api/pricing-tasks/${taskId}/detail-report/export`)
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || `请求失败 ${response.status}`)
  }
  return response.blob()
}

export async function streamPricingTaskItem(
  boq_item_id: number,
  chapter_ids: number[],
  manual_project_id: number | null,
  onEvent: (e: PricingTaskEvent) => void,
): Promise<void> {
  const url = `${API}/api/pricing-task/match-item-stream`
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      boq_item_id,
      chapter_ids,
      manual_project_id,
    }),
  })

  if (!response.ok) {
    onEvent({ type: 'error', error: `HTTP ${response.status}` })
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    onEvent({ type: 'error', error: 'No response body' })
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const jsonStr = line.slice(6)
        try {
          const evt = JSON.parse(jsonStr)
          onEvent(evt)
        } catch (e) {
          console.error('Parse error:', e, jsonStr)
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

export async function streamPricingTaskRunItem(
  taskId: number,
  boqItemId: number,
  onEvent: (e: PricingTaskEvent) => void,
): Promise<void> {
  const response = await fetch(`${API}/api/pricing-tasks/${taskId}/items/${boqItemId}/run-stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ boq_item_id: boqItemId }),
  })

  if (!response.ok) {
    onEvent({ type: 'error', error: `HTTP ${response.status}` })
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    onEvent({ type: 'error', error: 'No response body' })
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          onEvent(JSON.parse(line.slice(6)) as PricingTaskEvent)
        } catch (e) {
          console.error('Parse error:', e, line.slice(6))
        }
      }
    }
    const tail = buffer.trim()
    if (tail.startsWith('data: ')) {
      try {
        onEvent(JSON.parse(tail.slice(6)) as PricingTaskEvent)
      } catch (e) {
        console.error('Parse error:', e, tail.slice(6))
      }
    }
  } finally {
    reader.releaseLock()
  }
}

export async function streamPricingTaskConversionCheck(
  runId: number,
  onEvent: (e: PricingTaskEvent) => void,
): Promise<void> {
  const response = await fetch(`${API}/api/pricing-task-runs/${runId}/conversion-check-stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })

  if (!response.ok) {
    onEvent({ type: 'error', error: `HTTP ${response.status}` })
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    onEvent({ type: 'error', error: 'No response body' })
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          onEvent(JSON.parse(line.slice(6)) as PricingTaskEvent)
        } catch (e) {
          console.error('Parse error:', e, line.slice(6))
        }
      }
    }
    const tail = buffer.trim()
    if (tail.startsWith('data: ')) {
      try {
        onEvent(JSON.parse(tail.slice(6)) as PricingTaskEvent)
      } catch (e) {
        console.error('Parse error:', e, tail.slice(6))
      }
    }
  } finally {
    reader.releaseLock()
  }
}

export async function streamPricingTaskCoefficientCheck(
  runId: number,
  onEvent: (e: PricingTaskEvent) => void,
): Promise<void> {
  const response = await fetch(`${API}/api/pricing-task-runs/${runId}/coefficient-check-stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })

  if (!response.ok) {
    onEvent({ type: 'error', error: `HTTP ${response.status}` })
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    onEvent({ type: 'error', error: 'No response body' })
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          onEvent(JSON.parse(line.slice(6)) as PricingTaskEvent)
        } catch (e) {
          console.error('Parse error:', e, line.slice(6))
        }
      }
    }
    const tail = buffer.trim()
    if (tail.startsWith('data: ')) {
      try {
        onEvent(JSON.parse(tail.slice(6)) as PricingTaskEvent)
      } catch (e) {
        console.error('Parse error:', e, tail.slice(6))
      }
    }
  } finally {
    reader.releaseLock()
  }
}

async function readPricingTaskEventStream(response: Response, onEvent: (e: PricingTaskEvent) => void): Promise<void> {
  if (!response.ok) {
    onEvent({ type: 'error', error: `HTTP ${response.status}` })
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    onEvent({ type: 'error', error: 'No response body' })
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          onEvent(JSON.parse(line.slice(6)) as PricingTaskEvent)
        } catch (e) {
          console.error('Parse error:', e, line.slice(6))
        }
      }
    }
    const tail = buffer.trim()
    if (tail.startsWith('data: ')) {
      try {
        onEvent(JSON.parse(tail.slice(6)) as PricingTaskEvent)
      } catch (e) {
        console.error('Parse error:', e, tail.slice(6))
      }
    }
  } finally {
    reader.releaseLock()
  }
}

export async function streamPricingTaskBatchItemRun(
  batchId: number,
  boqItemId: number,
  onEvent: (e: PricingTaskEvent) => void,
): Promise<void> {
  return readPricingTaskEventStream(
    await fetch(`${API}/api/pricing-task-batches/${batchId}/items/${boqItemId}/run-stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }),
    onEvent,
  )
}

export async function streamPricingTaskBatchConversionCheck(
  itemRunId: number,
  onEvent: (e: PricingTaskEvent) => void,
): Promise<void> {
  return readPricingTaskEventStream(
    await fetch(`${API}/api/pricing-task-batch-item-runs/${itemRunId}/conversion-check-stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }),
    onEvent,
  )
}

export async function streamPricingTaskBatchCoefficientCheck(
  itemRunId: number,
  onEvent: (e: PricingTaskEvent) => void,
): Promise<void> {
  return readPricingTaskEventStream(
    await fetch(`${API}/api/pricing-task-batch-item-runs/${itemRunId}/coefficient-check-stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }),
    onEvent,
  )
}

export interface QuotaTreeConversionRule {
  prompt: string | null
  description: string | null
  group_no: number | null
}

export interface QuotaTreeItemDetail {
  item: QuotaTreeItem & {
    review_message: string | null
  }
  cost_breakdown: QuotaCostBreakdown
  resources: QuotaTreeResource[]
  conversion_rules: QuotaTreeConversionRule[]
  input_prompts: string[]
  input_prompt_rules: QuotaInputPromptRule[]
}

export interface QuotaInputPromptItem {
  dekid: number
  library_name: string
  quota_item_id: number
  quota_code: string | null
  quota_name: string
  unit: string | null
  chapter_name: string | null
  prompt_count: number
  prompt_rules: QuotaInputPromptRule[]
}

export interface QuotaConversionRuleListItem {
  dekid: number
  library_name: string
  quota_item_id: number
  quota_code: string | null
  quota_name: string
  unit: string | null
  chapter_name: string | null
  rule_count: number
  conversion_rules: QuotaTreeConversionRule[]
}

export const fetchPricingKbSummary = () =>
  req<PricingKbSummary>('/api/pricing-kb/summary')

export const fetchPricingKbLibraries = () =>
  req<PricingKbLibrary[]>('/api/pricing-kb/libraries')

export const fetchBoqTreeTopCategories = () =>
  req<BoqTreeCategory[]>('/api/pricing-kb/boq-tree/top-categories')

export const fetchBoqTreeChapter = (chapterId: number) =>
  req<BoqTreeChapterResponse>(`/api/pricing-kb/boq-tree/chapter/${chapterId}`)

export const fetchQuotaTreeTopLibraries = () =>
  req<QuotaTreeCategory[]>('/api/pricing-kb/quota-tree/top-libraries')

export const fetchQuotaTreeChapter = (dekid: number, chapterId: number) =>
  req<QuotaTreeChapterResponse>(`/api/pricing-kb/quota-tree/chapter/${chapterId}?dekid=${dekid}`)

export const fetchQuotaTreeItemDetail = (dekid: number, itemId: number) =>
  req<QuotaTreeItemDetail>(`/api/pricing-kb/quota-tree/items/${itemId}?dekid=${dekid}`)

export const fetchQuotaTreeItemDetailByCode = (dekid: number, code: string) =>
  req<QuotaTreeItemDetail>(`/api/pricing-kb/quota-tree/item-by-code/${encodeURIComponent(code)}?dekid=${dekid}`)

export function fetchQuotaInputPrompts(params: {
  library_id?: number | null
  q?: string
  page?: number
  page_size?: number
}) {
  const query = new URLSearchParams()
  if (params.library_id) query.set('library_id', String(params.library_id))
  if (params.q) query.set('q', params.q)
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  return req<PricingKbList<QuotaInputPromptItem>>(`/api/pricing-kb/quota-input-prompts?${query}`)
}

export function fetchQuotaConversionRules(params: {
  library_id?: number | null
  q?: string
  page?: number
  page_size?: number
}) {
  const query = new URLSearchParams()
  if (params.library_id) query.set('library_id', String(params.library_id))
  if (params.q) query.set('q', params.q)
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  return req<PricingKbList<QuotaConversionRuleListItem>>(`/api/pricing-kb/quota-conversion-rules?${query}`)
}

export function fetchPricingKbBoqItems(params: {
  q?: string
  code?: string
  library_id?: number | null
  page?: number
  page_size?: number
}) {
  const query = new URLSearchParams()
  if (params.q) query.set('q', params.q)
  if (params.code) query.set('code', params.code)
  if (params.library_id) query.set('library_id', String(params.library_id))
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  return req<PricingKbList<PricingKbBoqItem>>(`/api/pricing-kb/boq-items?${query}`)
}

export function fetchBoqProcesses(params: {
  q?: string
  code?: string
  appendix_code?: string | null
  library_id?: number | null
  page?: number
  page_size?: number
}) {
  const query = new URLSearchParams()
  if (params.q) query.set('q', params.q)
  if (params.code) query.set('code', params.code)
  if (params.appendix_code) query.set('appendix_code', params.appendix_code)
  if (params.library_id) query.set('library_id', String(params.library_id))
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  return req<BoqProcessList>(`/api/pricing-kb/boq-processes?${query}`)
}

export function fetchBoqFeatureDefaults(params: {
  q?: string
  code?: string
  item_name?: string
  feature_name?: string
  library_id?: number | null
  page?: number
  page_size?: number
}) {
  const query = new URLSearchParams()
  if (params.q) query.set('q', params.q)
  if (params.code) query.set('code', params.code)
  if (params.item_name) query.set('item_name', params.item_name)
  if (params.feature_name) query.set('feature_name', params.feature_name)
  if (params.library_id) query.set('library_id', String(params.library_id))
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  return req<BoqFeatureDefaultList>(`/api/pricing-kb/feature-defaults?${query}`)
}

export function fetchPricingKbQuotaItems(params: {
  q?: string
  code?: string
  library_id?: number | null
  page?: number
  page_size?: number
}) {
  const query = new URLSearchParams()
  if (params.q) query.set('q', params.q)
  if (params.code) query.set('code', params.code)
  if (params.library_id) query.set('library_id', String(params.library_id))
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  return req<PricingKbList<PricingKbQuotaItem>>(`/api/pricing-kb/quota-items?${query}`)
}

export const fetchPricingKbCandidates = (boqItemId: number, libraryId: number) =>
  req<PricingKbCandidateResponse>(
    `/api/pricing-kb/boq-items/${boqItemId}/candidates?qdkid=${libraryId}`,
  )

export function fetchPricingKbImportRuns(page = 1, pageSize = 20) {
  return req<PricingKbList<PricingKbImportRun>>(
    `/api/pricing-kb/import-runs?page=${page}&page_size=${pageSize}`,
  )
}

export function fetchPricingKbImportIssues(params: {
  run_id?: number | null
  issue_type?: string
  page?: number
  page_size?: number
}) {
  const query = new URLSearchParams()
  if (params.run_id) query.set('run_id', String(params.run_id))
  if (params.issue_type) query.set('issue_type', params.issue_type)
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  return req<PricingKbList<PricingKbImportIssue>>(`/api/pricing-kb/import-issues?${query}`)
}

const adminHeaders = (token: string, json = false): HeadersInit => ({
  'X-Admin-Token': token,
  ...(json ? { 'Content-Type': 'application/json' } : {}),
})

export async function uploadPricingKb(file: File, token: string) {
  const body = new FormData()
  body.append('file', file)
  return req<PricingKbUploadResult>('/api/pricing-kb/uploads', {
    method: 'POST', headers: adminHeaders(token), body,
  })
}

export const fetchPricingKbImportProfiles = () =>
  req<PricingKbImportProfile[]>('/api/pricing-kb/import-profiles')

export const savePricingKbImportProfile = (profile: {
  profile_id: string
  name: string
  description?: string
  selected_tables: string[]
  required_tables: string[]
}, token: string) => req<{ profile_id: string }>('/api/pricing-kb/import-profiles', {
  method: 'POST', headers: adminHeaders(token, true), body: JSON.stringify(profile),
})

export function createPricingKbImportJob(input: {
  upload_id: number
  profile_id: string | null
  selected_tables: string[]
  unknown_tables: Record<string, string>
}, token: string) {
  return req<{ id: number; status: string }>('/api/pricing-kb/import-jobs', {
    method: 'POST', headers: adminHeaders(token, true), body: JSON.stringify(input),
  })
}

export const fetchPricingKbImportJob = (id: number, token: string) =>
  req<PricingKbImportJob>(`/api/pricing-kb/import-jobs/${id}`, { headers: adminHeaders(token) })

export const cancelPricingKbImportJob = (id: number, token: string) =>
  req<{ id: number; status: string }>(`/api/pricing-kb/import-jobs/${id}/cancel`, {
    method: 'POST', headers: adminHeaders(token),
  })

export const fetchPricingKbVersions = () =>
  req<PricingKbVersion[]>('/api/pricing-kb/versions')

export const publishPricingKbVersion = (id: number, token: string) =>
  req<PricingKbVersion>(`/api/pricing-kb/versions/${id}/publish`, {
    method: 'POST', headers: adminHeaders(token, true), body: JSON.stringify({ published_by: 'web-admin' }),
  })

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
  const API = process.env.NEXT_PUBLIC_API_URL || ''
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

// ── 单条清单 BS2024 匹配（Phase 2 Step 1） ──────────────────────────────────────

export type BS2024MatchEvent =
  | { type: 'item_info'; item: BoqItem; system_prompt: string; system_prompt_len: number; user_message: string; chapter_name: string }
  | { type: 'reasoning_token'; token: string }
  | { type: 'code_check'; item_code: string; base_code: string; item_name: string; standard_names: string[]; found: boolean }
  | { type: 'judgment'; is_consistent: boolean; reasoning: string }
  | { type: 'done' }
  | { type: 'error'; error: string }

export async function streamBS2024MatchItem(
  boq_item_id: number,
  chapter_ids: number[],
  manual_project_id: number | null,
  onEvent: (e: BS2024MatchEvent) => void,
): Promise<void> {
  const API = process.env.NEXT_PUBLIC_API_URL || ''
  const res = await fetch(`${API}/api/bs2024-match/match-item-stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ boq_item_id, chapter_ids, manual_project_id }),
  })
  if (!res.ok) throw new Error(`API 请求失败: ${res.status} ${res.statusText}`)
  const reader = res.body?.getReader()
  if (!reader) throw new Error('无法读取响应流')
  const decoder = new TextDecoder()
  let buf = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const evt = JSON.parse(line.slice(6)) as BS2024MatchEvent
            onEvent(evt)
          } catch (e) {
            console.warn('SSE 事件解析错误:', line.slice(6), e)
          }
        }
      }
    }
  } catch (e) {
    throw new Error(`SSE 流读取错误: ${e instanceof Error ? e.message : String(e)}`)
  }
}
