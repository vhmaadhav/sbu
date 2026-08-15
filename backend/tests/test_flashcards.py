import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import db, flashcards


class FlashcardRequestTests(unittest.TestCase):
    def test_recognizes_explicit_create_request(self):
        request = flashcards.parse_request("Please create 12 flash cards about cell division.")
        self.assertEqual(request.topic, "cell division")
        self.assertEqual(request.count, 12)

    def test_accepts_common_request_variants(self):
        request = flashcards.parse_request("Can you make me flashcards on World War II?")
        self.assertEqual(request.topic, "World War II")
        self.assertEqual(request.count, 10)

        request = flashcards.parse_request("Could you create some flashcards about gravity?")
        self.assertEqual(request.topic, "gravity")

        request = flashcards.parse_request("I want you to build a set of 7 flashcards for algebra")
        self.assertEqual(request.topic, "algebra")
        self.assertEqual(request.count, 7)

    def test_does_not_intercept_an_ordinary_question(self):
        self.assertIsNone(flashcards.parse_request("How should I organize my flashcards?"))

    def test_caps_requested_card_count(self):
        request = flashcards.parse_request("Generate 100 flashcards for calculus")
        self.assertEqual(request.count, flashcards.MAX_CARD_COUNT)


class FlashcardCreationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "test.db"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    @patch("core.flashcards.vectorstore.search", return_value=[])
    @patch("core.flashcards.llm.chat_json")
    def test_chat_request_creates_a_persisted_deck(self, chat_json, _search):
        chat_json.return_value = {
            "title": "Cell Division",
            "cards": [
                {"front": "What is mitosis?", "back": "Division of a cell nucleus."},
                {"front": "What follows mitosis?", "back": "Cytokinesis."},
            ],
        }

        result = flashcards.maybe_create_from_chat("Create flashcards about cell division")

        self.assertIsNotNone(result["deck_id"])
        deck = db.get_flashcard_deck(result["deck_id"])
        self.assertEqual(deck["title"], "Cell Division")
        self.assertEqual(deck["card_count"], 2)
        self.assertEqual(deck["cards"][0]["front"], "What is mitosis?")

    def test_missing_topic_returns_a_follow_up_without_creating_a_deck(self):
        result = flashcards.maybe_create_from_chat("Create flashcards")
        self.assertIn("What topic", result["answer"])
        self.assertEqual(db.list_flashcard_decks(), [])


if __name__ == "__main__":
    unittest.main()
