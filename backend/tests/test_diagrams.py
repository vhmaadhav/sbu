import tempfile
import unittest

from PIL import Image, ImageDraw

from core.diagrams import graph_to_mermaid, trace_connectors, validate_graph


class DiagramValidationTests(unittest.TestCase):
    def test_normalizes_ids_and_drops_invalid_and_duplicate_edges(self):
        graph, messages = validate_graph({
            "is_diagram": True,
            "title": "Flow",
            "nodes": [
                {"id": "Start Here", "label": "Start", "shape": "rounded", "bbox": [1, 2, 3, 4]},
                {"id": "Done", "label": "Done", "shape": "rectangle", "bbox": [5, 6, 7, 8]},
            ],
            "edges": [
                {"from": "Start Here", "to": "Done", "label": ""},
                {"from": "Start Here", "to": "Done", "label": ""},
                {"from": "missing", "to": "Done", "label": ""},
            ],
        })
        self.assertEqual([n["id"] for n in graph["nodes"]], ["start_here", "done"])
        self.assertEqual(graph["edges"], [{"from": "start_here", "to": "done", "label": ""}])
        self.assertTrue(any("duplicate" in message.lower() for message in messages))
        self.assertTrue(any("unknown endpoint" in message.lower() for message in messages))

    def test_mermaid_escapes_labels_and_uses_shapes(self):
        mermaid = graph_to_mermaid({
            "nodes": [{"id": "decision", "label": 'Laptop "available"?', "shape": "diamond"}],
            "edges": [],
        })
        self.assertIn("decision{\"Laptop 'available'?\"}", mermaid)

    def test_detects_corner_coordinate_mode_across_nodes(self):
        graph, _ = validate_graph({
            "nodes": [
                {"id": "a", "label": "A", "bbox": [100, 300, 200, 500]},
                {"id": "b", "label": "B", "bbox": [300, 300, 400, 500]},
                {"id": "c", "label": "C", "bbox": [500, 300, 600, 500]},
            ],
            "edges": [],
        })
        self.assertEqual(graph["nodes"][1]["bbox"], [300, 300, 100, 200])

    def test_corrects_common_rag_ocr_confusion_in_context(self):
        graph, _ = validate_graph({
            "nodes": [{"id": "rag", "label": "Update R46 knowledge", "bbox": []}],
            "edges": [],
        })
        self.assertEqual(graph["nodes"][0]["label"], "Update RAG knowledge")

    def test_connector_threshold_ignores_faint_notebook_lines(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as image_file:
            image = Image.new("L", (240, 160), 245)
            draw = ImageDraw.Draw(image)
            for y in range(20, 160, 20):
                draw.line((0, y, 239, y), fill=205, width=1)
            draw.line((30, 80, 210, 80), fill=25, width=4)
            image.save(image_file.name)

            details, _ = trace_connectors(image_file.name)

        self.assertLess(details["threshold"], 205)
        self.assertLess(details["junction_pixels"], details["skeleton_pixels"])


if __name__ == "__main__":
    unittest.main()
