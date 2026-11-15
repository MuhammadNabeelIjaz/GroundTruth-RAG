# Production Deployment Guide (Render + Netlify)

This guide explains how to deploy the **GroundTruth RAG Assistant** with the **backend manually on Render** and the **frontend built locally and dropped onto Netlify**, with 100% provider-independent configuration flexibility.

---

## 1. Architecture & Provider-Independent Design

```
┌─────────────────────────────────┐           HTTPS (REST API)          ┌──────────────────────────────────┐
│        Frontend Client          │ ──────────────────────────────────> │         Backend Service          │
│   React 19 + Vite + Tailwind    │ <────────────────────────────────── │         FastAPI + Uvicorn        │
│  (Netlify Drop, S3, or any host)│           CORS_ORIGINS              │    (Render, Railway, or any VPS) │
└─────────────────────────────────┘                                     └──────────────────────────────────┘
```

The application is completely decoupled from any specific hosting provider:
- **No hardcoded domains**: Backend CORS origin checks read standard environment variables (`CORS_ORIGINS` and optional `CORS_ORIGIN_REGEX`).
- **Separation of Storage**: Sample reference PDFs (`sample_pdfs/`) remain in their seed folder and are indexed directly without copying into `uploads/`. User uploads stay in `uploads/`. Sample PDFs are protected against deletion.
- **Dynamic Backend Switching**: Frontend API calls read `localStorage` first, then `VITE_API_BASE_URL`. You can switch backend URLs on the fly from the in-app settings UI without rebuilding.

---

## 2. Step 1: Deploy Backend on Render (Manual Web Service)

1. Log into your [Render Dashboard](https://dashboard.render.com).
2. Click **New +** -> **Web Service**.
3. Connect your Git repository (`GroundTruth-RAG`).
4. Configure the Web Service settings:
   - **Name**: `groundtruth-rag-backend` (or your preferred name)
   - **Region**: Any region close to your users (e.g., `Oregon (US West)` or `Frankfurt (EU)`)
   - **Branch**: `main`
   - **Root Directory**: leave empty
   - **Environment / Runtime**: `Python 3`
   - **Build Command**:
     ```bash
     pip install --upgrade pip && pip install -r backend/requirements.txt
     ```
   - **Start Command**:
     ```bash
     uvicorn backend.main:app --host 0.0.0.0 --port $PORT
     ```
5. Configure **Environment Variables** in the Environment tab:
   | Variable | Value | Notes |
   | :--- | :--- | :--- |
   | `PYTHON_VERSION` | `3.11.9` | Ensures stable runtime dependencies |
   | `GROQ_API_KEY` | `gsk_...` | Your Groq API key for LLM generation |
   | `CORS_ORIGINS` | `*` or `https://<your-site>.netlify.app` | Comma-separated list of allowed origins, or `*` |
   | `LOG_LEVEL` | `INFO` | Standard application logging |

6. Click **Create Web Service**.
7. Once deployed, note down your Render backend URL (e.g., `https://groundtruth-rag-backend.onrender.com`).
8. Verify health by opening: `https://<your-backend-url>/health` in your browser. You should see:
   ```json
   {"status":"ok","service":"rag-qa-assistant","version":"0.1.0"}
   ```

---

## 3. Step 2: Build & Deploy Frontend (Netlify Drop)

Once you have your live Render backend URL:
1. In your local `frontend/` directory, set the backend URL in your environment:
   ```bash
   cd frontend
   ```
2. Build the production bundle:
   ```bash
   # Linux/macOS
   VITE_API_BASE_URL="https://<your-backend-url>" npm run build

   # Windows PowerShell
   $env:VITE_API_BASE_URL="https://<your-backend-url>"; npm run build
   ```
3. The build outputs to `frontend/dist`. Notice `frontend/dist/_redirects` is automatically included to support client-side SPA routing.
4. Log into [Netlify](https://app.netlify.com).
5. Go to **Sites** -> **Deploy manually** (Netlify Drop).
6. Drag and drop the `frontend/dist` folder directly into Netlify.

---

## 4. Connection Flexibility

### Switching Backend URLs Live in the Browser
If your Render URL changes or you deploy to another provider (e.g., Railway, Fly.io, AWS, or local `http://127.0.0.1:8000`), you **do not need to rebuild the frontend**:
1. Open your deployed frontend.
2. Click **Settings** (gear icon) -> navigate to the **About** tab.
3. Under **Backend Connection URL**, paste your new backend URL.
4. Click **Save & Connect**. The frontend immediately checks health and connects.
5. Click **Reset Default** anytime to revert to the build-time URL.
