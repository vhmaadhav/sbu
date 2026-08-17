# Model provider configuration

Axiom Trace talks to one OpenAI-compatible chat endpoint for generation, vision,
and structured extraction. That endpoint can be a local LM Studio server or a
hosted gateway; both are configured through the same `LMSTUDIO_*` settings in
`backend/.env`, and the code discovers the differences between them at runtime.

This document records what each option actually supports, because the two are
not interchangeable — three capabilities differ, and two of them fail *silently*
if they are not configured for.

## The settings

| Setting | Meaning |
| --- | --- |
| `LMSTUDIO_BASE_URL` | The OpenAI-compatible base URL. Its hostname decides whether the app reports itself as local or remote. |
| `LMSTUDIO_API_KEY` | Bearer token. `lm-studio` for a local server; a real key for a gateway. |
| `LMSTUDIO_MODEL` | Text generation: study notes, answers, concept extraction, quizzes. |
| `VISION_MODEL` | Image input: handwriting OCR, lecture-board frames, diagram figures. **Must accept images.** |
| `LLM_REASONING_EFFORT` | Sent as `reasoning_effort` on every call. Defaults to `low`. Set empty to omit the field. |
| `RERANKER_ENABLED` | Cross-encoder reranking. Requires token logprobs from the endpoint. |

`GET /api/system/provider` reports the resolved values from the running backend,
and the Settings screen renders them. Nothing about the provider is hard-coded in
the UI.

## Capability matrix

Measured on 2025-08-16 against `https://opencode.ai/zen/go/v1` (OpenCode Go).

| Capability | Local LM Studio | OpenCode Go gateway |
| --- | --- | --- |
| Text generation | yes | yes |
| Image input | depends on model | **only some models** — see below |
| `response_format: json_schema` | yes | **no** — 400 `This response_format type is unavailable now` |
| Token logprobs (reranker) | yes | **no** — keep `RERANKER_ENABLED=false` |
| `reasoning_effort` | ignored or accepted | yes, and **required** for reasoning models |

The application degrades on its own for the first three: each unsupported feature
is probed once, and the process remembers the answer. No configuration is needed
to *avoid* a crash. Configuration is only needed to get good results.

## Two failure modes worth knowing

### 1. A reasoning model can return nothing at all

`deepseek-v4-flash` is a reasoning model. Left unbounded it can spend its entire
`max_tokens` budget on reasoning tokens and return `content: ""` with
`finish_reason: "length"`. Measured rate on a long-form study-note prompt:

| `max_tokens` | empty completions |
| --- | --- |
| 900 | 4 of 4 |
| 1400 | 2 of 4 |
| 2400 | 1 of 4 |
| 4000 | 2 of 4 |

Raising the ceiling does not fix it — the behaviour is bimodal, so a bigger
budget just buys a longer runaway. `reasoning_effort` does fix it: `low` and
`none` both produced 0 empties in 4 runs.

`core.llm.chat` handles this on three fronts, so an ordinary install never sees
it:

1. It sends `LLM_REASONING_EFFORT` (default `low`) on every call.
2. On an empty completion it escalates — resample, then double the budget, then
   force `reasoning_effort: none`.
3. If all three attempts come back empty it raises `LocalLLMUnavailable`. It
   never returns `""`, which is what previously produced blank study notes and
   blank audiobook scripts with no error anywhere.

If an endpoint rejects `reasoning_effort` with a 400, the client drops the field
and stops sending it for the rest of the process.

### 2. A "vision" model may not accept images

`gpt-5.6-luna` answers text prompts normally but rejects **every** image request
through this gateway with a bare HTTP 400 and an empty body — no error message.
All 26 gateway models were probed with the same small PNG:

| Result | Models |
| --- | --- |
| Accepts images and reads them | `kimi-k2.5`, `kimi-k2.6`, `minimax-m3` |
| Accepts, returns empty content | `glm-5`, `glm-5.1`, `glm-5.2`, `kimi-k2.7-code`, `kimi-k3`, `mimo-v2.5`, `minimax-m2.7` |
| Rejects image input | `deepseek-v4-flash`, `deepseek-v4-pro`, `glm-5.3`, `gpt-5.6-luna`, `hy3`, `hy3-preview`, `mimo-v2-omni`, `mimo-v2-pro`, `mimo-v2.5-pro`, `minimax-m2.5` |
| Unavailable at probe time (503) | `grok-4.5`, `qwen3.5-plus`, `qwen3.6-plus`, `qwen3.7-max`, `qwen3.7-plus`, `qwen3.8-max` |

The three image-capable models were then scored on the app's real vision
workloads — a lecture-board frame and a handwritten line — against a known
ground truth:

| Model | Facts read | Board OCR | Handwriting | Latency | Leaks reasoning into `content` |
| --- | --- | --- | --- | --- | --- |
| `minimax-m3` | 10/10 | pass | pass | 4.5 s | no |
| `kimi-k2.5` | 10/10 | pass | pass | 8.1 s | **yes** |
| `kimi-k2.6` | 10/10 | pass | pass | 7.1 s | **yes** |

**`minimax-m3` is the configured choice.** All three read the images correctly,
but the two Kimi models prefix their answer with their own reasoning ("The user
wants me to transcribe…"), which lands verbatim in handwriting transcriptions and
lecture-board OCR. `minimax-m3` returns clean output and is the fastest.

`core.llm.chat_vision` now turns the bare 400 into a `LocalLLMUnavailable` that
names the model and says to change `VISION_MODEL`, instead of the unreadable
traceback it used to surface several layers up.

## Current configuration

`backend/.env` is wired to the OpenCode Go gateway:

```ini
LMSTUDIO_BASE_URL=https://opencode.ai/zen/go/v1
LMSTUDIO_MODEL=deepseek-v4-flash
VISION_MODEL=minimax-m3
LLM_REASONING_EFFORT=low
RERANKER_ENABLED=false
```

`RERANKER_ENABLED=false` is correct for this gateway: reranking scores candidates
from the logprobs of a single yes/no token, and the gateway does not return
logprobs. Retrieval falls back to vector order, which the retrieval trace reports
honestly as its mode.

## Privacy boundary

This matters and the UI now says so. With a **remote** endpoint, notes,
recordings, and search indexes still stay on the machine, but **prompts and
captured page text are sent to the gateway** for generation and vision. The
Settings screen reads the resolved hostname and switches its panel from "Private
by default" to "Partially private", naming the host.

To keep everything on the machine, point `LMSTUDIO_BASE_URL` at a local LM Studio
server and pick a local vision model:

```ini
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_API_KEY=lm-studio
LMSTUDIO_MODEL=qwen3.5-4b-mlx
VISION_MODEL=qwen/qwen3-vl-4b
LLM_REASONING_EFFORT=
RERANKER_ENABLED=true
```

## Verifying a provider change

After changing any of these, restart the backend and confirm:

```bash
curl -s http://127.0.0.1:8010/api/system/provider
```

Then check the Settings screen, which shows the endpoint, both model names, and
the correct privacy panel.
