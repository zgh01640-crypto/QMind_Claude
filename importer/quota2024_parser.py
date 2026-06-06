"""
OCR 和数据提取逻辑 - 消耗量标准 2024

使用 Claude Vision 进行 OCR 和结构化解析。
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Literal
import json
import base64
import anthropic


# ============ 数据结构 ============

@dataclass
class PageMap:
    """页面边界检测输出"""
    page_no: int
    chapter_no: Optional[int]
    chapter_name: Optional[str]
    section_type: Literal['intro', 'rules', 'items']  # 说明 / 工程量计算规则 / 子目构成表
    section_code: Optional[str]  # 如 "2.1", "2.2", "2.3"
    title: Optional[str]  # 如 "说明", "工程量计算规则", "子目构成表"


@dataclass
class SubItem:
    """子目/变体列"""
    subitem_code: str           # "010002-1"
    subitem_name: Optional[str]  # "实心砖基础"
    variant_desc: Optional[str]  # "干混砌筑砂浆"
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


@dataclass
class ResourceRow:
    """工料机消耗量行"""
    resource_type: str          # "人工" | "材料" | "机械"
    resource_name: str
    unit: Optional[str]
    # 按子目编码映射消耗量
    quantities: dict[str, Optional[float]] = field(default_factory=dict)
    ref_price: Optional[float] = None  # 参考价格，全行共用


@dataclass
class ItemTable:
    """定额项目表（一个项目含一个或多个子目）"""
    item_no: int
    item_name: str              # "泵送现浇混凝土"
    work_content: Optional[str]  # 工作内容
    unit: Optional[str]         # "10m³"
    subitems: list[SubItem] = field(default_factory=list)
    resources: list[ResourceRow] = field(default_factory=list)


@dataclass
class GroupBlock:
    """分组块（对应 X.3.Y 分组下的所有项目）"""
    group_code: Optional[str]     # "2.3.1"
    group_name: str               # "现浇预拌混凝土"
    items: list[ItemTable] = field(default_factory=list)


# ============ Claude API 调用 ============

class Quota2024Parser:
    """使用 Claude 的 OCR 解析器"""

    def __init__(self):
        self.client = anthropic.Anthropic()
        self.model = "claude-haiku-4-5"

    def img_to_base64(self, img_bytes: bytes) -> str:
        """图片字节转 base64"""
        return base64.standard_b64encode(img_bytes).decode('utf-8')

    def detect_boundaries(self, img_bytes: bytes, page_no: int) -> Optional[PageMap]:
        """
        检测页面边界和类型 (模式 C)

        Returns:
            PageMap 如果检测成功，否则 None
        """
        b64 = self.img_to_base64(img_bytes)

        prompt = """请分析这个 PDF 页面，输出 JSON 格式。

检测以下内容：
1. 如果页面顶部有 "第 X 章" 标题，提取章号和章名
2. 检测节类型：
   - "说明" = section_type: "intro"
   - "工程量计算规则" = section_type: "rules"
   - "子目构成表" = section_type: "items"
3. 提取节代码（如 "2.1", "2.2", "2.3"）和标题

返回的 JSON 格式（只返回 JSON，无其他文字）：
{
  "chapter_no": 数字或null,
  "chapter_name": "章名" 或 null,
  "section_type": "intro" | "rules" | "items" | null,
  "section_code": "X.Y" 或 null,
  "title": "节标题" 或 null,
  "confidence": "high" | "medium" | "low"
}

如果无法确定某个字段，设为 null。"""

        try:
            msg = self.client.messages.create(
                model=self.model,
                max_tokens=512,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64
                            }
                        },
                        {"type": "text", "text": prompt}
                    ]
                }]
            )

            text = msg.content[0].text.strip()
            # 提取 JSON
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                # 尝试从文本中提取 JSON
                start = text.find('{')
                end = text.rfind('}') + 1
                if start >= 0 and end > start:
                    data = json.loads(text[start:end])
                else:
                    return None

            result = PageMap(
                page_no=page_no,
                chapter_no=data.get('chapter_no'),
                chapter_name=data.get('chapter_name'),
                section_type=data.get('section_type'),
                section_code=data.get('section_code'),
                title=data.get('title')
            )
            return result

        except Exception as e:
            print(f"[ERROR] 边界检测页 {page_no} 失败: {e}")
            return None

    def extract_text(self, img_bytes: bytes) -> Optional[str]:
        """
        提取说明/规则文本为 Markdown (模式 B)

        Returns:
            Markdown 格式的文本，或 None 如果提取失败
        """
        b64 = self.img_to_base64(img_bytes)

        prompt = """请从这个页面提取所有文字内容并转为 Markdown 格式。

要求：
1. 保留原始的编号段落结构（如 X.1.1, X.1.2 等）
2. 将任何表格转为 Markdown 管道表格格式（使用 | 符号）
3. 保留加粗、标题等格式
4. 只返回纯 Markdown 文本，不要解释或总结
5. 如果表格有合并单元格，使用合理的 Markdown 表示

示例输出（仅作示意）：
### 1.1 说明

1.1.1 **第一条说明**
这是说明文本...

1.1.2 **第二条说明**
更多文本...

| 列1 | 列2 | 列3 |
|-----|-----|-----|
| 值1 | 值2 | 值3 |"""

        try:
            msg = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64
                            }
                        },
                        {"type": "text", "text": prompt}
                    ]
                }]
            )

            return msg.content[0].text.strip()

        except Exception as e:
            print(f"[ERROR] 文本提取失败: {e}")
            return None

    def extract_table(self, img_bytes: bytes, retry_count: int = 0) -> Optional[list[GroupBlock]]:
        """
        提取子目构成表为结构化 JSON (模式 A)

        Args:
            img_bytes: 页面图片字节
            retry_count: 当前重试次数

        Returns:
            list[GroupBlock]，或 None 如果提取失败
        """
        if retry_count > 2:
            print("[ERROR] 表格提取达到最大重试次数")
            return None

        b64 = self.img_to_base64(img_bytes)

        prompt = """请从这个页面的子目构成表提取所有数据并返回 JSON 格式。

表格结构说明：
- 表格分为两个主要区域：上方价格行，下方工料机消耗量行
- 价格行包含：
  * "子目编号" 行：各列的编码（如 010002-1, 010002-2 等）
  * "子目名称" 行：统一的项目名称
  * 变体描述行：每列的变体说明（如 "干混砌筑砂浆", "湿拌砌筑砂浆"）
  * "2023年8月全费用参考综合单价" 行 → total_unit_price
  * "2023年8月参考综合单价" 行 → unit_price
  * 5个费用分项行（人工费、材料费、机械费、管理费、利润）
  * 3个特殊费用行（安全措施费、规费、税金）
- 工料机行分为三组：人工、材料、机械
  * 每行有：工料机名称、单位、各子目的消耗量、最右列参考价格

规则：
- 单元格中的 "—" 表示为 null
- 数字中的空格要去除（如 "10 946.90" → 10946.90）
- 上方 "单位：10m³" 形式的行指定计量单位

返回格式（只返回有效的 JSON，不要 markdown 代码块）：
[
  {
    "group_code": "2.3.1" 或 null,
    "group_name": "现浇预拌混凝土",
    "items": [
      {
        "item_no": 1,
        "item_name": "泵送现浇混凝土",
        "work_content": "工作内容文本",
        "unit": "10m³",
        "subitems": [
          {
            "subitem_code": "010002-1",
            "subitem_name": "实心砖基础",
            "variant_desc": "干混砌筑砂浆",
            "total_unit_price": 123.45,
            "unit_price": 100.0,
            "labor_cost": 20.0,
            "material_cost": 50.0,
            "machine_cost": 10.0,
            "management_fee": 10.0,
            "profit": 5.0,
            "safety_fee": 2.0,
            "statutory_fee": 3.0,
            "tax": 2.45
          }
        ],
        "resources": [
          {
            "resource_type": "人工",
            "resource_name": "普通混凝土实心砖 240×115×53 (10.0MPa)",
            "unit": "千块",
            "quantities": {
              "010002-1": 50.5,
              "010002-2": 55.0
            },
            "ref_price": 1234.56
          }
        ]
      }
    ]
  }
]

如果无法完整识别表格的某部分，仍然返回尽可能多的数据。""" + (
    "\n\n[重试提示] 上次解析失败，请再次仔细检查数字和单元格内容。"
    if retry_count > 0 else ""
)

        try:
            msg = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64
                            }
                        },
                        {"type": "text", "text": prompt}
                    ]
                }]
            )

            text = msg.content[0].text.strip()

            # 尝试解析 JSON
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                # 尝试从文本中提取 JSON 数组
                start = text.find('[')
                end = text.rfind(']') + 1
                if start >= 0 and end > start:
                    try:
                        data = json.loads(text[start:end])
                    except json.JSONDecodeError:
                        print(f"[WARN] JSON 解析失败 (重试 {retry_count})")
                        if retry_count < 2:
                            return self.extract_table(img_bytes, retry_count + 1)
                        return None
                else:
                    return None

            # 转换为 GroupBlock 对象
            groups = []
            for group_data in data:
                items = []
                for item_data in group_data.get('items', []):
                    subitems = []
                    for sub_data in item_data.get('subitems', []):
                        subitems.append(SubItem(**sub_data))

                    resources = []
                    for res_data in item_data.get('resources', []):
                        resources.append(ResourceRow(**res_data))

                    items.append(ItemTable(
                        item_no=item_data['item_no'],
                        item_name=item_data['item_name'],
                        work_content=item_data.get('work_content'),
                        unit=item_data.get('unit'),
                        subitems=subitems,
                        resources=resources
                    ))

                groups.append(GroupBlock(
                    group_code=group_data.get('group_code'),
                    group_name=group_data['group_name'],
                    items=items
                ))

            return groups

        except Exception as e:
            print(f"[ERROR] 表格提取异常: {e}")
            if retry_count < 2:
                return self.extract_table(img_bytes, retry_count + 1)
            return None
