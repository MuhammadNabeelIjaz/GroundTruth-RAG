# GroundTruth - React Frontend

Modern, self-contained **React 19 + TypeScript + Vite + Tailwind CSS** frontend for GroundTruth: AI Document Assistant with Source-Backed Answers (RAG).

## Key Features

- **Claude-Inspired Conversational UI**: Fluid message typography, natural paragraph spacing, and seamless timeline.
- **Unified Chat Composer**: Integrated PDF attachment button inside the input pill, drag-and-drop file upload, file preview chips, auto-expanding textarea, and Enter-to-send.
- **Verifiable Document Citations**: Expandable source drawer with document names, page tags, 3-tier similarity badges (>=70% green, 40-69% amber, <40% red), and full passage view. Clickable inline `[Passage N]` chips scroll smoothly to supporting source cards.
- **Grounding Warnings**: Prominent callout banner for questions where documents lack sufficient evidence, refusing speculation.
- **Collapsible Sidebar**: Pinned Strict RAG status card, document drawer with PDF badges, conversation history with rename/delete popover menus.
- **Dedicated Document Library**: Full-screen table view with upload dropzone, search filter, and document deletion.
- **Zero Python Dependencies**: Installs and builds completely independently using standard `npm`.

## Quick Start

### 1. Install Dependencies
```bash
npm install
```

### 2. Configure Environment
Create a `.env` file (or copy `.env.example`):
```bash
# Optional: Set backend URL (defaults to Vite proxy pointing to http://127.0.0.1:8000)
VITE_API_BASE_URL=http://127.0.0.1:8000
```

### 3. Run Development Server
```bash
npm run dev
```
The application will start on `http://localhost:5173`.

### 4. Build for Production
```bash
npm run build
```
The static production assets will be built into the `dist/` folder.
