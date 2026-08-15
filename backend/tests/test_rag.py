import unittest
from unittest.mock import patch

from core import rag


class RagCitationLinkTests(unittest.TestCase):
    @patch("core.rag.db.note_id_for_item", return_value=9)
    @patch("core.rag.llm.chat")
    @patch("core.rag.llm.require_available")
    @patch("core.rag.reranker.rerank")
    @patch("core.rag.vectorstore.search")
    def test_video_citation_links_to_timestamped_player_url(
        self, search, rerank, _require_available, chat, _note_id
    ):
        search.return_value = [{
            "chunk_id": 1,
            "item_id": 12,
            "source_label": "Network Theorems",
            "text": "Maximum power occurs at the matched load.",
            "ts_start": 3502.8,
            "page": None,
            "image_path": None,
        }]
        rerank.return_value = search.return_value
        chat.return_value = "See [source: Network Theorems @ 58:22]."

        result = rag.ask("When is maximum power transferred?")

        self.assertIn(
            "[[source: Network Theorems @ 58:22]](/search?video=12&t=58m22s)",
            result["answer"],
        )
        self.assertEqual(result["sources"][0]["timestamp"], 3502.8)
        search.assert_called_once_with(
            "When is maximum power transferred?",
            subject=None,
            k=rag.RERANKER_CANDIDATE_K,
        )
        rerank.assert_called_once_with(
            "When is maximum power transferred?",
            search.return_value,
            top_k=8,
        )


if __name__ == "__main__":
    unittest.main()
