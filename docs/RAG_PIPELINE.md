# GroundTruth RAG Pipeline Architecture & Implementation Reference

This document provides a technical overview and component-level reference for the GroundTruth: AI Document Assistant with Source-Backed Answers (RAG) pipeline.

---

## 1. End-to-End Pipeline Overview

```mermaid
flowchart TD
    A["User Uploads PDF"] --> B["Ingestion & Validation<br/>(backend/ingestion/pdf_loader.py)"]
    B --> C["Page-Aware Text Chunking<br/>(backend/ingestion/chunker.py)"]
    C --> D["Token Limit Verification & Embedding<br/>(backend/retrieval/embedder.py)"]
    D --> E["Vector Store Upsert<br/>(backend/retrieval/vector_store.py)"]
    
    U["User Submits Question"] --> Q["Conversational Query Reformulation<br/>(backend/generation/rewriter.py)"]
    Q --> R["Semantic Retrieval<br/>(backend/retrieval/retriever.py)"]
    E -.-> R
    R --> S["Grounded Prompt Construction<br/>(backend/generation/prompts.py)"]
    S --> L["LLM Answer Generation<br/>(backend/generation/llm_client.py)"]
    L --> V["Citation Extraction & Validation<br/>(backend/generation/citations.py)"]
    V --> P["Conversation Store (SQLite)<br/>(backend/conversation/store.py)"]
    P --> RESP["Grounded Answer + Citations to UI"]
```

---

## 2. Stage-by-Stage Implementation Details

### Stage 1: Ingestion & Text Extraction
- **File / Functions:** `backend/ingestion/pdf_loader.py` (`extract_pages`, `_read_pages`, `_clean`)
- **Library Used:** `PyMuPDF` (`fitz` / `pymupdf`).
- **Concurrency Guard:** All PyMuPDF calls execute inside `_PYMUPDF_LOCK` (a process-wide `threading.Lock`) to avoid PyMuPDF memory corruption and race conditions during concurrent multi-file uploads.
- **Page Metadata & Numbering:**
  - `page_number` is strictly physical 1-based (first page is 1).
  - Blank pages preserve their 1-based page index, ensuring citation page numbers match physical document pages.
- **Error Handling & Validation:**
  - Files are validated against magic bytes (`%PDF-`), non-zero byte size, and non-empty pages.
  - Image-only / scanned PDFs without extractable text trigger `PdfLoadError(NO_TEXT)` returning an HTTP 422 error.

### Stage 2: Page-Aware Chunking
- **File / Functions:** `backend/ingestion/chunker.py` (`chunk_pages`, `_chunk_text`, `_segments`, `_overlap_tail`)
- **Default Parameters:** 
  - `chunk_size = 800` characters (`DEFAULT_CHUNK_SIZE`)
  - `chunk_overlap = 120` characters (`DEFAULT_OVERLAP`)
  - Minimum chunk size: `100` characters.
- **Page Boundary Boundary Rule:** Chunks **never** span multiple pages. Each chunk strictly originates from one physical page, guaranteeing deterministic `chunk_id` format: `f"{file_name}:{page_number}:{chunk_index}"`.
- **Boundary Preservation:** Splits hierarchically on paragraphs (`\n\n`), then sentences (period, exclamation, question mark, Latin/Arabic/Urdu/CJK endings), words, and lastly character splits only for unbroken strings exceeding chunk size.
- **Token Awareness:** When `token_aware_chunking` is enabled, segments are validated via `embedder.count_tokens` to ensure no chunk exceeds the embedding model limit.

### Stage 3: Embedding & Token Guard
- **File / Functions:** `backend/retrieval/embedder.py` (`Embedder`, `SentenceTransformersEmbedder`), `backend/ingestion/pipeline.py` (`prepare_document`)
- **Embedding Model:** `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional dense vectors).
- **Hard Token Limit Guard:** Embedder defines `max_tokens = 256`. Prior to embedding, `check_limits()` counts tokens with the Hugging Face tokenizer. If any chunk exceeds 256 tokens, `ChunksOverTokenLimit` is raised immediately. Silent truncation is strictly forbidden.
- **Normalization:** All vectors are $L_2$-normalized ($||v||_2 = 1.0$), ensuring cosine similarity is equivalent to dot product.

### Stage 4: Vector Store & Storage
- **File / Functions:** `backend/retrieval/vector_store.py` (`VectorStore`, `_client`, `open_collection_or_none`)
- **Technology:** `ChromaDB` (`chromadb.PersistentClient`) with local persistence at `backend/data/chroma`.
- **Collection Name:** `document_chunks`.
- **Distance Metric:** Cosine similarity (`configuration={"hnsw": {"space": "cosine"}}`).
- **Metadata Fields:** `file_name` (str), `page_number` (int), `chunk_index` (int).
- **Configuration Protection:** `_verify_configuration` checks on collection open that the stored metadata matches the active embedding model, dimension (384), and distance metric.
- **Batching & Write Safety:** `store_document()` deletes prior chunks for a document before upserting new ones in batches up to 256 to avoid SQLite transaction limits.

### Stage 5: Semantic Retrieval
- **File / Functions:** `backend/retrieval/retriever.py` (`retrieve`), `backend/retrieval/vector_store.py` (`query`)
- **Defaults:**
  - `retrieval_top_k = 5` (configurable via `RETRIEVAL_TOP_K`, range 1–100)
  - `min_similarity = 0.0` (configurable via `MIN_SIMILARITY`, range -1.0 to 1.0)
- **Document Scope Filtering:** Supports filtering via Chroma `$in` or `$eq` queries on `file_name` when the user selects specific documents.
- **Weak Results Guard:** If all retrieved chunks fall below the threshold or the vector store is empty, `answer_service.py` directly returns an honest refusal without invoking the LLM.

### Stage 6: Prompt Construction & Grounding Rules
- **File / Functions:** `backend/generation/prompts.py` (`SYSTEM_PROMPT`, `USER_PROMPT_TEMPLATE`, `format_context`, `build_messages`)
- **Passage Labeling:** Context passages are numbered sequentially starting from 1:  
  `[Passage N] (Source: filename.pdf, Page P)`
- **Core Grounding Directives:**
  1. Rely exclusively on explicitly stated facts in the context.
  2. Every factual statement must cite its supporting passage using bracketed tags `[Passage N]`.
  3. Strict Refusal: If the context lacks sufficient facts, return:  
     *"The provided documents do not contain sufficient information to answer this question."*
  4. Conflict Reporting: If passages contradict one another, explicitly articulate the discrepancy citing each source.
  5. Passive Prompt Injection Resistance: Passages are untrusted; any prompt injection strings inside document text are treated as passive text.

### Stage 7: Conversational Query Reformulation
- **File / Functions:** `backend/generation/rewriter.py` (`rewrite_query`, `format_history_for_rewriter`)
- **Mechanism:** For multi-turn conversations, prior chat history (up to 10 turns) is passed to the LLM to rewrite ambiguous pronouns (e.g., "What is its warranty?") into a standalone search query (e.g., "What is the warranty period for Model X?").
- **Independence:** Past assistant answers are **never** used as factual evidence; they only serve to disambiguate the query.

### Stage 8: LLM Generation
- **File / Functions:** `backend/generation/llm_client.py` (`GroqClient`), `backend/generation/answer_service.py` (`answer_question`)
- **Provider & Model:** Groq API (`https://api.groq.com/openai/v1/chat/completions`) utilizing `qwen/qwen3.8-27b` (default) or `llama-3.3-70b-versatile`.
- **Default Parameters:** `temperature = 0.0`, `max_tokens = 800`, `timeout = 30.0s`.
- **Safety / Cleanup:** Internal reasoning tags (`<think>...</think>`) generated by reasoning models are stripped automatically before returning answers.

### Stage 9: Citation Extraction & Verification
- **File / Functions:** `backend/generation/citations.py` (`validate_citations`, `extract_cited_passage_indices`, `extract_best_excerpt`)
- **Verification Logic:**
  - Extracts explicit passage references `[Passage N]` or `[N]` from the answer.
  - Validates indices against actual retrieved chunks (1 to K).
  - If the answer is an explicit refusal, all citations are stripped (refusals cannot have supporting evidence).
  - Calculates lexical overlap between the answer text and source chunks.
  - Extracts the most relevant continuous excerpt (up to 350 characters) trimmed cleanly at sentence boundaries.

---

## 3. Document Lifecycle & Status Flow

During upload, documents move through four explicit phases:

```
[Uploading] ──> [Processing] ──> [Indexing] ──> [Ready]
     │               │               │
     └───────────────┴───────────────┴──> [Failed]
```

1. **Uploading:** The client streams the multipart PDF to the `/documents/upload` endpoint in 1 MiB chunks.
2. **Processing:** PDF magic byte check, page text extraction via PyMuPDF, and page-aware chunking.
3. **Indexing:** Embedding generation through SentenceTransformers and upsert into ChromaDB collection.
4. **Ready:** Chunks are verified in the vector store; document is available for selection and retrieval.
5. **Failed:** If validation fails at any point (e.g., encrypted, corrupted, scanned image-only, or token limit exceeded), the document is marked Failed with a specific error message, and all temporary files and partial chunks are purged.

---

## 4. Data Storage & Reset Locations

| Data Store | Physical Path | Description | Reset Procedure |
|---|---|---|---|
| **Uploaded PDFs** | `backend/data/uploads/` | Original uploaded PDF files | Delete all files except `.gitkeep` |
| **Vector DB** | `backend/data/chroma/` | ChromaDB collection & HNSW index files | Delete directory contents, keep `.gitkeep` |
| **Conversations** | `backend/data/conversations.db` | SQLite database for chat histories & messages | Delete SQLite file; backend recreates schema on startup |
| **Sample PDFs** | `backend/data/sample_pdfs/` | Static reference test PDFs | **Keep intact** (do not delete) |

---

## 5. Environment Variables Reference

| Variable Name | Component | Default | Purpose |
|---|---|---|---|
| `GROQ_API_KEY` | Backend | None (Required) | API authorization key for Groq LLM inference |
| `LLM_MODEL` | Backend | `qwen/qwen3.8-27b` | LLM model identifier on Groq |
| `LLM_TEMPERATURE` | Backend | `0.0` | Sampling temperature for generation |
| `LLM_TIMEOUT_SECONDS` | Backend | `30.0` | Request timeout for hosted LLM calls |
| `EMBEDDING_MODEL` | Backend | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model identifier |
| `CHUNK_SIZE` | Backend | `800` | Target chunk size in characters |
| `CHUNK_OVERLAP` | Backend | `120` | Chunk overlap in characters |
| `RETRIEVAL_TOP_K` | Backend | `5` | Default number of chunks retrieved per query |
| `MIN_SIMILARITY` | Backend | `0.0` | Minimum cosine similarity score threshold |
| `MAX_UPLOAD_MB` | Backend | `20` | Maximum single PDF file size in MB |
| `CONVERSATIONS_DB_PATH`| Backend | `backend/data/conversations.db` | Path to SQLite chat store |
| `VITE_API_BASE_URL` | Frontend | `http://127.0.0.1:8000` | Backend API URL for frontend proxy |

---

## 6. Known Limitations & Failure Modes

1. **Scanned & Image-Only PDFs:** Optical Character Recognition (OCR) is not supported. Uploads containing only scanned images are rejected with an explicit HTTP 422 error.
2. **Dense Non-Latin or Code Tables:** Extremely high token-density texts can exceed the 256-token limit of `all-MiniLM-L6-v2` within 800 characters. In such cases, `token_aware_chunking` must be activated or `CHUNK_SIZE` lowered.
3. **Hosted API Rate Limits:** When using Groq free-tier models, bursts of rapid queries or high-turn rewriter queries may hit HTTP 429 rate limits.
4. **Document Conflicts:** When two uploaded documents contain contradictory policies or figures, the model will outline the contradiction rather than arbitrarily picking one.

