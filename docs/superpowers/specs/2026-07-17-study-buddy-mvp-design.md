# Study Buddy MVP — Design

Date: 2026-07-17
Status: Approved (mock interview module deferred to a later phase)

## Goal

A fully local, single-user study workspace for a 16GB MacBook Air. Capture lectures,
documents and screenshots; transcribe, OCR, classify and turn them into structured
notes; search and chat over the notes with citations; generate audiobooks from notes.

## Constraints

- Everything runs locally. LLM served by LM Studio (OpenAI-compatible API), configured
  via `.env` (base URL, API key, model name).
- Hardware budget: 16GB unified memory, must coexist with a 4B LLM. Every other model
  must be lightweight.
- MVP simplicity: no external DB servers, no multi-device sync, no subagents/services.
  One repo, plain files + SQLite + LanceDB.

## Components

### 1. Overlay buddy (`buddy/`)

macOS menu-bar app built with `rumps`. Menu actions:

- **Capture screenshot** — runs `screencapture -i` (interactive region select), saves
  PNG to `inbox/`.
- **Save clipboard** — saves clipboard text (as `.txt`) or image (as `.png`) to `inbox/`.
- **Start/Stop recording** — records mic audio via `sounddevice` to WAV in `inbox/`.
- **Add file…** — file picker; copies the chosen file into `inbox/`.
- **Open Study Buddy** — opens the Streamlit homepage in the browser.

All captures are timestamp-named. The buddy writes files only; it never processes.

### 2. Ingestion pipeline (`core/ingest.py` + workers)

A background worker thread inside the Streamlit process. Sources: a watchdog on
`inbox/` plus direct uploads from the UI. Items are queued in SQLite
(status: pending → processing → done/error) and processed one at a time.

Per file type:

- **Audio / video** → `ffmpeg` extracts mono 16kHz WAV → **Silero VAD** finds speech
  segments → **Moonshine base** (ONNX) transcribes each segment → transcript with
  per-segment timestamps.
- **PDF** → PyMuPDF text extraction; pages with no text layer are rendered to images
  and OCR'd.
- **Images (PNG/JPG)** → **Apple Vision OCR** via `ocrmac` (no model download).
- **Text / markdown** → used as-is.

Then, via LM Studio (structured JSON prompts, chunked to fit a 4B model):

1. Transcript cleanup (light punctuation/formatting fix).
2. Subject + topic classification (assign to existing subject or create one).
3. Topic/chapter segmentation.
4. Concept / definition / formula extraction.
5. Hierarchical note generation (markdown, with `[source @ mm:ss]` / page refs).

### 3. Storage (`data/`)

- `data/files/` — original media, copied from inbox (inbox item is then removed).
- `data/app.db` — SQLite: `items` (file, type, status, subject, created_at),
  `subjects`, `notes` (markdown, item ref), `chunks` (text, item ref, timestamp/page,
  optional image path).
- `data/lancedb/` — one LanceDB table of chunk embeddings
  (**sentence-transformers all-MiniLM-L6-v2**, 384-dim) with metadata columns:
  subject, item id, source label, timestamp/page, image path. Images (slides,
  screenshots) are chunk rows whose text is the OCR result and whose `image_path`
  points at the stored PNG.
- `data/audiobooks/` — generated WAVs.

### 4. Streamlit homepage (`app.py` + `ui/`)

Tabs:

- **Library** — subjects → items → generated notes (markdown render), original file
  link, processing status.
- **Upload** — drag-and-drop audio/video/PDF/image/text; enqueue for ingestion; queue
  status list.
- **Ask My Notes** — chat box, optional subject filter. Flow: embed query → LanceDB
  hybrid search (vector + FTS) → top-k chunks → LM Studio answers grounded in chunks,
  citing `[source: <item> @ <ts/page>]`. Retrieved slide/screenshot images are shown
  under the answer.
- **Audiobook** — pick subject/notes → LLM rewrites notes into a narration script →
  **Kokoro** (82M) synthesizes WAV per chapter → playable + downloadable in the UI.

No dedicated reranker model (memory budget); prompt-level selection by the LLM.

### 5. Config (`.env` / `core/config.py`)

`LMSTUDIO_BASE_URL` (default `http://localhost:1234/v1`), `LMSTUDIO_API_KEY`
(default `lm-studio`), `LMSTUDIO_MODEL`, `DATA_DIR`, `INBOX_DIR`, model names for
STT/embeddings/TTS. `.env.example` committed; `.env` gitignored.

## Error handling

- Ingestion failures mark the item `error` with a message shown in the Upload tab;
  originals are never deleted on failure.
- LM Studio unreachable → clear banner in UI; ingestion steps that need the LLM wait
  and retry; capture/upload still works (queue accumulates).
- JSON parsing from the LLM: tolerant parser + one retry with a "fix your JSON" prompt,
  then fall back to storing raw transcript + a generic subject.

## Testing (MVP level)

Smoke-level only, per user request (no test loops): a `scripts/smoke.py` that
exercises config, DB creation, embedding, and LanceDB round-trip without needing
LM Studio or audio hardware.

## Out of scope (deferred)

Mock interview module, multi-device sync, live streaming transcription, slide-frame
detection from video, router model, dedicated reranker, multi-user.
