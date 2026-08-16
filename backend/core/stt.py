"""Speech-to-text: Silero VAD segmentation + Moonshine ONNX transcription."""
from functools import lru_cache
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from core.config import STT_MODEL

SAMPLE_RATE = 16000
MAX_SEGMENT_S = 30.0  # Moonshine works best on short clips; VAD keeps us under this


@lru_cache(maxsize=1)
def _vad():
    from silero_vad import load_silero_vad
    return load_silero_vad()


@lru_cache(maxsize=1)
def _moonshine():
    from moonshine_onnx import MoonshineOnnxModel, load_tokenizer
    return MoonshineOnnxModel(model_name=STT_MODEL), load_tokenizer()


def _speech_segments(audio: np.ndarray) -> list[tuple[float, float]]:
    import torch
    from silero_vad import get_speech_timestamps
    ts = get_speech_timestamps(torch.from_numpy(audio), _vad(), sampling_rate=SAMPLE_RATE)
    segs = [(t["start"] / SAMPLE_RATE, t["end"] / SAMPLE_RATE) for t in ts]

    merged: list[list[float]] = []
    for start, end in segs:
        if merged and end - merged[-1][0] <= MAX_SEGMENT_S and start - merged[-1][1] < 1.0:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    # split anything still too long
    out: list[tuple[float, float]] = []
    for start, end in merged:
        while end - start > MAX_SEGMENT_S:
            out.append((start, start + MAX_SEGMENT_S))
            start += MAX_SEGMENT_S
        out.append((start, end))
    return out


def transcribe(wav_path: str) -> list[dict]:
    """Transcribe a 16kHz mono WAV. Returns [{start, end, text}]."""
    audio, sr = sf.read(wav_path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    assert sr == SAMPLE_RATE, f"expected {SAMPLE_RATE}Hz audio, got {sr}"

    model, tokenizer = _moonshine()
    results = []
    for start, end in _speech_segments(audio):
        clip = audio[int(start * sr):int(end * sr)]
        if len(clip) < sr * 0.3:
            continue
        tokens = model.generate(clip[np.newaxis, :])
        text = tokenizer.decode_batch(tokens)[0].strip()
        if text:
            results.append({"start": round(start, 2), "end": round(end, 2), "text": text})
    return results


def transcribe_media(media_path: str) -> list[dict]:
    """Convert browser/media audio to 16 kHz mono WAV, then transcribe it."""
    wav_path = Path(tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name)
    try:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", media_path, "-ac", "1", "-ar", str(SAMPLE_RATE), "-vn", str(wav_path),
            ],
            check=True,
            capture_output=True,
        )
        return transcribe(str(wav_path))
    finally:
        wav_path.unlink(missing_ok=True)
