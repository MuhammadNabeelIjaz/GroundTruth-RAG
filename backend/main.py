"""FastAPI entry point. Run from the repository root:

    uvicorn backend.main:app --reload
"""

import gc
import logging
import re
import shutil
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
import threading

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.chat import router as chat_router
from backend.api.conversations import router as conversations_router
from backend.api.documents import router as documents_router
from backend.api.search import router as search_router
from backend.config import settings
from backend.ingestion import pdf_loader, pipeline
from backend.logging_config import configure_logging
from backend.retrieval import vector_store
from backend.schemas import HealthResponse

configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

_SEED_LOCK = threading.Lock()


def _seed_sample_documents() -> None:
    """Ensure sample PDFs in sample_pdfs are indexed directly without copying to uploads."""
    if not _SEED_LOCK.acquire(blocking=False):
        logger.info("Sample document seeding is already in progress; skipping duplicate run.")
        return
    try:
        sample_dir = Path(settings.sample_dir)
        if not sample_dir.is_dir():
            return

        counts = vector_store.read_file_chunk_counts(
            Path(settings.chroma_dir), settings.chroma_collection_name
        )

        # Process smaller documents first to get the index responsive quickly
        all_pdfs = [p for p in sample_dir.rglob("*.pdf") if p.is_file()]
        all_pdfs.sort(key=lambda p: (p.stat().st_size, p.name.lower()))

        for pdf in all_pdfs:
            if counts.get(pdf.name, 0) == 0:
                try:
                    pages = pdf_loader.extract_pages(pdf, pdf.name)
                    pipeline.ingest_pages(pdf.name, pages)
                    logger.info("Ingested sample document %s directly from %s", pdf.name, pdf.parent.name)
                except Exception as e:
                    logger.warning("Could not auto-ingest %s: %s", pdf.name, e)
                finally:
                    gc.collect()
                    time.sleep(0.5)  # Yield CPU to uvicorn between documents
    except Exception as exc:
        logger.warning("Sample document seeding failed: %s", exc)
    finally:
        _SEED_LOCK.release()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Runs once when the server starts (before `yield`) and stops (after)."""
    logger.info(
        "Starting %s v%s (log level: %s)",
        settings.app_name,
        settings.app_version,
        settings.log_level.upper(),
    )
    # Seed sample PDFs in a background thread so the server binds to $PORT immediately
    seeder_thread = threading.Thread(
        target=_seed_sample_documents, daemon=True, name="seed_sample_docs"
    )
    seeder_thread.start()
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)


def _is_allowed_origin(origin: str | None) -> bool:
    if not origin:
        return False
    if "*" in settings.cors_origins or origin in settings.cors_origins:
        return True
    if settings.cors_origin_regex and re.match(settings.cors_origin_regex, origin):
        return True
    return False


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Ensure unhandled 500 errors return clean JSON and preserve CORS headers without leaking secrets."""
    logger.exception("Unhandled server exception on %s %s: %s", request.method, request.url.path, exc)
    origin = request.headers.get("origin")
    headers: dict[str, str] = {}
    if _is_allowed_origin(origin):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Access-Control-Allow-Methods"] = "*"
        headers["Access-Control-Allow-Headers"] = "*"
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."},
        headers=headers,
    )

is_wildcard = "*" in settings.cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if is_wildcard else settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex if not is_wildcard else None,
    allow_credentials=False if is_wildcard else True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents_router)
app.include_router(search_router)
app.include_router(chat_router)
app.include_router(conversations_router)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Confirm that the backend is running."""
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
    )
