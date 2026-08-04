from contextlib import asynccontextmanager
import logging
import os
import socket
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from api.routers import periods, categories, items, upload, quota, measure, boq, manual_boq, quota2024, building_standard_2024, bs2024_match, prompt_templates, standard_reference_prices, pricing_kb, pricing_kb_admin, pricing_task

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
    stop_event = threading.Event()
    worker_thread: threading.Thread | None = None
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
    try:
        yield
    finally:
        stop_event.set()
        if worker_thread:
            worker_thread.join(timeout=5)


app = FastAPI(title="深圳信息价管理系统", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(periods.router, prefix="/api", tags=["periods"])
app.include_router(categories.router, prefix="/api", tags=["categories"])
app.include_router(items.router, prefix="/api", tags=["items"])
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(quota.router, prefix="/api", tags=["quota"])
app.include_router(quota2024.router, prefix="/api", tags=["quota2024"])
app.include_router(measure.router, prefix="/api", tags=["measure"])
app.include_router(boq.router, prefix="/api", tags=["boq"])
app.include_router(manual_boq.router, prefix="/api", tags=["manual_boq"])
app.include_router(building_standard_2024.router, prefix="/api", tags=["building_standard_2024"])
app.include_router(bs2024_match.router, prefix="/api", tags=["bs2024-match"])
app.include_router(prompt_templates.router, prefix="/api", tags=["prompt-templates"])
app.include_router(standard_reference_prices.router, prefix="/api", tags=["standard-reference-prices"])
app.include_router(pricing_kb.router, prefix="/api", tags=["pricing-kb"])
app.include_router(pricing_kb_admin.router, prefix="/api", tags=["pricing-kb-admin"])
app.include_router(pricing_task.router, prefix="/api", tags=["pricing-task"])
