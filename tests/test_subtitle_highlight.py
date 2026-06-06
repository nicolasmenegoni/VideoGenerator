from pathlib import Path
import sys
import types

# A automação de desktop exige display/áudio reais; os testes exercitam apenas helpers puros.
sys.modules.setdefault("pyautogui", types.SimpleNamespace())
sys.modules.setdefault("soundcard", types.SimpleNamespace())

from PIL import Image

from app import ScreenPoint, VideoGeneratorApp


class Value:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


def _subtitle_app() -> VideoGeneratorApp:
    app = object.__new__(VideoGeneratorApp)
    app.subtitle_font = Value("Arial Black")
    app.subtitle_color = Value("#FFFFFF")
    app.subtitle_highlight_color = Value("#FFD84D")
    app.subtitle_outline_color = Value("#000000")
    app.subtitle_background_color = Value("#000000")
    app.subtitle_background = Value("Sim")
    app.subtitle_position = Value("Baixo")
    return app


def test_subtitle_file_shows_full_sentence_and_highlights_current_word(tmp_path: Path) -> None:
    app = _subtitle_app()
    subtitle_file = tmp_path / "subtitle.ass"

    app._write_progressive_subtitle_file(subtitle_file, "Olá mundo bonito", 4.0, 3.0, 64, 1, 12)

    content = subtitle_file.read_text(encoding="utf-8")
    dialogue_lines = [line for line in content.splitlines() if line.startswith("Dialogue:")]

    assert len(dialogue_lines) == 4
    assert "Olá mundo bonito" not in dialogue_lines[0]  # A palavra destacada recebe tags ASS no meio da frase.
    assert "Olá" in dialogue_lines[0]
    assert "mundo" in dialogue_lines[0]
    assert "bonito" in dialogue_lines[0]
    assert "{\\c&H004DD8FF&}Olá{\\c&H00FFFFFF&}" in dialogue_lines[0]
    assert "{\\c&H004DD8FF&}mundo{\\c&H00FFFFFF&}" in dialogue_lines[1]
    assert dialogue_lines[-1].endswith("Olá mundo bonito")


def test_more_button_ranking_prefers_latest_response_near_composer() -> None:
    app = object.__new__(VideoGeneratorApp)
    image = Image.new("RGB", (1000, 900), "white")
    candidates = [ScreenPoint(980, 840), ScreenPoint(700, 610), ScreenPoint(650, 250)]

    ranked = app._rank_response_more_candidates(image, candidates)

    assert ranked[0] == ScreenPoint(700, 610)
