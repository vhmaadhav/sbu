import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core import reranker


def _choice(index: int, yes: float, no: float):
    return SimpleNamespace(
        index=index,
        message=SimpleNamespace(content="yes" if yes >= no else "no"),
        logprobs=SimpleNamespace(
            content=[
                SimpleNamespace(
                    top_logprobs=[
                        SimpleNamespace(token=" yes", logprob=yes),
                        SimpleNamespace(token=" no", logprob=no),
                    ]
                )
            ]
        ),
    )


class RerankerTests(unittest.TestCase):
    @patch("core.reranker._score")
    def test_reranks_hits_by_normalized_yes_probability(self, score):
        hits = [
            {"chunk_id": 1, "text": "Irrelevant passage"},
            {"chunk_id": 2, "text": "The answer is in this passage"},
            {"chunk_id": 3, "text": "Somewhat related"},
        ]
        scores = {1: 0.02, 2: 0.99, 3: 0.55}
        score.side_effect = lambda _query, hit: scores[hit["chunk_id"]]

        ranked = reranker.rerank("What is the answer?", hits, top_k=2)

        self.assertEqual([hit["chunk_id"] for hit in ranked], [2, 3])

    @patch("core.reranker._client")
    def test_score_requests_chat_token_logprobs_with_thinking_disabled(self, client):
        client.with_options.return_value.chat.completions.create.return_value = (
            SimpleNamespace(choices=[_choice(0, -0.05, -5.0)])
        )

        result = reranker._score("What is the answer?", {"text": "The answer."})

        self.assertGreater(result, 0.9)
        request = (
            client.with_options.return_value.chat.completions.create.call_args.kwargs
        )
        self.assertEqual(request["model"], reranker.RERANKER_MODEL)
        self.assertEqual(request["max_tokens"], 4)
        self.assertTrue(request["logprobs"])
        self.assertEqual(request["top_logprobs"], 10)
        self.assertFalse(
            request["extra_body"]["chat_template_kwargs"]["enable_thinking"]
        )

    @patch("core.reranker._score")
    def test_preserves_vector_order_when_lm_studio_fails(self, score):
        hits = [
            {"chunk_id": 1, "text": "First"},
            {"chunk_id": 2, "text": "Second"},
        ]
        score.side_effect = RuntimeError("server unavailable")

        with self.assertLogs("core.reranker", level="WARNING"):
            ranked = reranker.rerank("query", hits, top_k=1)

        self.assertEqual(ranked, hits[:1])

    def test_score_is_normalized_between_yes_and_no(self):
        score = reranker._choice_score(_choice(0, math.log(0.8), math.log(0.2)))

        self.assertAlmostEqual(score, 0.8)


if __name__ == "__main__":
    unittest.main()
