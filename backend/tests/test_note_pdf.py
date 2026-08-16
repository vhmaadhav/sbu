import tempfile
import unittest
from pathlib import Path

import fitz
from PIL import Image

from core import note_pdf


class NotePdfTests(unittest.TestCase):
    def test_renders_markdown_structure_and_embedded_image(self):
        with tempfile.TemporaryDirectory() as folder:
            image_path = Path(folder) / "diagram.png"
            Image.new("RGB", (640, 240), "#dbeafe").save(image_path)
            markdown = """# Circuit Analysis

## Summary

Use **Kirchhoff's laws** to analyze a circuit. The energy is
**$E_n$** where \\(E_n = n^2\\).

```math
E_n = \\frac{n^2 \\pi^2}{2ma^2}
```

- Sum voltages around a loop.
- Sum currents at a node.

| Law | Statement |
| --- | --- |
| KVL | Voltages sum to zero |
| KCL | Currents sum to zero |

![Circuit diagram](/api/doc/figures/diagram.png)

```text
V1 - IR = 0
```
"""

            payload = note_pdf.to_pdf(
                markdown,
                title="Circuit Analysis",
                subject="Electronics",
                created_at=1_785_000_000,
                image_paths={"/api/doc/figures/diagram.png": image_path},
            )

        document = fitz.open(stream=payload, filetype="pdf")
        text = "\n".join(page.get_text() for page in document)
        self.assertGreaterEqual(document.page_count, 1)
        self.assertIn("Circuit Analysis", text)
        self.assertIn("Kirchhoff's laws", text)
        # Math is typeset, not printed as raw LaTeX: no delimiters, no commands.
        self.assertIn("En", text.replace(" ", ""))
        self.assertNotIn("$", text)
        self.assertNotIn("\\frac", text)
        self.assertIn("π", text)
        self.assertIn("Voltages sum to zero", text)
        self.assertIn("Circuit diagram", text)
        self.assertIn("Page 1", text)
        self.assertTrue(any(page.get_images() for page in document))


if __name__ == "__main__":
    unittest.main()
