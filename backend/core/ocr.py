"""Text extraction from images (Apple Vision OCR) and PDFs (PyMuPDF + OCR fallback)."""
import tempfile
from pathlib import Path


def ocr_image_annotations(image_path: str) -> list[tuple]:
    """Apple Vision annotations: [(text, confidence, bbox)]."""
    from ocrmac import ocrmac
    return ocrmac.OCR(image_path, recognition_level="accurate").recognize()


def ocr_image(image_path: str) -> str:
    return "\n".join(a[0] for a in ocr_image_annotations(image_path)).strip()


def extract_pdf(pdf_path: str) -> list[dict]:
    """Returns [{page, text}] using the text layer, OCRing pages that lack one."""
    import fitz  # PyMuPDF

    pages = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            if not text:
                pix = page.get_pixmap(dpi=200)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    pix.save(tmp.name)
                    text = ocr_image(tmp.name)
                    Path(tmp.name).unlink(missing_ok=True)
            if text:
                pages.append({"page": i, "text": text})
    return pages
