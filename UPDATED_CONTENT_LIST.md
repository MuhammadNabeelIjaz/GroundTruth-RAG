# GroundTruth-RAG: Production Updates & Content List

**Project:** GroundTruth-RAG  
**Date:** November 15, 2026  
**Repository:** `MuhammadNabeelIjaz/GroundTruth-RAG` (`main` branch)  
**Frontend Deployment:** Netlify (`https://groundtruth-rag.netlify.app/`)  
**Backend Deployment:** Render (`https://groundtruth-rag-backend.onrender.com`)  

---

## 1. Summary of Changes by File

### Added Files:
- **`backend/tests/unit/test_cors.py`**: Added 7 comprehensive regression tests covering CORS headers on success, 404, 500, OPTIONS preflight, Netlify production origin, Netlify preview domains, and localhost origin.
- **`UPDATED_CONTENT_LIST.md`**: This inventory and production change summary document.

### Modified Files:
- **`backend/config.py`**:
  - Added `https://groundtruth-rag.netlify.app` directly to default `cors_origins`.
  - Added `cors_origin_regex = r"^https:\/\/.*\.netlify\.app$"` by default to permit Netlify branch and preview deploy subdomains.
  - Updated `_parse_cors_origins` validator to strip trailing slashes from origin strings.
  - Decreased default `embedding_batch_size` from 32 to 16 to reduce peak ONNX tensor activation memory.
- **`backend/main.py`**:
  - Added `_is_allowed_origin` helper validating origin against configured allowed origins and origin regex.
  - Enhanced `global_exception_handler` to explicitly attach `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, `Access-Control-Allow-Methods`, and `Access-Control-Allow-Headers` on 500 JSON responses.
  - Optimized `_seed_sample_documents` to seed smaller PDFs first, call `gc.collect()`, and add a 0.5s pause between files to yield CPU to Uvicorn and prevent memory accumulation.
- **`backend/retrieval/st_embedder.py`**:
  - Configured `_OnnxMiniLMAdapter` with `SessionOptions(intra_op_num_threads=1, inter_op_num_threads=1)` and pinned `CPUExecutionProvider` to eliminate multi-threaded host thread bloat and RAM consumption.
- **`frontend/src/services/api.ts`**:
  - Increased `checkHealth` timeout from 10,000 ms to 30,000 ms to handle Render free-tier cold-start latencies.
  - Added `checkHealthWithRetry(retries=3, delayMs=2000)` for resilient startup checks.
- **`frontend/src/context/ChatContext.tsx`**:
  - Used `api.checkHealthWithRetry(3, 2000)` in `refreshData` during initial mount.
  - Added a 2-consecutive-failures threshold to the 15-second heartbeat check before setting `isBackendConnected` to `false`.
- **`frontend/src/App.tsx`** *(Committed in `0489a4f`)*:
  - Replaced hardcoded localhost URL in disconnection banner with `{getApiBaseUrl() || 'configured backend'}`.
- **`frontend/src/components/SettingsModal.tsx`** *(Committed in `0489a4f`)*:
  - Updated API URL placeholder to point to the production Render URL.
- **`frontend/src/constants/copy.ts`** *(Committed in `0489a4f`)*:
  - Removed hardcoded port 8000 and localhost strings from UI copy.

---

## 2. Backend Fixes
1. **CORS Configuration Defaults:** The default configuration now permits `https://groundtruth-rag.netlify.app` and any Netlify preview subdomain without requiring manual Render environment variable overrides.
2. **Error CORS Header Preservation:** Unhandled 500 exceptions now return CORS headers on their JSON responses, preventing browsers from misinterpreting internal server errors as CORS violations.
3. **Render Free-Tier Memory & CPU Stabilization:**
   - Single-threaded ONNX session execution prevents worker thread proliferation on multi-core host VMs.
   - Paced document seeding with garbage collection stops the background task from pegging CPU at 100% and exceeding Render's 512 MB RAM limit.

---

## 3. Frontend Fixes
1. **Cold-Start Latency Tolerance:** Health check timeout increased to 30 seconds; initial mount retries up to 3 times before declaring the backend unreachable.
2. **Heartbeat Flapping Prevention:** A transient timeout no longer flips the UI to disconnected; 2 consecutive failures are required.
3. **Localhost Removal:** All hardcoded production references to `127.0.0.1:8000` and `localhost:8000` were eliminated from bundles and copy; stale localStorage development URLs are automatically purged when accessing production.

---

## 4. CORS Details
- **Allowed Production Origin:** `https://groundtruth-rag.netlify.app`
- **Allowed Regex:** `^https:\/\/.*\.netlify\.app$`
- **Allowed Development Origins:** `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000`, `http://127.0.0.1:3000`
- **Preflight Methods:** `DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT, QUERY`
- **Credentials:** Allowed (`true`)

---

## 5. Verification & Test Results
- **Backend Test Suite:** **556 passed, 1 skipped, 1 warning** (including 7 new CORS regression tests).
- **Frontend Production Build:** **Clean build** via Vite (`dist/assets/index-Bv3F0awF.js` 601.99 kB; zero occurrences of `127.0.0.1:8000` or `localhost:8000`).
- **Netlify Configuration Files:** `_redirects` (`/* /index.html 200`) and `_headers` verified present in `dist`.

---

## 6. Known Limitations
1. **Render Free Tier Spin-up (Cold Starts):** When the backend is inactive for more than 15 minutes, Render spins the container down to 0 instances. The first request takes 30–50 seconds while the container boots. The frontend retry logic handles this window, but the initial page load will take longer.
2. **Ephemeral Disk Storage:** On Render Free instances, disk changes do not persist across container reboots. Seed sample PDFs are re-indexed into in-memory/ephemeral Chroma on boot.

---

## 7. Required Deployment Steps
1. **Backend (Render):** Automatically deploys upon pushing this commit to `origin main` (if configured for Auto-Deploy On Commit).
2. **Frontend (Netlify):** Manually upload the freshly generated `frontend/dist` directory to the Netlify site deploy area (`https://app.netlify.com/`).

---

## 8. Commit Information
- **Commit Message:** `fix: resolve production CORS, stabilize memory limits, and add cold-start retries`
- **Branch:** `main`
- **Remote:** `origin` (`MuhammadNabeelIjaz/GroundTruth-RAG`)
