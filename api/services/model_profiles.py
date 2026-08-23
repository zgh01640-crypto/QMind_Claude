"""Per-user, encrypted model-provider configuration and runtime clients."""
from __future__ import annotations

import ipaddress
import os
import socket
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from openai import OpenAI

from db.connection import get_connection


PROVIDERS = {
    "deepseek": "https://api.deepseek.com",
    "openai": "https://api.openai.com/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}
CUSTOM_PROVIDER = "openai-compatible"
_active_profile: ContextVar["ModelProfile | None"] = ContextVar("active_model_profile", default=None)


@dataclass(frozen=True)
class ModelProfile:
    id: int
    user_id: int
    name: str
    provider: str
    base_url: str
    model: str
    api_key: str
    input_price_per_million: Decimal = Decimal("0")
    cached_input_price_per_million: Decimal | None = None
    output_price_per_million: Decimal = Decimal("0")


def _fernet() -> Fernet:
    key = os.getenv("MODEL_CONFIG_ENCRYPTION_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="模型配置加密密钥未配置")
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=503, detail="模型配置加密密钥无效") from exc


def encrypt_api_key(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_api_key(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=503, detail="模型配置密钥无法解密，请重新保存配置") from exc


def key_hint(value: str) -> str:
    return "…" + value[-4:] if len(value) >= 4 else "已设置"


def _public_host(hostname: str) -> bool:
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise HTTPException(status_code=422, detail="自定义 Base URL 的主机无法解析") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            return False
    return bool(addresses)


def normalize_profile_input(provider: str, base_url: str | None, model: str) -> tuple[str, str, str]:
    provider = provider.strip().lower()
    model = model.strip()
    if provider not in {*PROVIDERS, CUSTOM_PROVIDER}:
        raise HTTPException(status_code=422, detail="不支持的模型供应商")
    if not model or len(model) > 160:
        raise HTTPException(status_code=422, detail="模型名不能为空且不能超过 160 个字符")
    if provider != CUSTOM_PROVIDER:
        return provider, PROVIDERS[provider], model
    candidate = (base_url or "").strip().rstrip("/")
    parsed = urlparse(candidate)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(status_code=422, detail="自定义 Base URL 必须是无查询参数的公网 HTTPS 地址")
    if not _public_host(parsed.hostname):
        raise HTTPException(status_code=422, detail="自定义 Base URL 不允许指向内网或保留地址")
    return provider, candidate, model


def profile_dict(row) -> dict:
    return {
        "id": int(row[0]), "name": row[1], "provider": row[2], "base_url": row[3],
        "model": row[4], "key_hint": row[5], "is_default": bool(row[6]),
        "input_price_per_million": row[7], "cached_input_price_per_million": row[8],
        "output_price_per_million": row[9], "created_at": row[10], "updated_at": row[11],
    }


def list_profiles(user_id: int) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT id,name,provider,base_url,model,key_hint,is_default,input_price_per_million,
                                  cached_input_price_per_million,output_price_per_million,created_at,updated_at
                           FROM user_model_profiles WHERE user_id=%s ORDER BY is_default DESC,updated_at DESC,id DESC""", (user_id,))
            return [profile_dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _profile_from_row(row) -> ModelProfile:
    return ModelProfile(id=int(row[0]), user_id=int(row[1]), name=row[2], provider=row[3], base_url=row[4], model=row[5], api_key=decrypt_api_key(row[6]), input_price_per_million=row[7], cached_input_price_per_million=row[8], output_price_per_million=row[9])


def resolve_default_profile(user_id: int) -> ModelProfile:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT id,user_id,name,provider,base_url,model,encrypted_api_key,input_price_per_million,
                                  cached_input_price_per_million,output_price_per_million
                           FROM user_model_profiles WHERE user_id=%s AND is_default""", (user_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=422, detail="该任务所有者尚未配置默认模型，请先在我的账号中完成配置")
    return _profile_from_row(row)


def client_for(profile: ModelProfile, *, timeout: float = 120.0, track_usage: bool = True) -> OpenAI:
    client = OpenAI(api_key=profile.api_key, base_url=profile.base_url, timeout=timeout, max_retries=1)
    if not track_usage:
        return client
    from api.services.ai_usage import MeteredClient
    return MeteredClient(client, profile)  # type: ignore[return-value]


@contextmanager
def use_default_profile(user_id: int, **usage_context):
    token = _active_profile.set(resolve_default_profile(user_id))
    usage_manager = None
    try:
        if usage_context:
            from api.services.ai_usage import use_usage_context
            usage_manager = use_usage_context(**usage_context)
            usage_manager.__enter__()
        yield _active_profile.get()
    finally:
        if usage_manager:
            usage_manager.__exit__(None, None, None)
        _active_profile.reset(token)


def active_profile() -> ModelProfile:
    profile = _active_profile.get()
    if not profile:
        raise RuntimeError("当前 AI 调用未绑定用户模型配置")
    return profile


def bind_default_profile_iterator(user_id: int, iterator, **usage_context):
    """Keep a profile attached to every ``next`` of a sync SSE iterator.

    Starlette may advance a streaming generator on different worker threads.
    ContextVar values are intentionally thread-context-local, so a normal
    ``with use_default_profile`` around a generator is not sufficient.
    """
    profile = resolve_default_profile(user_id)
    while True:
        token = _active_profile.set(profile)
        usage_manager = None
        try:
            if usage_context:
                from api.services.ai_usage import use_usage_context
                usage_manager = use_usage_context(**usage_context)
                usage_manager.__enter__()
            item = next(iterator)
        except StopIteration:
            return
        finally:
            if usage_manager:
                usage_manager.__exit__(None, None, None)
            _active_profile.reset(token)
        yield item
