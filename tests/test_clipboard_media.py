from __future__ import annotations

import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image


# O app usa pyautogui em tempo de execução, mas os testes rodam sem interface gráfica.
sys.modules.setdefault("pyautogui", types.SimpleNamespace())
sys.modules.setdefault("soundcard", types.SimpleNamespace())
app = importlib.import_module("app")


class ClipboardMediaTest(unittest.TestCase):
    def test_clipboard_image_is_converted_to_png_bytes(self) -> None:
        instance = app.VideoGeneratorApp.__new__(app.VideoGeneratorApp)
        image = Image.new("RGB", (2, 2), "red")

        with patch.object(app.ImageGrab, "grabclipboard", return_value=image):
            image_bytes = instance._clipboard_image_bytes()

        self.assertIsNotNone(image_bytes)
        self.assertTrue(image_bytes.startswith(b"\x89PNG"))

    def test_download_media_writes_clipboard_image_to_temp_file(self) -> None:
        instance = app.VideoGeneratorApp.__new__(app.VideoGeneratorApp)
        media_key = f"{app.CLIPBOARD_IMAGE_PREFIX}test.png"
        image_bytes = app.VideoGeneratorApp._png_bytes_from_image(Image.new("RGB", (2, 2), "blue"))
        instance.media_preview_bytes = {media_key: image_bytes}

        with tempfile.TemporaryDirectory() as tmp:
            output_path = instance._download_media(app.ScriptLine("frase", media_key), Path(tmp), 1)
            self.assertEqual(output_path.name, "media_001.png")
            self.assertEqual(output_path.read_bytes(), image_bytes)

    def test_only_empty_or_unresolved_pexels_media_needs_api_key(self) -> None:
        instance = app.VideoGeneratorApp.__new__(app.VideoGeneratorApp)

        self.assertTrue(instance._line_needs_pexels_key(""))
        self.assertTrue(instance._line_needs_pexels_key("https://www.pexels.com/photo/example-123456/"))
        self.assertFalse(instance._line_needs_pexels_key(f"{app.CLIPBOARD_IMAGE_PREFIX}test.png"))
        self.assertFalse(instance._line_needs_pexels_key("https://images.pexels.com/photos/1/test.jpeg"))
        self.assertFalse(instance._line_needs_pexels_key("https://example.com/media.png"))


if __name__ == "__main__":
    unittest.main()
