import base64
import sys
import types

# A automação de desktop exige dependências reais; os testes exercitam só helpers puros/API.
sys.modules.setdefault("pyautogui", types.SimpleNamespace())
sys.modules.setdefault("soundcard", types.SimpleNamespace())

import requests

from app import VideoGeneratorApp


class Value:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self) -> dict:
        return self.payload


def test_clean_image_prompt_removes_wrappers_and_limits_size() -> None:
    raw = 'prompt: "cinematic vertical scene with China landmarks"\nextra words'

    prompt = VideoGeneratorApp._clean_image_prompt(raw)

    assert prompt == "cinematic vertical scene with China landmarks extra words"
    assert len(VideoGeneratorApp._clean_image_prompt("x" * 1300)) == 1200


def test_primary_civitai_model_file_prefers_model_file() -> None:
    version = {
        "files": [
            {"name": "preview.jpeg", "type": "Image", "metadata": {"format": "JPEG"}},
            {"name": "model.safetensors", "type": "Model", "metadata": {"format": "SafeTensor"}},
        ]
    }

    file_info = VideoGeneratorApp._primary_civitai_model_file(version)

    assert file_info["name"] == "model.safetensors"


def test_forge_txt2img_sends_vertical_payload_and_decodes_image(monkeypatch) -> None:
    app = object.__new__(VideoGeneratorApp)
    app.forge_api_url = Value("http://forge.local/")
    calls = []
    image_bytes = b"fake-png"

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse({"images": [base64.b64encode(image_bytes).decode("ascii")]})

    monkeypatch.setattr("app.requests.post", fake_post)

    result = app._forge_txt2img("a cinematic prompt", checkpoint_name="model.safetensors")

    assert result == image_bytes
    assert calls[0]["url"] == "http://forge.local/sdapi/v1/txt2img"
    assert calls[0]["json"]["width"] == 1080
    assert calls[0]["json"]["height"] == 1920
    assert calls[0]["json"]["override_settings"]["sd_model_checkpoint"] == "model.safetensors"


def test_assert_forge_api_available_shows_friendly_connection_message(monkeypatch) -> None:
    app = object.__new__(VideoGeneratorApp)
    app.forge_api_url = Value("http://127.0.0.1:7860")

    def fake_get(url: str, timeout: int) -> FakeResponse:
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr("app.requests.get", fake_get)

    try:
        app._assert_forge_api_available()
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("A conexão com Forge deveria falhar no teste.")

    assert "Não consegui conectar ao Forge WebUI" in message
    assert "--api" in message
    assert "http://127.0.0.1:7860" in message


def test_forge_txt2img_wraps_connection_errors(monkeypatch) -> None:
    app = object.__new__(VideoGeneratorApp)
    app.forge_api_url = Value("http://127.0.0.1:7860")

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr("app.requests.post", fake_post)

    try:
        app._forge_txt2img("a cinematic prompt")
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("A geração deveria falhar quando o Forge está offline.")

    assert "Não consegui conectar ao Forge WebUI" in message
    assert "Detalhe técnico" in message
