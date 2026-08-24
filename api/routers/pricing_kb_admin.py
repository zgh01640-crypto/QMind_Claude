from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from psycopg2.extras import Json

from api.services.pricing_kb_import_admin import (
    KNOWN_TABLES,
    expand_dependencies,
    inspect_sqlite,
    require_admin,
    upload_root,
)
from db.connection import get_connection
from db.pricing_kb_versions import apply_version_schema, get_active_version_id


router = APIRouter()
MAX_UPLOAD_BYTES = int(os.getenv("PRICING_KB_MAX_UPLOAD_BYTES", str(500 * 1024 * 1024)))


class ImportProfileCreate(BaseModel):
    profile_id: str
    name: str
    description: str | None = None
    selected_tables: list[str] = Field(default_factory=list)
    required_tables: list[str] = Field(default_factory=list)


class ImportJobCreate(BaseModel):
    upload_id: int
    profile_id: str | None = None
    parent_version_id: int | None = None
    selected_tables: list[str] = Field(default_factory=list)
    unknown_tables: dict[str, str] = Field(default_factory=dict)
    change_note: str | None = Field(default=None, max_length=1000)


def _conn():
    conn = get_connection()
    apply_version_schema(conn)
    return conn


@router.post("/pricing-kb/uploads", dependencies=[Depends(require_admin)])
async def upload_pricing_kb(file: UploadFile = File(...)):
    original = Path(file.filename or "upload.db").name
    if Path(original).suffix.lower() != ".db":
        raise HTTPException(status_code=400, detail="only .db files are accepted")
    root = upload_root()
    temp = root / f".{uuid.uuid4().hex}.upload"
    digest = hashlib.sha256()
    size = 0
    try:
        with temp.open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="knowledge-base file exceeds upload limit")
                digest.update(chunk)
                target.write(chunk)
        with temp.open("rb") as source:
            if source.read(16) != b"SQLite format 3\x00":
                raise HTTPException(status_code=400, detail="file is not a SQLite database")
        file_hash = digest.hexdigest()
        conn = _conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id,inspection_json FROM pricing_kb_uploads WHERE file_sha256=%s", (file_hash,))
                existing = cur.fetchone()
                if existing:
                    temp.unlink(missing_ok=True)
                    return {"id": existing[0], "duplicate": True, "inspection": existing[1]}
            final_path = root / f"{file_hash}.db"
            temp.replace(final_path)
            try:
                inspection = inspect_sqlite(final_path)
                status = "inspected" if inspection["quick_check"] == "ok" else "failed"
                error = None if status == "inspected" else inspection["quick_check"]
            except Exception as exc:
                inspection, status, error = {}, "failed", str(exc)
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO pricing_kb_uploads(original_name,stored_path,file_sha256,size_bytes,status,
                    quick_check,schema_signature,inspection_json,error_message)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (original, str(final_path), file_hash, size, status, inspection.get("quick_check"),
                     inspection.get("schema_signature"), Json(inspection), error))
                upload_id = int(cur.fetchone()[0])
            conn.commit()
            if status == "failed":
                raise HTTPException(status_code=422, detail=error)
            return {"id": upload_id, "duplicate": False, "inspection": inspection}
        finally:
            conn.close()
    finally:
        temp.unlink(missing_ok=True)


@router.get("/pricing-kb/uploads/{upload_id}/inspection", dependencies=[Depends(require_admin)])
def get_upload_inspection(upload_id: int):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id,original_name,file_sha256,size_bytes,status,inspection_json,error_message,created_at FROM pricing_kb_uploads WHERE id=%s", (upload_id,))
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="upload not found")
        return {"id": row[0], "original_name": row[1], "file_sha256": row[2], "size_bytes": row[3],
                "status": row[4], "inspection": row[5] or {}, "error_message": row[6], "created_at": row[7]}
    finally:
        conn.close()


@router.delete("/pricing-kb/uploads/{upload_id}", dependencies=[Depends(require_admin)])
def delete_upload(upload_id: int):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT stored_path FROM pricing_kb_uploads WHERE id=%s", (upload_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="upload not found")
            cur.execute("SELECT 1 FROM pricing_kb_import_jobs WHERE upload_id=%s LIMIT 1", (upload_id,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="upload is referenced by an import job")
            cur.execute("DELETE FROM pricing_kb_uploads WHERE id=%s", (upload_id,))
        conn.commit()
        Path(row[0]).unlink(missing_ok=True)
        return {"ok": True}
    finally:
        conn.close()


@router.get("/pricing-kb/import-profiles")
def list_import_profiles():
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT profile_id,name,description,selected_tables,required_tables,is_system FROM pricing_kb_import_profiles ORDER BY is_system DESC,name")
            return [{"profile_id": r[0], "name": r[1], "description": r[2], "selected_tables": r[3] or [],
                     "required_tables": r[4] or [], "is_system": r[5]} for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/pricing-kb/import-profiles", dependencies=[Depends(require_admin)])
def create_import_profile(body: ImportProfileCreate):
    profile_id = re.sub(r"[^a-z0-9-]+", "-", body.profile_id.lower()).strip("-")
    if not profile_id:
        raise HTTPException(status_code=400, detail="profile_id is invalid")
    unknown = (set(body.selected_tables) | set(body.required_tables)) - set(KNOWN_TABLES)
    if unknown:
        raise HTTPException(status_code=400, detail=f"profile contains unknown typed tables: {sorted(unknown)}")
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO pricing_kb_import_profiles(profile_id,name,description,selected_tables,required_tables)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT(profile_id) DO UPDATE SET name=EXCLUDED.name,
                description=EXCLUDED.description,selected_tables=EXCLUDED.selected_tables,
                required_tables=EXCLUDED.required_tables,updated_at=NOW() RETURNING profile_id""",
                (profile_id, body.name.strip(), body.description, Json(body.selected_tables), Json(body.required_tables)))
        conn.commit()
        return {"profile_id": profile_id}
    finally:
        conn.close()


@router.post("/pricing-kb/import-jobs", dependencies=[Depends(require_admin)])
def create_import_job(body: ImportJobCreate):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT status,inspection_json,stored_path FROM pricing_kb_uploads WHERE id=%s", (body.upload_id,))
            upload = cur.fetchone()
            if not upload or upload[0] != "inspected":
                raise HTTPException(status_code=409, detail="upload is not ready")
            inspection = upload[1] or {}
            # Uploads created before schema governance do not have a contract
            # report. Reinspect them before allowing a new version to use them.
            if "schema_diff" not in inspection:
                inspection = inspect_sqlite(Path(upload[2]))
                cur.execute(
                    "UPDATE pricing_kb_uploads SET inspection_json=%s,schema_signature=%s,quick_check=%s WHERE id=%s",
                    (Json(inspection), inspection.get("schema_signature"), inspection.get("quick_check"), body.upload_id),
                )
            schema_diff = inspection.get("schema_diff") or {}
            if schema_diff:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": "SQLite knowledge-base schema does not match the governed contract",
                        "schema_diff": schema_diff,
                    },
                )
            available = {t["name"] for t in inspection.get("tables", [])}
            selected = set(body.selected_tables)
            if body.profile_id:
                cur.execute("SELECT selected_tables,required_tables FROM pricing_kb_import_profiles WHERE profile_id=%s", (body.profile_id,))
                profile = cur.fetchone()
                if not profile:
                    raise HTTPException(status_code=404, detail="import profile not found")
                if not selected:
                    selected = set(profile[0] or [])
                selected.update(profile[1] or [])
            selected &= set(KNOWN_TABLES)
            # 典型组价表是可选的：旧版知识库没有该表时仍可沿用普通候选表导入。
            if "TQDK_TQDZY_SPECIAL" not in available:
                selected.discard("TQDK_TQDZY_SPECIAL")
            selected = expand_dependencies(selected, available)
            missing = selected - available
            if missing:
                raise HTTPException(status_code=400, detail=f"selected source tables are missing: {sorted(missing)}")
            raw_tables = {name: mode for name, mode in body.unknown_tables.items() if name in available and name not in KNOWN_TABLES and mode == "raw"}
            parent_id = body.parent_version_id
            if parent_id is None:
                parent_id = get_active_version_id(conn, required=False)
            if len(selected) < len(KNOWN_TABLES) and parent_id is None:
                raise HTTPException(status_code=409, detail="partial import requires an active parent version")
            config = {"selected_tables": sorted(selected), "unknown_tables": raw_tables}
            change_note = (body.change_note or "").strip() or None
            cur.execute("""INSERT INTO pricing_kb_import_jobs(
                    upload_id,profile_id,parent_version_id,config_json,change_note,total_tables
                ) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id""",
                (body.upload_id, body.profile_id, parent_id, Json(config), change_note,
                 len(selected) + len(raw_tables)))
            job_id = int(cur.fetchone()[0])
        conn.commit()
        return {"id": job_id, "status": "queued", "config": config, "parent_version_id": parent_id}
    finally:
        conn.close()


@router.get("/pricing-kb/import-jobs/{job_id}", dependencies=[Depends(require_admin)])
def get_import_job(job_id: int):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT id,upload_id,profile_id,parent_version_id,version_id,config_json,status,current_table,
                completed_tables,total_tables,processed_rows,progress_json,error_message,attempts,created_at,started_at,finished_at,
                change_note
                FROM pricing_kb_import_jobs WHERE id=%s""", (job_id,))
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="import job not found")
        keys = ["id","upload_id","profile_id","parent_version_id","version_id","config","status","current_table",
                "completed_tables","total_tables","processed_rows","progress","error_message","attempts","created_at","started_at","finished_at",
                "change_note"]
        return dict(zip(keys, row))
    finally:
        conn.close()


@router.post("/pricing-kb/import-jobs/{job_id}/cancel", dependencies=[Depends(require_admin)])
def cancel_import_job(job_id: int):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""UPDATE pricing_kb_import_jobs SET status=CASE WHEN status='queued' THEN 'cancelled'
                ELSE 'cancel_requested' END,finished_at=CASE WHEN status='queued' THEN NOW() ELSE finished_at END,updated_at=NOW()
                WHERE id=%s AND status IN ('queued','running') RETURNING status""", (job_id,))
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=409, detail="job cannot be cancelled")
        conn.commit()
        return {"id": job_id, "status": row[0]}
    finally:
        conn.close()
