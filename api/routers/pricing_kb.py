"""Read-only API for the smart pricing knowledge base."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from db.connection import get_connection


router = APIRouter()

RESOURCE_TYPES = {
    1: "人工",
    2: "材料",
    3: "机械",
    4: "特殊材料",
    6: "设备",
    22: "使用费",
}


def page_bounds(page: int, page_size: int) -> tuple[int, int]:
    return page_size, (page - 1) * page_size


@router.get("/pricing-kb/boq-tree/top-categories")
def list_boq_top_categories(qdkid: int = 1020025):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.qdkid, c.pid, c.zjmc, c.zjsm,
                       (SELECT COUNT(*) FROM tqdk_tzjmc child WHERE child.qdkid=c.qdkid AND child.pid=c.id) AS child_count,
                       (SELECT COUNT(*) FROM tqdk_tqdzm item WHERE item.qdkid=c.qdkid AND item.zjh=c.id) AS item_count
                FROM tqdk_tzjmc c
                WHERE c.qdkid=%s AND COALESCE(c.pid, 0)=0
                ORDER BY c.zjmc
                """,
                (qdkid,),
            )
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "qdkid": r[1],
                "pid": r[2],
                "zjmc": r[3],
                "zjsm": r[4],
                "child_count": r[5],
                "item_count": r[6],
                "enabled": True,
            }
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/pricing-kb/boq-tree/chapter/{chapter_id}")
def get_boq_chapter_children(chapter_id: int, qdkid: int = 1020025):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, qdkid, pid, zjmc, zjsm
                FROM tqdk_tzjmc
                WHERE qdkid=%s AND id=%s
                """,
                (qdkid, chapter_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="chapter not found")
            chapter = {
                "id": row[0],
                "qdkid": row[1],
                "pid": row[2],
                "zjmc": row[3],
                "zjsm": row[4],
            }

            cur.execute(
                """
                SELECT c.id, c.qdkid, c.pid, c.zjmc, c.zjsm,
                       (SELECT COUNT(*) FROM tqdk_tzjmc child WHERE child.qdkid=c.qdkid AND child.pid=c.id) AS child_count,
                       (SELECT COUNT(*) FROM tqdk_tqdzm item WHERE item.qdkid=c.qdkid AND item.zjh=c.id) AS item_count
                FROM tqdk_tzjmc c
                WHERE c.qdkid=%s AND c.pid=%s
                ORDER BY c.zjmc
                """,
                (qdkid, chapter_id),
            )
            child_rows = cur.fetchall()

            cur.execute(
                """
                SELECT i.id, i.qdkid, i.zmbh, i.zmmc, i.dw, i.zjh, c.zjmc AS chapter_name,
                       COUNT(cand.source_rowid) AS candidate_count
                FROM tqdk_tqdzm i
                LEFT JOIN tqdk_tzjmc c ON c.qdkid=i.qdkid AND c.id=i.zjh
                LEFT JOIN tqdk_tqdzy cand ON cand.qdkid=i.qdkid AND cand.qdzmid=i.id
                WHERE i.qdkid=%s AND i.zjh=%s
                GROUP BY i.id, i.qdkid, i.zmbh, i.zmmc, i.dw, i.zjh, c.zjmc
                ORDER BY i.zmbh, i.id
                """,
                (qdkid, chapter_id),
            )
            item_rows = cur.fetchall()
        return {
            "chapter": chapter,
            "children": [
                {
                    "id": r[0],
                    "qdkid": r[1],
                    "pid": r[2],
                    "zjmc": r[3],
                    "zjsm": r[4],
                    "child_count": r[5],
                    "item_count": r[6],
                }
                for r in child_rows
            ],
            "items": [
                {
                    "id": r[0],
                    "qdkid": r[1],
                    "zmbh": r[2],
                    "zmmc": r[3],
                    "dw": r[4],
                    "zjh": r[5],
                    "chapter_name": r[6],
                    "candidate_count": r[7],
                }
                for r in item_rows
            ],
        }
    finally:
        conn.close()


@router.get("/pricing-kb/quota-tree/top-libraries")
def list_quota_tree_top_libraries():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.dekid, c.id, c.pid, c.zjmc, c.zjsm,
                       (SELECT COUNT(*) FROM tdek_tzjmc child WHERE child.dekid=c.dekid AND child.pid=c.id) AS child_count,
                       (SELECT COUNT(*) FROM tdek_tdezm item WHERE item.dekid=c.dekid) AS quota_count
                FROM tdek_tzjmc c
                WHERE COALESCE(c.pid, 0)=0
                ORDER BY c.dekid, c.id
                """
            )
            rows = cur.fetchall()
        return [
            {
                "dekid": r[0],
                "id": r[1],
                "pid": r[2],
                "zjmc": r[3],
                "zjsm": r[4],
                "child_count": r[5],
                "item_count": 0,
                "quota_count": r[6],
            }
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/pricing-kb/quota-tree/chapter/{chapter_id}")
def get_quota_chapter_children(chapter_id: int, dekid: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, dekid, pid, zjmc, zjsm
                FROM tdek_tzjmc
                WHERE dekid=%s AND id=%s
                """,
                (dekid, chapter_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="quota chapter not found")
            chapter = {
                "id": row[0],
                "dekid": row[1],
                "pid": row[2],
                "zjmc": row[3],
                "zjsm": row[4],
            }

            cur.execute(
                """
                SELECT c.id, c.dekid, c.pid, c.zjmc, c.zjsm,
                       (SELECT COUNT(*) FROM tdek_tzjmc child WHERE child.dekid=c.dekid AND child.pid=c.id) AS child_count,
                       (SELECT COUNT(*) FROM tdek_tdezm item WHERE item.dekid=c.dekid AND item.zjh=c.id) AS item_count
                FROM tdek_tzjmc c
                WHERE c.dekid=%s AND c.pid=%s
                ORDER BY c.zjmc, c.id
                """,
                (dekid, chapter_id),
            )
            child_rows = cur.fetchall()

            cur.execute(
                """
                SELECT i.id, i.dekid, i.zmbh, i.zmmc, i.dw, i.gznr, i.zjh, c.zjmc AS chapter_name,
                       (SELECT COUNT(*) FROM tdek_tzmgc r WHERE r.dekid=i.dekid AND r.dezmid=i.id) AS resource_count,
                       (SELECT COUNT(*) FROM tdek_tznhs r WHERE r.dekid=i.dekid AND r.dezmid=i.id) AS conversion_rule_count,
                       (SELECT COUNT(*) FROM tdek_tzhhs r WHERE r.dekid=i.dekid AND r.dezmid=i.id) AS input_prompt_count,
                       COALESCE(link.link_status, 'unlinked') AS link_status,
                       link.target_table, link.target_item_id
                FROM tdek_tdezm i
                LEFT JOIN tdek_tzjmc c ON c.dekid=i.dekid AND c.id=i.zjh
                LEFT JOIN pricing_kb_original_target_links link
                  ON link.dekid=i.dekid AND link.dezmid=i.id
                WHERE i.dekid=%s AND i.zjh=%s
                ORDER BY i.zmbh NULLS LAST, i.id
                """,
                (dekid, chapter_id),
            )
            item_rows = cur.fetchall()
        return {
            "chapter": chapter,
            "children": [
                {
                    "id": r[0],
                    "dekid": r[1],
                    "pid": r[2],
                    "zjmc": r[3],
                    "zjsm": r[4],
                    "child_count": r[5],
                    "item_count": r[6],
                }
                for r in child_rows
            ],
            "items": [
                {
                    "id": r[0],
                    "dekid": r[1],
                    "zmbh": r[2],
                    "zmmc": r[3],
                    "dw": r[4],
                    "gznr": r[5],
                    "zjh": r[6],
                    "chapter_name": r[7],
                    "resource_count": r[8],
                    "conversion_rule_count": r[9],
                    "input_prompt_count": r[10],
                    "link_status": r[11],
                    "target_table": r[12],
                    "target_item_id": r[13],
                }
                for r in item_rows
            ],
        }
    finally:
        conn.close()


@router.get("/pricing-kb/quota-tree/items/{quota_item_id}")
def get_quota_tree_item_detail(quota_item_id: int, dekid: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT i.id, i.dekid, i.zmbh, i.zmmc, i.dw, i.gznr, i.zjh, c.zjmc AS chapter_name,
                       COALESCE(link.link_status, 'unlinked') AS link_status,
                       link.target_table, link.target_item_id, link.review_message
                FROM tdek_tdezm i
                LEFT JOIN tdek_tzjmc c ON c.dekid=i.dekid AND c.id=i.zjh
                LEFT JOIN pricing_kb_original_target_links link
                  ON link.dekid=i.dekid AND link.dezmid=i.id
                WHERE i.dekid=%s AND i.id=%s
                """,
                (dekid, quota_item_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="quota item not found")
            item = {
                "id": row[0],
                "dekid": row[1],
                "zmbh": row[2],
                "zmmc": row[3],
                "dw": row[4],
                "gznr": row[5],
                "zjh": row[6],
                "chapter_name": row[7],
                "link_status": row[8],
                "target_table": row[9],
                "target_item_id": row[10],
                "review_message": row[11],
            }

            cur.execute(
                """
                SELECT lx, zmbh, zmmc, dw, gcl
                FROM tdek_tzmgc
                WHERE dekid=%s AND dezmid=%s
                ORDER BY source_rowid
                """,
                (dekid, quota_item_id),
            )
            resources = [
                {
                    "resource_type": RESOURCE_TYPES.get(r[0], str(r[0]) if r[0] is not None else None),
                    "resource_code": r[1],
                    "resource_name": r[2],
                    "unit": r[3],
                    "quantity": float(r[4]) if r[4] is not None else None,
                }
                for r in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT tsxx, hssm, groupno
                FROM tdek_tznhs
                WHERE dekid=%s AND dezmid=%s
                ORDER BY groupno NULLS LAST, source_rowid
                """,
                (dekid, quota_item_id),
            )
            conversion_rules = [
                {"prompt": r[0], "description": r[1], "group_no": r[2]}
                for r in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT tsxx
                FROM tdek_tzhhs
                WHERE dekid=%s AND dezmid=%s
                ORDER BY source_rowid
                """,
                (dekid, quota_item_id),
            )
            input_prompts = [r[0] for r in cur.fetchall()]
        return {
            "item": item,
            "resources": resources,
            "conversion_rules": conversion_rules,
            "input_prompts": input_prompts,
        }
    finally:
        conn.close()


def build_filters(
    alias: str,
    name_col: str,
    code_col: str,
    library_col: str,
    q: str | None,
    code: str | None,
    library_id: int | None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    q = q if isinstance(q, str) else None
    code = code if isinstance(code, str) else None
    if q:
        clauses.append(f"({alias}.{name_col} ILIKE %s OR {alias}.{code_col} ILIKE %s)")
        like = f"%{q.strip()}%"
        params.extend([like, like])
    if code:
        clauses.append(f"{alias}.{code_col} ILIKE %s")
        params.append(f"{code.strip()}%")
    if library_id:
        clauses.append(f"{alias}.{library_col}=%s")
        params.append(library_id)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


@router.get("/pricing-kb/summary")
def get_summary():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH boq_candidate_counts AS (
                    SELECT bi.qdkid, bi.id, COUNT(c.source_rowid) AS candidate_count
                    FROM tqdk_tqdzm bi
                    LEFT JOIN tqdk_tqdzy c ON c.qdkid = bi.qdkid AND c.qdzmid = bi.id
                    GROUP BY bi.qdkid, bi.id
                )
                SELECT
                    (SELECT COUNT(*) FROM tlibs) AS library_count,
                    (SELECT COUNT(*) FROM tqdk_tzjmc) + (SELECT COUNT(*) FROM tdek_tzjmc) AS chapter_count,
                    (SELECT COUNT(*) FROM tqdk_tqdzm) AS boq_item_count,
                    (SELECT COUNT(*) FROM tdek_tdezm) AS quota_item_count,
                    (SELECT COUNT(*) FROM tdek_tzmgc) AS resource_count,
                    (SELECT COUNT(*) FROM tdek_tznhs) + (SELECT COUNT(*) FROM tdek_tzhhs) AS conversion_rule_count,
                    (SELECT COUNT(*) FROM tqdk_tqdzy) AS candidate_count,
                    (SELECT COUNT(*) FROM pricing_kb_original_target_links) AS target_link_count,
                    (SELECT COUNT(*) FROM pricing_kb_import_issues) AS issue_count,
                    (SELECT COUNT(*) FROM boq_candidate_counts WHERE candidate_count > 0) AS boq_with_candidates,
                    (SELECT COUNT(*) FROM boq_candidate_counts WHERE candidate_count = 0) AS boq_without_candidates,
                    COALESCE((
                        SELECT jsonb_object_agg(link_status, cnt)
                        FROM (
                            SELECT link_status, COUNT(*) AS cnt
                            FROM pricing_kb_original_target_links
                            GROUP BY link_status
                        ) s
                    ), '{}'::jsonb) AS link_status_counts,
                    COALESCE((
                        SELECT jsonb_object_agg(issue_type, cnt)
                        FROM (
                            SELECT issue_type, COUNT(*) AS cnt
                            FROM pricing_kb_import_issues
                            GROUP BY issue_type
                        ) s
                    ), '{}'::jsonb) AS issue_type_counts
                """
            )
            row = cur.fetchone()
        return {
            "library_count": row[0],
            "chapter_count": row[1],
            "boq_item_count": row[2],
            "quota_item_count": row[3],
            "resource_count": row[4],
            "conversion_rule_count": row[5],
            "candidate_count": row[6],
            "target_link_count": row[7],
            "issue_count": row[8],
            "boq_with_candidates": row[9],
            "boq_without_candidates": row[10],
            "link_status_counts": row[11] or {},
            "issue_type_counts": row[12] or {},
        }
    finally:
        conn.close()


@router.get("/pricing-kb/libraries")
def list_libraries():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT l.id, l.mc,
                       (SELECT COUNT(*) FROM tdek_tdezm qi WHERE qi.dekid = l.id) AS quota_count,
                       (SELECT COUNT(*) FROM tqdk_tqdzm bi WHERE bi.qdkid = l.id) AS boq_count
                FROM tlibs l
                ORDER BY l.id
                """
            )
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "source_library_id": r[0],
                "name": r[1],
                "quota_count": r[2],
                "boq_count": r[3],
            }
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/pricing-kb/boq-items")
def list_boq_items(
    q: str | None = Query(None, max_length=200),
    code: str | None = Query(None, max_length=64),
    library_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    where_sql, params = build_filters("i", "zmmc", "zmbh", "qdkid", q, code, library_id)
    limit, offset = page_bounds(page, page_size)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM tqdk_tqdzm i {where_sql}", params)
            total = cur.fetchone()[0]
            cur.execute(
                f"""
                SELECT i.id, i.qdkid, l.mc AS library_name,
                       i.zmbh, i.zmmc, i.dw, c.zjmc AS chapter_name,
                       COUNT(cand.source_rowid) AS candidate_count
                FROM tqdk_tqdzm i
                JOIN tlibs l ON l.id = i.qdkid
                LEFT JOIN tqdk_tzjmc c ON c.qdkid = i.qdkid AND c.id = i.zjh
                LEFT JOIN tqdk_tqdzy cand ON cand.qdkid = i.qdkid AND cand.qdzmid = i.id
                {where_sql}
                GROUP BY i.id, i.qdkid, l.mc, i.zmbh, i.zmmc, i.dw, c.zjmc
                ORDER BY i.qdkid, i.zmbh NULLS LAST, i.id
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = cur.fetchall()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": r[0],
                    "source_library_id": r[1],
                    "library_name": r[2],
                    "code": r[3],
                    "name": r[4],
                    "unit": r[5],
                    "chapter_name": r[6],
                    "candidate_count": r[7],
                }
                for r in rows
            ],
        }
    finally:
        conn.close()


@router.get("/pricing-kb/quota-items")
def list_quota_items(
    q: str | None = Query(None, max_length=200),
    code: str | None = Query(None, max_length=64),
    library_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    where_sql, params = build_filters("i", "zmmc", "zmbh", "dekid", q, code, library_id)
    limit, offset = page_bounds(page, page_size)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM tdek_tdezm i {where_sql}", params)
            total = cur.fetchone()[0]
            cur.execute(
                f"""
                SELECT i.id, i.dekid, l.mc AS library_name,
                       i.zmbh, i.zmmc, i.dw, c.zjmc AS chapter_name,
                       COALESCE(link.link_status, 'unlinked') AS link_status,
                       link.target_table, link.target_item_id
                FROM tdek_tdezm i
                JOIN tlibs l ON l.id = i.dekid
                LEFT JOIN tdek_tzjmc c ON c.dekid = i.dekid AND c.id = i.zjh
                LEFT JOIN pricing_kb_original_target_links link
                  ON link.dekid = i.dekid AND link.dezmid = i.id
                {where_sql}
                ORDER BY i.dekid, i.zmbh NULLS LAST, i.id
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = cur.fetchall()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": r[0],
                    "source_library_id": r[1],
                    "library_name": r[2],
                    "code": r[3],
                    "name": r[4],
                    "unit": r[5],
                    "chapter_name": r[6],
                    "link_status": r[7],
                    "target_table": r[8],
                    "target_item_id": r[9],
                }
                for r in rows
            ],
        }
    finally:
        conn.close()


@router.get("/pricing-kb/boq-items/{boq_item_id}/candidates")
def get_boq_item_candidates(boq_item_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT i.id, i.qdkid, l.mc, i.zmbh, i.zmmc, i.dw, c.zjmc
                FROM tqdk_tqdzm i
                JOIN tlibs l ON l.id = i.qdkid
                LEFT JOIN tqdk_tzjmc c ON c.qdkid = i.qdkid AND c.id = i.zjh
                WHERE i.id=%s
                """,
                (boq_item_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="boq item not found")
            boq_item = {
                "id": row[0],
                "source_library_id": row[1],
                "library_name": row[2],
                "code": row[3],
                "name": row[4],
                "unit": row[5],
                "chapter_name": row[6],
            }

            cur.execute(
                """
                SELECT cand.source_rowid, qi.id, qi.dekid, l.mc AS quota_library_name,
                       qi.zmbh, qi.zmmc, qi.dw, qi.gznr, qc.zjmc AS quota_chapter_name,
                       COALESCE(link.link_status, 'unlinked') AS link_status,
                       link.target_table, link.target_item_id, link.review_message
                FROM tqdk_tqdzy cand
                JOIN tdek_tdezm qi ON qi.dekid = cand.dekid AND qi.id = cand.dezmid
                JOIN tlibs l ON l.id = qi.dekid
                LEFT JOIN tdek_tzjmc qc ON qc.dekid = qi.dekid AND qc.id = qi.zjh
                LEFT JOIN pricing_kb_original_target_links link
                  ON link.dekid = qi.dekid AND link.dezmid = qi.id
                WHERE cand.qdkid=%s AND cand.qdzmid=%s
                ORDER BY qi.dekid, qi.zmbh NULLS LAST, qi.id, cand.source_rowid
                """,
                (boq_item["source_library_id"], boq_item_id),
            )
            candidate_rows = cur.fetchall()
            quota_keys = sorted({(r[2], r[1]) for r in candidate_rows})

            resources_by_quota: dict[tuple[int, int], list[dict[str, Any]]] = {}
            rules_by_quota: dict[tuple[int, int], list[dict[str, Any]]] = {}
            if quota_keys:
                cur.execute(
                    """
                    SELECT r.dekid, r.dezmid, r.lx, r.zmbh, r.zmmc, r.dw, r.gcl
                    FROM tdek_tzmgc r
                    JOIN (SELECT * FROM unnest(%s::bigint[], %s::bigint[]) AS k(dekid, dezmid)) k
                      ON k.dekid = r.dekid AND k.dezmid = r.dezmid
                    ORDER BY r.dekid, r.dezmid, r.source_rowid
                    """,
                    ([k[0] for k in quota_keys], [k[1] for k in quota_keys]),
                )
                for dekid, dezmid, lx, rcode, rname, unit, qty in cur.fetchall():
                    resources_by_quota.setdefault((dekid, dezmid), []).append({
                        "resource_type": RESOURCE_TYPES.get(lx, str(lx) if lx is not None else None),
                        "resource_code": rcode,
                        "resource_name": rname,
                        "unit": unit,
                        "quantity": float(qty) if qty is not None else None,
                    })

                cur.execute(
                    """
                    SELECT r.dekid, r.dezmid, 'conversion' AS rule_type, r.tsxx, r.hssm, r.groupno
                    FROM tdek_tznhs r
                    JOIN (SELECT * FROM unnest(%s::bigint[], %s::bigint[]) AS k(dekid, dezmid)) k
                      ON k.dekid = r.dekid AND k.dezmid = r.dezmid
                    UNION ALL
                    SELECT r.dekid, r.dezmid, 'input_prompt' AS rule_type, r.tsxx, NULL AS hssm, NULL AS groupno
                    FROM tdek_tzhhs r
                    JOIN (SELECT * FROM unnest(%s::bigint[], %s::bigint[]) AS k(dekid, dezmid)) k
                      ON k.dekid = r.dekid AND k.dezmid = r.dezmid
                    ORDER BY dekid, dezmid, rule_type
                    """,
                    (
                        [k[0] for k in quota_keys], [k[1] for k in quota_keys],
                        [k[0] for k in quota_keys], [k[1] for k in quota_keys],
                    ),
                )
                for dekid, dezmid, rule_type, prompt, description, group_no in cur.fetchall():
                    rules_by_quota.setdefault((dekid, dezmid), []).append({
                        "rule_type": rule_type,
                        "prompt": prompt,
                        "description": description,
                        "group_no": group_no,
                    })

        candidates = []
        for r in candidate_rows:
            qid = r[1]
            dekid = r[2]
            key = (dekid, qid)
            resources = resources_by_quota.get(key, [])
            candidates.append({
                "candidate_id": r[0],
                "quota_item": {
                    "id": qid,
                    "source_library_id": dekid,
                    "library_name": r[3],
                    "code": r[4],
                    "name": r[5],
                    "unit": r[6],
                    "work_content": r[7],
                    "chapter_name": r[8],
                },
                "target_link": {
                    "link_status": r[9],
                    "target_table": r[10],
                    "target_item_id": r[11],
                    "review_message": r[12],
                },
                "resource_summary": resources[:8],
                "resource_count": len(resources),
                "conversion_rules": rules_by_quota.get(key, []),
            })
        return {"boq_item": boq_item, "total": len(candidates), "candidates": candidates}
    finally:
        conn.close()


@router.get("/pricing-kb/import-runs")
def list_import_runs(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    limit, offset = page_bounds(page, page_size)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM pricing_kb_import_runs")
            total = cur.fetchone()[0]
            cur.execute(
                """
                SELECT id, source_file, source_file_sha256, status, stats_json,
                       error_message, created_at, finished_at
                FROM pricing_kb_import_runs
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            rows = cur.fetchall()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": r[0],
                    "source_file": r[1],
                    "source_file_sha256": r[2],
                    "status": r[3],
                    "stats_json": r[4] or {},
                    "error_message": r[5],
                    "created_at": r[6],
                    "finished_at": r[7],
                }
                for r in rows
            ],
        }
    finally:
        conn.close()


@router.get("/pricing-kb/import-issues")
def list_import_issues(
    run_id: int | None = None,
    issue_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    clauses: list[str] = []
    params: list[Any] = []
    if run_id:
        clauses.append("run_id=%s")
        params.append(run_id)
    if issue_type:
        clauses.append("issue_type=%s")
        params.append(issue_type)
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
    limit, offset = page_bounds(page, page_size)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM pricing_kb_import_issues {where_sql}", params)
            total = cur.fetchone()[0]
            cur.execute(
                f"""
                SELECT id, run_id, severity, issue_type, message,
                       source_table, source_library_id, source_record_id,
                       context_json, created_at
                FROM pricing_kb_import_issues
                {where_sql}
                ORDER BY id DESC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = cur.fetchall()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": r[0],
                    "run_id": r[1],
                    "severity": r[2],
                    "issue_type": r[3],
                    "message": r[4],
                    "source_table": r[5],
                    "source_library_id": r[6],
                    "source_record_id": r[7],
                    "context_json": r[8] or {},
                    "created_at": r[9],
                }
                for r in rows
            ],
        }
    finally:
        conn.close()
