from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date


class Period(BaseModel):
    id: int
    year: int
    month: int
    version: int
    source_file: Optional[str]
    imported_at: datetime
    item_count: Optional[int] = None


class Category(BaseModel):
    id: int
    sheet_index: int
    sheet_name: str
    category_group: str


class PriceItem(BaseModel):
    id: int
    sequence_no: Optional[int]
    material_code: Optional[str]
    material_name: str
    specification: Optional[str]
    unit: Optional[str]
    price_yuan: Optional[float]
    coefficient: Optional[float]
    calculation_formula: Optional[str]
    remarks: Optional[str]


class PriceItemList(BaseModel):
    total: int
    items: list[PriceItem]


class TrendPoint(BaseModel):
    year: int
    month: int
    version: int
    price_yuan: Optional[float]
    label: str


class ImportResult(BaseModel):
    period_id: int
    year: int
    month: int
    version: int
    categories: int
    items: int


# ── 消耗量标准 ──────────────────────────────────────────

class QuotaStandard(BaseModel):
    id: int
    standard_code: str
    name: str
    region: Optional[str] = None
    base_date: Optional[date]
    source_file: Optional[str]
    imported_at: datetime
    item_count: Optional[int] = None


class QuotaChapter(BaseModel):
    id: int
    code: Optional[str]
    name: str
    level: int
    parent_id: Optional[int]
    sort_order: int


class QuotaResource(BaseModel):
    id: int
    resource_type: str
    resource_name: str
    unit: Optional[str]
    quantity: Optional[float]
    ref_price: Optional[float]


class QuotaItem(BaseModel):
    id: int
    chapter_id: Optional[int]
    chapter_name: Optional[str]
    item_code: str
    item_name: str
    variant_desc: Optional[str]
    unit: Optional[str]
    work_content: Optional[str]
    total_unit_price: Optional[float]
    unit_price: Optional[float]
    labor_cost: Optional[float]
    material_cost: Optional[float]
    machine_cost: Optional[float]
    management_fee: Optional[float]
    profit: Optional[float]
    safety_fee: Optional[float]
    statutory_fee: Optional[float]
    tax: Optional[float]
    source_row: Optional[int]
    resources: list[QuotaResource] = []


class QuotaItemList(BaseModel):
    total: int
    items: list[QuotaItem]


# ── 国标清单（工程量计算标准）─────────────────────────────

class MeasureStandard(BaseModel):
    id: int
    name: str
    source_file: Optional[str]
    imported_at: datetime
    item_count: Optional[int] = None


class MeasureSection(BaseModel):
    id: int
    code: Optional[str]
    name: str
    level: int
    parent_id: Optional[int]
    sort_order: int
    num_code: Optional[str] = None
    description: Optional[str] = None


class MeasureItem(BaseModel):
    id: int
    section_id: Optional[int]
    section_name: Optional[str]
    item_code: str
    item_name: str
    item_features: Optional[str]
    unit: Optional[str]
    calc_rule: Optional[str]
    work_content: Optional[str]


class MeasureItemList(BaseModel):
    total: int
    items: list[MeasureItem]


# ── 工程量清单（分部分项）────────────────────────────────

class BoqProject(BaseModel):
    id: int
    project_name: str
    bid_section: Optional[str]
    source_file: Optional[str]
    tag: Optional[str]
    imported_at: datetime
    item_count: Optional[int] = None


class BoqSection(BaseModel):
    id: int
    seq: int
    section_name: str


class BoqItem(BaseModel):
    id: int
    section_id: Optional[int]
    section_name: Optional[str]
    item_seq: int
    item_code: str
    item_name: str
    item_description: Optional[str]
    unit: Optional[str]
    quantity: Optional[float]
    unit_price: Optional[float]
    total_price: Optional[float]
    provisional_price: Optional[float]


class BoqItemList(BaseModel):
    total: int
    items: list[BoqItem]


# ── BOQ 套定额匹配 ──────────────────────────────────────

class BoqMatchResult(BaseModel):
    # 匹配关系
    id: int
    boq_item_id: int
    quota_item_id: int
    qty_factor: float
    ai_reasoning: Optional[str]
    reasoning_chain: Optional[str] = None   # 完整思维链
    confidence: Optional[str]
    status: str  # ai / confirmed / rejected
    confirmed_at: Optional[datetime] = None

    # 定额基本信息
    quota_item_code: str
    quota_item_name: str
    quota_variant_desc: Optional[str]
    quota_unit: Optional[str]
    quota_work_content: Optional[str] = None

    # 定额价格构成
    quota_total_unit_price: Optional[float] = None
    quota_unit_price: Optional[float] = None
    quota_labor_cost: Optional[float] = None
    quota_material_cost: Optional[float] = None
    quota_machine_cost: Optional[float] = None
    quota_management_fee: Optional[float] = None
    quota_profit: Optional[float] = None
    quota_safety_fee: Optional[float] = None
    quota_statutory_fee: Optional[float] = None
    quota_tax: Optional[float] = None

    # 工序和换算说明（新增）
    work_procedure: Optional[str] = None
    factor_explanation: Optional[str] = None

    # 工料机消耗量
    quota_resources: list[QuotaResource] = []


# ── 人工套定额工程 ──────────────────────────────────────

class ManualBoqProject(BaseModel):
    id: int
    project_name: str
    bid_section: Optional[str]
    source_file: Optional[str]
    tag: Optional[str]
    imported_at: datetime
    item_count: Optional[int] = None


class ManualBoqSection(BaseModel):
    id: int
    seq: Optional[int]
    section_name: str


class ManualBoqQuota(BaseModel):
    id: int
    boq_item_id: int
    quota_code: Optional[str]
    quota_name: Optional[str]
    quota_unit: Optional[str]
    quantity: Optional[float]
    unit_price: Optional[float]
    total_price: Optional[float]
    qty_factor: Optional[float]
    quota_item_id: Optional[int]
    # 关联定额库价格（可选）
    qi_total_unit_price: Optional[float] = None
    qi_unit_price: Optional[float] = None
    qi_labor_cost: Optional[float] = None
    qi_material_cost: Optional[float] = None
    qi_machine_cost: Optional[float] = None
    qi_management_fee: Optional[float] = None
    qi_profit: Optional[float] = None
    qi_safety_fee: Optional[float] = None
    qi_statutory_fee: Optional[float] = None
    qi_tax: Optional[float] = None
    qi_work_content: Optional[str] = None
    qi_variant_desc: Optional[str] = None
    qi_unit: Optional[str] = None


class ManualBoqItem(BaseModel):
    id: int
    section_id: Optional[int]
    section_name: Optional[str]
    item_seq: Optional[int]
    item_code: Optional[str]
    item_name: Optional[str]
    item_description: Optional[str]
    unit: Optional[str]
    quantity: Optional[float]
    unit_price: Optional[float]
    total_price: Optional[float]
    quotas: list[ManualBoqQuota] = []


class ManualBoqProjectDetail(BaseModel):
    project: ManualBoqProject
    sections: list[ManualBoqSection]
    items: list[ManualBoqItem]


class BoqSummaryItem(BaseModel):
    boq_item_id: int
    item_seq: int
    item_code: str
    item_name: str
    unit: Optional[str]
    quantity: Optional[float]
    unit_price: Optional[float]   # 工料机综合单价（按工程量折算）
    total_price: Optional[float]
    match_count: int              # 已匹配定额条数
    match_status: str             # all_confirmed / partial / none


class BoqResourceSummary(BaseModel):
    resource_type: str
    resource_name: str
    unit: Optional[str]
    total_quantity: float


class BoqMatchRun(BaseModel):
    id: int
    project_id: int
    standard_id: int
    standard_code: Optional[str]
    run_name: Optional[str] = None
    standard_ids: Optional[str] = None   # JSON 数组字符串，如 "[1,2]"
    status: str  # running / done / error
    total_items: int
    matched_items: int
    created_at: datetime
    finished_at: Optional[datetime] = None


# ── 定额比较 ──────────────────────────────────────────

class CompareRunInfo(BaseModel):
    run_id: int
    run_name: Optional[str]
    standard_code: Optional[str]
    project_id: int
    project_name: str


class CompareQuota(BaseModel):
    quota_item_id: Optional[int]    # 人工套定额的公式子目可为 NULL
    quota_item_code: str
    quota_item_name: str
    qty_factor: float
    confidence: Optional[str]
    work_procedure: Optional[str]


class CompareBoqItem(BaseModel):
    item_code: str
    item_name: str
    unit: Optional[str]
    quantity: Optional[float]
    item_description: Optional[str] = None
    quotas_a: list[CompareQuota]
    quotas_b: list[CompareQuota]
    consistent: bool   # 两侧定额编码集合相同（均非空）


class CompareSummary(BaseModel):
    total: int
    consistent: int
    different: int
    only_a: int
    only_b: int
    both_empty: int


class CompareResult(BaseModel):
    run_a: CompareRunInfo
    run_b: CompareRunInfo
    items: list[CompareBoqItem]
    summary: CompareSummary

