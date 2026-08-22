from contextlib import asynccontextmanager
import logging
import os
import socket
import threading

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

from api.routers import auth, model_profiles, periods, categories, items, upload, quota, measure, boq, manual_boq, quota2024, building_standard_2024, bs2024_match, prompt_templates, standard_reference_prices, pricing_kb, pricing_kb_admin, pricing_task
from api.auth import SESSION_COOKIE, apply_auth_schema, is_auth_enabled, require_authenticated, require_business_access, require_admin, require_system_access, resolve_session
from db.connection import DatabasePoolBusyError

from api.services.pricing_kb_import_admin import run_next_job

logger = logging.getLogger(__name__)


def _pricing_kb_worker_loop(stop_event: threading.Event) -> None:
    worker_id = f"api:{socket.gethostname()}:{os.getpid()}"
    while not stop_event.is_set():
        try:
            job_id = run_next_job(worker_id)
        except Exception:
            logger.exception("pricing knowledge import job failed")
            stop_event.wait(2)
            continue
        if job_id is None:
            stop_event.wait(2)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if is_auth_enabled():
        apply_auth_schema()
    pricing_task.initialize_schema()
    stop_event = threading.Event()
    worker_thread: threading.Thread | None = None
    background_worker_thread: threading.Thread | None = None
    disabled_values = {"0", "false", "no"}
    worker_enabled = os.getenv("PRICING_KB_EMBEDDED_WORKER", "1").strip().lower() not in disabled_values
    if worker_enabled:
        worker_thread = threading.Thread(
            target=_pricing_kb_worker_loop,
            args=(stop_event,),
            name="pricing-kb-import-worker",
            daemon=True,
        )
        worker_thread.start()
    background_worker_enabled = os.getenv("PRICING_BACKGROUND_BATCH_EMBEDDED_WORKER", "1").strip().lower() not in disabled_values
    if background_worker_enabled:
        background_worker_thread = threading.Thread(
            target=pricing_task.run_background_pricing_worker,
            args=(stop_event,),
            name="background-pricing-worker",
            daemon=True,
        )
        background_worker_thread.start()
    try:
        yield
    finally:
        stop_event.set()
        if worker_thread:
            worker_thread.join(timeout=5)
        if background_worker_thread:
            background_worker_thread.join(timeout=5)


app = FastAPI(title="深圳信息价管理系统", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def attach_authenticated_user(request: Request, call_next):
    if is_auth_enabled() and request.url.path.startswith("/api/"):
        request.state.user = resolve_session(request.cookies.get(SESSION_COOKIE))
    try:
        return await call_next(request)
    except DatabasePoolBusyError:
        return JSONResponse(status_code=503, content={"detail": "数据库繁忙，请稍后重试"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(model_profiles.router, prefix="/api", tags=["model-profiles"], dependencies=[Depends(require_authenticated)])
for module, tag in ((periods, "periods"), (categories, "categories"), (items, "items"), (quota, "quota"), (quota2024, "quota2024"), (measure, "measure"), (building_standard_2024, "building_standard_2024"), (standard_reference_prices, "standard-reference-prices"), (pricing_kb, "pricing-kb")):
    app.include_router(module.router, prefix="/api", tags=[tag], dependencies=[Depends(require_authenticated)])
for module, tag in ((upload, "upload"), (prompt_templates, "prompt-templates")):
    app.include_router(module.router, prefix="/api", tags=[tag], dependencies=[Depends(require_system_access)])
for module, tag in ((boq, "boq"), (manual_boq, "manual_boq"), (bs2024_match, "bs2024-match"), (pricing_task, "pricing-task")):
    app.include_router(module.router, prefix="/api", tags=[tag], dependencies=[Depends(require_business_access)])
app.include_router(pricing_kb_admin.router, prefix="/api", tags=["pricing-kb-admin"], dependencies=[Depends(require_admin)])
