import unittest
import threading
from unittest.mock import patch

import core.ingest as ingest
from core.ingest import _assemble_structured_notes, _clean_generated_markdown, _extract


class PdfExtractionTests(unittest.TestCase):
    @patch(
        "core.ocr.extract_pdf",
        return_value=[{"page": 1, "text": "Ohm's law relates voltage and current."}],
    )
    def test_pdf_ingestion_uses_the_ocr_public_interface(self, extract_pdf):
        item = {"id": 42, "kind": "pdf", "stored_path": "/tmp/lecture.pdf"}

        chunks = _extract(item)

        extract_pdf.assert_called_once_with("/tmp/lecture.pdf")
        self.assertEqual(chunks[0]["page"], 1)
        self.assertIn("Ohm's law", chunks[0]["text"])

    def test_worker_logging_does_not_conflict_with_log_record_fields(self):
        stop = threading.Event()
        item = {"id": 42, "filename": "lecture.pdf"}

        def finish_processing(_item):
            stop.set()

        with (
            patch.object(ingest.db, "init_db"),
            patch.object(ingest, "_sweep_inbox"),
            patch.object(ingest.db, "claim_next_pending_item", return_value=item),
            patch.object(ingest, "process_item", side_effect=finish_processing) as process,
            patch.object(ingest.db, "set_status") as set_status,
        ):
            ingest.worker_loop(stop)

        process.assert_called_once_with(item)
        set_status.assert_not_called()


class ImageDiagramExtractionTests(unittest.TestCase):
    @patch("core.diagrams.analyze_diagram")
    def test_detected_diagram_uses_mermaid_pipeline(self, analyze):
        analyze.return_value = {
            "graph": {
                "is_diagram": True,
                "nodes": [{"id": "a", "label": "A"}],
                "title": "Detected flow",
                "summary": "A to B.",
            },
            "ocr_markdown": "A → B",
            "mermaid": "flowchart LR\n  a --> b",
            "stages": [],
        }
        item = {"id": 7, "kind": "image", "stored_path": "/tmp/screenshot.png"}

        chunks = _extract(item)

        analyze.assert_called_once_with("/tmp/screenshot.png")
        self.assertIn("```mermaid", chunks[0]["text"])
        self.assertEqual(chunks[0]["diagram_result"]["graph"]["title"], "Detected flow")

    @patch("core.ocr.ocr_image_annotations", return_value=[("ordinary photo text", 1.0, ())])
    @patch("core.diagrams.analyze_diagram")
    def test_non_diagram_falls_back_to_regular_image_ocr(self, analyze, annotations):
        analyze.return_value = {
            "graph": {"is_diagram": False, "nodes": []},
            "ocr_markdown": "",
            "mermaid": "flowchart LR",
            "stages": [],
        }
        item = {"id": 8, "kind": "image", "stored_path": "/tmp/photo.png"}

        chunks = _extract(item)

        self.assertEqual(chunks, [{"text": "ordinary photo text", "image_path": "/tmp/photo.png"}])
        annotations.assert_called_once_with("/tmp/photo.png")


class GenerateNotesVisualTests(unittest.TestCase):
    def setUp(self):
        self._orig = ingest.llm.chat

    def tearDown(self):
        ingest.llm.chat = self._orig

    def test_places_figure_inline_and_drops_appendix(self):
        ingest.llm.chat = lambda system, user, **kw: "## Summary\n\nThe flow is shown.\n\n[[FIG:1]]"
        visuals = [{
            "token_id": 1, "url": "/api/doc/figures/fig_1.png",
            "caption": "Flowchart", "anchor": ("page", 3),
        }]

        notes = ingest._generate_notes("[p. 3] source about the flow.",
                                       [{"text": "x", "page": 3}], "Title", visuals)

        self.assertIn("![Flowchart](/api/doc/figures/fig_1.png)", notes)
        self.assertNotIn("[[FIG:1]]", notes)
        self.assertNotIn("Important lecture visuals", notes)

    def test_unplaced_frame_falls_inline_near_timestamp(self):
        ingest.llm.chat = lambda system, user, **kw: "## Summary\n\nA lecture summary with no token."
        visuals = [{
            "token_id": 1, "url": "/api/video/frames/7/image",
            "caption": "Board", "anchor": ("ts", 12),
        }]
        chunks = [{"text": "[@ 0:12] talking here", "ts_start": 12.0}]

        notes = ingest._generate_notes("[@ 0:12] talking here", chunks, "Lec", visuals)

        self.assertIn("![Board](/api/video/frames/7/image)", notes)
        self.assertNotIn("Important lecture visuals", notes)

    def test_llm_selects_and_persists_important_term_highlights(self):
        calls = []

        def generate(system, user, **kwargs):
            calls.append((system, user))
            return "## Summary\n\n==Ohm's law== relates voltage and current."

        ingest.llm.chat = generate

        notes = ingest._generate_notes(
            "Ohm's law relates voltage and current.",
            [{"text": "Ohm's law relates voltage and current."}],
            "Circuits",
        )

        self.assertIn("==Ohm's law==", notes)
        self.assertIn("or a short sentence when the complete statement is important", calls[0][0])

    def test_note_omits_the_verbatim_source_transcript(self):
        # The note is the study guide; the transcript stays in the chunks that
        # back RAG retrieval, not appended to every lecture note.
        ingest.llm.chat = lambda system, user, **kw: "## Summary\n\nA lecture summary."
        transcript = "[@ 0:12] a distinctive spoken sentence about induction"

        notes = ingest._generate_notes(
            transcript, [{"text": transcript, "ts_start": 12.0}], "Lec",
        )

        self.assertIn("A lecture summary.", notes)
        self.assertNotIn("Complete timestamped transcript", notes)
        self.assertNotIn("a distinctive spoken sentence", notes)


class NotePartBudgetTests(unittest.TestCase):
    """One generated part costs one sequential LLM call, so the count is capped."""

    def test_short_sources_split_on_the_plain_part_size(self):
        self.assertEqual(ingest._note_part_chars(1_000), ingest.NOTES_INPUT_CHARS)
        self.assertEqual(
            ingest._note_part_chars(ingest.NOTES_INPUT_CHARS * ingest.NOTES_MAX_PARTS),
            ingest.NOTES_INPUT_CHARS,
        )

    def test_long_sources_widen_parts_instead_of_adding_calls(self):
        length = ingest.NOTES_INPUT_CHARS * ingest.NOTES_MAX_PARTS * 2
        part = ingest._note_part_chars(length)

        self.assertGreater(part, ingest.NOTES_INPUT_CHARS)
        self.assertLessEqual(-(-length // part), ingest.NOTES_MAX_PARTS)

    def test_part_size_never_exceeds_the_prompt_ceiling(self):
        self.assertEqual(
            ingest._note_part_chars(10_000_000), ingest.NOTES_MAX_PART_CHARS
        )

    def test_a_realistic_lecture_stays_within_the_target(self):
        # 16 minutes of speech plus its board captures, the case that produced
        # 31 sequential generations before parts were budgeted.
        parts = -(-40_000 // ingest._note_part_chars(40_000))
        self.assertLessEqual(parts, ingest.NOTES_MAX_PARTS)

    def test_generation_covers_the_whole_source(self):
        original = ingest.llm.chat
        parts = []
        ingest.llm.chat = lambda system, user, **kw: (
            parts.append(user) or "## Summary\n\nPart summary."
        )
        try:
            source = "".join(f"<{n:06d}>" for n in range(20_000))  # 160 KB, uniquely marked
            ingest._generate_notes(source, [{"text": source}], "Very long lecture")
        finally:
            ingest.llm.chat = original

        generations = [part for part in parts if "Source part:" in part]
        material = "".join(part.split("Source material:\n", 1)[1] for part in generations)
        self.assertIn("<000000>", material)
        self.assertIn("<019999>", material)  # the tail is never dropped
        self.assertLessEqual(len(generations), -(-len(source) // ingest.NOTES_MAX_PART_CHARS))


class GeneratedNoteCleanupTests(unittest.TestCase):
    def test_removes_placeholder_references_but_preserves_real_sources_and_math(self):
        markdown = (
            "# Notes\n\nValue is $R_{TH}$ [@ mm:ss].\n\n"
            "Real source [@ 58:22]. Page placeholder [p. N]."
        )

        cleaned = _clean_generated_markdown(markdown)

        self.assertNotIn("mm:ss", cleaned)
        self.assertNotIn("p. N", cleaned)
        self.assertIn("$R_{TH}$", cleaned)
        self.assertIn("[@ 58:22]", cleaned)

    def test_normalizes_decorative_symbols_and_model_markdown_fence(self):
        markdown = "```markdown\n# Overview 📅\n\n• First point\n*   Second point ✅\n```"

        cleaned = _clean_generated_markdown(markdown)

        self.assertEqual(cleaned, "# Overview\n\n- First point\n- Second point")

    def test_removes_at_prefixed_page_placeholder(self):
        cleaned = _clean_generated_markdown("Definition [@ p. N].")

        self.assertEqual(cleaned, "Definition.")

    def test_assembles_one_title_and_merges_repeated_sections(self):
        assembled = _assemble_structured_notes(
            "  # Neural   Networks\nignored  ",
            [
                "# Model title\n\n## Summary\nFirst overview.\n\n## Key concepts\n- **Neuron:** unit",
                "## Summary\nSecond overview.\n\n## Detailed notes\n- Training detail",
            ],
        )

        self.assertEqual(assembled.count("# Neural Networks"), 1)
        self.assertEqual(assembled.count("## Summary"), 1)
        self.assertIn("First overview.\n\nSecond overview.", assembled)
        self.assertLess(assembled.index("## Key concepts"), assembled.index("## Detailed notes"))

    def test_assembles_unsectioned_model_output_as_detailed_notes(self):
        assembled = _assemble_structured_notes("Short source", ["- One factual point"])

        self.assertEqual(
            assembled,
            "# Short source\n\n## Detailed notes\n\n- One factual point",
        )

    def test_drops_bullets_repeated_verbatim_across_parts(self):
        repeated = "- **Degeneracy:** distinct states that share one energy level"

        assembled = _assemble_structured_notes(
            "Quantum",
            [f"## Key concepts\n{repeated}", f"## Key concepts\n{repeated}\n- A second concept"],
        )

        self.assertEqual(assembled.count("Degeneracy:"), 1)
        self.assertIn("A second concept", assembled)

    def test_condenses_repeated_per_part_summaries_into_one(self):
        calls = []

        def fake_chat(system, user, **kwargs):
            calls.append((system, user))
            return "## Summary\n\nOne merged overview."

        original = ingest.llm.chat
        ingest.llm.chat = fake_chat
        try:
            assembled = _assemble_structured_notes(
                "Quantum",
                [
                    "## Summary\nThe 1D box is non-degenerate, unlike the 3D box.",
                    "## Summary\nA 1D box has unique energies while a 3D box degenerates.",
                    "## Summary\nEnergy levels in one dimension are unique; three dimensions repeat.",
                ],
                condense=True,
            )
        finally:
            ingest.llm.chat = original

        self.assertEqual(assembled, "# Quantum\n\n## Summary\n\nOne merged overview.")
        self.assertEqual(len(calls), 1)
        self.assertIn("three dimensions repeat", calls[0][1])

    def test_keeps_fragments_when_condensing_fails(self):
        def failing_chat(system, user, **kwargs):
            raise RuntimeError("model offline")

        original = ingest.llm.chat
        ingest.llm.chat = failing_chat
        try:
            with self.assertLogs(level="ERROR"):
                assembled = _assemble_structured_notes(
                    "Quantum",
                    ["## Summary\nFirst overview of the material.",
                     "## Summary\nSecond overview of the same material."],
                    condense=True,
                )
        finally:
            ingest.llm.chat = original

        self.assertIn("First overview of the material.", assembled)
        self.assertIn("Second overview of the same material.", assembled)

    def test_single_part_note_is_not_sent_for_condensing(self):
        def unexpected_chat(system, user, **kwargs):
            raise AssertionError("single-part notes must not call the merge pass")

        original = ingest.llm.chat
        ingest.llm.chat = unexpected_chat
        try:
            assembled = _assemble_structured_notes(
                "Quantum", ["## Summary\nOnly one overview."], condense=True,
            )
        finally:
            ingest.llm.chat = original

        self.assertIn("Only one overview.", assembled)


if __name__ == "__main__":
    unittest.main()
