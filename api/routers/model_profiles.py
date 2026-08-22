from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import CurrentUser, current_user
from api.services.model_profiles import (
    CUSTOM_PROVIDER, PROVIDERS, client_for, encrypt_api_key, key_hint, list_profiles,
    normalize_profile_input,
)
from db.connection import get_connection

router = APIRouter()


class ModelProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    provider: str
    base_url: str | None = Field(default=None, max_length=500)
    model: str = Field(min_length=1, max_length=160)
    api_key: str = Field(min_length=1, max_length=1000)
    is_default: bool = False


class ModelProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    provider: str | None = None
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, min_length=1, max_length=160)
    api_key: str | None = Field(default=None, max_length=1000)
    is_default: bool | None = None


def _require_access(user: CurrentUser) -> CurrentUser:
    if user.role not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="当前角色不能管理模型配置")
    return user


def _get_owned_profile(conn, user_id: int, profile_id: int):
    with conn.cursor() as cur:
        cur.execute("SELECT id,name,provider,base_url,model,encrypted_api_key,key_hint,is_default,created_at,updated_at FROM user_model_profiles WHERE id=%s AND user_id=%s FOR UPDATE", (profile_id, user_id))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    return row


def _as_dict(row) -> dict:
    return {"id": int(row[0]), "name": row[1], "provider": row[2], "base_url": row[3], "model": row[4], "key_hint": row[6], "is_default": bool(row[7]), "created_at": row[8], "updated_at": row[9]}


def _set_default(cur, user_id: int, profile_id: int) -> None:
    cur.execute("UPDATE user_model_profiles SET is_default=FALSE,updated_at=NOW() WHERE user_id=%s AND is_default", (user_id,))
    cur.execute("UPDATE user_model_profiles SET is_default=TRUE,updated_at=NOW() WHERE id=%s AND user_id=%s", (profile_id, user_id))


@router.get("/model-profiles")
def get_model_profiles(user: CurrentUser = Depends(current_user)):
    _require_access(user)
    return {"providers": [{"id": key, "base_url": value} for key, value in PROVIDERS.items()] + [{"id": CUSTOM_PROVIDER, "base_url": None}], "profiles": list_profiles(user.id)}


@router.post("/model-profiles")
def create_model_profile(body: ModelProfileCreate, user: CurrentUser = Depends(current_user)):
    _require_access(user)
    provider, base_url, model = normalize_profile_input(body.provider, body.base_url, body.model)
    name, api_key = body.name.strip(), body.api_key.strip()
    if not name or not api_key:
        raise HTTPException(status_code=422, detail="配置名称和 API Key 不能为空")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT EXISTS(SELECT 1 FROM user_model_profiles WHERE user_id=%s)", (user.id,))
            has_profiles = bool(cur.fetchone()[0])
            cur.execute("""INSERT INTO user_model_profiles(user_id,name,provider,base_url,model,encrypted_api_key,key_hint,is_default)
                           VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                           RETURNING id,name,provider,base_url,model,encrypted_api_key,key_hint,is_default,created_at,updated_at""",
                        (user.id, name, provider, base_url, model, encrypt_api_key(api_key), key_hint(api_key), body.is_default or not has_profiles))
            row = cur.fetchone()
            if row[7]:
                _set_default(cur, user.id, int(row[0]))
                cur.execute("SELECT id,name,provider,base_url,model,encrypted_api_key,key_hint,is_default,created_at,updated_at FROM user_model_profiles WHERE id=%s", (row[0],))
                row = cur.fetchone()
        conn.commit()
        return _as_dict(row)
    finally:
        conn.close()


@router.patch("/model-profiles/{profile_id}")
def update_model_profile(profile_id: int, body: ModelProfileUpdate, user: CurrentUser = Depends(current_user)):
    _require_access(user)
    conn = get_connection()
    try:
        existing = _get_owned_profile(conn, user.id, profile_id)
        provider = body.provider if body.provider is not None else existing[2]
        base_url = body.base_url if body.base_url is not None else existing[3]
        model = body.model if body.model is not None else existing[4]
        provider, base_url, model = normalize_profile_input(provider, base_url, model)
        name = body.name.strip() if body.name is not None else existing[1]
        if not name:
            raise HTTPException(status_code=422, detail="配置名称不能为空")
        encrypted_key, hint = existing[5], existing[6]
        if body.api_key is not None:
            if not body.api_key.strip():
                raise HTTPException(status_code=422, detail="API Key 不能为空")
            encrypted_key, hint = encrypt_api_key(body.api_key.strip()), key_hint(body.api_key.strip())
        with conn.cursor() as cur:
            cur.execute("""UPDATE user_model_profiles SET name=%s,provider=%s,base_url=%s,model=%s,encrypted_api_key=%s,key_hint=%s,updated_at=NOW()
                           WHERE id=%s AND user_id=%s
                           RETURNING id,name,provider,base_url,model,encrypted_api_key,key_hint,is_default,created_at,updated_at""",
                        (name, provider, base_url, model, encrypted_key, hint, profile_id, user.id))
            row = cur.fetchone()
            if body.is_default is True:
                _set_default(cur, user.id, profile_id)
                cur.execute("SELECT id,name,provider,base_url,model,encrypted_api_key,key_hint,is_default,created_at,updated_at FROM user_model_profiles WHERE id=%s", (profile_id,))
                row = cur.fetchone()
        conn.commit()
        return _as_dict(row)
    finally:
        conn.close()


@router.post("/model-profiles/{profile_id}/default")
def set_default_model_profile(profile_id: int, user: CurrentUser = Depends(current_user)):
    _require_access(user)
    conn = get_connection()
    try:
        _get_owned_profile(conn, user.id, profile_id)
        with conn.cursor() as cur:
            _set_default(cur, user.id, profile_id)
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.delete("/model-profiles/{profile_id}")
def delete_model_profile(profile_id: int, user: CurrentUser = Depends(current_user)):
    _require_access(user)
    conn = get_connection()
    try:
        row = _get_owned_profile(conn, user.id, profile_id)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_model_profiles WHERE id=%s AND user_id=%s", (profile_id, user.id))
            if row[7]:
                cur.execute("SELECT id FROM user_model_profiles WHERE user_id=%s ORDER BY updated_at DESC,id DESC LIMIT 1", (user.id,))
                replacement = cur.fetchone()
                if replacement:
                    _set_default(cur, user.id, int(replacement[0]))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/model-profiles/{profile_id}/test")
def test_model_profile(profile_id: int, user: CurrentUser = Depends(current_user)):
    _require_access(user)
    conn = get_connection()
    try:
        row = _get_owned_profile(conn, user.id, profile_id)
        from api.services.model_profiles import ModelProfile, decrypt_api_key
        profile = ModelProfile(int(row[0]), user.id, row[1], row[2], row[3], row[4], decrypt_api_key(row[5]))
    finally:
        conn.close()
    try:
        client_for(profile, timeout=20.0).chat.completions.create(model=profile.model, messages=[{"role": "user", "content": "ping"}], max_tokens=1)
        return {"ok": True, "message": "连接成功"}
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"连接失败：{str(exc)[:300]}") from exc
