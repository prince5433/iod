"""
FastAPI application entry point.

Serves:
- REST API at /api/*
- Static frontend files at /
- Interactive API docs at /docs (Swagger UI)
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os
import mimetypes

# Fix MIME types for Linux deployments (Render, etc.)
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")

from .database import init_db
from .routes import router



@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="Transaction & Ranking System",
    description=(
        "A financial transaction processing system with multi-factor ranking. "
        "Features idempotent transactions, rate limiting, and anti-manipulation ranking."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow all origins for demo purposes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)

# Serve frontend static files
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        """Serve the frontend index.html."""
        return FileResponse(os.path.join(frontend_dir, "index.html"))
