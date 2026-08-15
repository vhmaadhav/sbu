"""LM Studio client (OpenAI-compatible) with tolerant JSON handling."""
import json
import re

from openai import OpenAI

from core.config import LMSTUDIO_API_KEY, LMSTUDIO_BASE_URL, LMSTUDIO_MODEL, VISION_MODEL

_client = OpenAI(base_url=LMSTUDIO_BASE_URL, api_key=LMSTUDIO_API_KEY)

# A local model server drops connections under sustained load — a long lecture
# sends dozens of back-to-back requests — and one reset used to fail the whole
# ingestion. The SDK retries connection errors, timeouts and 5xx with backoff;
# a server that is genuinely down still exhausts these and raises, so the
# fail-closed behaviour in require_available is unchanged.
REQUEST_RETRIES = 2


class LocalLLMUnavailable(RuntimeError):
    """The only configured LLM endpoint is unavailable or missing its model."""


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
    resp = _client.with_options(timeout=timeout, max_retries=REQUEST_RETRIES).chat.completions.create(
        model=model or LMSTUDIO_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = resp.choices[0].message.content or ""
    # strip <think> blocks some local models emit
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


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
    resp = _client.with_options(timeout=90.0, max_retries=REQUEST_RETRIES).chat.completions.create(
        model=model or VISION_MODEL,
        messages=[{"role": "user", "content": content}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = resp.choices[0].message.content or ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


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
    """Use LM Studio's JSON Schema constrained decoding for reliable JSON."""
    require_available()
    response = _client.with_options(timeout=timeout, max_retries=REQUEST_RETRIES).chat.completions.create(
        model=model or LMSTUDIO_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
        max_tokens=max_tokens,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": name,
                "strict": True,
                "schema": schema,
            },
        },
    )
    raw = response.choices[0].message.content or ""
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    result = _extract_json(raw)
    if not isinstance(result, dict):
        raise ValueError("Structured model response was not a JSON object")
    return result
