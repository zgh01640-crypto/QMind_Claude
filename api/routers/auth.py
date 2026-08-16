from __future__ import annotations

import os
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from api.auth import (
    SESSION_COOKIE, SESSION_DAYS, CurrentUser, create_session, current_user,
    hash_password, require_admin, revoke_session, revoke_sessions,
    validate_password, verify_password,
)
from db.connection import get_connection

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    password: str
    role: str = Field(pattern=r"^(admin|operator|reader)$")


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, pattern=r"^(admin|operator|reader)$")
    is_active: bool | None = None


class PasswordReset(BaseModel):
    password: str


class OwnershipTransfer(BaseModel):
    owner_user_id: int


def _user_dict(row) -> dict:
    return {"id": row[0], "username": row[1], "display_name": row[2], "role": row[3], "is_active": row[4], "created_at": row[5], "last_login_at": row[6]}


def _cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True,
        samesite="lax", secure=os.getenv("AUTH_COOKIE_SECURE", "0").lower() in {"1", "true", "yes"}, path="/",
    )


@router.post("/auth/login")
def login(body: LoginRequest, response: Response):
    username = body.username.strip().lower()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id,username,display_name,password_hash,role,is_active FROM users WHERE username=%s", (username,))
            row = cur.fetchone()
            if not row or not row[5] or not verify_password(row[3], body.password):
                raise HTTPException(status_code=401, detail="用户名或密码错误")
            cur.execute("UPDATE users SET last_login_at=NOW(),updated_at=NOW() WHERE id=%s", (row[0],))
        conn.commit()
    finally:
        conn.close()
    token, _ = create_session(int(row[0]))
    _cookie(response, token)
    return {"user": {"id": row[0], "username": row[1], "display_name": row[2], "role": row[4]}}


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    revoke_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request):
    user = current_user(request)
    return {"id": user.id, "username": user.username, "display_name": user.display_name, "role": user.role}


@router.post("/auth/change-password")
def change_password(body: PasswordChange, request: Request):
    user = current_user(request)
    validate_password(body.new_password)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT password_hash FROM users WHERE id=%s", (user.id,))
            row = cur.fetchone()
            if not row or not verify_password(row[0], body.current_password):
                raise HTTPException(status_code=400, detail="当前密码不正确")
            cur.execute("UPDATE users SET password_hash=%s,updated_at=NOW() WHERE id=%s", (hash_password(body.new_password), user.id))
        conn.commit()
    finally:
        conn.close()
    revoke_sessions(user.id)
    return {"ok": True}


@router.get("/admin/users")
def list_users(_: CurrentUser = Depends(require_admin)):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id,username,display_name,role,is_active,created_at,last_login_at FROM users ORDER BY created_at")
            return [_user_dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


@router.post("/admin/users")
def create_user(body: UserCreate, _: CurrentUser = Depends(require_admin)):
    password_hash = hash_password(body.password)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO users(username,display_name,password_hash,role) VALUES(%s,%s,%s,%s) RETURNING id,username,display_name,role,is_active,created_at,last_login_at", (body.username.lower(), body.display_name.strip(), password_hash, body.role))
            row = cur.fetchone()
        conn.commit()
        return _user_dict(row)
    except Exception as exc:
        conn.rollback()
        if getattr(exc, "pgcode", None) == "23505":
            raise HTTPException(status_code=409, detail="用户名已存在") from exc
        raise
    finally:
        conn.close()


def _ensure_admin_survives(conn, target_id: int, next_role: str | None, next_active: bool | None) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT role,is_active FROM users WHERE id=%s", (target_id,))
        target = cur.fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="用户不存在")
        remains_admin = (next_role or target[0]) == "admin" and (target[1] if next_active is None else next_active)
        if remains_admin:
            return
        cur.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND is_active AND id<>%s", (target_id,))
        if int(cur.fetchone()[0]) == 0:
            raise HTTPException(status_code=409, detail="不能停用或降级最后一个有效管理员")


@router.patch("/admin/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, _: CurrentUser = Depends(require_admin)):
    conn = get_connection()
    try:
        _ensure_admin_survives(conn, user_id, body.role, body.is_active)
        fields, values = [], []
        if body.display_name is not None:
            fields.append("display_name=%s"); values.append(body.display_name.strip())
        if body.role is not None:
            fields.append("role=%s"); values.append(body.role)
        if body.is_active is not None:
            fields.append("is_active=%s"); values.append(body.is_active)
        if not fields:
            raise HTTPException(status_code=400, detail="没有需要更新的字段")
        values.append(user_id)
        with conn.cursor() as cur:
            cur.execute(f"UPDATE users SET {','.join(fields)},updated_at=NOW() WHERE id=%s RETURNING id,username,display_name,role,is_active,created_at,last_login_at", values)
            row = cur.fetchone()
        conn.commit()
        if body.is_active is False:
            revoke_sessions(user_id)
        return _user_dict(row)
    finally:
        conn.close()


@router.post("/admin/users/{user_id}/reset-password")
def reset_password(user_id: int, body: PasswordReset, _: CurrentUser = Depends(require_admin)):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET password_hash=%s,updated_at=NOW() WHERE id=%s RETURNING id", (hash_password(body.password), user_id))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="用户不存在")
        conn.commit()
    finally:
        conn.close()
    revoke_sessions(user_id)
    return {"ok": True}


@router.post("/admin/ownership/{asset_type}/{asset_id}")
def transfer_ownership(asset_type: str, asset_id: int, body: OwnershipTransfer, _: CurrentUser = Depends(require_admin)):
    tables = {"boq-project": "boq_projects", "manual-project": "manual_boq_projects", "pricing-task": "pricing_tasks", "pricing-batch": "pricing_task_batches"}
    table = tables.get(asset_type)
    if not table:
        raise HTTPException(status_code=404, detail="未知资产类型")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE id=%s AND is_active", (body.owner_user_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=422, detail="目标用户不存在或已停用")
            cur.execute(f"UPDATE {table} SET owner_user_id=%s WHERE id=%s RETURNING id", (body.owner_user_id, asset_id))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="资产不存在")
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
