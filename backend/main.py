"""FastAPI entry point. Run from the repository root:

    uvicorn backend.main:app --reload
"""

import logging
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


def _seed_sample_documents() -> None:
    """Ensure all sample PDFs in sample_pdfs are indexed directly without copying to uploads."""
    try:
        sample_dir = Path(settings.sample_dir)
        if not sample_dir.is_dir():
            return

        counts = vector_store.read_file_chunk_counts(
            Path(settings.chroma_dir), settings.chroma_collection_name
        )

        for pdf in sorted(sample_dir.rglob("*.pdf"), key=lambda p: p.name.lower()):
            if pdf.is_file() and counts.get(pdf.name, 0) == 0:
                try:
                    pages = pdf_loader.extract_pages(pdf, pdf.name)
                    pipeline.ingest_pages(pdf.name, pages)
                    logger.info("Ingested sample document %s directly from %s", pdf.name, pdf.parent.name)
                except Exception as e:
                    logger.warning("Could not auto-ingest %s: %s", pdf.name, e)
    except Exception as exc:
        logger.warning("Sample document seeding failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Runs once when the server starts (before `yield`) and stops (after)."""
    logger.info(
        "Starting %s v%s (log level: %s)",
        settings.app_name,
        settings.app_version,
        settings.log_level.upper(),
    )
    _seed_sample_documents()
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
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
