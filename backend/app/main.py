"""FastAPI 应用入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import assessments, contact_requests, health
from app.config import settings


app = FastAPI(
    title="OncoTriage — Breast Cancer Side-Effect Triage Agent",
    version=__version__,
    description="MVP — 患者副作用自评分诊系统",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由
app.include_router(health.router, tags=["health"])
app.include_router(assessments.router, prefix="/api/v1", tags=["assessments"])
app.include_router(contact_requests.router, prefix="/api/v1", tags=["contact_requests"])
