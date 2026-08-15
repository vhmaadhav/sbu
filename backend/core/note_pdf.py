"""Render editable Study Buddy Markdown notes as polished, portable PDFs."""
from __future__ import annotations

import re
from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path

from PIL import Image as PillowImage

from core import db, mathmd

_HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
_IMAGE = re.compile(r"^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.+)$")
_NUMBERED = re.compile(r"^(\s*)(\d+)[.)]\s+(.+)$")
_TABLE_DIVIDER = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)
_HORIZONTAL_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_DISPLAY_MATH_FENCE = re.compile(r"^\s*\$\$\s*$")


def _font() -> str:
    """Register a broad Unicode font when the host provides one."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    name = "StudyBuddyNoteUnicode"
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            pdfmetrics.registerFont(TTFont(name, str(candidate)))
            pdfmetrics.registerFontFamily(
                name, normal=name, bold=name, italic=name, boldItalic=name
            )
            return name
    return "Helvetica"


def image_paths_for_item(item_id: int) -> dict[str, Path]:
    """Resolve the internal image URLs that can appear in an item's Markdown."""
    paths: dict[str, Path] = {}
    for figure in db.list_doc_figures(item_id):
        path = Path(figure["image_path"])
        paths[f"/api/doc/figures/{path.name}"] = path
    for frame in db.list_video_frames(item_id):
        paths[f"/api/video/frames/{frame['id']}/image"] = Path(frame["frame_path"])
    return paths


def _inline(value: str) -> str:
    """Convert the small inline Markdown subset used in notes to ReportLab XML."""
    code_spans: list[str] = []

    def save_code(match: re.Match) -> str:
        code_spans.append(match.group(1))
        return f"@@CODE{len(code_spans) - 1}@@"

    value = re.sub(r"`([^`]+)`", save_code, value)

    # Formulas are lifted out before escaping and emphasis: their backslashes,
    # underscores and asterisks are notation, not Markdown.
    math_spans: list[str] = []

    def save_math(match: re.Match) -> str:
        body = match.group(1) if match.group(1) is not None else match.group(2)
        math_spans.append(mathmd.to_markup(body))
        return f"@@MATH{len(math_spans) - 1}@@"

    value = mathmd.MATH_SPAN.sub(save_math, value)
    value = escape(value)
    value = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda match: f"{match.group(1)} ({match.group(2)})",
        value,
    )
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"__(.+?)__", r"<b>\1</b>", value)
    value = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", value)
    # Underscores inside formulas and identifiers (E_n, file_name) are not
    # emphasis delimiters. Require non-word boundaries on both sides.
    value = re.sub(r"(?<![\w])_([^_\n]+)_(?![\w])", r"<i>\1</i>", value)
    value = re.sub(r"~~(.+?)~~", r"<strike>\1</strike>", value)
    for index, code in enumerate(code_spans):
        value = value.replace(
            f"@@CODE{index}@@",
            f'<font name="Courier">{escape(code)}</font>',
        )
    for index, formula in enumerate(math_spans):
        value = value.replace(f"@@MATH{index}@@", formula)
    return value


def _table_cells(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def _is_block_start(lines: list[str], index: int) -> bool:
    stripped = lines[index].strip()
    if not stripped:
        return True
    if (
        stripped.startswith("```")
        or _HEADING.match(stripped)
        or _IMAGE.match(stripped)
        or _BULLET.match(lines[index])
        or _NUMBERED.match(lines[index])
        or _HORIZONTAL_RULE.match(stripped)
        or _DISPLAY_MATH_FENCE.match(stripped)
        or stripped.startswith(">")
    ):
        return True
    return (
        index + 1 < len(lines)
        and "|" in stripped
        and _TABLE_DIVIDER.match(lines[index + 1]) is not None
    )


def _image_flowables(url: str, alt: str, paths: dict[str, Path], styles: dict):
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, Spacer

    path = paths.get(url.split("#", 1)[0].split("?", 1)[0])
    if path is None or not path.is_file():
        label = alt.strip() or "Image"
        return [Paragraph(f"<i>{escape(label)} unavailable in PDF export.</i>", styles["caption"])]
    try:
        with PillowImage.open(path) as source:
            width, height = source.size
        max_width, max_height = 165 * mm, 110 * mm
        scale = min(max_width / width, max_height / height, 1.0)
        image = Image(str(path), width=width * scale, height=height * scale)
        image.hAlign = "CENTER"
        result = [Spacer(1, 2 * mm), image]
        if alt.strip():
            result.append(Paragraph(escape(alt.strip()), styles["caption"]))
        result.append(Spacer(1, 2 * mm))
        return result
    except Exception:
        label = alt.strip() or path.name
        return [Paragraph(f"<i>{escape(label)} could not be rendered.</i>", styles["caption"])]


def _story(markdown: str, title: str, paths: dict[str, Path], styles: dict, page_width):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable, Paragraph, Spacer, Table, TableStyle,
    )

    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    story = []
    index = 0
    first_content = True
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        if not stripped:
            index += 1
            continue

        if stripped.startswith("```"):
            index += 1
            code_lines = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            code = "<br/>".join(escape(line) or " " for line in code_lines)
            story.extend([Paragraph(code or " ", styles["code"]), Spacer(1, 2 * mm)])
            first_content = False
            continue

        if _DISPLAY_MATH_FENCE.match(stripped):
            index += 1
            formula_lines = []
            while index < len(lines) and not _DISPLAY_MATH_FENCE.match(lines[index]):
                formula_lines.append(lines[index].strip())
                index += 1
            if index < len(lines):
                index += 1
            formulas = "<br/>".join(
                mathmd.to_markup(line) for line in formula_lines if line
            )
            if formulas:
                story.extend([Paragraph(formulas, styles["formula"]), Spacer(1, 1 * mm)])
            first_content = False
            continue

        image_match = _IMAGE.match(stripped)
        if image_match:
            story.extend(_image_flowables(
                image_match.group(2), image_match.group(1), paths, styles
            ))
            index += 1
            first_content = False
            continue

        heading = _HEADING.match(stripped)
        if heading:
            level = len(heading.group(1))
            heading_text = heading.group(2).strip()
            if not (first_content and level == 1 and heading_text.casefold() == title.casefold()):
                story.append(Paragraph(_inline(heading_text), styles[f"h{level}"]))
            index += 1
            first_content = False
            continue

        if _HORIZONTAL_RULE.match(stripped):
            story.extend([
                Spacer(1, 1.5 * mm),
                HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#CBD5E1")),
                Spacer(1, 2.5 * mm),
            ])
            index += 1
            first_content = False
            continue

        if (
            index + 1 < len(lines)
            and "|" in stripped
            and _TABLE_DIVIDER.match(lines[index + 1])
        ):
            rows = [_table_cells(raw)]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                rows.append(_table_cells(lines[index]))
                index += 1
            columns = max(len(row) for row in rows)
            normalized = [row + [""] * (columns - len(row)) for row in rows]
            cells = [
                [Paragraph(_inline(cell), styles["table"]) for cell in row]
                for row in normalized
            ]
            table = Table(
                cells,
                colWidths=[page_width / columns] * columns,
                repeatRows=1,
                hAlign="LEFT",
            )
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF7")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#172033")),
                ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.extend([table, Spacer(1, 3 * mm)])
            first_content = False
            continue

        bullet = _BULLET.match(raw)
        numbered = _NUMBERED.match(raw)
        if bullet or numbered:
            while index < len(lines):
                bullet = _BULLET.match(lines[index])
                numbered = _NUMBERED.match(lines[index])
                if not bullet and not numbered:
                    break
                match = bullet or numbered
                indent = len(match.group(1).expandtabs(2))
                text_group = 2 if bullet else 3
                marker = "\u2022" if bullet else f"{numbered.group(2)}."
                style = styles["list"].clone(f"List-{index}")
                style.leftIndent += min(indent, 12) * 2
                story.append(Paragraph(
                    _inline(match.group(text_group)),
                    style,
                    bulletText=marker,
                ))
                index += 1
            story.append(Spacer(1, 1.5 * mm))
            first_content = False
            continue

        if stripped.startswith(">"):
            quote_lines = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(lines[index].strip().lstrip(">").strip())
                index += 1
            story.append(Paragraph(_inline(" ".join(quote_lines)), styles["quote"]))
            story.append(Spacer(1, 2 * mm))
            first_content = False
            continue

        paragraph_lines = [stripped]
        index += 1
        while index < len(lines) and not _is_block_start(lines, index):
            paragraph_lines.append(lines[index].strip())
            index += 1
        body = " ".join(part for part in paragraph_lines if part)
        story.append(Paragraph(_inline(body), styles["body"]))
        first_content = False

    return story


def to_pdf(
    markdown: str,
    *,
    title: str | None = None,
    subject: str | None = None,
    created_at: float | None = None,
    image_paths: dict[str, Path] | None = None,
) -> bytes:
    """Render a note to an A4 PDF and return its bytes."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    # Notes written before math normalization existed still carry \(…\) spans
    # and ```math fences, so every export is normalized on the way in.
    from core.notes import strip_placement_tokens

    markdown = mathmd.normalize(strip_placement_tokens(markdown))
    first_heading = next(
        (
            match.group(2).strip()
            for line in markdown.splitlines()
            if (match := _HEADING.match(line.strip())) and len(match.group(1)) == 1
        ),
        None,
    )
    document_title = (title or first_heading or "Study notes").strip()
    font = _font()
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "NoteTitle", parent=base["Title"], fontName=font, fontSize=22,
            leading=28, alignment=TA_CENTER, textColor=colors.HexColor("#172033"),
            spaceAfter=5 * mm,
        ),
        "meta": ParagraphStyle(
            "NoteMeta", parent=base["BodyText"], fontName=font, fontSize=9,
            leading=12, textColor=colors.HexColor("#526078"), alignment=TA_CENTER,
        ),
        "h1": ParagraphStyle(
            "NoteH1", parent=base["Heading1"], fontName=font, fontSize=18,
            leading=23, textColor=colors.HexColor("#172033"), spaceBefore=5 * mm,
            spaceAfter=3 * mm,
        ),
        "h2": ParagraphStyle(
            "NoteH2", parent=base["Heading2"], fontName=font, fontSize=14,
            leading=18, textColor=colors.HexColor("#0F766E"), spaceBefore=5 * mm,
            spaceAfter=2.5 * mm,
        ),
        "h3": ParagraphStyle(
            "NoteH3", parent=base["Heading3"], fontName=font, fontSize=11.5,
            leading=15, textColor=colors.HexColor("#273247"), spaceBefore=3.5 * mm,
            spaceAfter=2 * mm,
        ),
        "h4": ParagraphStyle(
            "NoteH4", parent=base["Heading4"], fontName=font, fontSize=10.5,
            leading=14, textColor=colors.HexColor("#334155"), spaceBefore=3 * mm,
            spaceAfter=1.5 * mm,
        ),
        "body": ParagraphStyle(
            "NoteBody", parent=base["BodyText"], fontName=font, fontSize=10.2,
            leading=15.5, textColor=colors.HexColor("#253047"), spaceAfter=2.5 * mm,
        ),
        "list": ParagraphStyle(
            "NoteList", parent=base["BodyText"], fontName=font, fontSize=10,
            leading=15, leftIndent=6 * mm, firstLineIndent=0, bulletIndent=1.5 * mm,
            textColor=colors.HexColor("#253047"), spaceAfter=1 * mm,
        ),
        "quote": ParagraphStyle(
            "NoteQuote", parent=base["BodyText"], fontName=font, fontSize=9.8,
            leading=15, leftIndent=7 * mm, rightIndent=5 * mm,
            borderColor=colors.HexColor("#0F766E"), borderWidth=0,
            borderPadding=(3, 6, 3, 8), backColor=colors.HexColor("#F0FDFA"),
            textColor=colors.HexColor("#334155"),
        ),
        "formula": ParagraphStyle(
            "NoteFormula", parent=base["BodyText"], fontName=font, fontSize=10.5,
            leading=17, alignment=TA_CENTER, textColor=colors.HexColor("#172033"),
            spaceBefore=2 * mm, spaceAfter=2 * mm,
        ),
        "code": ParagraphStyle(
            "NoteCode", parent=base["Code"], fontName="Courier", fontSize=8.5,
            leading=12, leftIndent=4 * mm, rightIndent=4 * mm,
            borderPadding=6, backColor=colors.HexColor("#F1F5F9"),
            textColor=colors.HexColor("#172033"), spaceAfter=2 * mm,
        ),
        "table": ParagraphStyle(
            "NoteTable", parent=base["BodyText"], fontName=font, fontSize=8.5,
            leading=11, textColor=colors.HexColor("#253047"),
        ),
        "caption": ParagraphStyle(
            "NoteCaption", parent=base["BodyText"], fontName=font, fontSize=8.5,
            leading=11, alignment=TA_CENTER, textColor=colors.HexColor("#64748B"),
            spaceBefore=1.5 * mm, spaceAfter=2 * mm,
        ),
        "footer": ParagraphStyle(
            "NoteFooter", parent=base["BodyText"], fontName=font, fontSize=7.5,
            leading=9, alignment=TA_RIGHT, textColor=colors.HexColor("#64748B"),
        ),
    }

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=17 * mm,
        title=document_title,
        author="Study Buddy",
        subject=subject or "Study notes",
    )
    story = [Paragraph(_inline(document_title), styles["title"])]
    metadata = []
    if subject:
        metadata.append(subject.strip())
    if created_at:
        metadata.append(datetime.fromtimestamp(created_at).strftime("%d %B %Y"))
    if metadata:
        meta_table = Table(
            [[Paragraph(escape("  |  ".join(metadata)), styles["meta"])]],
            colWidths=[document.width],
        )
        meta_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.extend([meta_table, Spacer(1, 5 * mm)])
    story.extend(_story(
        markdown,
        document_title,
        image_paths or {},
        styles,
        document.width,
    ))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#E2E8F0"))
        canvas.setLineWidth(0.4)
        canvas.line(doc.leftMargin, 12 * mm, A4[0] - doc.rightMargin, 12 * mm)
        canvas.setFont(font, 7.5)
        canvas.setFillColor(colors.HexColor("#64748B"))
        footer_title = document_title[:65]
        canvas.drawString(doc.leftMargin, 8 * mm, footer_title)
        canvas.drawRightString(A4[0] - doc.rightMargin, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
