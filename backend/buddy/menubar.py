"""Overlay buddy: a macOS menu-bar app for quick capture.

Everything it saves lands in the inbox/ folder; the Streamlit app's background
worker picks it up from there. Image captures therefore use the same automatic
diagram detection and Mermaid extraction as web uploads. Run with:
``python -m buddy.menubar``.
"""
import subprocess
import time
import webbrowser
from pathlib import Path

import rumps

from core.config import INBOX_DIR


def _stamp(prefix: str, ext: str) -> Path:
    return INBOX_DIR / f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}.{ext}"


class BuddyApp(rumps.App):
    def __init__(self):
        super().__init__("📚", quit_button=rumps.MenuItem("Quit Study Buddy"))
        self.record_item = rumps.MenuItem("🎙️ Start recording", callback=self.toggle_recording)
        self.menu = [
            rumps.MenuItem("📸 Capture screenshot", callback=self.screenshot),
            rumps.MenuItem("📋 Save clipboard", callback=self.clipboard),
            self.record_item,
            rumps.MenuItem("📂 Add file…", callback=self.add_file),
            None,
            rumps.MenuItem("🏠 Open Study Buddy", callback=self.open_home),
        ]
        self._recorder = None

    def screenshot(self, _):
        out = _stamp("screenshot", "png")
        subprocess.run(["screencapture", "-i", str(out)])
        if out.exists():
            rumps.notification(
                "Study Buddy",
                "Screenshot queued",
                f"{out.name} · checking for a diagram",
            )

    def clipboard(self, _):
        import AppKit
        pb = AppKit.NSPasteboard.generalPasteboard()
        png = pb.dataForType_(AppKit.NSPasteboardTypePNG)
        if png:
            out = _stamp("clipboard", "png")
            png.writeToFile_atomically_(str(out), True)
            rumps.notification(
                "Study Buddy",
                "Clipboard image queued",
                f"{out.name} · checking for a diagram",
            )
            return
        text = pb.stringForType_(AppKit.NSPasteboardTypeString)
        if text and text.strip():
            out = _stamp("clipboard", "txt")
            out.write_text(text)
            rumps.notification("Study Buddy", "Clipboard text saved", out.name)
        else:
            rumps.notification("Study Buddy", "Clipboard is empty", "")

    def toggle_recording(self, _):
        if self._recorder is None:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        import sounddevice as sd
        import soundfile as sf

        path = _stamp("recording", "wav")
        tmp = path.with_suffix(".part")
        file = sf.SoundFile(tmp, mode="w", samplerate=16000, channels=1)

        def callback(indata, frames, t, status):
            file.write(indata)

        stream = sd.InputStream(samplerate=16000, channels=1, callback=callback)
        stream.start()
        self._recorder = (stream, file, tmp, path)
        self.record_item.title = "⏹ Stop recording"
        self.title = "🔴"

    def _stop_recording(self):
        stream, file, tmp, path = self._recorder
        stream.stop(); stream.close(); file.close()
        tmp.rename(path)  # only now does the ingest worker see a complete file
        self._recorder = None
        self.record_item.title = "🎙️ Start recording"
        self.title = "📚"
        rumps.notification("Study Buddy", "Recording saved", path.name)

    def add_file(self, _):
        script = 'POSIX path of (choose file with prompt "Add to Study Buddy")'
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        src = result.stdout.strip()
        if src:
            import shutil
            shutil.copy2(src, INBOX_DIR / Path(src).name)
            rumps.notification("Study Buddy", "File queued", Path(src).name)

    def open_home(self, _):
        webbrowser.open("http://localhost:3000")


if __name__ == "__main__":
    BuddyApp().run()
