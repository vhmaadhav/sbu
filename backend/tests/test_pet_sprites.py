import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pet.models import Mood
from scripts.gen_pet_sprites import FRAME_SIZE, FRAMES, generate


class GenerateTests(unittest.TestCase):
    def test_writes_one_strip_per_mood_with_the_right_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            output = generate(Path(directory))
            for mood in Mood:
                strip = output / f"{mood.value}.png"
                self.assertTrue(strip.exists(), f"missing {strip.name}")
                with Image.open(strip) as image:
                    self.assertEqual(image.size, (FRAME_SIZE * FRAMES, FRAME_SIZE))
                    self.assertEqual(image.mode, "RGBA")

    def test_meta_describes_every_mood(self):
        with tempfile.TemporaryDirectory() as directory:
            output = generate(Path(directory))
            meta = json.loads((output / "meta.json").read_text())
        self.assertEqual(meta["frame_size"], FRAME_SIZE)
        for mood in Mood:
            entry = meta["moods"][mood.value]
            self.assertEqual(entry["frames"], FRAMES)
            self.assertEqual(entry["file"], f"{mood.value}.png")
            self.assertGreater(entry["fps"], 0)

    def test_frames_differ_so_the_animation_is_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            output = generate(Path(directory))
            with Image.open(output / "idle.png") as image:
                first = image.crop((0, 0, FRAME_SIZE, FRAME_SIZE)).tobytes()
                second = image.crop((FRAME_SIZE, 0, FRAME_SIZE * 2, FRAME_SIZE)).tobytes()
        self.assertNotEqual(first, second)

    def test_moods_are_visually_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            output = generate(Path(directory))
            with Image.open(output / "idle.png") as idle, Image.open(output / "sad.png") as sad:
                self.assertNotEqual(idle.tobytes(), sad.tobytes())


class CommittedAssetTests(unittest.TestCase):
    def test_the_repository_ships_generated_sprites(self):
        assets = Path(__file__).resolve().parent.parent / "assets" / "pet"
        self.assertTrue(
            (assets / "meta.json").exists(),
            "run: uv run --python 3.12 python -m scripts.gen_pet_sprites",
        )
        for mood in Mood:
            self.assertTrue((assets / f"{mood.value}.png").exists())


if __name__ == "__main__":
    unittest.main()
