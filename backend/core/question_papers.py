"""Generate grounded, printable question papers from selected notes."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from io import BytesIO
from pathlib import Path

from core import db, llm

TYPE_MARKS = {"mcq": 1, "short": 3, "long": 5}
TYPE_LABELS = {
    "mcq": "multiple-choice",
    "short": "short-answer",
    "long": "long-answer",
}
MAX_QUESTIONS = 30
MAX_SOURCE_CHARS = 30_000
GENERATION_BATCH_SIZE = 5

GENERATION_SYSTEM = """You are an assessment designer.
Create questions using only the supplied notes. Do not test facts that are absent
from the notes. Questions should test understanding rather than quote sentences.
Avoid duplicates and ambiguous wording. Every multiple-choice question must have
exactly four distinct options and one option must exactly equal its answer.
Short and long answers must include a concise model answer and a brief marking
explanation. Return one JSON object with this exact shape:
{"title": "Paper title", "questions": [
  {"type": "mcq|short|long", "prompt": "...", "options": ["..."], "answer": "...",
   "explanation": "..."}
]}.
"""


@dataclass(frozen=True)
class PaperRequest:
    note_ids: list[int]
    title: str
    difficulty: str
    duration_minutes: int
    mcq_count: int
    short_count: int
    long_count: int

    @property
    def question_count(self) -> int:
        return self.mcq_count + self.short_count + self.long_count

    @property
    def total_marks(self) -> int:
        return (
            self.mcq_count * TYPE_MARKS["mcq"]
            + self.short_count * TYPE_MARKS["short"]
            + self.long_count * TYPE_MARKS["long"]
        )


def validate_request(request: PaperRequest) -> None:
    if not request.note_ids:
        raise ValueError("Select at least one note")
    if request.difficulty not in {"easy", "medium", "hard"}:
        raise ValueError("Difficulty must be easy, medium, or hard")
    if not 15 <= request.duration_minutes <= 300:
        raise ValueError("Duration must be between 15 and 300 minutes")
    counts = (request.mcq_count, request.short_count, request.long_count)
    if any(count < 0 for count in counts):
        raise ValueError("Question counts cannot be negative")
    if request.question_count < 1:
        raise ValueError("Add at least one question")
    if request.question_count > MAX_QUESTIONS:
        raise ValueError(f"A paper can contain at most {MAX_QUESTIONS} questions")


def _selected_notes(note_ids: list[int]) -> tuple[str, list[dict]]:
    unique_ids = list(dict.fromkeys(note_ids))
    placeholders = ",".join("?" for _ in unique_ids)
    with db.conn() as c:
        rows = c.execute(
            "SELECT notes.id, notes.markdown, items.title, subjects.name AS subject "
            "FROM notes JOIN items ON items.id=notes.item_id "
            "LEFT JOIN subjects ON subjects.id=items.subject_id "
            f"WHERE notes.id IN ({placeholders})",
            unique_ids,
        ).fetchall()
    by_id = {row["id"]: row for row in rows}
    ordered = [by_id[note_id] for note_id in unique_ids if note_id in by_id]
    if len(ordered) != len(unique_ids):
        raise ValueError("One or more selected notes no longer exist")
    sources = [
        {
            "note_id": row["id"],
            "title": row["title"] or "Untitled",
            "subject": row["subject"],
        }
        for row in ordered
    ]
    per_note_chars = max(1000, MAX_SOURCE_CHARS // len(ordered))
    blocks = [
        f"[NOTE {row['id']}: {row['title'] or 'Untitled'}]\n"
        f"{row['markdown'][:per_note_chars]}"
        for row in ordered
    ]
    return "\n\n---\n\n".join(blocks)[:MAX_SOURCE_CHARS], sources


def _clean_questions(payload: dict, request: PaperRequest) -> list[dict]:
    raw_questions = payload.get("questions")
    if not isinstance(raw_questions, list):
        raise ValueError("The model did not return a question list")
    requested = {
        "mcq": request.mcq_count,
        "short": request.short_count,
        "long": request.long_count,
    }
    grouped: dict[str, list[dict]] = {kind: [] for kind in TYPE_MARKS}
    seen: set[str] = set()
    for raw in raw_questions:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("type", "")).strip().casefold().replace("-", "_")
        kind = {
            "multiple_choice": "mcq",
            "multiple choice": "mcq",
            "short_answer": "short",
            "long_answer": "long",
        }.get(kind, kind)
        prompt = str(raw.get("prompt", "")).strip()
        answer = str(raw.get("answer", "")).strip()
        if kind not in requested or not prompt or not answer:
            continue
        key = prompt.casefold()
        if key in seen or len(grouped[kind]) >= requested[kind]:
            continue
        options: list[str] = []
        if kind == "mcq":
            raw_options = raw.get("options")
            if not isinstance(raw_options, list):
                continue
            options = [str(option).strip() for option in raw_options if str(option).strip()]
            if len(options) != 4 or len({option.casefold() for option in options}) != 4:
                continue
            matching = next(
                (option for option in options if option.casefold() == answer.casefold()),
                None,
            )
            if matching is None:
                answer_label = answer.casefold().removeprefix("option ").strip(" .():")
                if len(answer_label) == 1 and "a" <= answer_label <= "d":
                    matching = options[ord(answer_label) - ord("a")]
            if matching is None:
                continue
            answer = matching
        grouped[kind].append({
            "type": kind,
            "prompt": prompt[:2000],
            "options": options,
            "answer": answer[:4000],
            "explanation": str(raw.get("explanation", "")).strip()[:4000],
            "marks": TYPE_MARKS[kind],
        })
        seen.add(key)
    missing = [
        f"{requested[kind] - len(grouped[kind])} {TYPE_LABELS[kind]}"
        for kind in requested if len(grouped[kind]) != requested[kind]
    ]
    if missing:
        raise ValueError(
            "The model returned an incomplete paper (missing " + ", ".join(missing) + ")"
        )
    return grouped["mcq"] + grouped["short"] + grouped["long"]


def _request_for_type(request: PaperRequest, kind: str, count: int) -> PaperRequest:
    return PaperRequest(
        note_ids=request.note_ids,
        title=request.title,
        difficulty=request.difficulty,
        duration_minutes=request.duration_minutes,
        mcq_count=count if kind == "mcq" else 0,
        short_count=count if kind == "short" else 0,
        long_count=count if kind == "long" else 0,
    )


def _batch_schema(kind: str, count: int) -> dict:
    option_limits = (
        {"minItems": 4, "maxItems": 4} if kind == "mcq"
        else {"minItems": 0, "maxItems": 0}
    )
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "questions": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": [kind]},
                        "prompt": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            **option_limits,
                        },
                        "answer": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                    "required": [
                        "type", "prompt", "options", "answer", "explanation",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["title", "questions"],
        "additionalProperties": False,
    }


def _generate_questions(request: PaperRequest, context: str) -> list[dict]:
    """Generate small JSON batches so long papers cannot truncate one response."""
    questions: list[dict] = []
    seen_prompts: set[str] = set()
    for kind, requested_count in (
        ("mcq", request.mcq_count),
        ("short", request.short_count),
        ("long", request.long_count),
    ):
        remaining = requested_count
        batch_number = 1
        while remaining:
            count = min(GENERATION_BATCH_SIZE, remaining)
            batch_request = _request_for_type(request, kind, count)
            prior = "\n".join(
                f"- {question['prompt']}" for question in questions[-20:]
            ) or "(none)"
            user_prompt = (
                f"Generate batch {batch_number}: exactly {count} "
                f"{TYPE_LABELS[kind]} question(s).\n"
                f"Difficulty: {request.difficulty}\n"
                f"Each question is worth {TYPE_MARKS[kind]} mark(s).\n"
                f"Do not repeat these existing questions:\n{prior}\n\n"
                f"Source notes:\n{context}"
            )
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    feedback = (
                        f"\n\nThe previous attempt failed validation: {last_error}. "
                        "Correct that exact problem and produce different questions."
                        if last_error else ""
                    )
                    payload = llm.chat_json_schema(
                        GENERATION_SYSTEM,
                        user_prompt + feedback,
                        _batch_schema(kind, count),
                        name=f"{kind}_questions",
                        max_tokens=3200,
                        timeout=120.0,
                    )
                    batch = _clean_questions(payload, batch_request)
                    if any(
                        question["prompt"].casefold() in seen_prompts
                        for question in batch
                    ):
                        raise ValueError("The model repeated a question from an earlier batch")
                    questions.extend(batch)
                    seen_prompts.update(
                        question["prompt"].casefold() for question in batch
                    )
                    break
                except Exception as error:
                    last_error = error
            else:
                detail = str(last_error) if isinstance(last_error, ValueError) else (
                    "the local model returned truncated or malformed JSON"
                )
                raise ValueError(
                    f"Could not generate {TYPE_LABELS[kind]} batch {batch_number}: "
                    f"{detail}. Try fewer questions or shorter source notes."
                ) from last_error
            remaining -= count
            batch_number += 1
    return questions


def generate(request: PaperRequest) -> dict:
    validate_request(request)
    context, sources = _selected_notes(request.note_ids)
    questions = _generate_questions(request, context)
    title = request.title.strip()
    if not title:
        source_title = sources[0]["title"] if len(sources) == 1 else "Combined Notes"
        title = f"{source_title} Question Paper"
    instructions = (
        f"Answer all {request.question_count} questions. "
        f"Time allowed: {request.duration_minutes} minutes. "
        f"Maximum marks: {request.total_marks}."
    )
    paper_id = db.create_question_paper(
        title=title[:180],
        difficulty=request.difficulty,
        duration_minutes=request.duration_minutes,
        instructions=instructions,
        questions=questions,
        sources=sources,
    )
    return db.get_question_paper(paper_id)


def to_markdown(paper: dict, include_answers: bool = False) -> str:
    lines = [
        f"# {paper['title']}",
        "",
        f"**Time:** {paper['duration_minutes']} minutes  ",
        f"**Maximum marks:** {paper['total_marks']}  ",
        f"**Difficulty:** {paper['difficulty'].title()}",
        "",
        paper["instructions"],
        "",
        "---",
    ]
    for index, question in enumerate(paper["questions"], start=1):
        lines.extend([
            "",
            f"## {index}. {question['prompt']} [{question['marks']}]",
        ])
        if question["options"]:
            lines.extend(
                f"{chr(65 + option_index)}. {option}"
                for option_index, option in enumerate(question["options"])
            )
    if include_answers:
        lines.extend(["", "---", "", "# Answer key"])
        for index, question in enumerate(paper["questions"], start=1):
            lines.extend(["", f"## {index}. {question['answer']}"])
            if question["explanation"]:
                lines.append(question["explanation"])
    return "\n".join(lines).strip() + "\n"


def _pdf_font() -> str:
    """Register a Unicode font when the host provides one."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_name = "QuestionPaperUnicode"
    if font_name in pdfmetrics.getRegisteredFontNames():
        return font_name
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            pdfmetrics.registerFont(TTFont(font_name, str(candidate)))
            pdfmetrics.registerFontFamily(
                font_name, normal=font_name, bold=font_name,
                italic=font_name, boldItalic=font_name,
            )
            return font_name
    return "Helvetica"


def to_pdf(paper: dict, include_answers: bool = False) -> bytes:
    """Render a polished A4 student paper, optionally followed by its answer key."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
        TableStyle,
    )

    buffer = BytesIO()
    font = _pdf_font()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "PaperTitle", parent=styles["Title"], fontName=font, fontSize=20,
        leading=25, alignment=TA_CENTER, textColor=colors.HexColor("#172033"),
        spaceAfter=5 * mm,
    )
    meta_style = ParagraphStyle(
        "PaperMeta", parent=styles["BodyText"], fontName=font, fontSize=9.5,
        leading=13, textColor=colors.HexColor("#465166"),
    )
    instruction_style = ParagraphStyle(
        "Instructions", parent=styles["BodyText"], fontName=font, fontSize=9.5,
        leading=14, textColor=colors.HexColor("#273247"),
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Heading2"], fontName=font, fontSize=11,
        leading=14, textColor=colors.HexColor("#0F766E"), spaceBefore=4 * mm,
        spaceAfter=3 * mm,
    )
    question_style = ParagraphStyle(
        "Question", parent=styles["BodyText"], fontName=font, fontSize=10.5,
        leading=15, textColor=colors.HexColor("#172033"),
    )
    marks_style = ParagraphStyle(
        "Marks", parent=question_style, alignment=TA_RIGHT,
        textColor=colors.HexColor("#526078"),
    )
    option_style = ParagraphStyle(
        "Option", parent=styles["BodyText"], fontName=font, fontSize=9.7,
        leading=14, leftIndent=7 * mm, textColor=colors.HexColor("#273247"),
    )
    answer_style = ParagraphStyle(
        "Answer", parent=styles["BodyText"], fontName=font, fontSize=9.7,
        leading=14, textColor=colors.HexColor("#172033"),
    )
    explanation_style = ParagraphStyle(
        "Explanation", parent=answer_style, fontSize=9, leading=13,
        textColor=colors.HexColor("#526078"), spaceBefore=1.5 * mm,
    )

    document = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm,
        topMargin=18 * mm, bottomMargin=17 * mm,
        title=paper["title"], author="Study Buddy",
    )
    story = [
        Paragraph(escape(paper["title"]), title_style),
        Table(
            [[
                Paragraph(
                    f"<b>Time:</b> {paper['duration_minutes']} minutes",
                    meta_style,
                ),
                Paragraph(
                    f"<b>Maximum marks:</b> {paper['total_marks']}",
                    meta_style,
                ),
                Paragraph(
                    f"<b>Difficulty:</b> {escape(paper['difficulty'].title())}",
                    meta_style,
                ),
            ]],
            colWidths=[55 * mm, 65 * mm, 40 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]),
        ),
        Spacer(1, 4 * mm),
        Paragraph(f"<b>Instructions:</b> {escape(paper['instructions'])}", instruction_style),
        Spacer(1, 3 * mm),
    ]

    type_labels = {
        "mcq": "Section A - Multiple-choice questions",
        "short": "Section B - Short-answer questions",
        "long": "Section C - Long-answer questions",
    }
    current_type = None
    for index, question in enumerate(paper["questions"], start=1):
        block = []
        if question["type"] != current_type:
            current_type = question["type"]
            block.append(Paragraph(type_labels[current_type], section_style))
        block.extend([
            Table(
                [[
                    Paragraph(
                        f"<b>{index}.</b> {escape(question['prompt'])}",
                        question_style,
                    ),
                    Paragraph(f"[{question['marks']}]", marks_style),
                ]],
                colWidths=[157 * mm, 13 * mm],
                style=TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]),
            ),
            Spacer(1, 2 * mm),
        ])
        for option_index, option in enumerate(question["options"]):
            block.append(Paragraph(
                f"{chr(65 + option_index)}. {escape(option)}", option_style
            ))
        if not question["options"]:
            line_count = 3 if question["type"] == "short" else 7
            block.append(Table(
                [[""] for _ in range(line_count)],
                colWidths=[165 * mm],
                rowHeights=[6 * mm] * line_count,
                style=TableStyle([
                    ("LINEBELOW", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
                ]),
            ))
        block.append(Spacer(1, 4 * mm))
        story.append(KeepTogether(block))

    if include_answers:
        story.extend([
            PageBreak(),
            Paragraph("Answer key", title_style),
            Paragraph(
                f"{escape(paper['title'])} - {paper['total_marks']} marks",
                meta_style,
            ),
            Spacer(1, 4 * mm),
        ])
        for index, question in enumerate(paper["questions"], start=1):
            answer_block = [
                Paragraph(
                    f"<b>{index}. {escape(question['prompt'])}</b>",
                    answer_style,
                ),
                Spacer(1, 1.5 * mm),
                Table(
                    [[Paragraph(
                        f"<b>Answer:</b> {escape(question['answer'])}",
                        answer_style,
                    )]],
                    colWidths=[166 * mm],
                    style=TableStyle([
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ECFDF5")),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#99D5C9")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 7),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ]),
                ),
            ]
            if question["explanation"]:
                answer_block.extend([
                    Spacer(1, 1.5 * mm),
                    Paragraph(
                        f"<b>Marking guidance:</b> {escape(question['explanation'])}",
                        explanation_style,
                    ),
                ])
            answer_block.append(Spacer(1, 4 * mm))
            story.append(KeepTogether(answer_block))

    def page_decoration(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
        canvas.setLineWidth(0.5)
        canvas.line(17 * mm, 12 * mm, A4[0] - 17 * mm, 12 * mm)
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(17 * mm, 7.5 * mm, "Study Buddy")
        canvas.drawRightString(
            A4[0] - 17 * mm, 7.5 * mm, f"Page {doc.page}"
        )
        canvas.restoreState()

    document.build(
        story, onFirstPage=page_decoration, onLaterPages=page_decoration,
    )
    return buffer.getvalue()
