"""Audiobook generation: notes -> narration script (LLM) -> Kokoro TTS -> WAV."""
import re
import time
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import soundfile as sf

from core import llm
from core.config import AUDIOBOOKS_DIR, KOKORO_VOICE

SCRIPT_SYSTEM = (
    "Rewrite the following study notes as a flowing narration script for an audiobook. "
    "Plain spoken prose only: no markdown, no headings, no bullet symbols, no source "
    "references. Explain naturally, as a good teacher would. Output only the script."
)

SAMPLE_RATE = 24000
KOKORO_REPO = "hexgrad/Kokoro-82M"


def _cached_asset(filename: str) -> str:
    """Resolve a Kokoro asset locally without making a network request."""
    from huggingface_hub import hf_hub_download

    try:
        return hf_hub_download(
            repo_id=KOKORO_REPO,
            filename=filename,
            local_files_only=True,
        )
    except Exception as error:
        raise RuntimeError(
            f"Kokoro asset {filename!r} is not cached locally. "
            "Download hexgrad/Kokoro-82M once before generating an audiobook."
        ) from error


@lru_cache(maxsize=1)
def _pipeline():
    import spacy
    import torch
    from kokoro import KModel, KPipeline

    config = _cached_asset("config.json")
    weights = _cached_asset("kokoro-v1_0.pth")
    model = KModel(repo_id=KOKORO_REPO, config=config, model=weights).eval()

    if spacy.util.is_package("en_core_web_sm"):
        pipeline = KPipeline(lang_code="a", repo_id=KOKORO_REPO, model=model)
    else:
        # Misaki otherwise calls spacy.cli.download() at runtime. Use Kokoro's
        # bundled eSpeak phonemizer so audiobook generation remains offline.
        from misaki.espeak import EspeakFallback

        fallback = EspeakFallback(british=False)
        pipeline = KPipeline(lang_code="e", repo_id=KOKORO_REPO, model=model)
        pipeline.g2p = lambda text: fallback(SimpleNamespace(text=text))

    voice_paths = [
        _cached_asset(f"voices/{voice.strip()}.pt")
        for voice in KOKORO_VOICE.split(",")
        if voice.strip()
    ]
    voices = [torch.load(path, weights_only=True) for path in voice_paths]
    voice = voices[0] if len(voices) == 1 else torch.mean(torch.stack(voices), dim=0)
    return pipeline, voice


def notes_to_script(notes_md: str) -> str:
    parts = []
    for i in range(0, len(notes_md), 4000):
        parts.append(llm.chat(SCRIPT_SYSTEM, notes_md[i:i + 4000], max_tokens=1500))
    return "\n\n".join(parts)


def synthesize(script: str, name: str) -> Path:
    pipeline, voice = _pipeline()
    audio_parts = [audio for _, _, audio in pipeline(script, voice=voice)]
    audio = np.concatenate([np.asarray(a) for a in audio_parts])
    safe = re.sub(r"[^\w\-]+", "_", name).strip("_") or "audiobook"
    out = AUDIOBOOKS_DIR / f"{safe}_{int(time.time())}.wav"
    sf.write(out, audio, SAMPLE_RATE)
    return out


def generate(notes_md: str, name: str) -> Path:
    return synthesize(notes_to_script(notes_md), name)
