# Axiom Trace delivery checklist

This checklist converts the adopted T2-2 merge plan into verifiable repository work.

## Foundation

- [x] Create a clean `agent/axiom-trace-submission` branch in a fresh repository folder.
- [x] Replace broken nested-repository pointers with a normal, portable source tree.
- [x] Keep the original Study Buddy and Glean folders untouched.
- [x] Make the Python backend installable with a locked development test dependency.

## Learning evidence

- [x] Port the Manifest V3 browser capture extension.
- [x] Point the extension at `POST /api/captures` on port 8010.
- [x] Preserve URL, title, visible text, dwell time, capture time, and metadata.
- [x] Make capture retries idempotent through an event ledger.
- [x] Feed captured pages into the existing item/chunk ingestion path.
- [x] Expose recent captures through `GET /api/learn/evidence`.

## Knowledge-graph-guided RAG

- [x] Seed retrieval from the concept currently being studied.
- [x] Expand into weak immediate prerequisites and dependents.
- [x] Merge graph-bound evidence with semantic candidates and remove duplicates.
- [x] Rerank the bounded candidate set.
- [x] Order context as prerequisite → target → dependent → semantic fallback.
- [x] Return a retrieval trace with graph paths and human-readable evidence reasons.
- [x] Keep the graph path usable if the vector index is temporarily unavailable.

## Personalized knowledge tracing

- [x] Retain Bayesian Knowledge Tracing after every quiz attempt.
- [x] Retain confidence, mastery thresholds, forgetting risk, and spaced review.
- [x] Prioritize weak prerequisites in graph expansion and gap ranking.
- [x] Show mastery, gaps, concept map, sessions, and evidence in the focused UI.

## Submission experience

- [x] Rebrand the product and API as Axiom Trace.
- [x] Hide unrelated inherited tools from the primary submission navigation.
- [x] Add “Why this answer?” retrieval disclosure.
- [x] Add a visible Learning Evidence feed and source-rebind action.
- [x] Add one-command Windows start and stop scripts.
- [x] Add a deterministic Computer Science demo seed.
- [x] Add the PPT-ready system architecture image.
- [x] Document architecture, evaluation, and the live-demo sequence.

## Verification and delivery

- [x] Run browser-capture JavaScript tests and syntax checks.
- [x] Run focused backend integration tests.
- [x] Run ESLint, TypeScript, and a full Next.js production build.
- [x] Run the complete backend test collection and classify platform-only failures.
- [x] Exercise the one-command launcher against live ports 3000 and 8010.
- [x] Audit the final diff for generated data, secrets, and personal paths.
- [x] Push the integration branch and open a draft pull request.

## Deliberately excluded from the T2-2 submission path

- Glean's separate FastAPI service, SQLite database, embeddings, and search UI.
- Duplicate capture storage or a second retrieval stack.
- Calendar, Telegram, desktop pet, audiobook, handwriting, flashcard, question-paper,
  and video-review features in the main navigation.
- Cloud deployment and multi-user authentication.
- Training a new transformer; the project applies local embedding, reranking, and
  generation models around an explicit student knowledge graph.
