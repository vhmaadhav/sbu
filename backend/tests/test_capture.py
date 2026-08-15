import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import server
from core import capture, db


class BrowserCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.root / "capture.db"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    @staticmethod
    def event() -> dict:
        return {
            "event_id": "capture-001",
            "source_type": "browser",
            "source_uri": "https://example.test/graphs",
            "title": "Breadth-first search",
            "text": "Breadth-first search explores graph vertices level by level.",
            "captured_at": "2026-08-15T20:00:00+05:30",
            "dwell_ms": 2450,
            "metadata": {"language": "en"},
        }

    def test_capture_is_queued_with_attention_metadata(self):
        result = capture.ingest_browser_event(self.event(), self.root / "files")

        self.assertEqual(result["status"], "queued")
        row = db.get_capture_event("capture-001")
        self.assertEqual(row["dwell_ms"], 2450)
        self.assertEqual(row["source_uri"], "https://example.test/graphs")
        self.assertEqual(row["status"], "pending")
        stored = Path(db.get_item(result["item_id"])["stored_path"])
        self.assertEqual(
            stored.read_text(encoding="utf-8"),
            "Breadth-first search explores graph vertices level by level.",
        )

    def test_retry_is_idempotent(self):
        first = capture.ingest_browser_event(self.event(), self.root / "files")
        second = capture.ingest_browser_event(self.event(), self.root / "files")

        self.assertEqual(second["status"], "duplicate_event")
        self.assertEqual(second["item_id"], first["item_id"])
        self.assertEqual(len(db.list_items()), 1)
        self.assertEqual(len(db.list_capture_events()), 1)


class BrowserCaptureApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.root / "capture-api.db"
        db.init_db()
        self.files_patch = patch.object(server, "FILES_DIR", self.root / "files")
        self.files_patch.start()
        self.client = TestClient(server.app)

    def tearDown(self):
        self.client.close()
        self.files_patch.stop()
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_extension_contract_and_evidence_feed(self):
        event = BrowserCaptureTests.event()
        response = self.client.post("/api/captures", json={"events": [event]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["accepted_event_ids"], ["capture-001"])
        self.assertEqual(response.json()["results"][0]["status"], "queued")

        evidence = self.client.get("/api/learn/evidence").json()["evidence"]
        self.assertEqual(evidence[0]["title"], "Breadth-first search")
        self.assertEqual(evidence[0]["dwell_ms"], 2450)

    def test_capture_payload_rejects_non_browser_sources(self):
        event = {**BrowserCaptureTests.event(), "source_type": "pdf"}
        response = self.client.post("/api/captures", json={"events": [event]})

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
