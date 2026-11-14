"""Measure real token counts of chunks with the REAL embedding model.

Run from the repository root, on a machine that can download the model:

    python -m scripts.measure_tokens path/to/a.pdf [more.pdf ...] [--size 800 --overlap 120]

For every PDF it chunks the pages with the given settings (defaults: the
configured CHUNK_SIZE / CHUNK_OVERLAP), counts tokens with the model's own
tokenizer (special tokens included) and prints the distribution and how many
chunks exceed the model's limit. Nothing is embedded or stored. Use the output
to decide whether 800/120 characters is a safe starting point (D-002, D-032).
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

from backend.config import settings
from backend.ingestion.chunker import chunk_pages
from backend.ingestion.pdf_loader import extract_pages
from backend.retrieval.embedder import Embedder
from backend.retrieval.st_embedder import SentenceTransformerEmbedder


def percentile(sorted_values: list[int], fraction: float) -> int:
    return sorted_values[min(len(sorted_values) - 1, int(fraction * len(sorted_values)))]


def measure(pdfs: list[Path], embedder: Embedder, size: int, overlap: int) -> dict:
    """Token statistics over all chunks of all PDFs."""
    counts: list[int] = []
    chars: list[int] = []
    for pdf in pdfs:
        for chunk in chunk_pages(extract_pages(pdf, pdf.name), size, overlap):
            counts.append(embedder.count_tokens(chunk.text))
            chars.append(len(chunk.text))
    if not counts:
        return {"chunks": 0}
    ordered = sorted(counts)
    limit = embedder.max_tokens
    return {
        "chunks": len(counts),
        "limit": limit,
        "min": ordered[0],
        "median": int(statistics.median(ordered)),
        "p95": percentile(ordered, 0.95),
        "max": ordered[-1],
        "over_limit": sum(1 for c in counts if c > limit),
        "chars_per_token": round(sum(chars) / sum(counts), 2),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("pdfs", nargs="+", type=Path)
    parser.add_argument("--size", type=int, default=settings.chunk_size)
    parser.add_argument("--overlap", type=int, default=settings.chunk_overlap)
    args = parser.parse_args(argv)

    embedder = SentenceTransformerEmbedder(settings.embedding_model, settings.embedding_batch_size)
    stats = measure(args.pdfs, embedder, args.size, args.overlap)
    print(f"model={settings.embedding_model} chunk_size={args.size} overlap={args.overlap}")
    for key, value in stats.items():
        print(f"{key}: {value}")
    return 1 if stats.get("over_limit") else 0


if __name__ == "__main__":
    sys.exit(main())
