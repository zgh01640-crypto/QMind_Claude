import os
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from db.connection import get_connection, apply_schema
from importer.parser import parse_filename, parse_workbook
from importer.loader import (
    get_existing_period,
    create_period,
    delete_period,
    upsert_categories,
    insert_items,
)
from api.schemas import ImportResult

router = APIRouter()


@router.post("/upload", response_model=ImportResult)
async def upload_file(
    file: UploadFile = File(...),
    force: bool = Query(False, description="已存在时强制覆盖"),
):
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="只支持 .xlsx 格式文件")

    try:
        year, month, version = parse_filename(file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    content = await file.read()
    suffix = f"_{year}{month:02d}{version}.xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        conn = get_connection()
        apply_schema(conn)

        existing_id = get_existing_period(conn, year, month, version)
        if existing_id and not force:
            conn.close()
            raise HTTPException(
                status_code=409,
                detail=f"{year}年{month}月第{version}版数据已存在，设置 force=true 可覆盖",
            )
        if existing_id and force:
            delete_period(conn, existing_id)

        sheets_meta, price_items = parse_workbook(tmp_path)
        period_id = create_period(conn, year, month, version, file.filename)
        category_map = upsert_categories(conn, sheets_meta)
        inserted = insert_items(conn, period_id, price_items, category_map)
        conn.close()

        return ImportResult(
            period_id=period_id, year=year, month=month, version=version,
            categories=len(sheets_meta), items=inserted,
        )
    finally:
        os.unlink(tmp_path)
