"""Cross-encoder reranking through LM Studio's OpenAI-compatible API."""
from concurrent.futures import ThreadPoolExecutor
import logging
import math

from openai import OpenAI

from core.config import (
    LMSTUDIO_API_KEY,
    LMSTUDIO_BASE_URL,
    RERANKER_ENABLED,
    RERANKER_MAX_CHARS,
    RERANKER_MODEL,
)

logger = logging.getLogger(__name__)

_client = OpenAI(base_url=LMSTUDIO_BASE_URL, api_key=LMSTUDIO_API_KEY)

_INSTRUCTION = (
    "Given a student's question, retrieve note passages that contain the information "
    "needed to answer it."
)
_SYSTEM = (
    "Judge whether the Document meets the requirements based on the Query and the "
    'Instruct provided. Note that the answer can only be "yes" or "no".'
)
_PARALLEL_REQUESTS = 4


def _prompt(query: str, document: str) -> str:
    return (
        f"<Instruct>: {_INSTRUCTION}\n"
        f"<Query>: {query}\n"
        f"<Document>: {document[:RERANKER_MAX_CHARS]}"
    )


def _choice_score(choice) -> float:
    """Return P(yes) from the first generated token's yes/no log probabilities."""
    content_logprobs = getattr(getattr(choice, "logprobs", None), "content", None)
    first_token = content_logprobs[0] if content_logprobs else None
    top_logprobs = getattr(first_token, "top_logprobs", None) or []
    normalized: dict[str, float] = {}
    for token_score in top_logprobs:
        token = str(token_score.token).strip().lower()
        logprob = float(token_score.logprob)
        normalized[token] = max(normalized.get(token, -math.inf), logprob)
    yes_logprob = normalized.get("yes")
    no_logprob = normalized.get("no")

    if yes_logprob is None and no_logprob is None:
        message = getattr(choice, "message", None)
        generated = (getattr(message, "content", "") or "").strip().lower()
        if generated.startswith("yes"):
            return 1.0
        if generated.startswith("no"):
            return 0.0
        raise ValueError(
            "reranker returned neither yes/no log probabilities nor a yes/no token"
        )

    # LM Studio normally includes both tokens in the requested top 10. Keep a
    # stable, strongly directional score if one falls just outside that window.
    if yes_logprob is None:
        yes_logprob = no_logprob - 10.0
    if no_logprob is None:
        no_logprob = yes_logprob - 10.0
    maximum = max(yes_logprob, no_logprob)
    yes_probability = math.exp(yes_logprob - maximum)
    no_probability = math.exp(no_logprob - maximum)
    return yes_probability / (yes_probability + no_probability)


def _score(query: str, hit: dict) -> float:
    response = _client.with_options(timeout=90.0, max_retries=0).chat.completions.create(
        model=RERANKER_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _prompt(query, hit["text"])},
        ],
        max_tokens=4,
        temperature=0.0,
        logprobs=True,
        top_logprobs=10,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    if not response.choices:
        raise ValueError("reranker returned no choice")
    return _choice_score(response.choices[0])


def rerank(query: str, hits: list[dict], top_k: int) -> list[dict]:
    """Rerank vector candidates and fall back to their original order on failure."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if not hits or not RERANKER_ENABLED:
        return hits[:top_k]

    try:
        with ThreadPoolExecutor(
            max_workers=min(_PARALLEL_REQUESTS, len(hits))
        ) as executor:
            scores = list(executor.map(lambda hit: _score(query, hit), hits))
    except Exception as error:
        logger.warning(
            "LM Studio reranking failed; retaining vector-search order: %s",
            error,
        )
        return hits[:top_k]

    ranked = sorted(
        enumerate(hits),
        key=lambda pair: (-scores[pair[0]], pair[0]),
    )
    return [hit for _, hit in ranked[:top_k]]
