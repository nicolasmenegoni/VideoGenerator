import sys
import types
from pathlib import Path

from PIL import Image

sys.modules.setdefault("pyautogui", types.SimpleNamespace())
sys.modules.setdefault("soundcard", types.SimpleNamespace())

from app import VideoGeneratorApp


class Value:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


def test_logo_file_path_accepts_png_with_positive_size(tmp_path: Path) -> None:
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (10, 10), "red").save(logo)
    app = object.__new__(VideoGeneratorApp)
    app.logo_path = Value(str(logo))
    app.logo_size = Value("20")

    assert app._logo_file_path() == logo


def test_logo_file_path_rejects_zero_size(tmp_path: Path) -> None:
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (10, 10), "red").save(logo)
    app = object.__new__(VideoGeneratorApp)
    app.logo_path = Value(str(logo))
    app.logo_size = Value("0")

    assert app._logo_file_path() is None


def test_logo_overlay_expression_uses_selected_corner() -> None:
    app = object.__new__(VideoGeneratorApp)
    app.logo_position = Value("Canto inferior esquerdo")

    assert app._logo_overlay_expression() == ("36", "H-h-36")


def test_logo_preview_coordinates_uses_selected_corner() -> None:
    app = object.__new__(VideoGeneratorApp)
    app.logo_position = Value("Canto superior direito")

    assert app._logo_preview_coordinates(300, 500, 60, 40, 22) == (218, 22)
