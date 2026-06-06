from io import BytesIO
from pathlib import Path
import sys
import types

from PIL import Image

# A automação de mouse exige DISPLAY no Linux; nos testes dos helpers de mídia usamos um stub.
sys.modules.setdefault("pyautogui", types.SimpleNamespace())
sys.modules.setdefault("soundcard", types.SimpleNamespace())

from app import VideoGeneratorApp


def _decoded_png_size(image_bytes: bytes) -> tuple[int, int]:
    # Valida o PNG produzido pelos helpers sem precisar abrir a interface Tk.
    with Image.open(BytesIO(image_bytes)) as image:
        return image.size


def test_clipboard_image_object_is_converted_to_png_bytes() -> None:
    image = Image.new("RGB", (12, 8), "red")

    image_bytes = VideoGeneratorApp._clipboard_image_bytes_from_value(image)

    assert image_bytes is not None
    assert _decoded_png_size(image_bytes) == (12, 8)


def test_clipboard_file_list_uses_first_supported_image(tmp_path: Path) -> None:
    unsupported = tmp_path / "documento.txt"
    unsupported.write_text("não é imagem", encoding="utf-8")
    image_path = tmp_path / "copiada.png"
    Image.new("RGBA", (5, 7), "blue").save(image_path)

    image_bytes = VideoGeneratorApp._clipboard_image_bytes_from_value([unsupported, image_path])

    assert image_bytes is not None
    assert _decoded_png_size(image_bytes) == (5, 7)


def test_local_media_path_rejects_remote_urls_and_accepts_images(tmp_path: Path) -> None:
    image_path = tmp_path / "preview.webp"
    Image.new("RGB", (3, 4), "green").save(image_path)

    assert VideoGeneratorApp._local_media_path(str(image_path)) == image_path
    assert VideoGeneratorApp._local_media_path("https://example.com/preview.webp") is None
