"""
提示词模板管理 API。
支持多版本存储、编辑、激活，供套定额流程调用。
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from db.connection import get_connection

router = APIRouter()


class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    content: str


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None


def _ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS prompt_templates (
                id          SERIAL PRIMARY KEY,
                name        VARCHAR(200) NOT NULL,
                description TEXT,
                content     TEXT NOT NULL,
                is_active   BOOLEAN DEFAULT FALSE,
                created_at  TIMESTAMP DEFAULT NOW(),
                updated_at  TIMESTAMP DEFAULT NOW()
            )
        """)
    conn.commit()


@router.get("/prompt-templates")
def list_templates():
    """列出所有提示词模板。"""
    conn = get_connection()
    try:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, description, is_active, created_at, updated_at,
                       LENGTH(content) AS content_len
                FROM prompt_templates ORDER BY created_at DESC
            """)
            rows = cur.fetchall()
        return [
            {
                "id": r[0], "name": r[1], "description": r[2],
                "is_active": r[3],
                "created_at": r[4].isoformat() if r[4] else None,
                "updated_at": r[5].isoformat() if r[5] else None,
                "content_len": r[6],
            }
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/prompt-templates/active")
def get_active_template():
    """获取当前激活的模板内容（供套定额调用）。"""
    conn = get_connection()
    try:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, content FROM prompt_templates WHERE is_active = TRUE LIMIT 1"
            )
            row = cur.fetchone()
        if not row:
            return {"id": None, "name": None, "content": None, "has_active": False}
        return {"id": row[0], "name": row[1], "content": row[2], "has_active": True}
    finally:
        conn.close()


@router.get("/prompt-templates/{template_id}")
def get_template(template_id: int):
    """获取单个模板完整内容。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, description, content, is_active, created_at, updated_at FROM prompt_templates WHERE id = %s",
                (template_id,)
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(404, "模板不存在")
        return {
            "id": row[0], "name": row[1], "description": row[2],
            "content": row[3], "is_active": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
            "updated_at": row[6].isoformat() if row[6] else None,
        }
    finally:
        conn.close()


@router.post("/prompt-templates")
def create_template(body: TemplateCreate):
    """创建新模板。"""
    conn = get_connection()
    try:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO prompt_templates (name, description, content)
                VALUES (%s, %s, %s) RETURNING id
            """, (body.name, body.description, body.content))
            new_id = cur.fetchone()[0]
        conn.commit()
        return {"id": new_id, "ok": True}
    finally:
        conn.close()


@router.put("/prompt-templates/{template_id}")
def update_template(template_id: int, body: TemplateUpdate):
    """更新模板内容或名称。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM prompt_templates WHERE id=%s", (template_id,))
            if not cur.fetchone():
                raise HTTPException(404, "模板不存在")
            fields = []
            values = []
            if body.name is not None:
                fields.append("name=%s"); values.append(body.name)
            if body.description is not None:
                fields.append("description=%s"); values.append(body.description)
            if body.content is not None:
                fields.append("content=%s"); values.append(body.content)
            if not fields:
                return {"ok": True, "changed": False}
            fields.append("updated_at=NOW()")
            values.append(template_id)
            cur.execute(f"UPDATE prompt_templates SET {', '.join(fields)} WHERE id=%s", values)
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/prompt-templates/{template_id}/activate")
def activate_template(template_id: int):
    """将指定模板设为当前激活，其余取消激活。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM prompt_templates WHERE id=%s", (template_id,))
            if not cur.fetchone():
                raise HTTPException(404, "模板不存在")
            cur.execute("UPDATE prompt_templates SET is_active=FALSE")
            cur.execute("UPDATE prompt_templates SET is_active=TRUE WHERE id=%s", (template_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/prompt-templates/deactivate-all")
def deactivate_all():
    """取消所有激活（回退到代码默认提示词）。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE prompt_templates SET is_active=FALSE")
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.delete("/prompt-templates/{template_id}")
def delete_template(template_id: int):
    """删除模板（不能删除激活中的模板）。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT is_active FROM prompt_templates WHERE id=%s", (template_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "模板不存在")
            if row[0]:
                raise HTTPException(400, "不能删除正在激活的模板，请先切换到其他模板")
            cur.execute("DELETE FROM prompt_templates WHERE id=%s", (template_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
