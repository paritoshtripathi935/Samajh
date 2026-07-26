"""Samajh backend — FastAPI entrypoint.

Run locally:
    cd backend
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env   # then fill in SARVAM_API_KEY etc.
    uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.settings import settings

app = FastAPI(
    title="Samajh API",
    description="Filing-understanding backend — Sarvam Document Intelligence, cited Q&A, jump-to-source.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "samajh-api"}


app.include_router(router)
