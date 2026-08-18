"""认证、角色和业务对象的所有权校验。"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock

from fastapi import HTTPException, Request

from db.connection import get_connection
from db.schema_lock import acquire_schema_transaction_lock

logger = logging.getLogger(__name__)
SESSION_COOKIE = "qmind_session"
SESSION_DAYS = 30
_schema_lock = Lock()
_schema_ready = False
_OWNERSHIP_TABLES = (
    "boq_projects",
    "manual_boq_projects",
    "pricing_tasks",
    "pricing_task_batches",
)


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool = True

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def is_auth_enabled() -> bool:
    """认证默认开启；仅本地测试可通过 AUTH_ENABLED=0 暂时关闭。"""
    return os.getenv("AUTH_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


TEST_USER = CurrentUser(id=0, username="test-admin", display_name="测试管理员", role="admin")


def _password_hasher():
    try:
        from argon2 import PasswordHasher
    except ImportError as exc:  # pragma: no cover - deployment configuration
        raise RuntimeError("缺少 argon2-cffi，请先安装 requirements.txt 中的依赖") from exc
    return PasswordHasher()


def validate_password(password: str) -> str:
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="密码至少需要 8 位")
    return password


def hash_password(password: str) -> str:
    return _password_hasher().hash(validate_password(password))


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return bool(_password_hasher().verify(password_hash, password))
    except Exception:
        return False


def apply_auth_schema() -> None:
    """初始化认证表，并在首次部署时创建由环境变量提供的管理员。"""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        conn = get_connection()
        try:
            from pathlib import Path
            acquire_schema_transaction_lock(conn)
            with conn.cursor() as cur:
                cur.execute(Path(__file__).parent.parent.joinpath("db", "schema_auth.sql").read_text(encoding="utf-8"))
                cur.execute("SELECT COUNT(*) FROM users")
                user_count = int(cur.fetchone()[0])
                if user_count == 0:
                    username = (os.getenv("AUTH_BOOTSTRAP_USERNAME") or "admin").strip().lower()
                    password = os.getenv("AUTH_BOOTSTRAP_PASSWORD")
                    if password:
                        cur.execute(
                            "INSERT INTO users(username,display_name,password_hash,role) VALUES(%s,%s,%s,'admin') RETURNING id",
                            (username, "系统管理员", hash_password(password)),
                        )
                        admin_id = int(cur.fetchone()[0])
                        for table in ("boq_projects", "manual_boq_projects", "pricing_tasks", "pricing_task_batches"):
                            cur.execute("SELECT to_regclass(%s)", (table,))
                            if cur.fetchone()[0]:
                                cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS owner_user_id INT REFERENCES users(id)")
                                cur.execute(f"UPDATE {table} SET owner_user_id=%s WHERE owner_user_id IS NULL", (admin_id,))
                    else:
                        logger.warning("认证表已初始化，但尚未创建管理员：请配置 AUTH_BOOTSTRAP_PASSWORD 后重启")
            conn.commit()
            _schema_ready = True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _missing_ownership_objects(conn) -> list[tuple[str, bool, bool]]:
    """Return existing tables that still need an owner column or index."""
    missing: list[tuple[str, bool, bool]] = []
    with conn.cursor() as cur:
        for table in _OWNERSHIP_TABLES:
            cur.execute("SELECT to_regclass(%s)", (table,))
            relation = cur.fetchone()[0]
            if not relation:
                continue
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM pg_attribute
                    WHERE attrelid=%s::regclass
                      AND attname='owner_user_id'
                      AND NOT attisdropped
                )
                """,
                (table,),
            )
            has_column = bool(cur.fetchone()[0])
            cur.execute("SELECT to_regclass(%s)", (f"idx_{table}_owner",))
            has_index = bool(cur.fetchone()[0])
            if not has_column or not has_index:
                missing.append((table, has_column, has_index))
    return missing


def ensure_ownership_schema(conn) -> None:
    """补齐延迟创建表的所有权结构；已就绪时不执行任何 DDL。"""
    try:
        missing = _missing_ownership_objects(conn)
        if missing:
            # End the catalog-inspection transaction before waiting for the
            # advisory lock, so it cannot retain relation locks needed by the
            # process currently performing the migration.
            conn.commit()
            # Recheck after obtaining the cluster-wide lock because another API
            # process may have completed the same migration while we waited.
            acquire_schema_transaction_lock(conn)
            for table, has_column, has_index in _missing_ownership_objects(conn):
                with conn.cursor() as cur:
                    if not has_column:
                        cur.execute(
                            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS owner_user_id INT REFERENCES users(id)"
                        )
                    if not has_index:
                        cur.execute(
                            f"CREATE INDEX IF NOT EXISTS idx_{table}_owner ON {table}(owner_user_id)"
                        )

        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE role='admin' AND is_active ORDER BY id LIMIT 1")
            admin = cur.fetchone()
            if admin:
                for table in _OWNERSHIP_TABLES:
                    cur.execute("SELECT to_regclass(%s)", (table,))
                    if cur.fetchone()[0]:
                        cur.execute(
                            f"UPDATE {table} SET owner_user_id=%s WHERE owner_user_id IS NULL",
                            (admin[0],),
                        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: int) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO auth_sessions(user_id,token_hash,expires_at) VALUES(%s,%s,%s)", (user_id, _digest(token), expires_at))
        conn.commit()
    finally:
        conn.close()
    return token, expires_at


def revoke_sessions(user_id: int) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE auth_sessions SET revoked_at=NOW() WHERE user_id=%s AND revoked_at IS NULL", (user_id,))
        conn.commit()
    finally:
        conn.close()


def revoke_session(token: str | None) -> None:
    if not token:
        return
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE auth_sessions SET revoked_at=NOW() WHERE token_hash=%s AND revoked_at IS NULL", (_digest(token),))
        conn.commit()
    finally:
        conn.close()


def resolve_session(token: str | None) -> CurrentUser | None:
    if not token:
        return None
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT u.id,u.username,u.display_name,u.role,u.is_active
                   FROM auth_sessions s JOIN users u ON u.id=s.user_id
                   WHERE s.token_hash=%s AND s.revoked_at IS NULL AND s.expires_at>NOW()""",
                (_digest(token),),
            )
            row = cur.fetchone()
        return CurrentUser(*row) if row and row[4] else None
    finally:
        conn.close()


def current_user(request: Request) -> CurrentUser:
    if not is_auth_enabled():
        return TEST_USER
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def require_authenticated(request: Request) -> CurrentUser:
    return current_user(request)


def require_business_access(request: Request) -> CurrentUser:
    user = current_user(request)
    if request.method not in {"GET", "HEAD", "OPTIONS"} and user.role == "reader":
        raise HTTPException(status_code=403, detail="只读账号无修改权限")
    _enforce_path_ownership(request, user)
    return user


def _enforce_path_ownership(request: Request, user: CurrentUser) -> None:
    """为带资源 ID 的业务路由提供最后一道统一所有权校验。

    具体列表和创建接口仍各自过滤/写入 owner；此处保护深层运行、结果和流式端点，
    防止仅凭 URL 中的子资源 ID 越权。
    """
    if user.is_admin:
        return
    params = request.path_params
    path = request.url.path
    checks: list[tuple[str, int, bool]] = []
    if "task_id" in params:
        checks.append(("pricing_tasks", int(params["task_id"]), False))
    if "batch_id" in params and "pricing-task" in path:
        checks.append(("pricing_task_batches", int(params["batch_id"]), False))
    conn = None
    try:
        if checks or any(key in params for key in ("run_id", "item_run_id", "match_id", "item_id", "project_id")):
            conn = get_connection()
        for table, asset_id, _ in checks:
            with conn.cursor() as cur:
                cur.execute(f"SELECT 1 FROM {table} WHERE id=%s AND owner_user_id=%s AND status <> 'deleted'", (asset_id, user.id))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="业务对象不存在")
        with conn.cursor() if conn else _null_cursor() as cur:
            if "run_id" in params:
                cur.execute("SELECT t.owner_user_id FROM pricing_task_runs r JOIN pricing_tasks t ON t.id=r.task_id WHERE r.id=%s", (params["run_id"],))
                row = cur.fetchone()
                if row is None:
                    cur.execute("SELECT p.owner_user_id FROM bs2024_match_runs r JOIN boq_projects p ON p.id=r.project_id WHERE r.id=%s", (params["run_id"],))
                    row = cur.fetchone()
                if not row or row[0] != user.id:
                    raise HTTPException(status_code=404, detail="运行记录不存在")
            if "item_run_id" in params:
                cur.execute("SELECT b.owner_user_id FROM pricing_task_batch_item_runs r JOIN pricing_task_batches b ON b.id=r.batch_id WHERE r.id=%s", (params["item_run_id"],))
                row = cur.fetchone()
                if not row or row[0] != user.id:
                    raise HTTPException(status_code=404, detail="运行记录不存在")
            if "batch_id" in params and path.startswith("/api/debug-batches"):
                cur.execute("SELECT p.owner_user_id FROM debug_batches d JOIN boq_projects p ON p.id=d.boq_project_id WHERE d.id=%s", (params["batch_id"],))
                row = cur.fetchone()
                if not row or row[0] != user.id:
                    raise HTTPException(status_code=404, detail="调试批次不存在")
            if "match_id" in params:
                cur.execute("SELECT p.owner_user_id FROM boq_quota_matches m JOIN boq_projects p ON p.id=m.project_id WHERE m.id=%s", (params["match_id"],))
                row = cur.fetchone()
                if row is None and path.startswith("/api/bs2024-match/"):
                    cur.execute("SELECT p.owner_user_id FROM bs2024_quota_matches m JOIN bs2024_match_runs r ON r.id=m.run_id JOIN boq_projects p ON p.id=r.project_id WHERE m.id=%s", (params["match_id"],))
                    row = cur.fetchone()
                if not row or row[0] != user.id:
                    raise HTTPException(status_code=404, detail="匹配记录不存在")
            if "item_id" in params and path.startswith("/api/boq/"):
                cur.execute("SELECT p.owner_user_id FROM boq_items i JOIN boq_projects p ON p.id=i.project_id WHERE i.id=%s", (params["item_id"],))
                row = cur.fetchone()
                if not row or row[0] != user.id:
                    raise HTTPException(status_code=404, detail="清单项不存在")
            if "project_id" in params:
                table = "manual_boq_projects" if path.startswith("/api/manual-boq/") else "boq_projects"
                cur.execute(f"SELECT owner_user_id FROM {table} WHERE id=%s", (params["project_id"],))
                row = cur.fetchone()
                if not row or row[0] != user.id:
                    raise HTTPException(status_code=404, detail="工程不存在")
    finally:
        if conn:
            conn.close()


class _null_cursor:
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False


def require_admin(request: Request) -> CurrentUser:
    user = current_user(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def require_system_access(request: Request) -> CurrentUser:
    user = current_user(request)
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def require_project_owner(conn, user: CurrentUser, project_id: int, *, manual: bool = False) -> None:
    if user.is_admin:
        return
    table = "manual_boq_projects" if manual else "boq_projects"
    with conn.cursor() as cur:
        cur.execute(f"SELECT 1 FROM {table} WHERE id=%s AND owner_user_id=%s", (project_id, user.id))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="工程不存在")


def require_task_owner(conn, user: CurrentUser, entity_id: int, *, batch: bool = False) -> None:
    if user.is_admin:
        return
    table = "pricing_task_batches" if batch else "pricing_tasks"
    with conn.cursor() as cur:
        cur.execute(f"SELECT 1 FROM {table} WHERE id=%s AND owner_user_id=%s AND status <> 'deleted'", (entity_id, user.id))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="任务不存在")
