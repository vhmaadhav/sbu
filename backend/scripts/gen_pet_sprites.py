"""Generate placeholder pet sprites.

Real artwork drops into assets/pet/ and replaces these files. Nothing in the
pet reads anything but meta.json and the strips it names, so swapping the art
needs no code change.

Run with: python -m scripts.gen_pet_sprites
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw

from pet.models import Mood

FRAME_SIZE = 64
FRAMES = 4

FPS: dict[str, int] = {
    Mood.IDLE.value: 4,
    Mood.WALK.value: 10,
    Mood.CONCERNED.value: 6,
    Mood.SAD.value: 3,
    Mood.ALERT.value: 8,
}

BODY: dict[str, tuple[int, int, int, int]] = {
    Mood.IDLE.value: (122, 196, 140, 255),
    Mood.WALK.value: (122, 196, 140, 255),
    Mood.CONCERNED.value: (232, 196, 106, 255),
    Mood.SAD.value: (128, 150, 186, 255),
    Mood.ALERT.value: (226, 122, 106, 255),
}

# How far the mouth corners drop, per mood: a smile, a flat line, a frown.
MOUTH_CURVE: dict[str, int] = {
    Mood.IDLE.value: -4,
    Mood.WALK.value: -3,
    Mood.CONCERNED.value: 0,
    Mood.SAD.value: 5,
    Mood.ALERT.value: 2,
}


def _draw_frame(mood: str, index: int) -> Image.Image:
    frame = Image.new("RGBA", (FRAME_SIZE, FRAME_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(frame)

    bob = (0, 1, 2, 1)[index % FRAMES]
    top = 10 + bob
    draw.ellipse((10, top, 54, top + 44), fill=BODY[mood])

    eye_y = top + 16
    for eye_x in (23, 39):
        draw.ellipse((eye_x - 3, eye_y - 3, eye_x + 3, eye_y + 3), fill=(30, 30, 40, 255))

    mouth_y = top + 30
    drop = MOUTH_CURVE[mood]
    draw.line(
        [(24, mouth_y + drop), (32, mouth_y), (40, mouth_y + drop)],
        fill=(30, 30, 40, 255),
        width=2,
    )
    return frame


def generate(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    moods: dict[str, dict] = {}
    for mood in Mood:
        strip = Image.new("RGBA", (FRAME_SIZE * FRAMES, FRAME_SIZE), (0, 0, 0, 0))
        for index in range(FRAMES):
            strip.paste(_draw_frame(mood.value, index), (FRAME_SIZE * index, 0))
        filename = f"{mood.value}.png"
        strip.save(output_dir / filename)
        moods[mood.value] = {
            "frames": FRAMES,
            "fps": FPS[mood.value],
            "file": filename,
        }
    (output_dir / "meta.json").write_text(
        json.dumps({"frame_size": FRAME_SIZE, "moods": moods}, indent=2) + "\n"
    )
    return output_dir


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "assets" / "pet"
    print(f"wrote {generate(target)}")
