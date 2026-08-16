"""OpenAI-compatible chat client with tolerant JSON handling.

Works against either a local LM Studio server or a hosted OpenAI-compatible
gateway; both are configured through the same LMSTUDIO_* settings. Capability
differences between the two are discovered at runtime and cached, so nothing
here needs to know which one it is talking to.
"""
import json
import logging
import re

from openai import BadRequestError, OpenAI

from core.config import (
    LLM_REASONING_EFFORT, LMSTUDIO_API_KEY, LMSTUDIO_BASE_URL, LMSTUDIO_MODEL, VISION_MODEL,
)

logger = logging.getLogger(__name__)

_client = OpenAI(base_url=LMSTUDIO_BASE_URL, api_key=LMSTUDIO_API_KEY)

# A local model server drops connections under sustained load — a long lecture
# sends dozens of back-to-back requests — and one reset used to fail the whole
# ingestion. The SDK retries connection errors, timeouts and 5xx with backoff;
# a server that is genuinely down still exhausts these and raises, so the
# fail-closed behaviour in require_available is unchanged.
REQUEST_RETRIES = 2

# A reasoning model can spend its entire max_tokens budget thinking and return
# an empty completion with finish_reason="length". Measured against
# deepseek-v4-flash that happened on 4 of 4 long-form generations at 900
# tokens and 2 of 4 at 1400, and raising the ceiling did not help — the run is
# bimodal, so a fresh sample is the cure, not a bigger budget.
EMPTY_COMPLETION_ATTEMPTS = 3

# Capability probes. Not every OpenAI-compatible server accepts these, and the
# ones that don't answer with a 400 rather than ignoring the field, so each is
# tried once and disabled for the rest of the process if it is rejected.
_supports_reasoning_effort = bool(LLM_REASONING_EFFORT)
_supports_json_schema = True


class LocalLLMUnavailable(RuntimeError):
    """The only configured LLM endpoint is unavailable or missing its model."""


def _unsupported_parameter(error: BadRequestError) -> bool:
    """A 400 that means "I don't know this field", not "your request is bad"."""
    text = str(error).lower()
    return any(
        hint in text
        for hint in ("unavailable now", "unsupported", "unrecognized", "unknown parameter",
                     "not supported", "invalid_request_error")
    )


def _completion(*, model: str, messages: list, temperature: float, max_tokens: int,
                timeout: float, effort: str | None = None, **extra):
    """One chat completion, degrading gracefully if reasoning_effort is refused."""
    global _supports_reasoning_effort
    options = _client.with_options(timeout=timeout, max_retries=REQUEST_RETRIES)
    if effort and _supports_reasoning_effort:
        try:
            return options.chat.completions.create(
                model=model, messages=messages, temperature=temperature,
                max_tokens=max_tokens, reasoning_effort=effort, **extra,
            )
        except BadRequestError as error:
            if not _unsupported_parameter(error):
                raise
            logger.info("endpoint rejected reasoning_effort; continuing without it")
            _supports_reasoning_effort = False
    return options.chat.completions.create(
        model=model, messages=messages, temperature=temperature,
        max_tokens=max_tokens, **extra,
    )


def _clean(text: str | None) -> str:
    """Drop the <think> block some models emit inline in the content field."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()


def is_available() -> bool:
    try:
        models = _client.with_options(timeout=2.0, max_retries=0).models.list()
        available = {model.id for model in models.data}
        return LMSTUDIO_MODEL in available and VISION_MODEL in available
    except Exception:
        return False


def require_available() -> None:
    """Fail closed: this application never substitutes a remote or heuristic LLM."""
    if not is_available():
        raise LocalLLMUnavailable(
            f"Local-network LM Studio is unavailable, or does not serve {LMSTUDIO_MODEL!r} "
            f"and {VISION_MODEL!r}, at {LMSTUDIO_BASE_URL}."
        )


def chat(system: str, user: str, temperature: float = 0.3, max_tokens: int = 2048,
         model: str | None = None, timeout: float = 60.0) -> str:
    require_available()
    target = model or LMSTUDIO_MODEL
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    # Escalate rather than just resample: a fresh sample usually lands in the
    # short-reasoning mode, but a budget too small to hold any reasoning at all
    # never will, so the ladder ends with reasoning switched off entirely.
    for attempt, (budget, effort) in enumerate(
        (
            (max_tokens, LLM_REASONING_EFFORT),
            (max_tokens * 2, LLM_REASONING_EFFORT),
            (max_tokens * 2, "none"),
        ),
        start=1,
    ):
        resp = _completion(
            model=target, messages=messages, temperature=temperature,
            max_tokens=budget, timeout=timeout, effort=effort or None,
        )
        text = _clean(resp.choices[0].message.content)
        if text:
            return text
        # An empty answer used to be returned as "", which silently produced
        # blank study notes and blank audiobook scripts instead of an error.
        logger.warning(
            "empty completion from %s (finish_reason=%s, budget=%d, effort=%s), attempt %d/3",
            target, resp.choices[0].finish_reason, budget, effort or "unset", attempt,
        )
    raise LocalLLMUnavailable(
        f"{target!r} returned no content in 3 attempts at {LMSTUDIO_BASE_URL} — it spent "
        f"every token budget reasoning. Set LLM_REASONING_EFFORT=none for this endpoint."
    )


def chat_vision(prompt: str, images_b64: list[str], temperature: float = 0.0,
                max_tokens: int = 256, model: str | None = None) -> str:
    """Send a text prompt plus one or more base64 PNG images to the vision model."""
    require_available()
    content: list = [{"type": "text", "text": prompt}]
    for b64 in images_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        })
    target = model or VISION_MODEL
    try:
        resp = _completion(
            model=target, messages=[{"role": "user", "content": content}],
            temperature=temperature, max_tokens=max_tokens, timeout=90.0,
            effort=LLM_REASONING_EFFORT or None,
        )
    except BadRequestError as error:
        # A text-only model answers an image request with a bare 400 and no
        # message, which surfaced as an unreadable traceback several layers up.
        raise LocalLLMUnavailable(
            f"{target!r} rejected image input at {LMSTUDIO_BASE_URL}. Set VISION_MODEL "
            f"to a model that accepts images."
        ) from error
    return _clean(resp.choices[0].message.content)


def _extract_json(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?|\n?```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


def chat_json(system: str, user: str, max_tokens: int = 1024,
              model: str | None = None, timeout: float = 60.0) -> dict:
    """One retry with a fix-your-JSON prompt, then raise."""
    raw = chat(system + " Respond with a single JSON object only, no prose.", user,
               temperature=0.1, max_tokens=max_tokens, model=model, timeout=timeout)
    try:
        return _extract_json(raw)
    except Exception:
        fixed = chat("You fix malformed JSON. Respond with the corrected JSON object only.",
                     raw, temperature=0.0, max_tokens=max_tokens,
                     model=model, timeout=timeout)
        return _extract_json(fixed)


def chat_json_schema(
    system: str,
    user: str,
    schema: dict,
    *,
    name: str = "response",
    max_tokens: int = 1024,
    model: str | None = None,
    timeout: float = 60.0,
) -> dict:
    """Constrained decoding when the endpoint supports it, tolerant parse when not.

    LM Studio implements response_format=json_schema; hosted gateways may not,
    and answer with a 400 ("This response_format type is unavailable now").
    That used to abort question-paper generation outright, so the capability is
    probed once and the prompt-and-parse path in chat_json takes over.
    """
    global _supports_json_schema
    require_available()
    if not _supports_json_schema:
        return chat_json(_schema_prompt(system, schema), user, max_tokens=max_tokens,
                         model=model, timeout=timeout)
    try:
        return _chat_json_schema_native(system, user, schema, name=name,
                                        max_tokens=max_tokens, model=model, timeout=timeout)
    except BadRequestError as error:
        if not _unsupported_parameter(error):
            raise
        logger.info("endpoint rejected response_format=json_schema; using prompted JSON")
        _supports_json_schema = False
        return chat_json(_schema_prompt(system, schema), user, max_tokens=max_tokens,
                         model=model, timeout=timeout)


def _schema_prompt(system: str, schema: dict) -> str:
    """Carry the schema in the prompt for endpoints that cannot enforce it."""
    return (
        f"{system}\n\nYour reply must be a single JSON object valid against this "
        f"JSON Schema. Include every required property and no others:\n"
        f"{json.dumps(schema, separators=(',', ':'))}"
    )


def _chat_json_schema_native(
    system: str,
    user: str,
    schema: dict,
    *,
    name: str = "response",
    max_tokens: int = 1024,
    model: str | None = None,
    timeout: float = 60.0,
) -> dict:
    response = _completion(
        model=model or LMSTUDIO_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
        max_tokens=max_tokens,
        timeout=timeout,
        effort=LLM_REASONING_EFFORT or None,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": name,
                "strict": True,
                "schema": schema,
            },
        },
    )
    result = _extract_json(_clean(response.choices[0].message.content))
    if not isinstance(result, dict):
        raise ValueError("Structured model response was not a JSON object")
    return result
