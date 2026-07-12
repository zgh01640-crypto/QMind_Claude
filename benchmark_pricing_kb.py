"""Read-only latency and query-plan benchmark for versioned pricing knowledge data."""

from __future__ import annotations

import argparse
import json
import math
from time import perf_counter
from typing import Any

from db.connection import get_connection
from db.pricing_kb_versions import apply_version_schema, get_active_version_id


def percentile(values: list[float], value: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * value) - 1)
    return round(ordered[index], 3)


def samples(conn, version_id: int) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT qdkid, id, zmbh, zmmc FROM tqdk_tqdzm WHERE kb_version_id=%s LIMIT 1",
            (version_id,),
        )
        boq = cur.fetchone()
        cur.execute(
            "SELECT dekid, id, zmbh, zmmc FROM tdek_tdezm WHERE kb_version_id=%s LIMIT 1",
            (version_id,),
        )
        quota = cur.fetchone()
    if not boq or not quota:
        raise RuntimeError(f"Version {version_id} has no BOQ or quota samples")
    return {"boq": boq, "quota": quota}


def query_cases(version_id: int, sample: dict[str, Any]) -> dict[str, tuple[str, tuple[Any, ...]]]:
    boq = sample["boq"]
    quota = sample["quota"]
    return {
        "boq_code": (
            "SELECT id,zmmc FROM tqdk_tqdzm WHERE kb_version_id=%s AND zmbh=%s",
            (version_id, boq[2]),
        ),
        "boq_candidates": (
            """
            SELECT q.id,q.zmbh,q.zmmc
            FROM tqdk_tqdzy c
            JOIN tdek_tdezm q ON q.kb_version_id=c.kb_version_id
             AND q.dekid=c.dekid AND q.id=c.dezmid
            WHERE c.kb_version_id=%s AND c.qdkid=%s AND c.qdzmid=%s
            """,
            (version_id, boq[0], boq[1]),
        ),
        "quota_detail": (
            "SELECT * FROM tdek_tdezm WHERE kb_version_id=%s AND dekid=%s AND id=%s",
            (version_id, quota[0], quota[1]),
        ),
        "quota_resources": (
            "SELECT * FROM tdek_tzmgc WHERE kb_version_id=%s AND dekid=%s AND dezmid=%s",
            (version_id, quota[0], quota[1]),
        ),
        "conversion_rules": (
            "SELECT * FROM tdek_tzhhs WHERE kb_version_id=%s AND dekid=%s AND dezmid=%s",
            (version_id, quota[0], quota[1]),
        ),
        "coefficient_rules": (
            "SELECT * FROM tdek_tznhs WHERE kb_version_id=%s AND dekid=%s AND dezmid=%s",
            (version_id, quota[0], quota[1]),
        ),
        "quota_name_search": (
            "SELECT id FROM tdek_tdezm WHERE kb_version_id=%s AND zmmc ILIKE %s LIMIT 80",
            (version_id, f"%{str(quota[3] or '')[:4]}%"),
        ),
    }


def benchmark_version(conn, version_id: int, iterations: int, explain: bool) -> dict[str, Any]:
    cases = query_cases(version_id, samples(conn, version_id))
    result: dict[str, Any] = {"version_id": version_id, "queries": {}}
    with conn.cursor() as cur:
        for name, (query, params) in cases.items():
            timings: list[float] = []
            for _ in range(iterations):
                started = perf_counter()
                cur.execute(query, params)
                cur.fetchall()
                timings.append((perf_counter() - started) * 1000)
            query_result: dict[str, Any] = {
                "p50_ms": percentile(timings, 0.50),
                "p95_ms": percentile(timings, 0.95),
                "max_ms": round(max(timings), 3),
            }
            if explain:
                cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query, params)
                query_result["plan"] = cur.fetchone()[0][0]
            result["queries"][name] = query_result
    conn.rollback()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version-id", type=int, action="append")
    parser.add_argument("--all-versions", action="store_true")
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--explain", action="store_true")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")

    conn = get_connection()
    try:
        apply_version_schema(conn)
        if args.all_versions:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM pricing_kb_versions WHERE status IN ('validated','active','retired') ORDER BY id"
                )
                version_ids = [int(row[0]) for row in cur.fetchall()]
        elif args.version_id:
            version_ids = args.version_id
        else:
            version_ids = [int(get_active_version_id(conn))]
        report = {
            "iterations": args.iterations,
            "versions": [
                benchmark_version(conn, version_id, args.iterations, args.explain)
                for version_id in version_ids
            ],
        }
        print(json.dumps(report, ensure_ascii=False, default=str, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
