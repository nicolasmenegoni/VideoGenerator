import sys
import types
from io import BytesIO

from PIL import Image

# A automação de desktop exige dependências reais; os testes exercitam só helpers puros/API.
sys.modules.setdefault("pyautogui", types.SimpleNamespace())
sys.modules.setdefault("soundcard", types.SimpleNamespace())

from app import LOCAL_IMAGE_HEIGHT, LOCAL_IMAGE_WIDTH, VideoGeneratorApp


class Value:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class FakePipelineResult:
    def __init__(self, images: list[Image.Image]) -> None:
        self.images = images


class FakePipeline:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, **kwargs: object) -> FakePipelineResult:
        self.calls.append(kwargs)
        return FakePipelineResult([Image.new("RGB", (8, 12), "purple")])


def _decoded_png_size(image_bytes: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(image_bytes)) as image:
        return image.size


def test_clean_image_prompt_removes_wrappers_and_limits_size() -> None:
    raw = 'prompt: "cinematic vertical scene with China landmarks"\nextra words'

    prompt = VideoGeneratorApp._clean_image_prompt(raw)

    assert prompt == "cinematic vertical scene with China landmarks extra words"
    assert len(VideoGeneratorApp._clean_image_prompt("x" * 1300)) == 1200


def test_local_image_device_auto_prefers_cuda() -> None:
    app = object.__new__(VideoGeneratorApp)
    app.local_image_device = Value("Auto")
    torch_module = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: True),
        backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False)),
    )

    assert app._local_image_device(torch_module) == "cuda"


def test_local_image_device_cuda_requires_available_gpu() -> None:
    app = object.__new__(VideoGeneratorApp)
    app.local_image_device = Value("CUDA")
    torch_module = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: False),
        backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False)),
    )

    try:
        app._local_image_device(torch_module)
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("CUDA selecionado deveria avisar quando não há GPU disponível.")

    assert "CUDA está selecionada" in message
    assert "GPU NVIDIA" in message


def test_local_image_device_can_force_cpu() -> None:
    app = object.__new__(VideoGeneratorApp)
    app.local_image_device = Value("CPU")
    torch_module = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: True),
        backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: True)),
    )

    assert app._local_image_device(torch_module) == "cpu"


def test_local_ai_txt2img_uses_vertical_local_pipeline_and_returns_png(monkeypatch) -> None:
    app = object.__new__(VideoGeneratorApp)
    app.local_image_steps = Value("12")
    fake_pipeline = FakePipeline()
    monkeypatch.setattr(app, "_load_local_image_pipeline", lambda: fake_pipeline)

    image_bytes = app._local_ai_txt2img("a cinematic prompt")

    assert _decoded_png_size(image_bytes) == (8, 12)
    assert fake_pipeline.calls[0]["prompt"] == "a cinematic prompt"
    assert fake_pipeline.calls[0]["width"] == LOCAL_IMAGE_WIDTH
    assert fake_pipeline.calls[0]["height"] == LOCAL_IMAGE_HEIGHT
    assert fake_pipeline.calls[0]["num_inference_steps"] == 12
    assert "watermark" in fake_pipeline.calls[0]["negative_prompt"]


def test_local_ai_txt2img_wraps_generation_errors(monkeypatch) -> None:
    app = object.__new__(VideoGeneratorApp)
    app.local_image_steps = Value("30")

    def failing_pipeline(**_kwargs: object) -> object:
        raise RuntimeError("out of memory")

    monkeypatch.setattr(app, "_load_local_image_pipeline", lambda: failing_pipeline)

    try:
        app._local_ai_txt2img("a cinematic prompt")
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("A geração local deveria falhar no teste.")

    assert "A IA local não conseguiu renderizar a imagem" in message
    assert "Detalhe técnico" in message
