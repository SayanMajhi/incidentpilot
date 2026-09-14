"""IncidentPilot FastAPI application."""

from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import API_VERSION, router
from backend.config import get_settings


load_dotenv()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="IncidentPilot API",
        description="Evidence-driven, bounded incident diagnosis and remediation.",
        version=API_VERSION,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )
    app.include_router(router)
    return app


app = create_app()
