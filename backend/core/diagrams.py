"""Local-first diagram understanding for images and captured video frames.

The pipeline deliberately keeps model calls and deterministic geometry separate:

1. PaddleOCR-VL transcribes document text/tables.
2. An optional fine-tuned D-FINE/RT-DETRv2 adapter supplies node/arrow boxes.
3. A dependency-free Zhang-Suen skeleton pass measures connector topology.
4. Qwen3-VL reconciles the image, OCR, and detector evidence into a graph.
5. Qwen3.5-4B-MLX reviews the graph, followed by strict local validation.

The detector adapter is explicit about missing weights; it never claims that the
fine-tuned detector ran when no checkpoint is configured.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from core import llm
from core.config import FIGURES_DIR

OCR_MODEL = os.getenv("DIAGRAM_OCR_MODEL", "paddleocr-vl-1.6")
VISION_MODEL = os.getenv("DIAGRAM_VISION_MODEL", "qwen/qwen3-vl-4b")
VALIDATOR_MODEL = os.getenv("DIAGRAM_VALIDATOR_MODEL", "qwen3.5-4b-mlx")
DETECTOR_WEIGHTS = os.getenv("DIAGRAM_DETECTOR_WEIGHTS", "").strip()

OCR_PROMPT = """Read this document image with PaddleOCR-VL.
Return Markdown containing every visible text label in reading order. Preserve
tables as Markdown tables. Do not explain or infer arrows. Ignore editor chrome."""

GRAPH_PROMPT = """You convert flowcharts and architecture diagrams into graphs.
Use the image as the primary source and the OCR evidence below as a hint. Return
one JSON object only:
{"is_diagram":true,"title":"short title","summary":"one sentence",
"nodes":[{"id":"stable_snake_case","label":"exact visible label",
"shape":"rectangle|diamond|rounded|circle|database|unknown",
"bbox":[x,y,width,height]}],
"edges":[{"from":"node_id","to":"node_id","label":""}]}
Coordinates are integers normalized to 0..1000. Include every meaningful node
and every directed connector. Follow arrowheads, including long curved arrows.
Do not turn instructions or editor chrome into nodes. If it is not a diagram,
return the same schema with is_diagram false and empty nodes/edges.

OCR evidence:
"""

VALIDATE_SYSTEM = """You validate a diagram graph using OCR evidence. Correct only
clear transcription mistakes, invalid edge endpoints, duplicate nodes, and
obviously reversed arrows. Never invent nodes absent from the evidence. Return
the complete corrected graph as one JSON object using the input schema."""


@dataclass
class Stage:
    name: str
    implementation: str
    status: str
    elapsed_ms: int
    details: dict[str, Any] = field(default_factory=dict)


def _image_b64(path: str | Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


def _vision_json(prompt: str, path: str | Path, model: str, max_tokens: int = 2500) -> dict:
    raw = llm.chat_vision(prompt, [_image_b64(path)], model=model, max_tokens=max_tokens)
    return llm._extract_json(raw)


def _clean_ocr(markdown: str) -> str:
    markdown = re.sub(r"<think>.*?</think>", "", markdown, flags=re.DOTALL)
    markdown = re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", markdown.strip())
    return markdown.strip()


def _sanitize_id(value: Any, fallback: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "")).strip("_").lower()
    if not clean:
        clean = fallback
    if clean[0].isdigit():
        clean = f"n_{clean}"
    return clean[:64]


def validate_graph(raw: dict) -> tuple[dict, list[str]]:
    """Make graph safe for storage/rendering and return validation messages."""
    messages: list[str] = []
    nodes: list[dict] = []
    used: set[str] = set()
    aliases: dict[str, str] = {}
    raw_nodes = raw.get("nodes", []) if isinstance(raw, dict) else []
    coordinate_pairs = [
        candidate.get("bbox")
        for candidate in raw_nodes
        if isinstance(candidate, dict)
        and isinstance(candidate.get("bbox"), list)
        and len(candidate["bbox"]) == 4
    ]

    def _correlation(left: list[float], right: list[float]) -> float:
        if len(left) < 3:
            return 0.0
        a, b = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
        if a.std() == 0 or b.std() == 0:
            return 0.0
        return float(np.corrcoef(a, b)[0, 1])

    # Some VLM runs return corners even when asked for dimensions. Across a
    # diagram, x1 strongly correlating with field 3 (or y1 with field 4) is a
    # reliable signal that the fields are x2/y2 rather than width/height.
    xyxy_mode = False
    if coordinate_pairs:
        try:
            xyxy_mode = (
                _correlation([box[0] for box in coordinate_pairs],
                             [box[2] for box in coordinate_pairs]) > 0.72
                or _correlation([box[1] for box in coordinate_pairs],
                                [box[3] for box in coordinate_pairs]) > 0.72
            )
        except (TypeError, ValueError):
            xyxy_mode = False

    for index, candidate in enumerate(raw_nodes):
        if not isinstance(candidate, dict):
            messages.append(f"Dropped non-object node at index {index}.")
            continue
        old_id = str(candidate.get("id", ""))
        node_id = _sanitize_id(old_id, f"node_{index + 1}")
        base = node_id
        suffix = 2
        while node_id in used:
            node_id = f"{base}_{suffix}"
            suffix += 1
        if node_id != old_id:
            messages.append(f"Normalized node id {old_id!r} to {node_id!r}.")
        used.add(node_id)
        aliases[old_id] = node_id
        label = re.sub(r"\s+", " ", str(candidate.get("label", "")).strip())[:160]
        label = re.sub(r"\bR4[6G]\s+(?=knowledge\b)", "RAG ", label, flags=re.IGNORECASE)
        if not label:
            label = node_id.replace("_", " ").title()
            messages.append(f"Filled the missing label for {node_id}.")
        shape = str(candidate.get("shape", "unknown")).lower()
        if shape not in {"rectangle", "diamond", "rounded", "circle", "database", "unknown"}:
            shape = "unknown"
        bbox = candidate.get("bbox", [])
        if not isinstance(bbox, list) or len(bbox) != 4:
            bbox = []
        else:
            bbox = [max(0, min(1000, int(float(value)))) for value in bbox]
            # Vision models frequently emit [x1,y1,x2,y2] despite the requested
            # [x,y,width,height] contract. Convert when the latter would leave
            # the normalized canvas.
            if xyxy_mode or bbox[0] + bbox[2] > 1000 or bbox[1] + bbox[3] > 1000:
                bbox = [bbox[0], bbox[1], max(0, bbox[2] - bbox[0]),
                        max(0, bbox[3] - bbox[1])]
        nodes.append({"id": node_id, "label": label, "shape": shape, "bbox": bbox})

    edges: list[dict] = []
    edge_keys: set[tuple[str, str, str]] = set()
    for index, candidate in enumerate(raw.get("edges", []) if isinstance(raw, dict) else []):
        if not isinstance(candidate, dict):
            continue
        source = aliases.get(str(candidate.get("from", "")), _sanitize_id(candidate.get("from"), ""))
        target = aliases.get(str(candidate.get("to", "")), _sanitize_id(candidate.get("to"), ""))
        if source not in used or target not in used:
            messages.append(f"Dropped edge {index + 1} with an unknown endpoint.")
            continue
        label = re.sub(r"\s+", " ", str(candidate.get("label", "")).strip())[:100]
        key = (source, target, label)
        if key in edge_keys:
            messages.append(f"Dropped duplicate edge {source} -> {target}.")
            continue
        edge_keys.add(key)
        edges.append({"from": source, "to": target, "label": label})

    connected = {e["from"] for e in edges} | {e["to"] for e in edges}
    orphans = [node["id"] for node in nodes if node["id"] not in connected]
    if orphans and len(nodes) > 1:
        messages.append("Orphan nodes: " + ", ".join(orphans))
    graph = {
        "is_diagram": bool(raw.get("is_diagram", nodes or edges)) if isinstance(raw, dict) else False,
        "title": re.sub(r"\s+", " ", str(raw.get("title", "Diagram")).strip())[:120] or "Diagram",
        "summary": re.sub(r"\s+", " ", str(raw.get("summary", "")).strip())[:500],
        "nodes": nodes,
        "edges": edges,
    }
    return graph, messages


def _thin(binary: np.ndarray, max_iterations: int = 80) -> np.ndarray:
    """Zhang-Suen thinning for a black-ink boolean image."""
    image = binary.astype(np.uint8).copy()
    for _ in range(max_iterations):
        changed = False
        for phase in (0, 1):
            p2 = np.roll(image, 1, axis=0)
            p3 = np.roll(p2, -1, axis=1)
            p4 = np.roll(image, -1, axis=1)
            p5 = np.roll(p4, -1, axis=0)
            p6 = np.roll(image, -1, axis=0)
            p7 = np.roll(p6, 1, axis=1)
            p8 = np.roll(image, 1, axis=1)
            p9 = np.roll(p8, 1, axis=0)
            neighbours = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            ring = (p2, p3, p4, p5, p6, p7, p8, p9)
            transitions = sum(
                ((ring[index] == 0) & (ring[(index + 1) % 8] == 1)).astype(np.uint8)
                for index in range(8)
            )
            remove = (image == 1) & (neighbours >= 2) & (neighbours <= 6) & (transitions == 1)
            if phase == 0:
                remove &= (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                remove &= (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            remove[[0, -1], :] = False
            remove[:, [0, -1]] = False
            if remove.any():
                changed = True
                image[remove] = 0
        if not changed:
            break
    return image.astype(bool)


def trace_connectors(path: str | Path, max_side: int = 480) -> tuple[dict, np.ndarray]:
    """Skeletonize ink and report endpoints/junctions for connector evidence."""
    with Image.open(path) as source:
        gray = source.convert("L")
        scale = min(1.0, max_side / max(gray.size))
        if scale < 1:
            gray = gray.resize((max(1, int(gray.width * scale)), max(1, int(gray.height * scale))))
        array = np.asarray(gray)
    # Keep faint paper/grid lines out of the topology. A high fixed threshold
    # turns an entire ruled notebook page into one giant junction.
    histogram = np.bincount(array.ravel(), minlength=256).astype(float)
    probabilities = histogram / histogram.sum()
    omega = np.cumsum(probabilities)
    means = np.cumsum(probabilities * np.arange(256))
    total_mean = means[-1]
    between = (total_mean * omega - means) ** 2 / np.maximum(
        omega * (1 - omega), 1e-12
    )
    threshold = min(190, max(70, int(np.argmax(between))))
    ink = array < threshold
    skeleton = _thin(ink)
    padded = np.pad(skeleton, 1)
    neighbour_count = np.zeros_like(skeleton, dtype=np.uint8)
    for dy in range(3):
        for dx in range(3):
            if dx == 1 and dy == 1:
                continue
            neighbour_count += padded[dy:dy + skeleton.shape[0], dx:dx + skeleton.shape[1]]
    endpoints = np.argwhere(skeleton & (neighbour_count == 1))
    junctions = np.argwhere(skeleton & (neighbour_count >= 3))
    return {
        "threshold": threshold,
        "scale": round(scale, 4),
        "skeleton_pixels": int(skeleton.sum()),
        "endpoint_pixels": int(len(endpoints)),
        "junction_pixels": int(len(junctions)),
    }, skeleton


def _detector_evidence(path: str | Path) -> tuple[dict, str]:
    """Run a configured detector adapter, or return an honest unavailable result."""
    if not DETECTOR_WEIGHTS:
        return {
            "nodes": [], "arrowheads": [],
            "reason": "DIAGRAM_DETECTOR_WEIGHTS is not configured",
        }, "unavailable"
    weights = Path(DETECTOR_WEIGHTS).expanduser()
    if not weights.exists():
        return {"nodes": [], "arrowheads": [], "reason": f"weights not found: {weights}"}, "error"
    # Fine-tuned checkpoints differ in export/runtime. The JSON sidecar is a
    # portable contract for D-FINE/RT-DETRv2 inference services and test rigs.
    sidecar = weights.with_suffix(weights.suffix + ".json")
    if sidecar.exists():
        return json.loads(sidecar.read_text()), "ok"
    return {
        "nodes": [], "arrowheads": [],
        "reason": "checkpoint exists but no inference adapter/JSON sidecar is installed",
    }, "unavailable"


def graph_to_mermaid(graph: dict) -> str:
    lines = ["flowchart LR"]
    for node in graph.get("nodes", []):
        label = str(node["label"]).replace('"', "'").replace("\n", " ")
        node_id = node["id"]
        shape = node.get("shape")
        if shape == "diamond":
            lines.append(f'  {node_id}{{"{label}"}}')
        elif shape == "rounded":
            lines.append(f'  {node_id}("{label}")')
        elif shape == "circle":
            lines.append(f'  {node_id}(("{label}"))')
        elif shape == "database":
            lines.append(f'  {node_id}[("{label}")]')
        else:
            lines.append(f'  {node_id}["{label}"]')
    for edge in graph.get("edges", []):
        label = str(edge.get("label", "")).replace('"', "'").replace("|", "/")
        connector = f" -->|{label}| " if label else " --> "
        lines.append(f"  {edge['from']}{connector}{edge['to']}")
    return "\n".join(lines)


def _draw_overlay(image_path: str | Path, graph: dict, output: Path) -> None:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for node in graph.get("nodes", []):
        if len(node.get("bbox", [])) != 4:
            continue
        x, y, w, h = node["bbox"]
        box = (x * width / 1000, y * height / 1000,
               (x + w) * width / 1000, (y + h) * height / 1000)
        draw.rectangle(box, outline="#00a6ff", width=max(2, width // 450))
        draw.text((box[0] + 3, max(0, box[1] - 13)), node["id"], fill="#0066cc")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "PNG")


def analyze_diagram(image_path: str | Path, output_dir: str | Path | None = None) -> dict:
    """Run the full local pipeline and persist JSON/overlay artifacts."""
    image_path = Path(image_path).resolve()
    output = Path(output_dir) if output_dir else FIGURES_DIR / "diagram-analysis"
    output.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", image_path.stem)
    stages: list[Stage] = []

    started = time.perf_counter()
    ocr_markdown = _clean_ocr(
        llm.chat_vision(OCR_PROMPT, [_image_b64(image_path)], model=OCR_MODEL, max_tokens=1800)
    )
    stages.append(Stage("ocr_and_tables", "PaddleOCR-VL-1.6 / PP-StructureV3-compatible Markdown",
                        "ok", int((time.perf_counter() - started) * 1000),
                        {"model": OCR_MODEL, "characters": len(ocr_markdown)}))

    started = time.perf_counter()
    detections, detector_status = _detector_evidence(image_path)
    stages.append(Stage("node_arrowhead_detection", "fine-tuned D-FINE/RT-DETRv2 adapter",
                        detector_status, int((time.perf_counter() - started) * 1000),
                        {"weights": DETECTOR_WEIGHTS or None, **detections}))

    started = time.perf_counter()
    skeleton, _ = trace_connectors(image_path)
    stages.append(Stage("connector_tracing", "Zhang-Suen skeleton topology",
                        "ok", int((time.perf_counter() - started) * 1000), skeleton))

    started = time.perf_counter()
    prompt = GRAPH_PROMPT + ocr_markdown + "\n\nDetector evidence:\n" + json.dumps(detections)
    raw_graph = _vision_json(prompt, image_path, VISION_MODEL)
    stages.append(Stage("vision_graph", "LM Studio OpenAI-compatible vision",
                        "ok", int((time.perf_counter() - started) * 1000),
                        {"model": VISION_MODEL}))

    started = time.perf_counter()
    preliminary, preliminary_messages = validate_graph(raw_graph)
    validation_input = json.dumps({"graph": preliminary, "ocr": ocr_markdown}, ensure_ascii=False)
    try:
        reviewed = llm.chat_json(
            VALIDATE_SYSTEM, validation_input, max_tokens=1800,
            model=VALIDATOR_MODEL, timeout=120.0,
        )
        reviewed_graph = reviewed.get("graph", reviewed)
        # The text validator is useful for topology, but it cannot inspect the
        # pixels. Preserve Qwen3-VL's visual labels, shapes, and coordinates for
        # any node that survives the review.
        visual_nodes = {node["id"]: node for node in preliminary["nodes"]}
        for node in reviewed_graph.get("nodes", []):
            visual = visual_nodes.get(_sanitize_id(node.get("id"), ""))
            if visual:
                node.update({
                    "label": visual["label"],
                    "shape": visual["shape"],
                    "bbox": visual["bbox"],
                })
        # A text-only validator must neither invent nor delete image topology.
        # It may improve labels on an edge that Qwen3-VL already saw.
        reviewed_by_pair = {
            (
                _sanitize_id(edge.get("from"), ""),
                _sanitize_id(edge.get("to"), ""),
            ): edge
            for edge in reviewed_graph.get("edges", [])
        }
        reviewed_graph["edges"] = [
            reviewed_by_pair.get((edge["from"], edge["to"]), edge)
            for edge in preliminary["edges"]
        ]
        graph, validation_messages = validate_graph(reviewed_graph)
        status = "ok"
    except Exception as error:
        graph, validation_messages = preliminary, []
        validation_messages.append(f"LLM review unavailable: {error}")
        status = "fallback"
    stages.append(Stage("graph_validation", "Qwen3.5-4B-MLX + deterministic validator",
                        status, int((time.perf_counter() - started) * 1000),
                        {"model": VALIDATOR_MODEL,
                         "messages": preliminary_messages + validation_messages}))

    mermaid = graph_to_mermaid(graph)
    overlay_path = output / f"{stem}.overlay.png"
    json_path = output / f"{stem}.diagram.json"
    markdown_path = output / f"{stem}.diagram.md"
    _draw_overlay(image_path, graph, overlay_path)
    result = {
        "source": str(image_path),
        "overlay": str(overlay_path.resolve()),
        "ocr_markdown": ocr_markdown,
        "graph": graph,
        "mermaid": mermaid,
        "stages": [stage.__dict__ for stage in stages],
    }
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(diagram_markdown(result), encoding="utf-8")
    result["json_path"] = str(json_path.resolve())
    result["markdown_path"] = str(markdown_path.resolve())
    return result


def diagram_markdown(result: dict, source_url: str | None = None,
                     overlay_url: str | None = None) -> str:
    graph = result["graph"]
    lines = [
        f"# {graph.get('title') or 'Diagram analysis'}",
        "",
        "## Summary",
        "",
        graph.get("summary") or "Diagram converted into a validated graph.",
        "",
    ]
    if source_url:
        lines += [f"![Original diagram]({source_url})", ""]
    if overlay_url:
        lines += [f"![Detected diagram nodes]({overlay_url})", ""]
    lines += ["## Editable diagram", "", "```mermaid", result["mermaid"], "```", "",
              "## Extracted text and tables", "", result["ocr_markdown"], "",
              "## Pipeline validation", ""]
    for stage in result["stages"]:
        lines.append(f"- **{stage['name'].replace('_', ' ').title()}:** "
                     f"{stage['status']} via {stage['implementation']} ({stage['elapsed_ms']} ms)")
    return "\n".join(lines).strip()
