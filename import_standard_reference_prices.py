"""Import Appendix A reference prices for SJG 171-2024."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from db.connection import get_connection
from importer.standard_reference_price_parser import (
    ReferencePriceRow,
    parse_markdown_table,
    validate_rows,
)


APPENDIX_CODE = "A"
EXPECTED_COUNT = 330
SCHEMA_PATH = Path(__file__).parent / "db" / "schema_standard_reference_prices.sql"

# Pages 268-273 already retain their corrected Markdown in bs2024_pages. These
# final four pages are kept here as reviewed source rows and are also written
# back to bs2024_pages.content_md for page-level traceability.
TAIL_ROWS = {
    274: """
213|模板嵌缝料|kg|8.00
214|651型橡胶止水带|m|40.00
215|遇水膨胀止水条 10×10|m|2.00
216|遇水膨胀止水条 30×20|m|6.00
217|润滑油|kg|3.36
218|防腐油|kg|31.50
219|松节油|kg|8.00
220|汽油|kg|10.64
221|柴油|kg|8.98
222|石油液化气|kg|10.00
223|电|kW·h|0.82
224|油漆溶剂油|kg|11.33
225|环氧树脂|kg|27.90
226|双飞粉|kg|1.80
227|石英粉|kg|1.57
228|苯磺酰氯|kg|1.85
229|硫酸|kg|0.51
230|丙酮|kg|8.80
231|甲苯|kg|6.20
232|乙二胺|kg|24.80
233|乙酸乙酯|kg|21.50
234|三异氰酸酯|kg|26.80
235|脱模剂|kg|8.40
236|过氯乙烯漆稀释剂|kg|17.00
237|酒精|kg|10.73
238|二甲苯|kg|18.75
239|聚氯乙烯稀释剂|kg|6.50
240|界面剂|kg|10.00
241|基层处理剂（防水专用）|kg|11.00
242|聚氨酯硬泡组合料|m³|18.00
243|氧气（工业用）|m³|19.58
244|乙炔气|m³|14.70
245|白乳胶|kg|10.00
246|108胶|kg|2.60
247|苯板泡沫胶|kg|17.00
248|XY401粘结剂|kg|18.20
""",
    275: """
249|氯丁橡胶粘剂|kg|17.50
250|高精砌块专用砌筑砂浆|kg|0.84
251|耐碱玻璃纤维网格布|m²|2.32
252|聚合物防水砂浆|kg|2.90
253|湿拌砌筑砂浆 M5|m³|440.90
254|湿拌砌筑砂浆 M7.5|m³|476.15
255|湿拌砌筑砂浆 M10|m³|481.07
256|湿拌抹灰砂浆 M15|m³|502.42
257|湿拌地面砂浆 M15|m³|511.03
258|干混砌筑砂浆 M7.5|t|453.13
259|聚合物水泥砂浆|kg|1.80
260|素水泥浆|m³|813.48
261|普通硅酸盐水泥 P.O 42.5R 散装|t|449.00
262|碎石 5～25|m³|196.00
263|毛石|m³|188.00
264|料石|m³|600.00
265|方整石|m³|454.78
266|环氧树脂砂浆|m³|16391.14
267|胶粉聚苯颗粒保温砂浆|m³|767.65
268|玻化微珠保温砂浆|m³|650.00
269|铁屑水泥砂浆|m³|1423.18
270|不发火沥青砂浆|m³|1970.00
271|抗裂砂浆|m³|2250.00
272|硫黄砂浆|m³|4927.73
273|水玻璃砂浆|m³|1580.00
274|重晶石砂浆|m³|2792.76
275|耐酸沥青砂浆|m³|1650.00
276|硫黄混凝土|m³|1750.80
277|水玻璃混凝土|m³|1274.31
278|防水混凝土 C25 P8|m³|557.47
279|泡沫混凝土 400kg/m³|m³|129.74
280|耐酸石油沥青混凝土（细粒式）|m³|1280.00
281|环氧酚醛胶泥|m³|18500.00
282|环氧树脂胶泥|m³|22250.00
283|聚氯乙烯胶泥|kg|3.80
284|酚醛树脂胶泥|m³|7120.00
""",
    276: """
285|耐酸沥青胶泥（砌筑用）|m³|2650.00
286|耐酸沥青胶泥（结合层用）|m³|2980.00
287|耐酸沥青胶泥（隔离层用）|m³|2320.00
288|水玻璃稀胶泥|m³|2450.00
289|石棉垫|kg|3.10
290|液压系统及电气控制系统|台班|300.45
291|脚手架提升系统|台班|32.95
292|脚手架电气控制系统|台班|30.96
293|汽车式起重机 起重量Gₙ(t) Gₙ=5|台班|651.50
294|机动翻斗车 装载质量M(t) M=1|台班|286.47
295|灰浆搅拌机 拌筒容量V(L) V=200|台班|201.79
296|挤压式灰浆输送泵 输送量Q(m³/h) Q=3|台班|236.24
297|混凝土输送泵 输送量Q(m³/h) Q=30|台班|932.59
298|混凝土输送泵车 输送量Q(m³/h) Q=60|台班|1888.81
299|滚筒式混凝土搅拌机（电动）出料容量V(L) V=400|台班|230.78
300|混凝土振动器 插入式|台班|11.85
301|混凝土振动器 平板式|台班|14.39
302|混凝土高压输送泵 大型|台班|3709.89
303|混凝土布料机|台班|67.42
304|钢筋调直机 直径D(mm) D=14|台班|41.92
305|钢筋切断机 直径D(mm) D=40|台班|44.11
306|钢筋弯曲机 直径D(mm) D=40|台班|25.31
307|预应力拉伸机 拉伸力F(kN) F=650|台班|58.60
308|预应力拉伸机 拉伸力F(kN) F=900|台班|73.32
309|木工圆锯机 直径D(mm) D=500|台班|30.14
310|木工圆锯机 直径D(mm) D=600|台班|41.16
311|木工压刨床 刨削宽度B(mm)/面数 B=600/单面|台班|44.91
312|剪板机 厚度T(mm)/宽度B(mm) T=20/B=2500|台班|457.10
313|剪板机 厚度T(mm)/宽度B(mm) T=40/B=3100|台班|1144.37
314|冷挤压机 直径D(mm) D=45|台班|76.71
315|锥型螺纹车丝机|台班|55.80
316|电动多级离心清水泵 扬程H(m)/出口直径D(mm) H>120/D=100|台班|431.91
317|电动多级离心清水泵 扬程H(m)/出口直径D(mm) H>180/D=150|台班|1174.66
318|高压油泵 压力P(MPa) P=80|台班|382.70
319|交流弧焊机 容量E(kV·A) E=32|台班|178.89
320|半自动切割机 厚度T(mm) T=100|台班|183.79
""",
    277: """
321|电渣焊机 电流I(A) I=1000|台班|286.63
322|点焊机长臂 容量E(kV·A) E=75|台班|241.49
323|交流电焊机 容量E(kV·A) E=30|台班|172.10
324|交流电焊机 容量E(kV·A) E=32|台班|178.89
325|交流电焊机 容量E(kV·A) E=40|台班|213.69
326|直流电焊机 功率P(kW) P=32|台班|183.45
327|电动空气压缩机 排气量Q(m³/min) Q=0.6|台班|209.97
328|电动空气压缩机 排气量Q(m³/min) Q=0.3|台班|202.44
329|轴流通风机 功率P(kW) P=7.5|台班|45.55
330|立式油压千斤顶 起重量Gₙ(t) Gₙ=200|台班|11.79
""",
}


def tail_markdown(page_no: int, raw_rows: str) -> str:
    lines = [
        "# 附录 A 材料、机械台班参考价格表",
        "",
        f"## 续表 A（PDF 第{page_no}页）",
        "",
        "| 序号 | 名称 | 单位 | 价格（元） |",
        "|---:|---|:---:|---:|",
    ]
    for line in raw_rows.strip().splitlines():
        number, name, unit, price = line.split("|")
        lines.append(f"| {number} | {name} | {unit} | {price} |")
    return "\n".join(lines) + "\n"


def resolve_document(cur, document_id: int | None) -> tuple[int, str]:
    if document_id is not None:
        cur.execute("SELECT id, name FROM bs2024_documents WHERE id=%s", (document_id,))
    else:
        cur.execute(
            """
            SELECT id, name
            FROM bs2024_documents
            WHERE standard_code='SJG 171-2024'
            ORDER BY imported_at DESC
            LIMIT 1
            """
        )
    row = cur.fetchone()
    if not row:
        raise ValueError("SJG 171-2024 document was not found")
    return row[0], row[1]


def ensure_tail_pages(cur, document_id: int) -> None:
    for page_no, raw_rows in TAIL_ROWS.items():
        markdown = tail_markdown(page_no, raw_rows)
        cur.execute(
            """
            INSERT INTO bs2024_pages
                (document_id, page_no, page_type, section_type, section_code,
                 title, content_md, confidence)
            VALUES (%s, %s, 'other', 'other', %s, %s, %s, 1.0000)
            ON CONFLICT (document_id, page_no) DO UPDATE SET
                section_code=EXCLUDED.section_code,
                title=EXCLUDED.title,
                content_md=EXCLUDED.content_md,
                confidence=COALESCE(bs2024_pages.confidence, EXCLUDED.confidence)
            """,
            (
                document_id,
                page_no,
                APPENDIX_CODE,
                "附录A 材料、机械台班参考价格表",
                markdown,
            ),
        )


def collect_rows(cur, document_id: int) -> tuple[list[ReferencePriceRow], dict[int, int]]:
    cur.execute(
        """
        SELECT id, page_no, content_md, confidence
        FROM bs2024_pages
        WHERE document_id=%s AND page_no BETWEEN 268 AND 277
        ORDER BY page_no
        """,
        (document_id,),
    )
    rows: list[ReferencePriceRow] = []
    page_ids: dict[int, int] = {}
    for page_id, page_no, markdown, confidence in cur.fetchall():
        page_ids[page_no] = page_id
        rows.extend(parse_markdown_table(markdown or "", page_no, confidence))
    return validate_rows(rows, EXPECTED_COUNT), page_ids


def import_prices(document_id: int | None = None) -> dict[str, object]:
    load_dotenv(".env")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
            resolved_id, document_name = resolve_document(cur, document_id)
            ensure_tail_pages(cur, resolved_id)
            rows, page_ids = collect_rows(cur, resolved_id)

            for row in rows:
                resource_type = "材料" if row.sequence_no <= 289 else "机械"
                raw_json = json.dumps(
                    {
                        "raw_text": row.raw_text,
                        "parser": "appendix_markdown_table_v1",
                    },
                    ensure_ascii=False,
                )
                cur.execute(
                    """
                    INSERT INTO standard_reference_prices
                        (document_id, appendix_code, sequence_no, resource_type,
                         name, unit, price, source_page_no, source_page_id,
                         confidence, raw_json)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                    ON CONFLICT (document_id, appendix_code, sequence_no) DO UPDATE SET
                        resource_type=EXCLUDED.resource_type,
                        name=EXCLUDED.name,
                        unit=EXCLUDED.unit,
                        price=EXCLUDED.price,
                        source_page_no=EXCLUDED.source_page_no,
                        source_page_id=EXCLUDED.source_page_id,
                        confidence=EXCLUDED.confidence,
                        raw_json=EXCLUDED.raw_json,
                        updated_at=NOW()
                    """,
                    (
                        resolved_id,
                        APPENDIX_CODE,
                        row.sequence_no,
                        resource_type,
                        row.name,
                        row.unit,
                        row.price,
                        row.source_page_no,
                        page_ids[row.source_page_no],
                        row.confidence,
                        raw_json,
                    ),
                )

            cur.execute(
                """
                DELETE FROM standard_reference_prices
                WHERE document_id=%s AND appendix_code=%s
                  AND sequence_no > %s
                """,
                (resolved_id, APPENDIX_CODE, EXPECTED_COUNT),
            )
            cur.execute(
                """
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE resource_type='材料'),
                       COUNT(*) FILTER (WHERE resource_type='机械'),
                       MIN(sequence_no), MAX(sequence_no)
                FROM standard_reference_prices
                WHERE document_id=%s AND appendix_code=%s
                """,
                (resolved_id, APPENDIX_CODE),
            )
            count, materials, machines, minimum, maximum = cur.fetchone()
        conn.commit()
        return {
            "document_id": resolved_id,
            "document_name": document_name,
            "appendix_code": APPENDIX_CODE,
            "count": count,
            "materials": materials,
            "machines": machines,
            "sequence_range": [minimum, maximum],
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-id", type=int)
    args = parser.parse_args()
    print(json.dumps(import_prices(args.document_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
