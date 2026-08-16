# Axiom Trace: Complete Project Guide, Function Reference, and Presentation Pitch

This is the repository-grounded handbook for **Axiom Trace — Knowledge-Graph-Guided RAG for Personalized Student Knowledge-Tracing**. It explains what the product does, how every subsystem cooperates, what the major functions are responsible for, how to demonstrate it, what can honestly be claimed, and how to pitch it as both an engineering project and a startup.

## 1. The shortest possible mental model

Axiom Trace turns a student's own learning evidence into a living model of what they know.

1. Notes, PDFs, videos, handwriting, audio, and attention-qualified web reading enter one ingestion pipeline.
2. The pipeline extracts text, visuals, dates, chunks, embeddings, and portable study notes.
3. A prerequisite graph connects concepts and binds them to evidence chunks.
4. Quiz attempts update each concept's Bayesian probability of mastery, `P(known)`.
5. When the student asks a question, retrieval expands through weak prerequisites and useful dependents before reranking evidence.
6. A local model answers only from the selected evidence and returns citations plus a visible retrieval trace.
7. The same mastery state determines the student's next study action and spaced-review queue.

The defining loop is:

```text
LEARNING EVIDENCE
      ↓
LOCAL INGESTION → SQLITE + LANCEDB
      ↓
PREREQUISITE GRAPH + P(KNOWN)
      ↓
GRAPH-GUIDED RETRIEVAL → RERANKING → CITED ANSWER
      ↓
QUIZ ATTEMPT → UPDATED MASTERY → NEXT STUDY ACTION
      └───────────────────────────────────────────┘
```

## 2. Problem, solution, and novelty

### The problem

Ordinary RAG systems answer the current question but do not know the learner. They retrieve semantically similar passages even when the real obstacle is a missing prerequisite. Ordinary learning dashboards track completion or marks but do not change retrieval. Student data is also commonly scattered across files, browser tabs, videos, handwritten pages, and separate productivity tools.

### The solution

Axiom Trace creates one local evidence layer, one prerequisite graph, and one persistent student model. It uses those three layers together to decide:

- what evidence is relevant;
- which weak foundations should be retrieved first;
- why a source was selected;
- what the learner should read or answer next;
- when a mastered concept is likely to be forgotten.

### What is technically distinctive

- **Personalization happens before generation.** Mastery affects graph expansion and evidence selection, not merely the wording of the final answer.
- **The graph is operational.** Prerequisite edges determine retrieval paths, session order, gap detection, and explanations.
- **Knowledge tracing closes the loop.** Answers to grounded quizzes update `P(known)` using Bayesian Knowledge Tracing.
- **Evidence is explainable.** The response exposes prerequisite, target, dependent, and semantic-seed roles.
- **Capture is idempotent.** Browser retries cannot silently create duplicate evidence records.
- **The required path is local-first.** SQLite, LanceDB, local files, sentence-transformer embeddings, a local reranker, and LM Studio are sufficient.

### What the project does not claim

Axiom Trace does not train a new foundation transformer. It composes pretrained transformer models with a knowledge graph, mastery model, deterministic orchestration, and local data contracts. The verified results prove functional behavior; they do not yet prove classroom learning gains.

## 3. System architecture

### Runtime layers

| Layer | Responsibility | Main implementation |
| --- | --- | --- |
| Evidence interfaces | Accept files, notes, recordings, handwriting, videos, and focused browser reading | FastAPI uploads, browser extension, web, Android, Telegram, menu bar |
| Canonical ingestion | Extract, normalize, split, annotate, and queue all source types | `backend/core/ingest.py` |
| Persistence | Store metadata, source files, chunks, graph state, attempts, jobs, and generated artifacts | SQLite through `backend/core/db.py` |
| Vector memory | Store normalized 384-dimensional embeddings and perform semantic search | LanceDB through `backend/core/vectorstore.py` and `embed.py` |
| Knowledge model | Build concepts, prerequisite edges, source bindings, and graph payloads | `backend/core/concepts.py` |
| Student model | Maintain BKT mastery, confidence, half-life, recall, and forgetting risk | `backend/core/mastery.py` |
| Graph-guided RAG | Expand weak neighbors, combine graph/vector candidates, deduplicate, rerank, and explain | `backend/core/graph_rag.py` |
| Grounded generation | Build evidence-only prompts, call the local model, and link citations | `backend/core/rag.py`, `llm.py`, `reranker.py` |
| Adaptation | Rank gaps, construct sessions, adapt after errors, prefetch questions, and schedule review | `gaps.py`, `planner.py`, `quiz.py`, `report.py` |
| Client experiences | Present the same backend through web, Android, extension, Telegram, and desktop utilities | `web`, `mobile`, `integrations`, `telegram_bot.py`, `pet` |

### Trust boundaries

- The default API is a local, single-user service.
- Required data stays in local files, SQLite, and LanceDB.
- The configured model endpoint is local LM Studio by default.
- Browser capture accepts HTTP(S) pages but sends only to an approved loopback receiver.
- The extension supports pause and excluded domains.
- Google Calendar and Telegram are optional external integrations, not requirements for the core demo.
- Before exposing the API outside a trusted device/LAN, authentication, HTTPS, and a stricter network policy are required.

## 4. Complete end-to-end flows

### 4.1 File-to-knowledge flow

1. A client uploads one or more files to `POST /api/upload`.
2. The API validates size/type, stores the file, and creates a pending `items` row.
3. The ingestion worker atomically claims the next pending item.
4. `_extract` routes by type: PDF, image, audio, video, text, or other supported material.
5. OCR/STT/media helpers turn the source into labeled text blocks with page or timestamp provenance.
6. `_classify` infers a title and subject.
7. `_split` creates embedding-sized chunks; every chunk is persisted in SQLite.
8. `embed.embed` creates normalized vectors; `vectorstore.upsert` writes them to LanceDB.
9. Visuals are extracted, captioned, and placed near the relevant note section.
10. `_generate_notes` produces structured Markdown grounded in the source.
11. Explicit commitments are extracted into proposed calendar reminders.
12. The item becomes `done`; failures become `error` and can be retried.

### 4.2 Browser-reading flow

1. The content script observes meaningful text elements with `IntersectionObserver`.
2. Dwell accumulates only while the element and tab are visibly active.
3. After the threshold, the script creates an event containing URL, title, visible text, dwell time, capture time, and metadata.
4. The background service worker writes the event to `chrome.storage.local` before network delivery.
5. `flush` batches events to `POST /api/captures` and removes only acknowledged event IDs.
6. The backend validates protocol, payload sizes, and batch bounds.
7. `ingest_browser_event` writes the text atomically and uses `event_id` as the idempotency key.
8. The normal ingestion worker processes it exactly like another source item.
9. `bind_sources` links its chunks to matching concepts.

Dwell is evidence of visible reading, not proof of understanding. Only assessed answers update mastery.

### 4.3 Goal-to-knowledge-graph flow

1. The student creates an exam or learning goal.
2. `create_goal` stores it with status `building` and starts graph construction.
3. `_study_material` gathers the student's relevant notes.
4. `_batches` keeps prompts within context limits.
5. `_extract` asks the local model for concepts, blurbs, and prerequisite names.
6. `_parse_entries` cleans model output and `_resolve_prereqs` resolves names safely.
7. `_assign_tiers` computes a prerequisite depth while tolerating malformed cycles.
8. `build` persists concepts and edges transactionally.
9. `_prune_ungrounded` removes unsupported concepts.
10. `bind_sources` scores chunk/concept relationships and stores the strongest source bindings.
11. `mastery.ensure_rows` initializes every concept at the prior `P(known)=0.25`.
12. The goal status changes to `ready`.

### 4.4 Question-to-cited-answer flow

1. The client sends an active concept and a question to `/api/learn/ask`.
2. `neighborhood` loads the target, up to four weakest immediate prerequisites, and up to four weakest dependents.
3. `_graph_candidates` takes up to three bound chunks per expanded concept.
4. `vectorstore.search` returns semantic candidates.
5. `retrieve` unions candidates by chunk ID, keeping the strongest graph role and capping the pool at 24.
6. `reranker.rerank` scores candidates with the local Qwen reranker; failure safely preserves the earlier order.
7. Top evidence is ordered pedagogically: prerequisite, target, dependent, semantic seed.
8. `rag.answer_from_hits` constructs an evidence-only prompt and asks the local generator.
9. Exact source labels are converted into links to notes, pages, video timestamps, or images.
10. The API returns the answer, citations, graph paths, expanded concepts, retrieval mode, and a reason for each source.

If graph evidence is available, mode is `graph_guided`. If not, the response explicitly reports `vector_fallback`.

### 4.5 Quiz-to-mastery flow

1. `quiz.generate` gathers source chunks bound to a concept.
2. The local model produces one MCQ with exactly one correct option and misconception labels for distractors.
3. `_parse` validates, cleans, truncates, and shuffles options.
4. `_persist` stores the question; the answer is withheld until grading.
5. `grade` stores the attempt, misconception, and latency.
6. `mastery.apply_attempt` performs a BKT update and appends mastery history.
7. If mastery reaches `0.85`, the concept enters spaced review.
8. If a learner misses a question, `_adapt` can insert the weakest prerequisite into the current diagnostic.

### 4.6 Adaptive-session flow

- A diagnostic rotates across graph tiers and prioritizes least-tested, high-impact concepts.
- A normal study session places missing prerequisites before weak target concepts.
- Untested concepts receive a read step before a quiz.
- Due spaced-review concepts are appended after current gaps.
- Question generation is prefetched in a background thread so only the first item may wait for the model.
- If the model is unavailable, cached questions are used; without a cached question, the item is skipped rather than freezing the session.

### 4.7 Forgetting and review flow

The project models recall using exponential decay:

```text
recall = 2 ^ (-elapsed_days / half_life)
risk   = 1 - recall
```

A successful review doubles half-life up to 180 days. A failed review multiplies it by `0.4`, with a floor of `0.25` days. Review becomes due when predicted recall falls below `0.85`.

## 5. Core algorithms and constants

### Bayesian Knowledge Tracing

Default parameters:

| Parameter | Value | Meaning |
| --- | ---: | --- |
| `P_INIT` | 0.25 | Prior probability of knowing a concept |
| `P_LEARN` | 0.15 | Chance the attempt itself produces learning |
| `P_SLIP` | 0.10 | Knows the concept but answers incorrectly |
| `P_GUESS` | 0.25 | Does not know it but guesses a four-option MCQ |
| Weak threshold | 0.60 | Below this, the concept is treated as a gap |
| Mastered threshold | 0.85 | At or above this, it enters spaced review |

For a correct answer:

```text
posterior = p(1-slip) / [p(1-slip) + (1-p)guess]
```

For an incorrect answer:

```text
posterior = p·slip / [p·slip + (1-p)(1-guess)]
```

The system then applies the learning transition:

```text
new_p = posterior + (1-posterior)·P_LEARN
```

### Graph-guided retrieval

- Maximum four neighbors per role.
- Maximum three bound sources per graph node.
- Maximum 24 candidates before reranking.
- Default eight final chunks.
- Duplicate chunks keep their strongest role: target > prerequisite > dependent > semantic seed.
- Prompt order is prerequisite → target → dependent → semantic seed.

### Confidence

Because basic BKT has no explicit variance, the project uses attempt count as a confidence proxy:

```text
confidence = 1 - exp(-attempts / 3)
```

This distinguishes “untested” from “tested and weak.”

## 6. Persistent data model

| Table | Purpose |
| --- | --- |
| `subjects` | User-defined subject taxonomy |
| `items` | Every ingested file/capture and its processing status |
| `capture_events` | Browser event ledger, provenance, dwell, hash, and idempotency key |
| `notes` | Generated or edited Markdown linked to an item |
| `chunks` | Retrieval units with page/timestamp/image provenance |
| `doc_figures` | Extracted figures and captions |
| `video_frames`, `video_ocr_segments` | Stable-board frames, OCR crops, review state, and consolidated text |
| `hw_pages`, `hw_lines` | Handwriting pages, line crops, predictions, and corrections |
| `chat_turns` | Persistent user/assistant turns and cited media |
| `flashcard_decks`, `flashcards` | Grounded decks and ordered cards |
| `question_papers`, `question_paper_questions`, `question_paper_jobs` | Generated assessments, answer keys, and background jobs |
| `tasks` | Planner tasks and optional Google event IDs |
| `calendar_reminders`, `calendar_reschedule_plans` | Extracted commitments and conflict-resolution plans |
| `audiobook_jobs` | Local TTS job status and output path |
| `exam_goals` | Active adaptive-learning goal and build status |
| `concepts`, `concept_edges`, `concept_sources` | Knowledge graph and evidence bindings |
| `mastery`, `mastery_history` | Current BKT state and historical points |
| `questions`, `attempts` | Grounded quizzes, answers, misconceptions, and latency |
| `sessions`, `session_items` | Diagnostic/study/review queues and progress |

## 7. Backend function-by-function reference

### `backend/server.py` — API boundary

#### Runtime and system endpoints

- `lifespan(application)`: initializes the database, starts one ingestion worker, and shuts it down with the app.
- `request_context(request, call_next)`: adds/correlates request IDs, timing, API version headers, and structured request logging.
- `unhandled_exception(request, error)`: converts unexpected failures into a stable JSON error response.
- `api_metadata()`: returns API name, version, discovery URLs, and capability groups.
- `health()`: compatibility health response.
- `liveness()`: confirms the process event loop is alive.
- `readiness()`: confirms required storage/runtime components are ready.
- `stats()`: counts notes, items, chunks, flashcards, audiobooks, and disk usage.

#### Library, notes, capture, and RAG endpoints

- `subjects()` / `create_subject(req)`: list or create subject labels.
- `items(subject_id)`: list source items, optionally filtered by subject.
- `retry_item(item_id)`: requeue failed ingestion or repair a missing vector index.
- `notes(limit)`: return note previews with source metadata.
- `_download_name(title, suffix)`: create a safe response filename.
- `export_notes()`: package portable note backups.
- `import_notes(backup)`: validate and restore exported notes without duplicating records.
- `download_note(note_id)`: render a note as a downloadable PDF.
- `note_detail(note_id)`: return full Markdown plus its item/visual context.
- `move_note(note_id, req)`: change a note's title/subject placement.
- `edit_note(note_id, req)`: save edited Markdown and update related search content.
- `delete_note(note_id)`: delete note-related records and generated files safely.
- `upload(...)`: validate multipart uploads, enqueue files, and return item IDs.
- `receive_browser_captures(batch)`: validate and ingest idempotent browser event batches.
- `_answer_question(question, subject)`: run normal RAG, persist chat turns, and detect flashcard commands.
- `ask_question(req)` / `ask_audio(...)`: answer text or transcribed audio questions.
- `chat_history(limit)` / `clear_chat_history()`: read or clear persistent chat.

#### Video, figures, and media endpoints

- `list_video_frames`, `list_video_segments`, `video_frames`, `video_frame`: retrieve review state and normalized frame payloads.
- `_video_frame_payload(frame)`: attach frame, video, and segment URLs to a database row.
- `video_frame_image`, `video_file`, `doc_figure_image`, `item_file`, `chunk_image`, `video_segment_image`: serve validated local media.
- `video_ocr_stream(frame_id)`: stream OCR progress as server-sent events.
- `verify_video_frame(frame_id)`: accept/reprocess a board frame and consolidate its note text.
- `_add_frame_to_note(frame, markdown)`: insert reviewed frame material into the corresponding note.
- `delete_video_frame(frame_id)`: remove frame metadata and generated crops.

#### Learning artifact endpoints

- `flashcard_decks`, `flashcard_deck`, `remove_flashcard_deck`: list, retrieve, and delete grounded decks.
- `list_question_papers`, `create_question_paper`, `question_paper_jobs`, `get_question_paper`, `download_question_paper`, `delete_question_paper`: queue, poll, inspect, export, and delete generated assessments.
- `audiobook_jobs`, `audiobooks`, `audiobook_file`, `make_audiobook`: create and serve local TTS study audio.

#### Calendar and tasks endpoints

- `google_calendar_status`, `google_calendar_auth_url`, `google_calendar_callback`, `google_calendar_events`, `google_calendar_disconnect`, `google_calendar_sync`: OAuth, connection state, event reads, revoke, and retry flow.
- `calendar_proposals`, `approve_calendar_proposal`, `dismiss_calendar_proposal`, `plan_calendar_proposal`: review extracted commitments and build plans.
- `calendar_plan`, `apply_calendar_plan`, `dismiss_calendar_plan`: inspect, revalidate, execute, or dismiss conflict plans.
- `tasks`, `create_task`, `patch_task`, `remove_task`: task CRUD plus optional Google event creation.

#### Handwriting and activity endpoints

- `handwriting_upload`: store pages and launch OCR processing.
- `handwriting_pages`, `handwriting_page`, `handwriting_crop`, `handwriting_page_image`: list pages and serve original/cropped images.
- `correct_line`: store a human correction for a recognized line.
- `handwriting_to_notes`: combine corrected lines into a new canonical note.
- `handwriting_status`: report correction statistics.
- `activity(limit)`: combine recent notes, files, and jobs into a dashboard feed.

#### Adaptive-learning endpoints

- `_require_goal()` / `_require_ready_goal()`: enforce active/ready goal preconditions.
- `learn_goal`, `create_learn_goal`, `delete_learn_goal`: inspect, build, or remove the active graph.
- `learn_graph`, `learn_gaps`, `learn_evidence`, `learn_rebind_sources`: expose graph, ranked gaps, captured evidence, and refreshed evidence bindings.
- `learn_diagnostic`, `learn_session`, `learn_session_state`, `learn_session_next`, `learn_session_read`: create and advance adaptive sessions.
- `learn_attempt`: grade a response and update mastery.
- `learn_review`, `learn_history`, `learn_report`: return forgetting queue, mastery history, and weekly analytics.
- `learn_ask`: run concept-scoped graph-guided RAG.

### `backend/core/graph_rag.py` — personalized retrieval

- `_evidence_reason(hit)`: converts graph role metadata into a human-readable explanation.
- `neighborhood(concept_id)`: selects the target and weakest immediate prerequisite/dependent neighbors and returns visible graph paths.
- `_graph_candidates(expanded)`: fetches bound chunks per node and deduplicates them by strongest role.
- `retrieve(concept_id, question, top_k)`: unions graph and semantic candidates, caps, reranks, orders, and builds the retrieval trace.
- `ask(concept_id, question, top_k)`: prefixes the active concept, generates the cited answer, and attaches the trace.

### `backend/core/mastery.py` — knowledge tracing and forgetting

- `MasteryState`: immutable current state with calculated `confidence` and `recall_at` helpers.
- `posterior(p, correct)`: Bayesian observation update before the learning transition.
- `update(p, correct)`: full BKT update including probability of learning.
- `confidence(attempts)`: attempt-based reliability proxy.
- `recall`, `risk`, `days_until_due`: exponential memory predictions.
- `next_half_life(current, correct)`: expands or contracts the review interval.
- `_row_to_state(row)`: converts SQLite rows into typed mastery state.
- `ensure_rows(concept_ids)`: initializes mastery/history baselines.
- `get(concept_id)`, `all_for_goal(goal_id)`: load one or all states.
- `apply_attempt(concept_id, correct)`: transactionally update BKT, SRS state, counters, and history.
- `history(goal_id)`: return chronological mastery points.
- `due_queue(goal_id, at)`: sort mastered concepts by predicted forgetting.

### `backend/core/concepts.py` — graph construction and binding

- `_slug(name)`: create a stable URL-safe goal slug.
- `current_goal`, `get_goal`: retrieve active/specific goals.
- `create_goal`: replace the active goal and launch a safe background build.
- `delete_goal`: cascade-delete graph, mastery, session, question, and attempt state.
- `_build_safely`: capture build exceptions into the goal status.
- `_assign_tiers`: derive prerequisite depth while preventing cycles from blocking the build.
- `_parse_entries`: normalize model-produced concept records.
- `_resolve_prereqs`: map prerequisite names to canonical concepts and remove invalid/self references.
- `_condense`: reduce Markdown to a prompt budget.
- `_study_material`: collect relevant student notes.
- `_batches`: split material into model-sized graph-extraction requests.
- `_extract`: ask the local model for grounded concepts and prerequisites.
- `build`: merge extractions, persist concepts/edges, initialize mastery, bind sources, and mark ready.
- `_prune_ungrounded`: remove concepts with no evidence support.
- `bind_sources`: calculate and persist strongest chunk-to-concept matches.
- `refresh_sources`: clear and rebuild bindings after new evidence arrives.
- `list_concepts`, `get_concept`, `list_edges`, `prerequisites_of`: graph read helpers.
- `downstream_counts`: measure how many concepts depend on each concept.
- `source_chunks`: load a concept's best bound evidence.
- `graph`: join concepts, mastery, confidence, downstream counts, and edges into the API graph.

### `backend/core/gaps.py`, `planner.py`, `quiz.py`, and `report.py`

- `gaps.rank(goal_id)`: rank weak concepts and missing prerequisites using mastery, confidence, graph tier, and downstream impact.
- `gaps.summary(goal_id)`: count concepts, mastered, weak, untested, and average mastery.
- `planner._diagnostic_concepts`: rotate through tiers, least-tested first.
- `planner._study_plan`: build prerequisite-first read/quiz/review order.
- `planner._create`, `start_diagnostic`, `start_session`: persist session queues.
- `planner._session_row`, `_pending_items`: load session state.
- `planner._take_prefetched`, `_prefetch`: consume/start background question generation.
- `planner._adapt`: after a wrong diagnostic answer, insert the weakest missing prerequisite.
- `planner.next_item`: serve reads/questions, skip unrecoverable items, prefetch the next, and complete the session.
- `planner._asked_question_ids`, `_mark_done`, `mark_read`, `_with_progress`, `complete`, `state`, `recent`: maintain progress and expose session history.
- `quiz._context_for`: collect bounded concept evidence.
- `quiz._parse`: validate a model MCQ and misconceptions.
- `quiz._persist`: store a generated question.
- `quiz.generate`: generate a grounded question.
- `quiz._cached_question_id`, `question_for`: retry generation and fall back to cache.
- `quiz.get_question`: withhold/reveal answers according to caller intent.
- `quiz.grade`: persist attempt, mark session progress, and update BKT.
- `quiz.misconception_counts`: aggregate repeated error patterns.
- `report.weekly`: combine session accuracy, mastery deltas, gaps, misconceptions, and review risk.

### `backend/core/capture.py`, `ingest.py`, `embed.py`, and `vectorstore.py`

- `capture._safe_stem`: sanitize browser titles for local filenames.
- `capture.ingest_browser_event`: atomically persist one event exactly once and enqueue it as a normal item.
- `ingest._clean_generated_markdown`, `_safe_markdown_title`, `_dedupe_lines`, `_condense_windows`, `_condense_section`, `_assemble_structured_notes`: clean and assemble consistent study notes.
- `ingest._ffmpeg_to_wav`, `_mmss`: normalize media audio and timestamps.
- `ingest._extract`: route source types through PDF/OCR/STT/video/text extraction.
- `ingest._split`: create retrieval-sized chunks.
- `ingest._classify`: infer title and subject.
- `ingest._visual_caption`, `_collect_visuals`: describe and collect figures/frames.
- `ingest._note_part_chars`, `_generate_notes`: control prompt budgets and create multi-part notes.
- `ingest._extract_calendar_reminders`, `_queue_calendar_reminders`: discover and persist explicit commitments.
- `ingest.process_item`: orchestrate the complete item transaction and status transitions.
- `ingest.enqueue_file`, `_sweep_inbox`: add files discovered through uploads or watched folders.
- `ingest.worker_loop`, `start_worker`, `stop_worker`: run one cooperative background worker.
- `embed._model`: lazily load the sentence-transformer once.
- `embed.embed`: return normalized 384-dimensional vectors.
- `vectorstore._write_lock`: serialize LanceDB mutations across threads and API/worker/Telegram processes using Windows or POSIX locking.
- `vectorstore._table`: open/create the LanceDB table with zero-delay cross-process read consistency.
- `vectorstore.ensure_ready`: initialize the index without loading the embedding model.
- `vectorstore._id_filter`: construct a validated numeric chunk-ID filter.
- `vectorstore._mutate`: perform an idempotent mutation and reopen a stale handle once after LanceDB `EIO`.
- `vectorstore.add_chunks`: embed rows, delete previous vectors for the same chunk IDs, and add the replacement batch.
- `vectorstore.delete_chunks`: remove a validated group of chunk vectors.
- `vectorstore.update_item_subject`: keep vector metadata synchronized after a note/item subject change.
- `vectorstore.search`: embed a query, apply optional subject filtering, and return normalized hit records.

### `backend/core/rag.py`, `reranker.py`, and `llm.py`

- `rag._mmss`, `_video_href`: format video citations and seek links.
- `rag.ask`: retrieve a broad semantic pool, rerank, and answer.
- `rag.answer_from_hits`: create source-labeled context, call the model, link citations, and expose matched images/videos.
- `reranker._candidate_text`: create bounded source-plus-text inputs.
- `reranker._score`: ask the reranker for a relevance probability.
- `reranker.rerank`: score and sort candidates, preserving original order on local-model failure.
- `llm.is_available`, `require_available`: probe/enforce the local model endpoint.
- `llm.chat`: normal text completion.
- `llm.chat_vision`: multimodal completion with base64 images.
- `llm._extract_json`: recover JSON from model text safely.
- `llm.chat_json`: request and parse unconstrained JSON.
- `llm.chat_json_schema`: use OpenAI-compatible JSON Schema constrained decoding.

### `backend/core/db.py` — persistence functions

- `conn`: open a foreign-key-enabled SQLite transaction context.
- `init_db`: create/migrate tables and indexes.
- `add_item`, `get_item`, `list_items`, `next_pending_item`, `claim_next_pending_item`, `set_status`, `retry_item`, `set_item_meta`, `index_rows_for_item`: item lifecycle and worker claiming.
- `add_browser_capture`, `get_capture_event`, `list_capture_events`: idempotent browser ledger.
- `get_or_create_subject`, `list_subjects`: subject taxonomy.
- `add_note`, `update_note`, `notes_for_item`, `notes_for_subject`, `note_id_for_item`: note persistence.
- `add_chunk`: retrieval-chunk persistence.
- `add_doc_figure`, `get_doc_figure`, `list_doc_figures`, `delete_doc_figures_for_item`: document-figure records.
- `add_video_frame`, `list_video_frames`, `get_video_frame`, `add_video_segment`, `set_video_segment_result`, `list_video_segments`, `set_video_frame_review`, `delete_video_frame`: video review records.
- `add_hw_page`, `set_hw_page_status`, `list_hw_pages`, `get_hw_page`, `add_hw_line`, `list_hw_lines`, `delete_hw_lines`, `set_hw_correction`, `hw_corrected_lines`: handwriting records and corrections.
- `add_audiobook_job`, `finish_audiobook_job`, `list_audiobook_jobs`: TTS job tracking.
- `list_tasks`, `add_task`, `set_task_done`, `delete_task`, `set_task_google_event`: task persistence.
- `add_calendar_reminder`, `list_pending_calendar_reminders`, `list_calendar_proposals`, `get_calendar_reminder`, `set_calendar_reminder_status`, `set_calendar_reminder_result`, `calendar_reminder_counts`: proposed-event lifecycle.
- `add_reschedule_plan`, `get_reschedule_plan`, `set_reschedule_plan_status`: persisted conflict plans.
- `add_chat_turn`, `list_chat_turns`, `clear_chat_turns`: chat persistence.
- `create_flashcard_deck`, `list_flashcard_decks`, `get_flashcard_deck`, `delete_flashcard_deck`, `flashcard_count`: deck transactions.
- `create_question_paper`, `list_question_papers`, `get_question_paper`, `delete_question_paper`: assessment transactions.
- `add_question_paper_job`, `finish_question_paper_job`, `list_question_paper_jobs`: background assessment jobs.

### Content and media helper modules

- `dates.capture_date_from_text`: derive a source capture/publication date from text.
- `dates.event_date_from_due_text`: parse a task's due wording into a calendar date.
- `ocr.ocr_image_annotations`, `ocr_image`, `extract_pdf`: OCR images and PDF pages with geometry.
- `stt._vad`, `_moonshine`: lazily load voice activity detection and Moonshine STT.
- `stt._speech_segments`: split waveform into voiced regions.
- `stt.transcribe`, `transcribe_media`: timestamp and transcribe WAV/other media.
- `figures._b64`, `_gate`, `_rect_ok`, `_iou`, `_merge_boxes`, `_overlaps_within_gap`, `_page_candidates`: filter and merge probable PDF figure regions.
- `figures._persist`, `extract_pdf_figures`, `_to_png_bytes`, `register_image_figure`: save and register visual evidence.
- `video.optimize_for_streaming`: make video fast-start compatible.
- `video._frame_samples`, `_thumbnail`, `_difference`, `_sharpness`, `_save_candidate`, `capture_stable_frames`: select stable, distinct, sharp board frames.
- `video._bbox_pixels`, `_regions`, `prepare_segments`: convert detected regions into OCR crops.
- `video._table_from_annotations`, `run_segment_ocr`, `consolidate_frame`, `analyze_frame`: OCR, reconstruct tables, combine regions, and produce reviewed notes.
- `handwriting._vision_line_boxes`, `_projection_line_boxes`, `segment_lines`: locate handwritten lines using vision/model fallback.
- `handwriting._zoom`, `_to_b64`, `_vocabulary_hint`, `_clean`: prepare crops and domain hints.
- `handwriting.recognize_line`, `recognize_lines`, `process_page`, `recognize_item_page`: transcribe lines and persist page results.
- `diagrams._image_b64`, `_vision_json`, `_clean_ocr`, `_sanitize_id`: prepare diagram-model inputs.
- `diagrams.validate_graph`: validate and repair nodes/edges from vision output.
- `diagrams._thin`, `trace_connectors`, `_detector_evidence`: skeletonize and trace connector geometry.
- `diagrams.graph_to_mermaid`, `_draw_overlay`, `analyze_diagram`, `diagram_markdown`: produce explainable graph, overlay, Mermaid, and note blocks.

### Study artifact helper modules

- `notes._img`, `_fmt_ts`, `build_manifest_block`: create portable visual references.
- `notes._line_seconds`, `_anchor_index`: find source-time/page placement anchors.
- `notes.strip_placement_tokens`, `place_visuals`, `update_note_markdown`: place visuals and safely persist edited Markdown.
- `note_pdf._font`, `image_paths_for_item`, `_inline`, `_table_cells`, `_is_block_start`, `_image_flowables`, `_story`, `to_pdf`: convert Markdown, math, tables, and local images into printable PDF notes.
- `mathmd.normalize`, `_normalize_fence`, `_normalize_prose`, `_split_inline_code`, `_normalize_math_spans`, `_clean_math`, `_wrap_bare_latex`, `_latex_run_end`: normalize inconsistent model-authored math Markdown.
- `mathmd.to_markup`, `to_plain`, `_render`, `_render_command`, `_read_argument`, `_read_optional`, `_render_script`, `_bracket`: render a supported LaTeX subset into styled/plain output.
- `flashcards.parse_request`: detect a chat instruction requesting a deck.
- `flashcards._source_context`: retrieve grounded topic evidence.
- `flashcards._clean_cards`: validate, deduplicate, and limit model cards.
- `flashcards.create_deck`, `maybe_create_from_chat`: generate/persist a deck directly or from chat.
- `audiobook._cached_asset`, `_pipeline`: cache Kokoro assets and the TTS pipeline.
- `audiobook.notes_to_script`, `synthesize`, `generate`: clean Markdown into speech, synthesize audio, and save it.
- `question_papers.validate_request`: enforce counts, duration, difficulty, and selected notes.
- `_selected_notes`: allocate context fairly across chosen notes.
- `_clean_questions`: enforce type/count/options/answer/duplicate invariants.
- `_request_for_type`, `_batch_schema`, `_generate_questions`: batch each mark type and use constrained JSON.
- `generate`: execute all batches and persist the paper transactionally.
- `to_markdown`, `_pdf_font`, `to_pdf`: produce student or answer-key versions.

### Calendar modules

- `calendar_planner._parse`, `_overlaps`, `_event_interval`: normalize times and detect conflicts.
- `priority_for`: assign deterministic category priorities.
- `_event_policy`: protect attendee, recurring, sensitive, and non-movable events.
- `_candidate_slots`: search 30-minute slots from 07:00–22:00 for up to seven days.
- `build_plan`: create a move/create plan and flag risky cross-day, large-cascade, or unresolved cases.
- `google_calendar._load_states`, `_save_states`: maintain temporary OAuth state/PKCE data.
- `is_configured`, `_client_config`, `_flow`: validate config and construct OAuth flow.
- `authorization_url`, `complete_authorization`, `record_oauth_error`, `last_oauth_error`: execute and diagnose OAuth.
- `_save_credentials`, `credentials`: persist/refresh credentials.
- `list_events`: read and normalize a date range.
- `_google_event_id`: create a deterministic reminder identifier.
- `create_reminder`, `create_task_event`: write extracted reminders/tasks.
- `sync_pending_reminders`: retry approved events.
- `apply_reschedule_plan`: recheck source events, move allowed conflicts, create the new event, and roll back on failure.
- `auto_reschedule_reminder`: automatically apply only uncomplicated plans.
- `disconnect`: revoke and remove credentials.

### Runtime, logging, optional interfaces, and scripts

- `axiom_trace.runtime.shutdown_signals`: return supported OS termination signals.
- `ProcessSupervisor.start`, `.terminate`, `.wait`, `.shutdown`: own optional child processes and stop them together.
- `runtime.run`: start uvicorn plus enabled menu-bar/Telegram helpers.
- `logging.JsonFormatter.format`: emit production JSON logs.
- `logging.ConsoleFormatter.format`: emit readable development logs.
- `configure_logging`: apply configured level/format and quiet noisy dependencies.
- `app._boot`: initialize SQLite and cache one ingestion worker for the Streamlit fallback.
- `buddy.menubar._stamp`: make timestamped capture filenames.
- `BuddyApp`: macOS menu-bar actions for screenshot/audio capture, inbox access, and backend launch.
- `scripts.seed_axiom_trace_demo._remove_previous_demo`, `seed`: remove only the previous deterministic demo and recreate its sources, graph, mastery, and bindings without duplicates.
- `scripts.smoke.main`: exercise a minimal backend workflow.
- `scripts.analyze_diagrams.publish`, `main`: command-line diagram analysis and artifact publishing.
- `scripts.retrofit_diagrams.retrofit`, `main`: add diagram analysis to existing items.
- `scripts.gen_pet_sprites._draw_frame`, `generate`: create placeholder animated pet assets.

### Desktop study pet

- `pet.models.Stage`, `Mood`, `ActivitySample`, `NudgeEvent`, `ContextSnapshot`, `Thresholds`: typed state and policy records.
- `classifier.normalize_host`, `_host_matches`: normalize/compare active browser domains.
- `classifier._ask_llm`: ask the local model only when deterministic classification is insufficient.
- `classifier.classify`: label foreground activity as study, distraction, neutral, or unknown.
- `classifier.reset_cache`: clear classification memoization.
- `context._parse_when`, `_describe`: parse and humanize deadlines.
- `ContextFetcher`: periodically obtain current tasks, calendar items, and weak concepts.
- `state._elapsed`, `_stage_for_dwell`, `_one_step_toward`, `_may_speak`, `advance`: deterministic escalation/recovery state machine.
- `voice.sanitize`, `_pool_key`, `_prompt`, `line`: create safe, varied, locally generated nudges.
- `watcher`: sample foreground application/browser state without persistent logging.
- `PetRunner`: coordinate sampling, classification, context, state transitions, movement, and speech.
- `watcher.parse_tab_output`: split AppleScript output into active-tab title and URL.
- `watcher.host_of`: accept HTTP(S) URLs and normalize their hostname.
- `watcher._run_applescript`: execute a bounded active-tab query.
- `watcher.browser_tab`: safely retrieve a supported browser's tab title/host.
- `watcher.frontmost`: retrieve the foreground macOS application/window.
- `watcher.sample`: build a failure-tolerant `ActivitySample`.
- `runner._default_locate`: find the distracting application's screen position when available.
- `window.PetWindow._make_window`: create borderless always-on-top sprite/bubble windows.
- `PetWindow.show`, `hide`, `render`, `_show_bubble`, `tick`, `_draw`: display, animate, walk, time, and redraw the pet.
- `window_center_x`: find a process window's horizontal center for pet movement.

### Telegram interface

- `_button`, `_menu_keyboard`, `_back`: build callback keyboards.
- `_is_allowed`, `_deny`: enforce configured user/chat allowlists.
- `_show`, `_send_long`: edit/send messages within Telegram limits.
- `_safe_name`, `_note_row`, `_item_row`, `_recent_notes`: sanitize filenames and fetch records.
- `start`, `id_command`, `cancel`, `help_command`, `menu_command`, `status_command`, `ask_command`, `capture_command`, `task_command`: command entry points.
- `_dashboard`, `_notes`, `_note`, `_download_note`, `_files`, `_file_detail`, `_download_file`: browsing and downloads.
- `_ask_menu`, `_answer_question`: grounded Q&A flow.
- `_tasks`, `_create_task_from_text`: task management.
- `_audiobooks`, `_audiobook_picker`, `_generate_audiobook`, `_send_audio`: TTS flow.
- `_calendar`, `_calendar_events`: calendar status and event display.
- `_settings`, `_export_notes`, `_import_notes`: settings and portable backup.
- `_queue_text`, `_media_details`, `handle_media`, `_watch_item`, `handle_text`: route messages/files into canonical ingestion and report completion.
- `callback`: dispatch inline-button actions.
- `error_handler`, `post_init`, `build_application`, `main`: lifecycle, logging, handlers, and polling.

## 8. Browser extension function reference

### `integrations/browser-capture/settings.js`

- `normalizeDomain(value)`: lowercases and strips protocol/path noise from an excluded domain.
- `normalizeDomains(values)`: normalizes and deduplicates the exclusion list.
- `isExcludedLocation(rawUrl, domains)`: rejects invalid locations and exact/subdomain matches.
- `read()`: merge stored settings with safe defaults.
- `ensureDefaults()`: persist missing defaults on install/update.

### `content.js`

- `normalizeText(text)`: collapse whitespace and bound captured text.
- `fingerprint(text)`: create a stable content fingerprint for local duplicate suppression.
- `isCaptureCandidate(element)`: accept meaningful visible text containers and reject UI/noise.
- `requiredVisibilityRatio(element)`: adjust the intersection threshold for large elements.
- `clearTimer(state)`, `stopInterval(state, now)`, `startInterval(state)`: accumulate only foreground-visible dwell.
- `makeCaptureEvent(state)`: construct the backend contract with provenance and timing.
- `emitIfEligible(state)`: enqueue only after threshold and avoid repeated emission.
- `scheduleThreshold(state)`: trigger emission when the remaining visible dwell reaches the threshold.
- `stateFor(element)`: create/retrieve per-element observation state.
- `handleIntersections(entries)`: start/stop dwell from intersection changes.
- `createObserver()`, `observeCandidate(element)`, `scan(root)`: discover and observe eligible content.
- `resetForNavigation()`: clear state when a single-page app changes URL.
- `handleMutations(mutations)`: debounce scanning of dynamically inserted content.
- `startCapture`, `stopCapture`, `applyCaptureSettings`: own observers/timers according to enable/domain settings.
- Visibility/pagehide listeners: immediately stop intervals and request queue delivery before the page disappears.

### `background.js`

- `serialized(operation)`: serialize queue reads/writes so concurrent messages cannot overwrite each other.
- `readQueue`, `writeQueue`: access the durable `chrome.storage.local` queue.
- `isAllowedReceiver(rawUrl)`: allow only loopback HTTP receiver URLs.
- `getReceiverUrl`: return the validated configured receiver.
- `enqueue(event)`: deduplicate by event ID/fingerprint and persist before sending.
- `flush`: POST a bounded batch and delete only acknowledged IDs.
- `requestFlush`, `cancelScheduledFlush`, `scheduleFlush`, `requestImmediateFlush`: coalesce retries, alarms, and urgent delivery.
- Runtime message/install/startup/alarm listeners: connect content/popup events to the queue lifecycle.

### `popup.js`

- `loadSettings`: show enabled state, exclusions, receiver, dwell, and queue size.
- `saveSettings`: validate and persist user changes, then request a flush.

## 9. Web application reference

### Shared clients and utilities

#### `web/src/lib/api.ts`

- `API`: same-origin base by default so Next can proxy to FastAPI consistently.
- `getJSON(path)`, `postJSON(path, body)`: typed fetch wrappers with no-store reads and error propagation.
- `askText`, `askAudio`: text and multipart voice Q&A clients.
- `timeAgo`, `shortDate`: human-readable activity timestamps.
- Interfaces such as `Stats`, `Item`, `NotePreview`, `Task`, `Deck`, `HwPage`, and `VideoFrame` define the browser's view of backend contracts.

#### `web/src/lib/learn.ts`

- `del(path)`: checked DELETE helper.
- `learn.goal`, `createGoal`, `deleteGoal`: goal lifecycle calls.
- `learn.graph`, `gaps`, `evidence`, `rebindEvidence`: knowledge-state calls.
- `learn.startDiagnostic`, `startSession`, `session`, `next`, `markRead`, `attempt`: session calls.
- `learn.review`, `history`, `report`: analytics/review calls.
- `learn.ask`: concept-scoped graph-RAG call.
- `masteryFill`: convert mastery into a shared accent tint.
- `masteryLabel`: map probability to WEAK/SHAKY/SOLID/MASTERED.
- Type interfaces document every adaptive-learning response used by the UI.

#### Markdown, math, links, and preferences

- `markdown.cleanStudyMarkdown`: remove internal placement markers before display.
- `mathMarkdown.normalizeMath`: normalize fenced and inline math without touching code.
- `normalizeFence`, `normalizeProse`, `splitInlineCode`, `normalizeMathSpans`, `cleanMath`, `wrapBareLatex`, `latexRunEnd`: the parser stages behind that normalization.
- `noteLinks.tsx` `tsSeconds`, `fmtTs`: parse/format media timestamps.
- `linkifySources`: convert source markers into actionable links.
- `SourceLink`, `makeSourceAnchor`: render note/video/page anchors and seek callbacks.
- `remarkHighlights.highlightText`, `transform`, `remarkHighlights`: turn `==highlight==` syntax into safe Markdown nodes.
- `prefs.readPrefs`, `writePrefs`: persist theme, dyslexic-reading, motion, and related browser settings.

### Application shell and common components

- `RootLayout`: global metadata, fonts, stylesheet, providers, and app shell.
- `AppShell`: responsive sidebar/topbar/content composition.
- `Sidebar.isActive`, `NavRow`, `Navigation`, `Sidebar`: route grouping, active state, numbered primary flow, and mobile drawer.
- `Topbar.screenName`, `Topbar`: derive page label and render global controls/status.
- `ThemeProvider.apply`, `ThemeProvider`, `useTheme`: apply persisted visual/accessibility preferences and expose updates.
- `NoteMarkdown`: normalize math, source links, GFM, KaTeX, highlights, and image/video actions.
- `NoteEditor`: controlled Markdown editor with save/cancel state.
- `MermaidDiagram`: render graph text client-side with error containment.
- `VideoModal`: accessible video playback at a requested timestamp.
- `CalendarWidget.dateKey`, `CalendarWidget`: reusable month grid with selected/marked dates.
- `FocusTimer`: local 25-minute focus timer; intentionally not backend state.
- UI primitives `Panel`, `SectionHeader`, `MonoLabel`, `StatTile`, and `GlowButton`: consistent visual building blocks.

### Chart functions

- `scale.innerBox`: derive padded plotting bounds.
- `linear`: map a numeric domain to screen coordinates.
- `ticks`: produce evenly spaced axis ticks.
- `linePath`: convert points to an SVG path.
- `formatPercent`, `formatDay`, `clip`: shared labels.
- `ChartFrame`: standardized title, subtitle, legend, empty state, and SVG frame.
- `ConceptMap`: place tiered nodes/edges, color by mastery, and expose concept selection.
- `MasteryCurve`: render mastery history over time.
- `ForgettingCurves`: plot predicted recall decay and due threshold.
- `WeakAreaBars`: rank weak concepts visually.
- `MisconceptionBars`: compare repeated error tags.
- `SlopeChart`: show before/after mastery deltas.

### Pages

- `DashboardPage` plus `greeting`/`todayLabel`: load headline statistics, activity, focus timer, and today's plan.
- `FilesPage` plus `recordingFormat`/`elapsedTime`: upload files, record audio, monitor processing, retry, and download sources.
- `NotesPage` plus `noteContext`: browse, search, edit, move, export/import, render, and download notes.
- `SearchPage`: persistent grounded chat, voice input, citations, source media, video seeking, and clear-history flow. Its helpers format timestamps and correlate sources to video items.
- `TasksPage`: create, complete, and delete tasks.
- `CalendarPage`: OAuth connection, proposal review, conflict plans, event range reads, and plan execution. `oauthErrorMessage` and `eventTime` normalize user-facing state.
- `FlashcardsPage`: create decks through grounded chat commands, browse cards, flip, and delete decks.
- `QuestionPapersPage` and `NumberField`: configure source notes, counts, difficulty, duration, poll jobs, inspect papers, and download student/answer versions.
- `AudiobooksPage`: select notes, queue TTS, poll jobs, and play/download output.
- `HandwritingPage` and `LineEditor`: upload pages, monitor OCR, correct individual lines, and convert a page into notes.
- `VideoReviewPage` and `timestamp`: inspect stable frames, stream OCR, review crops, verify, seek, and delete.
- `SettingsPage` with `Row`, `Toggle`, and `Group`: manage appearance, reading accessibility, and local preferences.
- `LearnPage` and `sourceHost`: create the goal, show summaries/sessions/evidence, link new evidence, and launch diagnostic/study actions.
- `ConceptMapPage`: load graph data and present the interactive concept map.
- `GapsPage`: show ranked gaps, blockers, and targeted study launch actions.
- `SessionPage` with `now`/`elapsedSince`: serve read/quiz items, measure answer latency, grade, reveal feedback, and advance.
- `ReportPage`: combine summary, deltas, weak areas, misconceptions, mastery curves, and forgetting curves.
- `ConceptAsk`: concept-specific question composer and “Why this answer?” retrieval-trace panel.
- `LearnNav`: focused navigation among path, gaps, map, and report.

#### Page-local action helpers

These small functions live inside React pages because they close over that page's state:

- Search helpers `historyTime`, `turnKey`, `timestampLabel`, `videoHref`, `timestampFromSourceLabel`, `sourceVideo`, and `speechRecordingFormat` correlate chat turns, citations, recordings, and video timestamps.
- Search actions `startRecording`, `stopRecording`, `submitVoice`, and `clearHistory` own microphone and chat-history transitions.
- Files actions `chooseFiles`, `saveRecording`, `discardRecording`, `retryItem`, `startStreaming`, and `stopRecording` manage native inputs, processing retries, and recording UI.
- Note actions `createFolder`, `startEdit`, `saveNote`, `moveNote`, `deleteNote`, `importBackup`, `prefixLine`, and `surround` manage taxonomy, editing shortcuts, backup, and lifecycle.
- Calendar actions `changeMonth`, `syncAndRefresh`, `planProposal`, `confirmPlan`, `applyPlan`, and `dismissProposal` keep OAuth/events/proposals/plans synchronized.
- Learning actions `linkEvidence`, `finishReading`, `drill`, and `Anchor` refresh evidence, advance sessions, open targeted study, and render source navigation.
- Artifact actions `loadDecks`, `openDeck`, `deleteDeck`, `removePaper`, `selectPage`, and `toNotes` refresh flashcards, papers, handwriting pages, and note conversion.
- Video actions `deleteFrame` and `saveCapture` remove or verify captured frames.

## 10. Android application reference

### Networking and state

- `AxiomTraceApi.stats`, `notes`, `tasks`, `decks`, `deck`, `ask`, `setTaskDone`: typed core calls.
- `objectRequest`, `arrayRequest`: expose generic JSON contracts for the full native workspace.
- `multipart`: upload content URIs from Android's document picker.
- `multipartBytes`: upload recordings or generated bytes.
- `consumeEventStream`: wait for long-running OCR event streams.
- `multipartRequest`: stream multipart bodies with request IDs and bounded buffers.
- `get`, `getArray`, `request`, `requestArray`: perform checked IO-thread HTTP calls and propagate backend request IDs.
- JSON helpers `int`, `long`, `double`, `string`, `stringOrNull`, `mapObjects`: concise safe decoding.
- `ApiException`: carries status and request ID into visible diagnostics.
- `AxiomViewModel.refresh`: concurrently fetch stats, notes, tasks, decks, and the first deck.
- `connect`: replace the API base URL at runtime.
- `selectDeck`, `toggleTask`, `ask`: perform user actions and update Compose state.
- `fail`: create a user-facing error containing the correlated backend request ID.

### App shell, appearance, and data

- `MainActivity.onCreate`: launch Compose and the Axiom app.
- `AxiomApp`: own theme, selected tab, saved server URL, native workspace, and global AI bar.
- `normalizeServerUrl`: sanitize the runtime backend address.
- `AmbientBackground`, `StatusRow`, `TopBar`, `AiBar`, `TabBar`, `TabItem`, `HairlineDivider`: main shell composables.
- `AxiomColors` and `lerp`: define/animate semantic color tokens.
- `AxiomData.kt` classes: typed screens, features, backend stats/notes/tasks/decks/cards, ask result, and aggregate `MobileData`.
- `AxiomType.readingStyle`: increase tracking/line height for long-form reading.
- `MobileTheme`: Material theme bridge.
- `AxiomIcons.icon`, `stroked`, `rect`, `roundRect`: build consistent vector icons from paths.

### Native workspace and screens

- `NativeWorkspaceScreen`: route the ALL tab to each native feature.
- `ConnectionPanel`: save/connect to a laptop backend without rebuilding.
- `FilesNative`, `NotesManagerNative`, `AskNative`, `HandwritingNative`, `VideoNative`, `FlashcardsNative`, `AudiobooksNative`, `TasksNative`, `CalendarNative`, `SettingsNative`: native equivalents of the corresponding backend workflows.
- `MonthGrid`, `CalendarEventCard`: calendar visualization and external event opening.
- `ReadingPanel`, `AxSwitch`: dyslexia-friendly reading preference.
- `NativeRecorder`: microphone recording lifecycle and upload.
- `RemoteImage`: load backend image bytes into a native image view.
- `NativeScroll`, `NativeCard`, `NativeField`, `NativeButton`: common native UI primitives.
- `JSONArray.objects`, `JSONObject.textOrEmpty`, `formatSeconds`, `enc`, `formatEventTime`, `openUrl`: JSON/display/navigation helpers.
- `Screens.kt` `HomeScreen`, `NotesScreen`, `CardsScreen`, `PlannerScreen`: primary tab content.
- `BackendState`: consistent loading/error/retry display.
- `StatsGrid`, `TimerCard`, `ActionButton`, `ProgressLine`, `TodaysPlan`, `PlannerTaskRow`: reusable dashboard/planner composables.
- `timeAgo`: mobile activity timestamp formatting.
- `CalendarDates.eventLocalDate`, `taskDueDate`, `dayMarkers`: normalize ISO/task dates and calendar markers.
- `MarkdownParser`: tokenize headings, lists, code, quotes, links, emphasis, and inline math.
- `annotate`, `markdownAnnotated`, `MarkdownText`: turn parsed Markdown into styled Compose text.
- `MathText`: parse/render the supported math subset natively.

### Build-time connection behavior

`defaultApiBaseUrl()` in `mobile/app/build.gradle.kts` detects a development LAN address when possible, accepts `-PAXIOM_TRACE_API_URL=...` as an override, and falls back to Android emulator host alias `10.0.2.2`. The app can still change and persist the server URL at runtime.

## 11. Configuration and launchers

### `backend/core/config.py`

- `_boolean`, `_integer`, `_path`, `_csv`, `_id_set`: validate environment variables into safe typed settings.
- `Settings`: centralizes paths, host/port, upload limits, CORS/trusted hosts, model names, reranker limits, Google OAuth, Telegram policy, pet thresholds, and optional interfaces.
- `kind_of(path)`: classify supported file extensions for ingestion.

### Windows launcher

- `Require-Command`: fail early with actionable prerequisites.
- `Wait-ForUrl`: poll a health URL with a deadline.
- `Stop-ProcessTree`: terminate a Windows process and descendants.
- `start-axiom-trace.ps1`: lock dependencies, expose bundled Node when necessary, launch backend/web invisibly, store PID/log files, health-check both, and clean up on failure.
- `stop-axiom-trace.ps1`: read the known PID files, stop only those process trees, and remove PID files.

### Containers and make targets

- `compose.yaml` runs backend and web as separate services, persists backend data/inbox/model cache, exposes LM Studio through `host.docker.internal`, and offers an Android build profile.
- `Makefile`/`scripts/run-backend`/`scripts/run-frontend` provide platform-friendly developer entry points.
- `backend/Dockerfile`, `web/Dockerfile`, and `mobile/Dockerfile` produce isolated runtime/build images.

## 12. Test suite: what each file protects

The suite is not a single “AI accuracy” test. It separates deterministic contracts from model-dependent quality.

| Test file | Contract protected |
| --- | --- |
| `test_capture.py` | Event sanitization, persistence, API batches, and retry idempotency |
| `test_demo_seed.py` | Deterministic seed shape and no duplicate demo records |
| `test_graph_rag.py` | Prerequisite/target/dependent expansion, ordering, reasons, and fallback |
| `test_mastery.py` | BKT arithmetic, confidence, half-life, recall, due queue, and persistence |
| `test_gaps_planner.py` | Gap ranking, prerequisite-first sessions, diagnostics, and adaptation |
| `test_quiz_concepts.py` | Graph extraction cleanup, grounded questions, grading, and misconceptions |
| `test_rag.py`, `test_reranker.py` | Citation construction, media links, candidate scoring, and safe fallback |
| `test_vectorstore.py`, `test_vectorstore_recovery.py` | LanceDB writes/search/locking and index repair |
| `test_server_api.py` | FastAPI contracts, headers, errors, validation, and endpoints |
| `test_notes.py`, `test_notes_placement.py`, `test_note_pdf.py`, `test_mathmd.py` | Portable Markdown, visual placement, PDF output, and math normalization |
| `test_diagrams.py`, `test_figures.py`, `test_db_figures.py` | Figure extraction, graph validation, overlays, and media persistence |
| `test_video.py` | Stable frames, OCR regions, consolidation, and review |
| `test_calendar_planner.py` | Protected events, priority, candidate slots, conflicts, confirmation flags |
| `test_question_papers.py`, `test_flashcards.py` | Grounded artifact validation, persistence, PDFs, and commands |
| `test_pet_*`, `test_menubar.py` | Pet state/policy/voice/UI boundaries and optional desktop behavior |
| `integrations/browser-capture/tests/*` | Durable queue, acknowledgment, retry, receiver restrictions, and settings |
| Android unit tests | Markdown/math parsing and calendar date logic |

Verified project snapshot used in the presentation material:

- 252 backend tests passed, with one skipped in the full verification run.
- Web lint, TypeScript checks, and production build passed.
- Browser extension tests and JavaScript syntax checks passed.
- Launcher health checks returned HTTP 200 for web and API.
- Tested replay scenarios produced zero duplicate records.
- The seeded story contains 3 evidence sources, 8 concepts, and 8 prerequisite edges.

These numbers are a verification snapshot, not permanent constants. Re-run checks before quoting them in a later submission.

## 13. How to run and demonstrate

### Deterministic presentation setup

```powershell
cd backend
uv run --frozen --python 3.12 python scripts\seed_axiom_trace_demo.py
cd ..
.\start-axiom-trace.ps1
```

Open:

- Web: `http://127.0.0.1:3000/learn`
- API documentation: `http://127.0.0.1:8010/api/docs`

Stop:

```powershell
.\stop-axiom-trace.ps1
```

### Four-minute demo order

1. Open **Concept Map**, select **Depth-First Search**, and point to Stacks and Recursion as prerequisites.
2. Open **Adaptive Path** and explain `P(known)`, confidence, attempts, and forgetting risk.
3. Show **Learning Evidence** with source domain, dwell, processing state, and linked concepts.
4. Start a DFS study session and ask: “Why does DFS use a stack, and when would BFS be better?”
5. Open **Why this answer?** and read one prerequisite reason and one graph path.
6. Answer a quiz and return to the graph/gaps to show that the next recommendation uses updated state.

### Safe demo fallbacks

- No internet: use the deterministic local seed.
- No LanceDB: demonstrate graph-bound evidence and show the reported mode.
- No LM Studio: demonstrate capture, graph, mastery, tests, and API responses, but do not claim live generation.
- Browser capture uncertainty: use the already seeded evidence and explain the extension separately.

## 14. Project presentation pitch to memorize

This version is designed for a technical project evaluation. At a calm pace it is about six to seven minutes, excluding the live demo.

### Opening — 30 seconds

> Good morning. We are team Highest in the Room, and our project is Axiom Trace. Our theme is Knowledge-Graph-Guided RAG for Personalized Student Knowledge-Tracing. The problem we address is simple: current study assistants can answer a question, but they usually do not know what that particular student understands, which prerequisite they are missing, or why a retrieved source is pedagogically useful. Axiom Trace turns the student's own learning evidence into a living model of what they know and what they should study next.

### Problem — 40 seconds

> A student's knowledge is fragmented across notes, PDFs, videos, handwritten pages, browser reading and quiz attempts. A normal vector RAG system finds semantically similar text, but similarity is not the same as learning relevance. If a student asks about depth-first search while being weak in stacks, retrieving only DFS passages may produce an answer without fixing the real gap. At the same time, dashboards that track marks usually do not change how evidence is retrieved. We wanted to close that loop.

### Solution — 45 seconds

> Axiom Trace has three connected models. First, an evidence model stores the student's own material with provenance. Second, a prerequisite graph represents how concepts depend on one another. Third, Bayesian Knowledge Tracing maintains a probability of mastery for every concept. When the student asks a question, retrieval starts from the active concept, expands into the weakest prerequisites and useful dependents, combines that graph evidence with semantic search, reranks the candidate pool, and sends only the selected evidence to a local language model. The answer returns citations and a visible explanation of why each source was chosen.

### Architecture — 70 seconds

> The complete pipeline is local-first. Files, notes, audio, video, handwriting and attention-qualified browser reading enter one FastAPI ingestion contract. The worker extracts text, page or timestamp provenance, visuals and calendar commitments. It stores metadata and learning state in SQLite, creates normalized 384-dimensional embeddings, and writes them to LanceDB. The concept builder extracts grounded concepts from the student's notes, resolves prerequisite edges, removes unsupported nodes and binds each concept to its strongest source chunks. Quiz attempts update P-known using Bayesian Knowledge Tracing. For a question, the graph retriever takes up to four weak prerequisites and four dependents, adds up to three chunks per node, unions them with semantic candidates, deduplicates by chunk ID, caps the pool at 24, reranks it, and retains the top evidence in prerequisite-to-target order. LM Studio then generates the answer locally from that evidence.

### Personalization — 55 seconds

> Personalization is not a prompt adjective in our system; it changes the computation. A correct or incorrect response changes the posterior probability that the student knows a concept. Attempt count gives us a confidence estimate, so untested is different from tested-and-weak. Missing prerequisites are ranked before weak target concepts. Once mastery reaches 0.85, the concept enters spaced review. Recall then decays exponentially using a learned half-life, so the same learner state affects immediate gaps, the next session, the review queue and graph-guided retrieval.

### Explainability and privacy — 45 seconds

> Every generated answer exposes its retrieval mode, seed concept, expanded concepts, graph paths and evidence reasons. A source is labeled as prerequisite, target, dependent or semantic seed. This lets the learner and evaluator inspect whether the graph actually influenced retrieval. The required system runs locally with SQLite, LanceDB, local files and LM Studio. Browser evidence is captured only after visible dwell, stored in a durable retry queue and accepted by the backend using an idempotent event ID. Dwell is treated only as a reading signal; mastery changes only after assessed answers.

### Results — 40 seconds

> Our verification focuses on behavior we can prove. In the completed run, 252 backend tests passed with one skipped; frontend lint, type checks and the production build passed; browser extension tests passed; and both the web and API health checks returned HTTP 200. Replayed browser events created zero duplicates in tested scenarios. The deterministic demonstration recreates three evidence sources, eight concepts and eight prerequisite edges. These results verify functional correctness. We do not present the seeded mastery values as measured learning gains; retrieval quality, latency and educational outcomes require a formal user study.

### Demo transition — 15 seconds

> I will now show the closed loop, not just separate screens: first the prerequisite graph, then the learner's mastery state, then a graph-guided cited answer, and finally how one quiz response changes the next recommendation.

### Closing — 25 seconds

> Axiom Trace changes RAG from “find text similar to my question” into “find the evidence this learner needs next.” Its contribution is the closed loop between personal evidence, prerequisite structure, Bayesian mastery and explainable retrieval. The immediate next step is a controlled comparison against semantic-only RAG using prerequisite recall, citation precision, faithfulness, latency and measured learning gain. Thank you.

## 15. Startup pitch to memorize

This version is about three minutes and emphasizes user pain, differentiation, market path, and responsible scale.

> Students already have enough content. What they lack is a system that remembers what they actually studied, understands what they have not mastered, and tells them the next best action.
>
> Today, notes live in one app, PDFs in folders, videos in another tab, and AI chat in a separate window. Generic AI tutors answer the current prompt, but they reset context, retrieve by similarity, and cannot explain which prerequisite the learner is missing. That creates confident answers without a reliable learning path.
>
> Axiom Trace is a private learning memory and adaptive tutor. It converts the student's own notes, documents, videos, handwriting and focused web reading into a personal evidence layer. It builds a prerequisite knowledge graph, tracks mastery with Bayesian Knowledge Tracing, and uses both to guide retrieval. When a learner asks about a topic, Axiom Trace retrieves not only similar passages but also evidence for the weak foundations beneath that topic. Every answer is cited and includes a visible “why this answer” trace.
>
> Our wedge is serious exam preparation for students who already accumulate large amounts of material but struggle to turn it into an adaptive plan. The product can begin as a local-first student application with a free personal tier. A paid tier can add encrypted multi-device sync, larger local or hosted model options, advanced analytics and automated study plans. An institution tier can offer consent-based cohort analytics, course graph templates and private deployment without exposing raw student notes.
>
> Our defensibility is not a chatbot wrapper. Over time, the product builds a permissioned longitudinal learning graph: evidence provenance, prerequisite structure, mastery history, misconception patterns and forgetting curves. The system's retrieval and recommendations improve because of that structured history while remaining explainable.
>
> We have already built the complete functional loop: idempotent evidence capture, local ingestion, SQLite and LanceDB persistence, prerequisite graph construction, Bayesian mastery, adaptive sessions, local reranking, cited generation, web and Android clients, and deterministic verification. The next milestone is a pilot with a focused course cohort. We will compare Axiom Trace with semantic-only RAG on citation precision, prerequisite recall, answer faithfulness, time to close knowledge gaps and learning gain.
>
> Our vision is to make every student's scattered study material behave like one private tutor that remembers what they learned, understands why they are stuck, and guides the next step. Axiom Trace is not trying to replace teachers. It gives each learner and teacher an inspectable map between evidence, understanding and action.

## 16. Thirty-second versions

### Technical elevator pitch

> Axiom Trace is a local-first adaptive learning platform. It ingests a student's own notes and focused reading, builds a prerequisite knowledge graph, and tracks concept mastery with Bayesian Knowledge Tracing. Its RAG pipeline expands retrieval through the student's weak prerequisites, reranks the evidence locally, and returns cited answers with a visible reason for every selected source. Quiz attempts update mastery, and that same state drives the next study session and forgetting review.

### Startup elevator pitch

> Axiom Trace turns a student's scattered notes, PDFs, videos and web reading into one private learning memory. Unlike a generic AI tutor, it knows which prerequisites the learner is missing, explains why it selected each source, and updates the next study action after every quiz. We are starting with exam-focused students and building toward private, explainable adaptive learning for individuals and institutions.

## 17. Judge and investor questions with strong answers

### “Where is the transformer?”

The system uses pretrained transformer models at three points: sentence-transformer embeddings, a Qwen reranker, and local answer generation through LM Studio. The project contribution is not foundation-model training; it is the graph- and mastery-guided orchestration around those models.

### “Why is this better than normal RAG?”

Normal RAG optimizes semantic similarity to the question. Axiom Trace adds pedagogical relevance: weak prerequisites, the target concept, and useful dependents become explicit candidate sources. The response also exposes whether graph guidance was actually used.

### “How is it personalized?”

Each concept has a persisted `P(known)`, attempts, confidence, half-life, recall, and risk. Those values change neighbor ordering, gap ranking, session construction, review timing, and retrieval context.

### “How do you know the student read the browser content?”

We do not claim certainty. The extension records cumulative foreground visibility as attention evidence. It is a weak signal for evidence collection. Only quiz performance changes knowledge mastery.

### “Can the model hallucinate?”

It can, so the system constrains the prompt to selected source chunks, requires exact source labels, returns citations, and exposes retrieval evidence. A formal evaluation should measure citation precision, faithfulness, and unsupported-claim rate.

### “What happens when the vector database fails?”

Graph-bound evidence can still ground the answer. The response reports the actual mode. If no graph evidence is available, it reports `vector_fallback` instead of pretending graph guidance occurred.

### “What happens when the local LLM is offline?”

The graph, mastery, evidence, gaps, sessions, and deterministic analytics still work. Quiz serving can use cached questions. The demo should not claim a live generated answer when the model is unavailable.

### “Is the graph manually created?”

The local model proposes concepts and prerequisites from the student's own notes. The application then normalizes names, removes invalid/self references, assigns safe tiers, prunes ungrounded concepts, persists edges, and binds nodes back to source chunks.

### “How do you avoid duplicate browser captures?”

The extension durably queues events and the server stores `event_id` as a primary key. Retries return the existing item instead of creating a new one. Atomic file replacement prevents partial local files.

### “What is your strongest evidence today?”

Contract tests verify the complete behavior: graph expansion and explanation, BKT updates, prerequisite-first planning, idempotent capture, vector locking/recovery, API contracts, and deterministic reseeding. This is engineering evidence, not yet a classroom efficacy result.

### “What is the business model?”

Free local personal use can drive adoption. Paid individual features can include encrypted sync, advanced analytics and model options. Institution plans can offer private deployment, course graph templates, consent-based analytics and administrative controls.

### “What is defensible?”

The defensible asset is a permissioned longitudinal learning graph connecting source provenance, prerequisite structure, mastery trajectories, misconceptions and forgetting—not a single chat completion. Explainable policies and private deployment also matter in education.

### “What would you build next?”

First, an evaluation harness comparing semantic-only and graph-guided retrieval. Second, learner/instructor graph correction controls. Third, authentication and encrypted sync for multi-device use. Fourth, a pilot measuring time to close gaps and learning gain.

## 18. Honest limitations and roadmap

### Current limitations

- No formal latency benchmark is included in the verified snapshot.
- Retrieval quality and answer faithfulness need a labeled evaluation set.
- Educational efficacy needs real learners and a controlled baseline.
- Model-extracted prerequisite graphs can be wrong and need human correction UX.
- The local API has no authentication contract and should not be exposed directly to the internet.
- Cleartext LAN access is acceptable only for development on trusted networks.
- The Android client does not yet expose every web workflow, particularly full conflict-plan review and question-paper UI.
- Optional Calendar/Telegram integrations introduce external privacy and configuration considerations.

### Evaluation roadmap

1. Freeze a learner-question-evidence dataset.
2. Compare semantic-only vs graph-guided retrieval on identical queries.
3. Measure prerequisite recall@K and citation precision.
4. Judge faithfulness and unsupported claims blindly.
5. Measure p50/p95 retrieval and total answer latency.
6. Run ablations without mastery ordering, graph expansion, and reranking.
7. Pilot with students and compare pre/post concept tests plus time-to-mastery.
8. Add graph correction and audit logs before institutional rollout.

## 19. Memorization plan

Do not memorize every sentence first. Memorize this seven-word spine:

```text
Problem → Evidence → Graph → Mastery → Retrieval → Proof → Vision
```

For each word, remember one sentence:

- **Problem:** Similarity-based AI does not know the learner's missing prerequisite.
- **Evidence:** All student material enters one local, provenance-preserving pipeline.
- **Graph:** Concepts are connected by prerequisites and bound back to sources.
- **Mastery:** Quiz attempts update Bayesian `P(known)` and forgetting risk.
- **Retrieval:** Weak neighbors change which evidence reaches the generator.
- **Proof:** Tests verify behavior; learning gains remain future evaluation.
- **Vision:** One private tutor connecting what the learner read, knows, and should do next.

Practice in three rounds:

1. Deliver only the seven spine sentences without slides.
2. Add one technical detail and one example to each.
3. Practice the demo transition and every fallback separately.

The one line to return to if you lose your place is:

> Axiom Trace closes the loop between the student's own evidence, prerequisite structure, measured mastery and the next learning action.

## 20. Final presentation discipline

- Say **“verified functional behavior”**, not “proven learning improvement.”
- Say **“attention-qualified reading evidence”**, not “we know the student understood the page.”
- Say **“pretrained transformer-backed system”**, not “we trained a transformer.”
- Show the retrieval trace immediately after the answer; that is the clearest proof of graph guidance.
- Use one concrete example throughout: DFS depends on stacks and recursion; BFS is a useful dependent/comparison.
- Keep optional features such as pet, calendar, audiobooks, and Telegram in reserve for Q&A. They demonstrate platform breadth but should not distract from the T2-2 loop.
- End on the closed loop: evidence changes the graph context, answers change mastery, and mastery changes the next retrieval and recommendation.
