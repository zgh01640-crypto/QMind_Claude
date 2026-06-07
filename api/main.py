from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import periods, categories, items, upload, quota, measure, boq, manual_boq, quota2024, building_standard_2024

app = FastAPI(title="深圳信息价管理系统", version="1.0.0")

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
