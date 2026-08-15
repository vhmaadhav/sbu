# Evaluation and evidence

## What is verified

| Claim | Evidence |
| --- | --- |
| Capture events persist attention metadata and survive retries without duplicates. | `backend/tests/test_capture.py` exercises the ingestion function and real FastAPI contract. |
| Retrieval expands prerequisites, target, and dependents in pedagogical order. | `backend/tests/test_graph_rag.py` builds Arrays → Stacks → Graph Traversal and asserts roles and paths. |
| Every displayed retrieval reason matches the API response contract. | The graph-RAG integration test asserts source labels and human-readable prerequisite reasons. |
| The Computer Science demo is repeatable and does not duplicate its own records. | `backend/tests/test_demo_seed.py` seeds twice and asserts one three-event evidence set and both DFS prerequisite paths. |
| The vector write lock works on Windows as well as POSIX systems. | `backend/tests/test_vectorstore.py` acquires the platform-selected lock implementation. |
| The web interface is production-buildable. | ESLint, TypeScript `--noEmit`, and `next build` are required before delivery. |

## Reproduce the focused checks

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q `
  tests\test_capture.py `
  tests\test_demo_seed.py `
  tests\test_graph_rag.py `
  tests\test_vectorstore.py `
  tests\test_rag.py `
  tests\test_gaps_planner.py `
  tests\test_quiz_concepts.py `
  tests\test_mastery.py `
  tests\test_server_api.py
```

```powershell
cd web
pnpm run lint
pnpm exec tsc --noEmit
pnpm run build
```

The repository records exact results in the pull-request body rather than
hard-coding a score that can become stale.

## Metrics for a formal experiment

For a larger evaluation, compare semantic-only retrieval against graph-guided
retrieval on the same student-question set and report:

- prerequisite evidence recall at K;
- citation precision judged against source chunks;
- answer faithfulness and unsupported-claim rate;
- knowledge-gap detection precision against instructor labels;
- next-question learning gain;
- p50/p95 retrieval latency and total answer latency;
- ablations for graph expansion, mastery ordering, and reranking.

Do not present demo mastery values as experimental learning gains. The seed is a
reproducible product story; the tests verify behavior, not educational efficacy.
