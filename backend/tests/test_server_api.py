import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import server
from core import db


class UploadApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.root / "test.db"
        db.init_db()
        self.files_patch = patch.object(server, "FILES_DIR", self.root / "files")
        self.files_patch.start().mkdir(parents=True)
        self.client = TestClient(server.app)

    def tearDown(self):
        self.client.close()
        self.files_patch.stop()
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_audio_webm_recording_is_queued_as_audio(self):
        response = self.client.post(
            "/api/upload",
            files={"files": ("live-recording.webm", b"webm audio bytes", "audio/webm")},
            data={"text": ""},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["items"][0]["kind"], "audio")
        self.assertEqual(db.list_items()[0]["kind"], "audio")

    def test_video_webm_upload_remains_video(self):
        response = self.client.post(
            "/api/upload",
            files={"files": ("lecture.webm", b"webm video bytes", "video/webm")},
            data={"text": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["kind"], "video")
        self.assertEqual(db.list_items()[0]["kind"], "video")

    @patch("server.vectorstore.add_chunks")
    def test_retry_repairs_completed_sqlite_work_without_duplicate_notes(self, add_chunks):
        subject_id = db.get_or_create_subject("Mathematics")
        item_id = db.add_item("test.txt", "/tmp/test.txt", "text")
        db.set_item_meta(item_id, "July 26 Test", subject_id)
        note_id = db.add_note(item_id, "# July 26 Test")
        chunk_id = db.add_chunk(item_id, "Study reminder", "July 26 Test — notes")
        db.set_status(item_id, "error", "Table 'chunks' already exists")

        response = self.client.post(f"/api/items/{item_id}/retry")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recovered"], "vector_index")
        self.assertEqual(db.get_item(item_id)["status"], "done")
        self.assertEqual([note["id"] for note in db.notes_for_item(item_id)], [note_id])
        add_chunks.assert_called_once()
        self.assertEqual(add_chunks.call_args.args[0][0]["chunk_id"], chunk_id)

    def test_retry_requeues_failure_that_has_no_completed_note(self):
        item_id = db.add_item("broken.txt", "/tmp/broken.txt", "text")
        db.set_status(item_id, "error", "model unavailable")

        response = self.client.post(f"/api/items/{item_id}/retry")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recovered"], "requeued")
        self.assertEqual(db.get_item(item_id)["status"], "pending")

    def test_create_subject_folder_reuses_case_insensitive_name(self):
        first = self.client.post("/api/subjects", json={"name": "Computer Science"})
        second = self.client.post("/api/subjects", json={"name": " computer   science "})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(len(db.list_subjects()), 1)

    @patch("server.vectorstore.update_item_subject")
    def test_move_note_changes_subject_folder_and_vector_metadata(self, update_subject):
        old_subject = db.get_or_create_subject("Physics")
        new_subject = db.get_or_create_subject("Computer Science")
        item_id = db.add_item("lecture.txt", "/tmp/lecture.txt", "text")
        db.set_item_meta(item_id, "Algorithms", old_subject)
        note_id = db.add_note(item_id, "# Algorithms")

        response = self.client.patch(
            f"/api/notes/{note_id}", json={"subject_id": new_subject}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.get_item(item_id)["subject_id"], new_subject)
        update_subject.assert_called_once_with(item_id, "Computer Science")

    def test_note_detail_includes_embedded_images_for_mobile(self):
        item_id = db.add_item("diagram.txt", "/tmp/diagram.txt", "text")
        note_id = db.add_note(
            item_id,
            "# Graphs\n\n![Shortest-path diagram](/api/doc/figures/graph.png)",
        )

        response = self.client.get(f"/api/notes/{note_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["images"], [{
            "id": None,
            "page": None,
            "caption": "Shortest-path diagram",
            "url": "/api/doc/figures/graph.png",
        }])

    def test_note_download_returns_a_named_pdf(self):
        subject_id = db.get_or_create_subject("Physics")
        item_id = db.add_item("waves.txt", "/tmp/waves.txt", "text")
        db.set_item_meta(item_id, "Wave Motion", subject_id)
        note_id = db.add_note(
            item_id,
            "# Wave Motion\n\n## Summary\n\nA wave transfers **energy**.\n\n"
            "| Quantity | Unit |\n| --- | --- |\n| Frequency | Hz |",
        )

        response = self.client.get(f"/api/notes/{note_id}/download")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertIn('filename="Wave Motion.pdf"', response.headers["content-disposition"])
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertGreater(len(response.content), 1000)

    @patch("server.vectorstore.delete_chunks")
    def test_delete_note_keeps_source_but_removes_note_chunks(self, delete_chunks):
        subject_id = db.get_or_create_subject("Computer Science")
        item_id = db.add_item("lecture.txt", "/tmp/lecture.txt", "text")
        db.set_item_meta(item_id, "Trees", subject_id)
        note_id = db.add_note(item_id, "# Trees")
        raw_chunk = db.add_chunk(item_id, "raw lecture", "Trees — source")
        note_chunk = db.add_chunk(item_id, "generated note", "Trees — source — notes")

        response = self.client.delete(f"/api/notes/{note_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.notes_for_item(item_id), [])
        self.assertIsNotNone(db.get_item(item_id))
        with db.conn() as c:
            remaining = [row["id"] for row in c.execute("SELECT id FROM chunks").fetchall()]
        self.assertEqual(remaining, [raw_chunk])
        delete_chunks.assert_called_once_with([note_chunk])

    @patch("server._answer_question")
    @patch("core.stt.transcribe_media")
    def test_audio_question_is_transcribed_then_sent_to_ask_flow(self, transcribe, answer):
        transcribe.return_value = [
            {"start": 0.2, "end": 1.0, "text": "What is"},
            {"start": 1.1, "end": 2.0, "text": "superposition?"},
        ]
        answer.return_value = {"answer": "A cited answer", "sources": [], "images": [], "videos": []}

        response = self.client.post(
            "/api/ask/audio",
            files={"audio": ("question.webm", b"webm audio bytes", "audio/webm")},
            data={"subject": " Electronic System Design "},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["transcript"], "What is superposition?")
        answer.assert_called_once_with("What is superposition?", "Electronic System Design")

    @patch("server.rag.ask", side_effect=RuntimeError("model unavailable"))
    @patch("server.flashcards.maybe_create_from_chat", return_value=None)
    def test_ask_failure_returns_json_without_orphaning_chat(self, _flashcards, _ask):
        response = self.client.post("/api/ask", json={"question": "What is KVL?", "subject": None})

        self.assertEqual(response.status_code, 503)
        self.assertIn("local AI", response.json()["detail"])
        self.assertEqual(db.list_chat_turns(), [])

    @patch("core.notes.vectorstore")
    def test_edit_note_persists_and_reindexes(self, _vs):
        subject_id = db.get_or_create_subject("Physics")
        item_id = db.add_item("lecture.pdf", "/tmp/lecture.pdf", "pdf")
        db.set_item_meta(item_id, "Waves", subject_id)
        note_id = db.add_note(item_id, "# Waves\n\nOld body.")

        response = self.client.put(
            f"/api/notes/{note_id}", json={"markdown": "# Waves\n\nNew edited body."}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.notes_for_item(item_id)[0]["markdown"], "# Waves\n\nNew edited body.")

    def test_edit_note_rejects_empty_markdown(self):
        item_id = db.add_item("l.txt", "/tmp/l.txt", "text")
        note_id = db.add_note(item_id, "# Something")

        response = self.client.put(f"/api/notes/{note_id}", json={"markdown": "   "})

        self.assertEqual(response.status_code, 400)

    def test_item_file_serves_pdf_source(self):
        source = self.root / "doc.pdf"
        source.write_bytes(b"%PDF-1.4 minimal")
        item_id = db.add_item("doc.pdf", str(source), "pdf")

        response = self.client.get(f"/api/items/{item_id}/file")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-1.4 minimal")

    def test_item_file_404_for_video_kind(self):
        item_id = db.add_item("v.mp4", "/tmp/v.mp4", "video")
        response = self.client.get(f"/api/items/{item_id}/file")
        self.assertEqual(response.status_code, 404)

    def test_doc_figure_rejects_traversal(self):
        with patch.object(server, "FIGURES_DIR", self.root / "figures"):
            (self.root / "figures").mkdir()
            with self.assertRaises(server.HTTPException) as ctx:
                server.doc_figure_image("../../secret.png")
            self.assertEqual(ctx.exception.status_code, 404)

    def test_api_discovery_and_trace_headers_are_available_to_all_clients(self):
        response = self.client.get("/api")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["openapi"], "/api/openapi.json")
        self.assertEqual(response.headers["x-api-version"], server.app.version)
        self.assertTrue(response.headers["x-request-id"])
        self.assertIn("x-process-time-ms", response.headers)

    def test_missing_resources_use_http_404(self):
        self.assertEqual(self.client.get("/api/notes/999999").status_code, 404)
        self.assertEqual(self.client.patch(
            "/api/tasks/999999", json={"done": True}
        ).status_code, 404)
        self.assertEqual(self.client.delete("/api/tasks/999999").status_code, 404)
        self.assertEqual(
            self.client.get("/api/audiobooks/missing.wav").status_code, 404
        )

    def test_audiobook_requires_at_least_one_note(self):
        response = self.client.post(
            "/api/audiobooks", json={"note_ids": [], "name": "Revision"}
        )

        self.assertEqual(response.status_code, 400)

    def test_handwriting_upload_rejects_non_image_files(self):
        response = self.client.post(
            "/api/handwriting/upload",
            files=[("files", ("lecture.txt", b"notes", "text/plain"))],
        )

        self.assertEqual(response.status_code, 415)

    @patch("core.google_calendar.create_task_event", side_effect=RuntimeError("offline"))
    def test_failed_calendar_task_creation_does_not_leave_partial_task(self, _create):
        response = self.client.post(
            "/api/tasks",
            json={
                "label": "Submit report",
                "due": "2026-08-20",
                "add_to_calendar": True,
            },
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(db.list_tasks(), [])

    @patch("core.google_calendar.list_events", return_value=[])
    @patch("core.google_calendar.credentials", return_value=object())
    def test_calendar_proposal_can_be_planned_without_changing_google(
        self, _credentials, _events
    ):
        item_id = db.add_item("schedule.png", "/tmp/schedule.png", "image")
        reminder_id = db.add_calendar_reminder(
            item_id, "Dentist", "2026-08-20", "10:00", "11:00", None
        )

        response = self.client.post(f"/api/calendar/proposals/{reminder_id}/plan")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_event"]["title"], "Dentist")
        self.assertEqual(response.json()["moves"], [])
        self.assertEqual(
            db.get_reschedule_plan(response.json()["id"])["status"], "proposed"
        )

    @patch("core.google_calendar.apply_reschedule_plan", return_value="google-event")
    def test_confirmed_calendar_plan_is_applied_and_audited(self, apply):
        item_id = db.add_item("schedule.png", "/tmp/schedule.png", "image")
        reminder_id = db.add_calendar_reminder(
            item_id, "Dentist", "2026-08-20", "10:00", "11:00", None
        )
        plan_id = db.add_reschedule_plan(reminder_id, {
            "reminder_id": reminder_id,
            "new_event": {"title": "Dentist"},
            "moves": [],
            "blocked": [],
            "needs_confirmation": False,
            "complex_reasons": [],
        })

        response = self.client.post(f"/api/calendar/plans/{plan_id}/apply")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["google_event_id"], "google-event")
        self.assertEqual(db.get_reschedule_plan(plan_id)["status"], "applied")
        self.assertEqual(db.get_calendar_reminder(reminder_id)["status"], "created")
        apply.assert_called_once()

    @patch("server.threading.Thread")
    @patch("server.llm.require_available")
    @patch("server.question_papers.generate")
    def test_question_paper_generation_uses_background_job(
        self, generate, _available, thread
    ):
        paper_id = db.create_question_paper(
            title="Physics assessment",
            difficulty="hard",
            duration_minutes=90,
            instructions="Answer all questions.",
            questions=[{
                "type": "short", "prompt": "Why?", "options": [],
                "answer": "Because.", "explanation": "", "marks": 3,
            }],
            sources=[],
        )
        generate.return_value = {"id": paper_id, "title": "Physics assessment"}

        response = self.client.post("/api/question-papers", json={
            "note_ids": [3, 4],
            "title": "Physics assessment",
            "difficulty": "hard",
            "duration_minutes": 90,
            "mcq_count": 5,
            "short_count": 3,
            "long_count": 2,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "processing")
        thread.assert_called_once()
        thread.call_args.kwargs["target"]()
        request = generate.call_args.args[0]
        self.assertEqual(request.note_ids, [3, 4])
        self.assertEqual(request.difficulty, "hard")
        self.assertEqual(request.total_marks, 24)
        jobs = self.client.get("/api/question-papers/jobs").json()
        self.assertEqual(jobs[0]["status"], "done")
        self.assertEqual(jobs[0]["paper_id"], paper_id)

    def test_question_paper_download_separates_student_copy_and_answer_key(self):
        import pymupdf

        paper_id = db.create_question_paper(
            title="Biology test",
            difficulty="medium",
            duration_minutes=30,
            instructions="Answer every question.",
            questions=[{
                "type": "short",
                "prompt": "Define mitosis.",
                "options": [],
                "answer": "Nuclear division.",
                "explanation": "Award one mark for division.",
                "marks": 3,
            }],
            sources=[],
        )

        student = self.client.get(f"/api/question-papers/{paper_id}/download")
        answer_key = self.client.get(
            f"/api/question-papers/{paper_id}/download?answers=true"
        )

        self.assertEqual(student.status_code, 200)
        self.assertEqual(student.headers["content-type"], "application/pdf")
        self.assertTrue(student.content.startswith(b"%PDF"))
        student_text = "\n".join(
            page.get_text()
            for page in pymupdf.open(stream=student.content, filetype="pdf")
        )
        key_text = "\n".join(
            page.get_text()
            for page in pymupdf.open(stream=answer_key.content, filetype="pdf")
        )
        self.assertNotIn("Nuclear division.", student_text)
        self.assertIn("Nuclear division.", key_text)
        self.assertIn(
            "Biology-test-answer-key.pdf",
            answer_key.headers["content-disposition"],
        )


if __name__ == "__main__":
    unittest.main()
