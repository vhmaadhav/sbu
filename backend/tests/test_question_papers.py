import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import db, question_papers


class QuestionPaperTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "test.db"
        db.init_db()
        subject_id = db.get_or_create_subject("Biology")
        item_id = db.add_item("cells.txt", "/tmp/cells.txt", "text")
        db.set_item_meta(item_id, "Cell Biology", subject_id)
        self.note_id = db.add_note(
            item_id,
            "# Cell Biology\n\nMitosis divides one nucleus into two genetically identical nuclei.",
        )

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def request(self, **overrides):
        values = {
            "note_ids": [self.note_id],
            "title": "Cell Biology Test",
            "difficulty": "medium",
            "duration_minutes": 45,
            "mcq_count": 1,
            "short_count": 1,
            "long_count": 0,
        }
        values.update(overrides)
        return question_papers.PaperRequest(**values)

    def test_request_marks_are_deterministic(self):
        request = self.request(mcq_count=4, short_count=2, long_count=1)
        self.assertEqual(request.question_count, 7)
        self.assertEqual(request.total_marks, 15)

    def test_rejects_empty_or_oversized_papers(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            question_papers.validate_request(
                self.request(mcq_count=0, short_count=0, long_count=0)
            )
        with self.assertRaisesRegex(ValueError, "at most"):
            question_papers.validate_request(
                self.request(mcq_count=31, short_count=0, long_count=0)
            )

    @patch("core.question_papers.llm.chat_json_schema")
    def test_generates_and_persists_a_paper_from_selected_notes(self, chat_json):
        chat_json.return_value = {
            "title": "Ignored because request title wins",
            "questions": [
                {
                    "type": "mcq",
                    "prompt": "What is the result of mitosis?",
                    "options": [
                        "Two identical nuclei",
                        "Four unrelated cells",
                        "One chromosome",
                        "No nucleus",
                    ],
                    "answer": "Two identical nuclei",
                    "explanation": "The note explicitly defines the result.",
                },
                {
                    "type": "short",
                    "prompt": "State the purpose of mitosis.",
                    "options": [],
                    "answer": "To produce two genetically identical nuclei.",
                    "explanation": "Award marks for division and genetic identity.",
                },
            ],
        }

        paper = question_papers.generate(self.request())

        self.assertEqual(paper["title"], "Cell Biology Test")
        self.assertEqual(paper["total_marks"], 4)
        self.assertEqual(paper["question_count"], 2)
        self.assertEqual(paper["sources"][0]["note_id"], self.note_id)
        prompt = chat_json.call_args.args[1]
        self.assertIn("Mitosis divides one nucleus", prompt)
        self.assertEqual(db.list_question_papers()[0]["id"], paper["id"])

    @patch("core.question_papers.llm.chat_json_schema")
    def test_rejects_an_invalid_mcq_before_persistence(self, chat_json):
        chat_json.return_value = {
            "questions": [{
                "type": "mcq",
                "prompt": "What happens?",
                "options": ["A", "B"],
                "answer": "A",
                "explanation": "",
            }]
        }

        with self.assertRaisesRegex(ValueError, "incomplete"):
            question_papers.generate(
                self.request(mcq_count=1, short_count=0, long_count=0)
            )
        self.assertEqual(db.list_question_papers(), [])

    @patch("core.question_papers.llm.chat_json_schema")
    def test_large_question_sets_are_generated_in_bounded_batches(self, chat_json):
        def payload(start, count):
            return {
                "questions": [{
                    "type": "mcq",
                    "prompt": f"Question {index}?",
                    "options": ["Correct", "Wrong 1", "Wrong 2", "Wrong 3"],
                    "answer": "Correct",
                    "explanation": "Grounded in the note.",
                } for index in range(start, start + count)]
            }

        chat_json.side_effect = [payload(1, 5), payload(6, 2)]

        paper = question_papers.generate(
            self.request(mcq_count=7, short_count=0, long_count=0)
        )

        self.assertEqual(paper["question_count"], 7)
        self.assertEqual(chat_json.call_count, 2)
        self.assertTrue(all(
            call.kwargs["max_tokens"] == 3200 for call in chat_json.call_args_list
        ))

    @patch(
        "core.question_papers.llm.chat_json_schema",
        side_effect=RuntimeError("completion ended before JSON closed"),
    )
    def test_truncated_model_output_becomes_actionable_error(self, _chat_json):
        with self.assertRaisesRegex(
            ValueError, "truncated or malformed JSON.*Try fewer questions"
        ):
            question_papers.generate(
                self.request(mcq_count=1, short_count=0, long_count=0)
            )

    @patch("core.question_papers.llm.chat_json_schema")
    def test_download_hides_answers_unless_requested(self, chat_json):
        import pymupdf

        chat_json.return_value = {
            "questions": [{
                "type": "short",
                "prompt": "Define mitosis.",
                "options": [],
                "answer": "Nuclear division.",
                "explanation": "One mark for division.",
            }]
        }
        paper = question_papers.generate(
            self.request(mcq_count=0, short_count=1, long_count=0)
        )

        student = question_papers.to_markdown(paper)
        key = question_papers.to_markdown(paper, include_answers=True)
        self.assertNotIn("Nuclear division.", student)
        self.assertIn("# Answer key", key)
        self.assertIn("Nuclear division.", key)

        student_pdf = question_papers.to_pdf(paper)
        key_pdf = question_papers.to_pdf(paper, include_answers=True)
        student_text = "\n".join(
            page.get_text() for page in pymupdf.open(stream=student_pdf, filetype="pdf")
        )
        key_text = "\n".join(
            page.get_text() for page in pymupdf.open(stream=key_pdf, filetype="pdf")
        )
        self.assertTrue(student_pdf.startswith(b"%PDF"))
        self.assertNotIn("Nuclear division.", student_text)
        self.assertIn("Answer key", key_text)
        self.assertIn("Nuclear division.", key_text)

    @patch("core.question_papers.llm.chat_json_schema")
    def test_deleting_completed_job_paper_preserves_job_history(self, chat_json):
        chat_json.return_value = {
            "questions": [{
                "type": "short",
                "prompt": "Define mitosis.",
                "options": [],
                "answer": "Nuclear division.",
                "explanation": "",
            }]
        }
        paper = question_papers.generate(
            self.request(mcq_count=0, short_count=1, long_count=0)
        )
        job_id = db.add_question_paper_job({"note_ids": [self.note_id]})
        db.finish_question_paper_job(job_id, paper_id=paper["id"])

        self.assertTrue(db.delete_question_paper(paper["id"]))

        job = db.list_question_paper_jobs()[0]
        self.assertEqual(job["status"], "done")
        self.assertIsNone(job["paper_id"])


if __name__ == "__main__":
    unittest.main()
