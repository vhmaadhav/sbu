# Axiom Trace live demo runbook

## Before presenting

Install Python 3.12, `uv`, LM Studio, and one of pnpm, Bun, or npm. In LM Studio,
load the model named in `backend/.env` or the default `qwen/qwen3-4b` and expose
its OpenAI-compatible server at `http://localhost:1234/v1`.

From the repository root:

```powershell
cd backend
uv run --frozen --python 3.12 python scripts/seed_axiom_trace_demo.py
cd ..
.\start-axiom-trace.ps1
```

Open `http://127.0.0.1:3000/learn`.

To demonstrate live browser capture, open `chrome://extensions`, enable Developer
mode, choose **Load unpacked**, and select `integrations/browser-capture`. Keep
the Axiom Trace API running on port 8010.

## Four-minute judge flow

1. **Start with the map.** Open Concept Map and select **Depth-First Search**.
   Point out that Stacks and Recursion are weak prerequisites, not generic related
   topics.
2. **Show the learner state.** Return to Adaptive Path. Explain that `P(known)`,
   attempts, confidence, and forgetting risk come from persisted quiz behavior.
3. **Show real evidence.** In Learning Evidence, highlight the captured source,
   URL domain, dwell time, processing state, and concept-link count.
4. **Ask one question.** In a DFS study item, ask: “Why does DFS use a stack, and
   when would BFS be better?”
5. **Open “Why this answer?”** Read the visible path and the prerequisite/target/
   dependent reasons. This is the proof that retrieval followed the student's
   graph rather than vector similarity alone.
6. **Close the loop.** Answer a quiz item and return to gaps or the map to show
   that the learner state is updated for the next recommendation.

## Capture demo

Visit a technical article, keep the tab visible for at least 30 seconds, and
select meaningful text if available. Open the extension popup and send queued
events. In Axiom Trace, select **Link new evidence**. The page should appear in
Learning Evidence and become eligible for concept binding after ingestion.

## Safe fallback

If internet access is poor, use the seeded local story; it needs no external
web page. If the vector index is unavailable, the graph-bound evidence path still
works and reports its retrieval mode. If LM Studio is unavailable, demonstrate
the graph, evidence feed, and tests, but do not claim a live generated answer.

## Stop

```powershell
.\stop-axiom-trace.ps1
```
