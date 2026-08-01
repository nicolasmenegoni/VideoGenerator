from __future__ import annotations

import html
import json
import queue
import time
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import warnings
import wave
import requests
import torch
from io import BytesIO
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, Button, Canvas, Entry, Frame, Label, StringVar, Text, Tk, Toplevel, filedialog, messagebox, ttk
from tkinter import font as tkfont

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageGrab, ImageTk
import soundcard as sc
import soundfile as sf
import sounddevice as sd

KOKORO_AVAILABLE = False
try:
    from kokoro import KModel, KPipeline
    KOKORO_AVAILABLE = True
except ImportError:
    KModel = None
    KPipeline = None

APP_TITLE = "VideoGenerator"
CONFIG_FILE = Path.home() / ".videogenerator_config.json"
VIDEO_SIZE = "1080:1920"
FPS = "30"
GROQ_MODEL = "llama-3.3-70b-versatile"
QWEN_URL = "https://chat.qwen.ai/"
DEFAULT_SCRIPT_TEXT = "Hoje vamos falar sobre a China.\nEsse país é incrível.\nVamos te provar."
CLIPBOARD_MEDIA_DIR = Path.home() / ".videogenerator_media"
LOGO_MEDIA_DIR = Path.home() / ".videogenerator_logos"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
LOCAL_MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}


@dataclass
class ScriptLine:
    text: str
    media_url: str = ""


@dataclass
class ScreenPoint:
    x: int
    y: int


@dataclass
class ScreenBounds:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center(self) -> ScreenPoint:
        return ScreenPoint(self.left + self.width // 2, self.top + self.height // 2)


@dataclass
class WindowCapture:
    image: Any
    offset_x: int
    offset_y: int


class VideoGeneratorApp:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1040x760")
        self.root.minsize(900, 660)
        self.root.configure(bg="#f6f7fb")

        self.pexels_key = StringVar()
        self.groq_key = StringVar()
        self.logo_path = StringVar(value="")
        self.logo_position = StringVar(value="Canto superior direito")
        self.logo_size = StringVar(value="20")
        self.video_title = StringVar(value="video_gerado")
        self.output_dir = StringVar(value=str(Path.home() / "Videos"))
        self.video_extra_after_audio = StringVar(value="1")
        self.subtitle_enabled = StringVar(value="Sim")
        self.subtitle_position = StringVar(value="Baixo")
        self.subtitle_color = StringVar(value="#FFFFFF")
        self.subtitle_highlight_color = StringVar(value="#FFD84D")
        self.subtitle_size = StringVar(value="64")
        self.subtitle_background = StringVar(value="Sim")
        self.subtitle_background_color = StringVar(value="#000000")
        self.subtitle_outline_color = StringVar(value="#000000")
        self.subtitle_font = StringVar(value="Arial Black")
        self.subtitle_preview_text = StringVar(value="Hoje vamos falar sobre a China.")
        self.qwen_shortcut = StringVar(value="alt+c")
        self.qwen_response_wait = StringVar(value="8")
        self.qwen_send_wait = StringVar(value="1")
        self.qwen_menu_wait = StringVar(value="1")
        self.qwen_menu_x = StringVar(value="0")
        self.qwen_menu_y = StringVar(value="0")
        self.qwen_input_x = StringVar(value="0")
        self.qwen_input_y = StringVar(value="0")
        self.qwen_send_x = StringVar(value="0")
        self.qwen_send_y = StringVar(value="0")
        self.qwen_read_x = StringVar(value="0")
        self.qwen_read_y = StringVar(value="0")
        self.qwen_record_extra = StringVar(value="2")
        
        # Novas variáveis para TTS local com Kokoro e XTTS
        self.tts_language = StringVar(value="pt-br")
        self.tts_voice_ref_path = StringVar(value="")
        self.tts_model_loaded = False
        self.tts_engine = StringVar(value="kokoro")  # kokoro ou xtts
        self.kokoro_model: KModel | None = None
        self.kokoro_pipeline: KPipeline | None = None
        self.xtts_model = None
        
        self.music_path = StringVar(value="")
        self.music_volume = StringVar(value="20")
        self.status_text = StringVar(value="Pronto.")
        self.progress_text = StringVar(value="")
        self.qwen_window_ready = False
        self.media_preview_images: dict[str, ImageTk.PhotoImage] = {}
        self.media_preview_bytes: dict[str, bytes] = {}
        self.media_preview_loading: set[str] = set()
        self.media_preview_failed: set[str] = set()
        self.logo_preview_image: ImageTk.PhotoImage | None = None
        self.script_text_value = DEFAULT_SCRIPT_TEXT
        self.script_prompt_value = StringVar(value="")
        self.lines: list[ScriptLine] = []
        self.used_media_urls: set[str] = set()
        self.message_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.tabs: dict[str, Frame] = {}
        self.nav_buttons: dict[str, Button] = {}
        self.active_tab = ""

        self._configure_style()
        self._load_config()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(120, self._process_queue)

    def run(self) -> None:
        self.root.mainloop()

    def _configure_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Muted.TLabel", background="#ffffff", foreground="#657084", font=("Segoe UI", 9))
        style.configure("Title.TLabel", background="#ffffff", foreground="#111827", font=("Segoe UI", 17, "bold"))
        style.configure("TLabel", background="#ffffff", foreground="#111827", font=("Segoe UI", 10))
        style.configure("Horizontal.TProgressbar", troughcolor="#edf0f7", background="#5b6cff")

    def _build_ui(self) -> None:
        shell = Frame(self.root, bg="#f6f7fb", padx=24, pady=20)
        shell.pack(fill=BOTH, expand=True)

        header = Frame(shell, bg="#f6f7fb")
        header.pack(fill=X, pady=(0, 12))
        Label(header, text="VideoGenerator", bg="#f6f7fb", fg="#111827", font=("Segoe UI", 24, "bold")).pack(anchor="w")
        Label(header, text="Gere vídeos verticais com Qwen, Pexels e legendas em poucos cliques.", bg="#f6f7fb", fg="#657084", font=("Segoe UI", 10)).pack(anchor="w")

        nav = Frame(shell, bg="#eef1f8", padx=6, pady=6)
        nav.pack(fill=X, pady=(0, 12))
        self._add_nav_button(nav, "apis", "APIs")
        self._add_nav_button(nav, "roteiro", "Roteiro")
        self._add_nav_button(nav, "video", "Video")
        self._add_nav_button(nav, "legendas", "Legendas")
        self._add_nav_button(nav, "logo", "Logo")
        self._add_nav_button(nav, "audio", "Audio")
        self._add_nav_button(nav, "musica", "Musica")

        self.content = Frame(shell, bg="#ffffff")
        self.content.pack(fill=BOTH, expand=True)

        self.tabs["apis"] = Frame(self.content, bg="#ffffff", padx=24, pady=24)
        self.tabs["roteiro"] = Frame(self.content, bg="#ffffff", padx=24, pady=24)
        self.tabs["video"] = Frame(self.content, bg="#ffffff", padx=24, pady=24)
        self.tabs["legendas"] = Frame(self.content, bg="#ffffff", padx=24, pady=24)
        self.tabs["logo"] = Frame(self.content, bg="#ffffff", padx=24, pady=24)
        self.tabs["audio"] = Frame(self.content, bg="#ffffff", padx=24, pady=24)
        self.tabs["musica"] = Frame(self.content, bg="#ffffff", padx=24, pady=24)

        self._build_api_tab(self.tabs["apis"])
        self._build_script_tab(self.tabs["roteiro"])
        self._build_video_tab(self.tabs["video"])
        self._build_subtitles_tab(self.tabs["legendas"])
        self._build_logo_tab(self.tabs["logo"])
        self._build_audio_tab(self.tabs["audio"])
        self._build_music_tab(self.tabs["musica"])
        self._refresh_lines()
        self._show_tab("roteiro")

        bottom = Frame(shell, bg="#f6f7fb", pady=12)
        bottom.pack(fill=X)
        self.progress = ttk.Progressbar(bottom, mode="determinate", style="Horizontal.TProgressbar")
        self.progress.pack(fill=X, pady=(0, 10))
        Button(bottom, text="Gerar vídeo", command=self._start_generation, bg="#5b6cff", fg="#ffffff", activebackground="#4657e8", activeforeground="#ffffff", relief="flat", padx=18, pady=13, font=("Segoe UI", 13, "bold")).pack(fill=X)

        footer = Frame(shell, bg="#f6f7fb")
        footer.pack(fill=X, pady=(8, 0))
        Label(footer, textvariable=self.status_text, bg="#f6f7fb", fg="#374151", font=("Segoe UI", 10)).pack(side=LEFT)
        Label(footer, textvariable=self.progress_text, bg="#f6f7fb", fg="#657084", font=("Segoe UI", 10)).pack(side=RIGHT)

    def _add_nav_button(self, parent: Frame, tab_id: str, label: str) -> None:
        button = Button(
            parent,
            text=label,
            command=lambda: self._show_tab(tab_id),
            bd=0,
            relief="flat",
            padx=18,
            pady=9,
            font=("Segoe UI", 10, "bold"),
        )
        button.pack(side=LEFT, padx=(0, 6))
        self.nav_buttons[tab_id] = button

    def _show_tab(self, tab_id: str) -> None:
        if tab_id == "video":
            self._refresh_lines()
        for frame in self.tabs.values():
            frame.pack_forget()
        self.tabs[tab_id].pack(fill=BOTH, expand=True)
        self.active_tab = tab_id
        for key, button in self.nav_buttons.items():
            if key == tab_id:
                button.configure(bg="#5b6cff", fg="#ffffff", activebackground="#4657e8", activeforeground="#ffffff")
            else:
                button.configure(bg="#ffffff", fg="#374151", activebackground="#ffffff", activeforeground="#374151")

    def _build_api_tab(self, parent: Frame) -> None:
        ttk.Label(parent, text="Chaves de API", style="Title.TLabel").pack(anchor="w")
        ttk.Label(parent, text="As chaves e endpoints ficam salvos localmente no seu usuário do Windows.", style="Muted.TLabel").pack(anchor="w", pady=(4, 22))

        self._labeled_entry(parent, "Pexels API", self.pexels_key, show="*")
        self._labeled_entry(parent, "Groq API", self.groq_key, show="*")
        Button(parent, text="Salvar chaves", command=self._save_config, bg="#111827", fg="#ffffff", activebackground="#2a3446", activeforeground="#ffffff", relief="flat", padx=18, pady=10, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(16, 0))

    def _build_script_tab(self, parent: Frame) -> None:
        top = Frame(parent, bg="#ffffff")
        top.pack(fill=X)
        ttk.Label(top, text="Roteiro", style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, text="Digite o título e depois uma frase por linha. O título será usado como nome do arquivo .mp4.", style="Muted.TLabel").pack(anchor="w", pady=(4, 12))

        Label(parent, text="Titulo", bg="#ffffff", fg="#111827", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        Entry(parent, textvariable=self.video_title, bd=0, bg="#f3f5fb", fg="#111827", insertbackground="#111827", font=("Segoe UI", 12)).pack(fill=X, ipady=10, pady=(6, 14))

        Label(parent, text="Prompt para o roteiro (opcional)", bg="#ffffff", fg="#111827", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        Entry(parent, textvariable=self.script_prompt_value, bd=0, bg="#f3f5fb", fg="#111827", insertbackground="#111827", font=("Segoe UI", 12)).pack(fill=X, ipady=10, pady=(6, 14))

        actions = Frame(parent, bg="#ffffff", pady=12)
        actions.pack(fill=X)
        Button(actions, text="Atualizar roteiro", command=self._refresh_lines, bg="#eef1ff", fg="#27319f", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        Button(actions, text="Gerar roteiro", command=self._start_script_generation, bg="#5b6cff", fg="#ffffff", activebackground="#4657e8", activeforeground="#ffffff", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(side=LEFT, padx=(10, 0))

        self.script_text = Text(parent, height=12, wrap="word", bd=0, bg="#f3f5fb", fg="#111827", insertbackground="#111827", font=("Segoe UI", 11), padx=14, pady=12)
        self.script_text.pack(fill=BOTH, expand=True)
        self.script_text.insert("1.0", self.script_text_value)

    def _start_script_generation(self) -> None:
        title = self.video_title.get().strip()
        if not title:
            messagebox.showerror(APP_TITLE, "Informe um título na aba Roteiro para gerar o roteiro.")
            return
        if not self.groq_key.get().strip():
            messagebox.showerror(APP_TITLE, "Informe a chave de API do Groq na aba APIs.")
            self._show_tab("apis")
            return
        self._save_config(show_status=False)
        self.progress.configure(value=0, maximum=1)
        self.progress_text.set("Gerando roteiro...")
        self.status_text.set("Gerando roteiro com Groq...")
        prompt = self.script_prompt_value.get().strip()
        threading.Thread(target=self._generate_script_worker, args=(title, prompt), daemon=True).start()

    def _generate_script_worker(self, title: str, prompt: str = "") -> None:
        try:
            lines = self._groq_script_lines(title, prompt)
            self.root.after(0, lambda: self._apply_generated_script(lines))
            self.message_queue.put(("done", "Roteiro gerado com Groq e salvo no app."))
        except Exception as exc:  # noqa: BLE001 - show desktop-friendly error
            self.message_queue.put(("error", str(exc)))

    def _apply_generated_script(self, lines: list[str]) -> None:
        script_text = "\n".join(lines)
        self.script_text.delete("1.0", END)
        self.script_text.insert("1.0", script_text)
        self._refresh_lines()
        self.progress.configure(value=1)

    def _groq_script_lines(self, title: str, prompt: str = "") -> list[str]:
        base_prompt = (
            "Crie um roteiro curto para um vídeo vertical em português do Brasil com base no título informado. "
            "O roteiro deve ter de 6 a 10 frases curtas, naturais para narração em voz alta, com gancho no começo e fechamento no final. "
            "Cada frase deve funcionar como uma cena separada do vídeo. "
            "Não use numeração, marcadores, emojis, markdown, aspas, chaves, colchetes ou título dentro das frases. "
            "Responda somente com as frases finais, uma por linha, sem JSON e sem texto extra.\n\n"
            f"Título: {title}"
        )
        if prompt:
            base_prompt = f"{prompt}\n\n{base_prompt}"
        content = self._groq_chat_content(
            messages=[
                {"role": "system", "content": "Você cria roteiros curtos para vídeos verticais em português do Brasil."},
                {"role": "user", "content": base_prompt},
            ],
            temperature=0.7,
            max_tokens=900,
        )
        try:
            data = self._json_object_from_text(content)
        except json.JSONDecodeError:
            raw_lines = self._script_lines_from_text(content)
        else:
            raw_lines = data.get("lines")
            if not isinstance(raw_lines, list):
                raw_lines = self._script_lines_from_text(content)
        lines = [self._clean_script_line(line) for line in raw_lines]
        lines = [line for line in lines if line]
        if not lines:
            raise RuntimeError("O Groq retornou um roteiro vazio.")
        return lines

    def _groq_chat_content(self, messages: list[dict[str, str]], temperature: float, max_tokens: int, timeout: int = 45) -> str:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.groq_key.get().strip()}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=timeout,
        )
        if response.status_code >= 400:
            detail = response.text.strip()
            try:
                error = response.json().get("error", {})
                detail = error.get("message") or detail
            except Exception:
                pass
            raise RuntimeError(f"Erro da API do Groq ({response.status_code}): {detail}")
        return response.json()["choices"][0]["message"]["content"]

    @staticmethod
    def _json_object_from_text(content: str) -> dict[str, Any]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, flags=re.DOTALL)
            if not match:
                raise
            data = json.loads(match.group(0))
        if not isinstance(data, dict):
            raise RuntimeError("O Groq não retornou um objeto JSON.")
        return data

    @staticmethod
    def _script_lines_from_text(content: str) -> list[str]:
        text = content.strip().replace("\\n", "\n")
        lines_match = re.search(r'"lines"\s*:\s*\[(.*?)\]\s*\}?\s*$', text, flags=re.DOTALL)
        if lines_match:
            text = lines_match.group(1).strip()
        text = re.sub(r'^\{?\s*"lines"\s*:\s*\[?', "", text).strip()
        text = re.sub(r'\]?\s*\}?$', "", text).strip()
        raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(raw_lines) <= 1 and "," in text:
            raw_lines = [line.strip() for line in text.split(",") if line.strip()]
        return raw_lines

    @staticmethod
    def _clean_script_line(line: Any) -> str:
        text = str(line).strip()
        text = re.sub(r'^\{?\s*"?lines"?\s*:\s*\[?', "", text).strip()
        text = re.sub(r"^[-•*\d.)\s]+", "", text).strip()
        text = text.strip(" \t\r\n,[]{}\"'")
        return " ".join(text.split())

    def _build_video_tab(self, parent: Frame) -> None:
        top = Frame(parent, bg="#ffffff")
        top.pack(fill=X)
        ttk.Label(top, text="Video", style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, text="Escolha o link do Pexels para cada frase ou use o Groq para encontrar vídeos que combinem com a frase e o contexto do roteiro.", style="Muted.TLabel").pack(anchor="w", pady=(4, 12))

        actions = Frame(parent, bg="#ffffff")
        actions.pack(fill=X, pady=(0, 12))
        Button(actions, text="Sincronizar frases do roteiro", command=self._refresh_lines, bg="#eef1ff", fg="#27319f", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        Button(actions, text="Atualizar videos", command=self._start_video_update, bg="#5b6cff", fg="#ffffff", activebackground="#4657e8", activeforeground="#ffffff", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(side=LEFT, padx=(10, 0))
        Button(actions, text="Escolher pasta de saída", command=self._choose_output_dir, bg="#eef1ff", fg="#27319f", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(side=LEFT, padx=(10, 0))
        Label(actions, textvariable=self.output_dir, bg="#ffffff", fg="#657084", font=("Segoe UI", 9)).pack(side=LEFT, padx=(12, 0))

        self._entry_row(parent, "Tempo extra após o áudio quando o vídeo for maior (segundos)", self.video_extra_after_audio, "Padrão: 1. Use 0 para cortar exatamente no fim do áudio.")

        list_card = Frame(parent, bg="#f3f5fb", padx=10, pady=10)
        list_card.pack(fill=BOTH, expand=True)
        self.lines_canvas = Canvas(list_card, bd=0, highlightthickness=0, bg="#f3f5fb")
        self.lines_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar = ttk.Scrollbar(list_card, orient="vertical", command=self.lines_canvas.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.lines_canvas.configure(yscrollcommand=scrollbar.set)
        self.lines_frame = Frame(self.lines_canvas, bg="#f3f5fb")
        self.lines_window = self.lines_canvas.create_window((0, 0), window=self.lines_frame, anchor="nw")
        self.lines_frame.bind("<Configure>", lambda _event: self.lines_canvas.configure(scrollregion=self.lines_canvas.bbox("all")))
        self.lines_canvas.bind("<Configure>", lambda event: self.lines_canvas.itemconfigure(self.lines_window, width=event.width))

    def _build_subtitles_tab(self, parent: Frame) -> None:
        top = Frame(parent, bg="#ffffff")
        top.pack(fill=X)
        ttk.Label(top, text="Legendas", style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, text="Configure como a frase de cada cena aparecerá por cima do vídeo.", style="Muted.TLabel").pack(anchor="w", pady=(4, 12))

        layout = Frame(parent, bg="#ffffff")
        layout.pack(fill=BOTH, expand=True)

        controls = Frame(layout, bg="#ffffff")
        controls.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 18))
        preview_box = Frame(layout, bg="#ffffff")
        preview_box.pack(side=RIGHT, fill=Y)

        self.subtitle_toggle_button = Button(controls, text="Legendas Desligadas", command=self._toggle_subtitles, bg="#111827", fg="#ffffff", activebackground="#2a3446", activeforeground="#ffffff", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold"))
        self.subtitle_toggle_button.pack(anchor="w", pady=(0, 14))
        self.subtitle_toggle_label = Label(controls, text="Legendas: Ligadas", bg="#ffffff", fg="#657084", font=("Segoe UI", 9, "bold"))
        self.subtitle_toggle_label.pack(anchor="w", pady=(0, 14))

        self._option_row(controls, "Posição no video", self.subtitle_position, ["Baixo", "Centro", "Topo"])
        self._entry_row(controls, "Cor da legenda", self.subtitle_color, "Ex.: #FFFFFF")
        self._entry_row(controls, "Cor de destaque", self.subtitle_highlight_color, "Cor da palavra falada no momento. Ex.: #FFD84D")
        self._entry_row(controls, "Tamanho", self.subtitle_size, "Ex.: 64")
        self._option_row(controls, "Fundo", self.subtitle_background, ["Sim", "Não"])
        self._entry_row(controls, "Cor do fundo", self.subtitle_background_color, "Ex.: #000000")
        self._entry_row(controls, "Cor do contorno", self.subtitle_outline_color, "Ex.: #000000")
        self._entry_row(controls, "Fonte", self.subtitle_font, "Ex.: Arial")

        ttk.Label(preview_box, text="Preview", style="Title.TLabel").pack(anchor="w")
        ttk.Label(preview_box, text="Digite uma frase para testar e veja a atualização em tempo real.", style="Muted.TLabel").pack(anchor="w", pady=(4, 10))
        Entry(preview_box, textvariable=self.subtitle_preview_text, bd=0, bg="#f3f5fb", fg="#111827", insertbackground="#111827", font=("Segoe UI", 10)).pack(fill=X, ipady=8, pady=(0, 10))
        self.subtitle_preview = Canvas(preview_box, width=300, height=500, bg="#111827", bd=0, highlightthickness=0)
        self.subtitle_preview.pack()

        for variable in [
            self.subtitle_enabled,
            self.subtitle_position,
            self.subtitle_color,
            self.subtitle_highlight_color,
            self.subtitle_size,
            self.subtitle_background,
            self.subtitle_background_color,
            self.subtitle_outline_color,
            self.subtitle_font,
            self.subtitle_preview_text,
        ]:
            variable.trace_add("write", lambda *_args: self._update_subtitle_preview())
        self._update_subtitle_preview()

    def _build_logo_tab(self, parent: Frame) -> None:
        top = Frame(parent, bg="#ffffff")
        top.pack(fill=X)
        ttk.Label(top, text="Logo", style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, text="Cole uma imagem PNG para aparecer por cima do vídeo e escolha o canto e o tamanho.", style="Muted.TLabel").pack(anchor="w", pady=(4, 22))

        controls = Frame(parent, bg="#ffffff")
        controls.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 18))
        preview_box = Frame(parent, bg="#ffffff")
        preview_box.pack(side=RIGHT, fill=Y)

        Label(controls, text="Arquivo PNG da logo", bg="#ffffff", fg="#111827", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        logo_row = Frame(controls, bg="#ffffff")
        logo_row.pack(fill=X, pady=(6, 14))
        Entry(logo_row, textvariable=self.logo_path, bd=0, bg="#f3f5fb", fg="#111827", insertbackground="#111827", font=("Segoe UI", 10)).pack(side=LEFT, fill=X, expand=True, ipady=9)
        Button(logo_row, text="Colar PNG", command=self._paste_logo, bg="#5b6cff", fg="#ffffff", activebackground="#4657e8", activeforeground="#ffffff", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(side=RIGHT, padx=(10, 0))
        Button(logo_row, text="Selecionar", command=self._choose_logo_file, bg="#eef1ff", fg="#27319f", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(side=RIGHT, padx=(10, 0))

        self._option_row(
            controls,
            "Canto do video",
            self.logo_position,
            ["Canto superior direito", "Canto superior esquerdo", "Canto inferior direito", "Canto inferior esquerdo"],
        )
        self._entry_row(controls, "Tamanho da logo (% da largura do vídeo)", self.logo_size, "Ex.: 20. Use 0 para não exibir a logo.")
        Button(controls, text="Remover logo", command=self._clear_logo, bg="#eef1ff", fg="#27319f", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(anchor="w")

        ttk.Label(preview_box, text="Preview", style="Title.TLabel").pack(anchor="w")
        self.logo_preview = Canvas(preview_box, width=300, height=500, bg="#111827", bd=0, highlightthickness=0)
        self.logo_preview.pack(pady=(12, 0))
        for variable in [self.logo_path, self.logo_position, self.logo_size]:
            variable.trace_add("write", lambda *_args: self._update_logo_preview())
        self._update_logo_preview()

    def _choose_logo_file(self) -> None:
        file_path = filedialog.askopenfilename(title="Selecionar logo PNG", filetypes=[("PNG", "*.png")])
        if file_path:
            self.logo_path.set(file_path)
            self._save_config()

    def _paste_logo(self) -> None:
        image_bytes = self._clipboard_image_bytes()
        if not image_bytes:
            messagebox.showerror(APP_TITLE, "Copie uma imagem PNG para a área de transferência e clique em Colar PNG.")
            return
        LOGO_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        output_path = LOGO_MEDIA_DIR / f"logo_{int(time.time() * 1000)}.png"
        output_path.write_bytes(image_bytes)
        self.logo_path.set(str(output_path))
        self._save_config()
        self.status_text.set("Logo colada e salva.")

    def _clear_logo(self) -> None:
        self.logo_path.set("")
        self._save_config()
        self.status_text.set("Logo removida.")

    def _update_logo_preview(self) -> None:
        if not hasattr(self, "logo_preview"):
            return
        canvas = self.logo_preview
        canvas.delete("all")
        width, height = 300, 500
        canvas.create_rectangle(0, 0, width, height, fill="#111827", outline="")
        canvas.create_rectangle(20, 28, 280, 472, outline="#657084", width=2)
        canvas.create_text(150, 250, text="Video", fill="#e5e7eb", font=("Segoe UI", 24, "bold"))
        logo_path = self._logo_file_path()
        if not logo_path:
            canvas.create_text(150, 315, text="Sem logo", fill="#8b95a7", font=("Segoe UI", 12, "bold"))
            return
        try:
            image = Image.open(logo_path).convert("RGBA")
            target_width = max(1, int(width * self._logo_size_fraction()))
            image.thumbnail((target_width, height), Image.LANCZOS)
            self.logo_preview_image = ImageTk.PhotoImage(image)
        except Exception:
            canvas.create_text(150, 315, text="PNG inválido", fill="#fca5a5", font=("Segoe UI", 12, "bold"))
            return
        margin = 22
        x, y = self._logo_preview_coordinates(width, height, self.logo_preview_image.width(), self.logo_preview_image.height(), margin)
        canvas.create_image(x, y, image=self.logo_preview_image, anchor="nw")

    def _entry_row(self, parent: Frame, label: str, variable: StringVar, hint: str) -> None:
        Label(parent, text=label, bg="#ffffff", fg="#111827", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        Entry(parent, textvariable=variable, bd=0, bg="#f3f5fb", fg="#111827", insertbackground="#111827", font=("Segoe UI", 11)).pack(fill=X, ipady=9, pady=(6, 4))
        Label(parent, text=hint, bg="#ffffff", fg="#657084", font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 12))

    def _option_row(self, parent: Frame, label: str, variable: StringVar, values: list[str]) -> None:
        Label(parent, text=label, bg="#ffffff", fg="#111827", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", font=("Segoe UI", 10))
        combo.pack(fill=X, ipady=6, pady=(6, 14))

    def _update_subtitle_preview(self) -> None:
        if not hasattr(self, "subtitle_preview"):
            return
        canvas = self.subtitle_preview
        canvas.delete("all")
        width = 300
        height = 500
        for step in range(0, height, 20):
            shade = 28 + int(step / height * 38)
            canvas.create_rectangle(0, step, width, step + 20, fill=f"#{shade:02x}{shade + 12:02x}{shade + 28:02x}", outline="")
        canvas.create_rectangle(20, 28, 280, 472, outline="#657084", width=2)
        canvas.create_oval(105, 95, 195, 185, fill="#5b6cff", outline="")
        canvas.create_rectangle(58, 235, 242, 350, fill="#27344f", outline="")
        canvas.create_line(42, 410, 258, 330, fill="#93a4c7", width=4)

        enabled = self.subtitle_enabled.get() == "Sim"
        if hasattr(self, "subtitle_toggle_label"):
            self.subtitle_toggle_label.configure(text="Legendas: Ligadas" if enabled else "Legendas: Desligadas", fg="#16a34a" if enabled else "#dc2626")
        if hasattr(self, "subtitle_toggle_button"):
            self.subtitle_toggle_button.configure(text="Legendas Desligadas" if enabled else "Ligar Legendas")
        if not enabled:
            canvas.create_text(150, 250, text="Legendas desligadas", fill="#e5e7eb", font=("Segoe UI", 18, "bold"), width=230, justify="center")
            return

        text = self.subtitle_preview_text.get().strip() or "Digite uma frase para testar."
        size = self._safe_int(self.subtitle_size.get(), 30, 1, 160)
        preview_size = max(1, int(size * 0.38))
        position = self.subtitle_position.get()
        y = {"Topo": 96, "Centro": 250, "Baixo": 405}.get(position, 405)
        color = self._normalize_color(self.subtitle_color.get(), "#FFFFFF")
        highlight_color = self._normalize_color(self.subtitle_highlight_color.get(), "#FFD84D")
        bg_color = self._normalize_color(self.subtitle_background_color.get(), "#000000")
        outline_color = self._normalize_color(self.subtitle_outline_color.get(), "#000000")
        font = self.subtitle_font.get().strip() or "Arial"
        lines = self._preview_subtitle_lines(text, font, preview_size, 230)
        line_height = max(preview_size + 5, int(preview_size * 1.25))
        total_height = max(line_height, len(lines) * line_height)
        start_y = y - total_height / 2 + line_height / 2

        box_padding = max(8, int(preview_size * 0.65))
        if self.subtitle_background.get() == "Sim":
            canvas.create_rectangle(24, y - total_height / 2 - box_padding, 276, y + total_height / 2 + box_padding, fill=bg_color, outline="")
        highlight_index = self._preview_highlight_index(text)
        outline_offset = max(1, min(2, preview_size // 8 or 1))
        for line_index, line_words in enumerate(lines):
            current_y = int(start_y + line_index * line_height)
            self._draw_preview_subtitle_line(
                canvas,
                line_words,
                highlight_index,
                150,
                current_y,
                font,
                preview_size,
                color,
                highlight_color,
                outline_color,
                outline_offset,
            )

    @staticmethod
    def _preview_highlight_index(text: str) -> int:
        words = text.split()
        if not words:
            return 0
        # O preview mostra uma palavra intermediária destacada para demonstrar o efeito durante a fala.
        return min(max(len(words) // 2, 0), len(words) - 1)

    @staticmethod
    def _preview_subtitle_lines(text: str, font_name: str, font_size: int, max_width: int) -> list[list[tuple[int, str]]]:
        words = [(index, word) for index, word in enumerate(text.split())]
        if not words:
            return [[(0, text)]]
        measuring_font = tkfont.Font(family=font_name, size=font_size, weight="bold")
        lines: list[list[tuple[int, str]]] = []
        current: list[tuple[int, str]] = []
        for indexed_word in words:
            candidate = [*current, indexed_word]
            candidate_text = " ".join(word for _index, word in candidate)
            if current and measuring_font.measure(candidate_text) > max_width:
                lines.append(current)
                current = [indexed_word]
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    @staticmethod
    def _draw_preview_subtitle_line(
        canvas: Canvas,
        words: list[tuple[int, str]],
        highlight_index: int,
        center_x: int,
        y: int,
        font_name: str,
        font_size: int,
        color: str,
        highlight_color: str,
        outline_color: str,
        outline_offset: int,
    ) -> None:
        measuring_font = tkfont.Font(family=font_name, size=font_size, weight="bold")
        word_widths = [measuring_font.measure(word) for _index, word in words]
        space_width = measuring_font.measure(" ")
        total_width = sum(word_widths) + max(0, len(words) - 1) * space_width
        current_x = center_x - total_width / 2
        for (word_index, word), word_width in zip(words, word_widths, strict=True):
            word_center = int(current_x + word_width / 2)
            fill = highlight_color if word_index == highlight_index else color
            # O contorno é desenhado palavra a palavra para o destaque manter o mesmo layout do vídeo final.
            for dx, dy in [(-outline_offset, 0), (outline_offset, 0), (0, -outline_offset), (0, outline_offset), (-outline_offset, -outline_offset), (outline_offset, -outline_offset), (-outline_offset, outline_offset), (outline_offset, outline_offset)]:
                canvas.create_text(word_center + dx, y + dy, text=word, fill=outline_color, font=(font_name, font_size, "bold"))
            canvas.create_text(word_center, y, text=word, fill=fill, font=(font_name, font_size, "bold"))
            current_x += word_width + space_width

    def _build_audio_tab(self, parent: Frame) -> None:
        top = Frame(parent, bg="#ffffff")
        top.pack(fill=X)
        ttk.Label(top, text="Audio", style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, text="Gere áudios localmente usando IA. Selecione um áudio de referência para clonar sua voz.", style="Muted.TLabel").pack(anchor="w", pady=(4, 12))

        canvas = Canvas(parent, bd=0, highlightthickness=0, bg="#ffffff")
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        canvas.configure(yscrollcommand=scrollbar.set)

        content = Frame(canvas, bg="#ffffff")
        content_window = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(content_window, width=event.width))
        canvas.bind("<MouseWheel>", lambda event: canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"))

        # Card de configurações de TTS
        tts_card = Frame(content, bg="#f8f9fd", padx=14, pady=12)
        tts_card.pack(fill=X, pady=(0, 12))
        Label(tts_card, text="Configurações de TTS Local", bg="#f8f9fd", fg="#111827", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))
        
        # Seleção do motor TTS
        engine_row = Frame(tts_card, bg="#f8f9fd")
        engine_row.pack(fill=X, pady=(6, 6))
        Label(engine_row, text="Motor TTS:", bg="#f8f9fd", fg="#111827", font=("Segoe UI", 9, "bold"), width=15, anchor="w").pack(side=LEFT)
        engine_combo = ttk.Combobox(engine_row, textvariable=self.tts_engine, values=[
            "kokoro (Vozes pré-treinadas)",
            "xtts (Clonagem de voz)"
        ], state="readonly", width=25, font=("Segoe UI", 9))
        engine_combo.pack(side=LEFT, ipady=4)
        Label(engine_row, text="Selecione o motor de síntese de voz.", bg="#f8f9fd", fg="#657084", font=("Segoe UI", 8)).pack(side=LEFT, padx=(10, 0))
        
        # Idioma
        lang_row = Frame(tts_card, bg="#f8f9fd")
        lang_row.pack(fill=X, pady=(6, 6))
        Label(lang_row, text="Idioma:", bg="#f8f9fd", fg="#111827", font=("Segoe UI", 9, "bold"), width=15, anchor="w").pack(side=LEFT)
        lang_combo = ttk.Combobox(lang_row, textvariable=self.tts_language, values=["pt-br", "en-us", "en-gb", "es-es", "fr-fr", "de-de", "it-it", "ja-jp", "zh-cn"], state="readonly", width=20, font=("Segoe UI", 9))
        lang_combo.pack(side=LEFT, ipady=4)
        Label(lang_row, text="Selecione o idioma para geração dos áudios.", bg="#f8f9fd", fg="#657084", font=("Segoe UI", 8)).pack(side=LEFT, padx=(10, 0))
        
        # Áudio de referência (apenas para XTTS)
        Label(tts_card, text="Áudio de referência (apenas XTTS)", bg="#f8f9fd", fg="#111827", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(12, 6))
        ref_row = Frame(tts_card, bg="#f8f9fd")
        ref_row.pack(fill=X, pady=(6, 6))
        Entry(ref_row, textvariable=self.tts_voice_ref_path, bd=0, bg="#e8eaef", fg="#657084", insertbackground="#111827", font=("Segoe UI", 9)).pack(side=LEFT, fill=X, expand=True, ipady=8)
        Button(ref_row, text="Selecionar áudio", command=self._choose_voice_ref_file, bg="#e8eaef", fg="#657084", relief="flat", padx=14, pady=8, font=("Segoe UI", 9)).pack(side=RIGHT, padx=(10, 0))
        Label(tts_card, text="Para XTTS: selecione um áudio de 3-10 segundos com a voz desejada. Kokoro ignora esta configuração.", bg="#f8f9fd", fg="#657084", font=("Segoe UI", 8)).pack(anchor="w", pady=(6, 0))
        
        # Seleção de voz (apenas para Kokoro)
        Label(tts_card, text="Voz do narrador (apenas Kokoro)", bg="#f8f9fd", fg="#111827", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(12, 6))
        voice_row = Frame(tts_card, bg="#f8f9fd")
        voice_row.pack(fill=X, pady=(6, 6))
        self.tts_voice_name = StringVar(value="af_heart")
        voice_combo = ttk.Combobox(voice_row, textvariable=self.tts_voice_name, values=[
            "af_heart (Feminina Americana - Principal)",
            "af_bella (Feminina Americana)",
            "af_nicole (Feminina Americana)",
            "af_sarah (Feminina Americana)",
            "am_adam (Masculino Americano)",
            "am_michael (Masculino Americano)"
        ], state="readonly", width=35, font=("Segoe UI", 9))
        voice_combo.pack(side=LEFT, ipady=4)
        Label(tts_card, text="Selecione a voz para narração. XTTS usa o áudio de referência acima.", bg="#f8f9fd", fg="#657084", font=("Segoe UI", 8)).pack(anchor="w", pady=(6, 0))
        
        # Status do modelo
        status_frame = Frame(tts_card, bg="#f8f9fd")
        status_frame.pack(fill=X, pady=(12, 0))
        self.tts_status_label = Label(status_frame, text="Modelo: Não carregado", bg="#f8f9fd", fg="#dc2626", font=("Segoe UI", 9))
        self.tts_status_label.pack(anchor="w")
        if KOKORO_AVAILABLE:
            self.tts_status_label.configure(text="Kokoro: Disponível ✓ | XTTS: Verifique instalação", fg="#059669")
        else:
            self.tts_status_label.configure(text="Kokoro: Não instalado | XTTS: pip install TTS", fg="#dc2626")
        
        # Botões para carregar modelos
        btn_frame = Frame(tts_card, bg="#f8f9fd")
        btn_frame.pack(fill=X, pady=(10, 0))
        Button(btn_frame, text="Carregar Kokoro", command=self._load_kokoro_model, bg="#5b6cff", fg="#ffffff", activebackground="#4657e8", activeforeground="#ffffff", relief="flat", padx=14, pady=8, font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 10))
        Button(btn_frame, text="Carregar XTTS", command=self._load_xtts_model, bg="#5b6cff", fg="#ffffff", activebackground="#4657e8", activeforeground="#ffffff", relief="flat", padx=14, pady=8, font=("Segoe UI", 9, "bold")).pack(side=LEFT)

        # Lista de frases com botões de escutar
        Label(content, text="Frases do Roteiro", bg="#ffffff", fg="#111827", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(16, 8))
        
        self.audio_list_frame = Frame(content, bg="#ffffff")
        self.audio_list_frame.pack(fill=BOTH, expand=True)
        self._refresh_audio_list()
        
        # Botões de ação
        actions = Frame(content, bg="#ffffff", pady=16)
        actions.pack(fill=X)
        Button(actions, text="Gerar todos os áudios", command=self._generate_all_audios, bg="#5b6cff", fg="#ffffff", activebackground="#4657e8", activeforeground="#ffffff", relief="flat", padx=18, pady=10, font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        Label(actions, text="Os áudios serão gerados e salvos automaticamente.", bg="#ffffff", fg="#657084", font=("Segoe UI", 9)).pack(side=LEFT, padx=(12, 0))

    def _refresh_audio_list(self) -> None:
        """Atualiza a lista de frases na aba Audio."""
        for widget in self.audio_list_frame.winfo_children():
            widget.destroy()
        
        # Não chama _refresh_lines() para não sobrescrever o roteiro atual
        # Apenas usa as linhas já existentes
        
        if not self.lines:
            Label(self.audio_list_frame, text="Nenhuma frase no roteiro. Vá para a aba Roteiro e gere ou digite um roteiro.", bg="#ffffff", fg="#657084", font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 0))
            return
        
        for index, line in enumerate(self.lines, start=1):
            frame = Frame(self.audio_list_frame, bg="#f9fafb", padx=10, pady=8)
            frame.pack(fill=X, pady=(0, 6))
            
            # Número da frase
            Label(frame, text=f"{index}.", bg="#f9fafb", fg="#657084", font=("Segoe UI", 9, "bold"), width=3).pack(side=LEFT)
            
            # Texto da frase
            text_label = Label(frame, text=line.text[:80] + ("..." if len(line.text) > 80 else ""), bg="#f9fafb", fg="#111827", font=("Segoe UI", 9), wraplength=500, justify=LEFT)
            text_label.pack(side=LEFT, fill=X, expand=True, padx=(6, 10))
            
            # Botão Escutar - usa caminho correto
            audio_path = CLIPBOARD_MEDIA_DIR / f"audio_{index:03d}.wav"
            if audio_path.exists():
                Button(frame, text="Escutar áudio", command=lambda p=audio_path: self._play_audio(p), bg="#e0f2fe", fg="#0369a1", relief="flat", padx=10, pady=4, font=("Segoe UI", 9)).pack(side=RIGHT)
            else:
                Label(frame, text="Áudio não gerado", bg="#f9fafb", fg="#9ca3af", font=("Segoe UI", 8)).pack(side=RIGHT, padx=(10, 0))

    def _play_audio(self, audio_path: Path) -> None:
        """Toca um arquivo de áudio usando sounddevice."""
        try:
            import sounddevice as sd
            # Lê o arquivo de áudio
            data, samplerate = sf.read(str(audio_path))
            # Toca o áudio
            sd.play(data, samplerate)
            # Aguarda até terminar
            sd.wait()
        except ImportError:
            # Fallback usando subprocess
            try:
                if sys.platform == "win32":
                    import os
                    os.startfile(str(audio_path))
                elif sys.platform == "darwin":
                    subprocess.run(["afplay", str(audio_path)], check=False)
                else:
                    subprocess.run(["aplay", str(audio_path)], check=False)
            except Exception as e:
                messagebox.showerror(APP_TITLE, f"Erro ao reproduzir áudio: {e}")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Erro ao reproduzir áudio: {e}")

    def _choose_voice_ref_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Selecionar áudio de referência",
            filetypes=[
                ("Arquivos de áudio", "*.mp3 *.wav *.m4a *.aac *.ogg *.flac"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if file_path:
            self.tts_voice_ref_path.set(file_path)
            self._save_config()

    def _load_kokoro_model(self) -> None:
        """Carrega o modelo Kokoro para TTS."""
        if not KOKORO_AVAILABLE:
            messagebox.showerror(APP_TITLE, "Kokoro não está instalado. Instale com: pip install kokoro")
            return
        
        try:
            self.status_text.set("Carregando modelo Kokoro...")
            self.root.update()
            
            # Mapeia o código de idioma para o formato do Kokoro
            lang_mapping = {
                "pt-br": "p",
                "en-us": "a",
                "en-gb": "b",
                "es": "e",
                "fr": "f",
                "hi": "h",
                "it": "i",
                "ja": "j",
                "zh": "z"
            }
            lang_code = lang_mapping.get(self.tts_language.get().lower(), "p")
            # KPipeline já carrega o modelo internamente quando model=True (padrão)
            self.kokoro_pipeline = KPipeline(lang_code=lang_code, model=False)  # Carrega sem modelo para economizar memória
            # O modelo será carregado sob demanda se necessário
            
            self.tts_model_loaded = True
            self.tts_engine.set("kokoro")
            self.tts_status_label.configure(text="Modelo Kokoro: Carregado e pronto", fg="#059669")
        except MemoryError:
            self.tts_status_label.configure(text="Erro: Memória insuficiente", fg="#dc2626")
            self.status_text.set("Erro: Kokoro requer mais memória RAM")
            messagebox.showerror(APP_TITLE, 
                "Memória insuficiente para carregar o Kokoro.\n\n"
                "Soluções:\n"
                "1. Feche outros programas para liberar memória\n"
                "2. Use um sistema com pelo menos 4GB de RAM livre\n"
                "3. Considere usar um serviço de TTS online alternativo")
        except Exception as e:
            self.tts_status_label.configure(text=f"Erro ao carregar modelo: {e}", fg="#dc2626")
            self.status_text.set(f"Erro: {e}")
            messagebox.showerror(APP_TITLE, f"Erro ao carregar modelo Kokoro:\n{e}")

    def _load_xtts_model(self) -> None:
        """Carrega o modelo XTTS para TTS com clonagem de voz."""
        try:
            from TTS.api import TTS
            self.status_text.set("Carregando modelo XTTS...")
            self.root.update()
            
            # Verifica se há GPU disponível
            use_cuda = torch.cuda.is_available()
            if not use_cuda:
                self.status_text.set("XTTS: Sem GPU detectada, usando CPU (lento)")
            
            # Carrega o modelo XTTS v2
            self.xtts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(
                "cuda" if use_cuda else "cpu"
            )
            
            self.tts_model_loaded = True
            self.tts_engine.set("xtts")
            self.tts_status_label.configure(
                text=f"XTTS: Carregado {'(GPU)' if use_cuda else '(CPU)'}", 
                fg="#059669"
            )
        except ImportError:
            self.tts_status_label.configure(text="XTTS: Não instalado (pip install TTS)", fg="#dc2626")
            messagebox.showerror(APP_TITLE, 
                "XTTS não está instalado.\n\n"
                "Instale com: pip install TTS\n\n"
                "Nota: Pode ser necessário instalar versões específicas:")
        except MemoryError:
            self.tts_status_label.configure(text="Erro: Memória insuficiente", fg="#dc2626")
            self.status_text.set("Erro: XTTS requer mais memória VRAM/RAM")
            messagebox.showerror(APP_TITLE, 
                "Memória insuficiente para carregar o XTTS.\n\n"
                "Soluções:\n"
                "1. Feche outros programas para liberar memória\n"
                "2. Use uma GPU com mais VRAM (mínimo 4GB recomendado)\n"
                "3. Considere usar Kokoro como alternativa")
        except Exception as e:
            self.tts_status_label.configure(text=f"Erro ao carregar XTTS: {e}", fg="#dc2626")
            self.status_text.set(f"Erro: {e}")
            messagebox.showerror(APP_TITLE, f"Erro ao carregar modelo XTTS:\n{e}")

    def _generate_all_audios(self) -> None:
        """Gera todos os áudios das frases."""
        if not self.lines:
            messagebox.showerror(APP_TITLE, "Nenhuma frase no roteiro. Gere um roteiro primeiro.")
            return
        
        # Verifica qual engine está selecionada
        engine = self.tts_engine.get().split()[0].lower()  # extrai "kokoro" ou "xtts"
        
        if engine == "kokoro":
            if not KOKORO_AVAILABLE:
                messagebox.showerror(APP_TITLE, "Kokoro não está instalado. Instale com: pip install kokoro")
                return
            if not self.tts_model_loaded or self.tts_engine.get() != "kokoro":
                messagebox.showwarning(APP_TITLE, "Modelo Kokoro não carregado.\nClique em Carregar Kokoro antes de gerar os áudios.")
                return
        elif engine == "xtts":
            if self.xtts_model is None:
                messagebox.showwarning(APP_TITLE, "Modelo XTTS não carregado.\nClique em Carregar XTTS antes de gerar os áudios.")
                return
        else:
            messagebox.showerror(APP_TITLE, "Motor TTS não selecionado corretamente.")
            return
        
        # Cria diretório de mídia
        CLIPBOARD_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        
        self.progress.configure(value=0, maximum=len(self.lines))
        self.progress_text.set(f"Gerando áudio 0/{len(self.lines)}")
        
        threading.Thread(target=self._generate_all_audios_worker, daemon=True).start()

    def _generate_all_audios_worker(self) -> None:
        """Worker para gerar todos os áudios em thread separada."""
        try:
            engine = self.tts_engine.get().split()[0].lower()
            
            if engine == "xtts":
                # Gera áudio com XTTS
                self._generate_all_audios_xtts()
            else:
                # Gera áudio com Kokoro
                self._generate_all_audios_kokoro()
                
        except Exception as e:
            self.message_queue.put(("error", f"Erro ao gerar áudios: {e}"))

    def _generate_all_audios_kokoro(self) -> None:
        """Worker para gerar áudios com Kokoro."""
        # Mapeia o código de idioma para o formato do Kokoro
        lang_mapping = {
            "pt-br": "p",
            "en-us": "a",
            "en-gb": "b",
            "es": "e",
            "fr": "f",
            "hi": "h",
            "it": "i",
            "ja": "j",
            "zh": "z"
        }
        lang_code = lang_mapping.get(self.tts_language.get().lower(), "p")
        
        # Carrega o modelo com memória limitada
        from kokoro import KModel
        
        self.message_queue.put(("status", "Carregando modelo Kokoro..."))
        
        # Tenta carregar o modelo com menos memória
        try:
            model = KModel()
            # Extrai apenas o nome da voz (sem a descrição)
            voice_full = self.tts_voice_name.get().strip()
            voice_name = voice_full.split()[0] if voice_full else "af_heart"
            
            # Nota: A versão atual do Kokoro (0.9.4) não suporta clonagem de voz
            # a partir de áudio de referência. Apenas vozes pré-treinadas (.pt) são suportadas.
            if self.tts_voice_ref_path.get().strip():
                self.message_queue.put(("status", "Aviso: Clonagem por áudio não disponível nesta versão do Kokoro. Usando voz padrão."))
            
            # Cria novo pipeline com modelo
            pipeline = KPipeline(lang_code=lang_code, model=model)
            
        except MemoryError:
            self.message_queue.put(("error", "Memória insuficiente para carregar o modelo TTS"))
            return
        except Exception as e:
            self.message_queue.put(("error", f"Erro ao carregar modelo: {e}"))
            return
        
        for index, line in enumerate(self.lines, start=1):
            self.message_queue.put(("status", f"Gerando áudio {index}/{len(self.lines)}: {line.text[:50]}..."))
            
            audio_path = CLIPBOARD_MEDIA_DIR / f"audio_{index:03d}.wav"
            
            try:
                # Gera áudio com Kokoro
                generator = pipeline(line.text, voice=voice_name)
                
                # Salva o áudio gerado
                with wave.open(str(audio_path), "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(24000)
                    
                    for chunk in generator:
                        # Converte float32 para int16
                        # Na nova versao do Kokoro, chunk é um objeto Result com propriedade audio
                        if hasattr(chunk, 'audio') and chunk.audio is not None:
                            audio_tensor = chunk.audio
                        elif hasattr(chunk, 'numpy'):
                            audio_tensor = chunk
                        else:
                            audio_tensor = torch.from_numpy(chunk)
                        
                        audio_data = (audio_tensor * 32767).to(torch.int16).numpy()
                        wf.writeframes(audio_data.tobytes())
                
                self.message_queue.put(("status", f"Áudio gerado: {line.text[:50]}..."))
                
            except MemoryError:
                self.message_queue.put(("error", "Memória insuficiente para gerar áudio"))
                return
            except Exception as e:
                self.message_queue.put(("error", f"Erro ao gerar áudio {index}: {e}"))
                return
            
            self.root.after(0, lambda i=index: self.progress.configure(value=i))
        
        self.root.after(0, lambda: self.progress_text.set("Todos os áudios gerados!"))
        self.root.after(0, lambda: self.status_text.set("Áudios gerados com Kokoro"))

    def _generate_all_audios_xtts(self) -> None:
        """Worker para gerar áudios com XTTS."""
        if self.xtts_model is None:
            self.message_queue.put(("error", "Modelo XTTS não carregado"))
            return
        
        speaker_wav = self.tts_voice_ref_path.get().strip()
        language = self.tts_language.get().lower()
        
        # Mapeia para o formato do XTTS
        lang_mapping = {
            "pt-br": "pt",
            "en-us": "en",
            "en-gb": "en",
            "es-es": "es",
            "fr-fr": "fr",
            "de-de": "de",
            "it-it": "it",
            "ja-jp": "ja",
            "zh-cn": "zh"
        }
        lang = lang_mapping.get(language, "pt")
        
        for index, line in enumerate(self.lines, start=1):
            self.message_queue.put(("status", f"Gerando áudio XTTS {index}/{len(self.lines)}: {line.text[:50]}..."))
            
            audio_path = CLIPBOARD_MEDIA_DIR / f"audio_{index:03d}.wav"
            
            try:
                # XTTS requer speaker_wav para clonagem de voz
                if not speaker_wav:
                    self.message_queue.put(("error", "XTTS requer um áudio de referência. Selecione um arquivo na aba Audio."))
                    return
                
                # Gera áudio com XTTS
                self.xtts_model.tts_to_file(
                    text=line.text,
                    speaker_wav=speaker_wav,
                    language=lang,
                    file_path=str(audio_path)
                )
                
                self.message_queue.put(("status", f"Áudio XTTS gerado: {line.text[:50]}..."))
                
            except MemoryError:
                self.message_queue.put(("error", "Memória insuficiente para gerar áudio XTTS"))
                return
            except Exception as e:
                self.message_queue.put(("error", f"Erro ao gerar áudio XTTS {index}: {e}"))
                return
            
            self.root.after(0, lambda i=index: self.progress.configure(value=i))
        
        self.root.after(0, lambda: self.progress_text.set("Todos os áudios XTTS gerados!"))
        self.root.after(0, lambda: self.status_text.set("Áudios gerados com XTTS"))

    def _generate_tts(self, text: str, output_path: Path) -> None:
        """Gera áudio usando o motor TTS selecionado (Kokoro ou XTTS)."""
        engine = self.tts_engine.get().split()[0].lower()
        
        if engine == "xtts":
            self._generate_tts_xtts(text, output_path)
        else:
            self._generate_tts_kokoro(text, output_path)

    def _generate_tts_kokoro(self, text: str, output_path: Path) -> None:
        """Gera áudio usando Kokoro TTS localmente."""
        if not KOKORO_AVAILABLE:
            raise RuntimeError("Kokoro não está instalado. Instale com: pip install kokoro")
        
        if not self.tts_model_loaded:
            raise RuntimeError("Modelo Kokoro não carregado. Carregue o modelo na aba Audio primeiro.")
        
        try:
            # Mapeia o código de idioma para o formato do Kokoro
            lang_mapping = {
                "pt-br": "p",
                "en-us": "a",
                "en-gb": "b",
                "es-es": "e",
                "fr-fr": "f",
                "de-de": "g",
                "it-it": "i",
                "ja-jp": "j",
                "zh-cn": "z"
            }
            lang_code = lang_mapping.get(self.tts_language.get().lower(), "p")
            
            # Carrega o modelo
            from kokoro import KModel
            model = KModel()
            # Extrai apenas o nome da voz (sem a descrição)
            voice_full = self.tts_voice_name.get().strip()
            voice_name = voice_full.split()[0] if voice_full else "af_heart"
            
            # Nota: A versão atual do Kokoro (0.9.4) não suporta clonagem de voz
            # a partir de áudio de referência. Apenas vozes pré-treinadas (.pt) são suportadas.
            if self.tts_voice_ref_path.get().strip():
                self._queue_status("Aviso: Clonagem por áudio não disponível nesta versão do Kokoro.", step=True)
            
            # Cria pipeline com modelo
            pipeline = KPipeline(lang_code=lang_code, model=model)
            
            # Gera áudio com Kokoro
            generator = pipeline(text, voice=voice_name)
            
            # Salva o áudio gerado
            with wave.open(str(output_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                
                for chunk in generator:
                    # Converte float32 para int16
                    # Na nova versao do Kokoro, chunk é um objeto Result com propriedade audio
                    if hasattr(chunk, 'audio') and chunk.audio is not None:
                        audio_tensor = chunk.audio
                    elif hasattr(chunk, 'numpy'):
                        audio_tensor = chunk
                    else:
                        audio_tensor = torch.from_numpy(chunk)
                    
                    audio_data = (audio_tensor * 32767).to(torch.int16).numpy()
                    wf.writeframes(audio_data.tobytes())
            
            self._queue_status(f"Áudio gerado: {text[:50]}...", step=True)
            
        except MemoryError:
            raise RuntimeError("Memória insuficiente para gerar áudio. Tente fechar outros programas.")
        except Exception as e:
            raise RuntimeError(f"Erro ao gerar áudio com Kokoro: {e}")

    def _generate_tts_xtts(self, text: str, output_path: Path) -> None:
        """Gera áudio usando XTTS com clonagem de voz."""
        if self.xtts_model is None:
            raise RuntimeError("Modelo XTTS não carregado. Carregue o modelo na aba Audio primeiro.")
        
        speaker_wav = self.tts_voice_ref_path.get().strip()
        if not speaker_wav:
            raise RuntimeError("XTTS requer um áudio de referência. Selecione um arquivo na aba Audio.")
        
        language = self.tts_language.get().lower()
        lang_mapping = {
            "pt-br": "pt",
            "en-us": "en",
            "en-gb": "en",
            "es-es": "es",
            "fr-fr": "fr",
            "de-de": "de",
            "it-it": "it",
            "ja-jp": "ja",
            "zh-cn": "zh"
        }
        lang = lang_mapping.get(language, "pt")
        
        try:
            # Gera áudio com XTTS
            self.xtts_model.tts_to_file(
                text=text,
                speaker_wav=speaker_wav,
                language=lang,
                file_path=str(output_path)
            )
            
            self._queue_status(f"Áudio XTTS gerado: {text[:50]}...", step=True)
            
        except MemoryError:
            raise RuntimeError("Memória insuficiente para gerar áudio XTTS.")
        except Exception as e:
            raise RuntimeError(f"Erro ao gerar áudio com XTTS: {e}")
            self.message_queue.put(("error", f"Erro ao gerar áudios: {e}"))

    def _build_music_tab(self, parent: Frame) -> None:
        top = Frame(parent, bg="#ffffff")
        top.pack(fill=X)
        ttk.Label(top, text="Musica", style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, text="Selecione uma música do PC para tocar durante todo o vídeo.", style="Muted.TLabel").pack(anchor="w", pady=(4, 22))

        Label(parent, text="Arquivo de música", bg="#ffffff", fg="#111827", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        music_row = Frame(parent, bg="#ffffff")
        music_row.pack(fill=X, pady=(6, 14))
        Entry(music_row, textvariable=self.music_path, bd=0, bg="#f3f5fb", fg="#111827", insertbackground="#111827", font=("Segoe UI", 10)).pack(side=LEFT, fill=X, expand=True, ipady=9)
        Button(music_row, text="Selecionar música", command=self._choose_music_file, bg="#eef1ff", fg="#27319f", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(side=RIGHT, padx=(10, 0))

        self._entry_row(parent, "Volume da música (%)", self.music_volume, "Padrão: 20. Use 0 para silenciar ou 100 para volume total.")

    def _choose_music_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Selecionar música",
            filetypes=[
                ("Arquivos de áudio", "*.mp3 *.wav *.m4a *.aac *.ogg *.flac"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if file_path:
            self.music_path.set(file_path)
            self._save_config()

    def _toggle_subtitles(self) -> None:
        self.subtitle_enabled.set("Não" if self.subtitle_enabled.get() == "Sim" else "Sim")

    def _labeled_entry(self, parent: Frame, text: str, variable: StringVar, show: str | None = None) -> None:
        Label(parent, text=text, bg="#ffffff", fg="#111827", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        Entry(parent, textvariable=variable, show=show, bd=0, bg="#f3f5fb", fg="#111827", insertbackground="#111827", font=("Segoe UI", 11)).pack(fill=X, ipady=10, pady=(6, 14))

    def _load_config(self) -> None:
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                self.pexels_key.set(data.get("pexels_key", ""))
                self.groq_key.set(data.get("groq_key", ""))
                self.video_title.set(data.get("video_title", self.video_title.get()))
                self.script_text_value = data.get("script_text", self.script_text_value)
                self.lines = self._config_lines(data.get("script_lines", []))
                self.used_media_urls.update({line.media_url for line in self.lines if line.media_url})
                self.output_dir.set(data.get("output_dir", self.output_dir.get()))
                self.video_extra_after_audio.set(data.get("video_extra_after_audio", self.video_extra_after_audio.get()))
                self.subtitle_enabled.set(data.get("subtitle_enabled", self.subtitle_enabled.get()))
                self.subtitle_position.set(data.get("subtitle_position", self.subtitle_position.get()))
                self.subtitle_color.set(data.get("subtitle_color", self.subtitle_color.get()))
                self.subtitle_highlight_color.set(data.get("subtitle_highlight_color", self.subtitle_highlight_color.get()))
                self.subtitle_size.set(data.get("subtitle_size", self.subtitle_size.get()))
                self.subtitle_background.set(data.get("subtitle_background", self.subtitle_background.get()))
                self.subtitle_background_color.set(data.get("subtitle_background_color", self.subtitle_background_color.get()))
                self.subtitle_outline_color.set(data.get("subtitle_outline_color", self.subtitle_outline_color.get()))
                self.subtitle_font.set(data.get("subtitle_font", self.subtitle_font.get()))
                self.subtitle_preview_text.set(data.get("subtitle_preview_text", self.subtitle_preview_text.get()))
                self.qwen_shortcut.set(data.get("qwen_shortcut", self.qwen_shortcut.get()))
                self.qwen_response_wait.set(data.get("qwen_response_wait", self.qwen_response_wait.get()))
                self.qwen_send_wait.set(data.get("qwen_send_wait", self.qwen_send_wait.get()))
                self.qwen_menu_wait.set(data.get("qwen_menu_wait", self.qwen_menu_wait.get()))
                self.qwen_menu_x.set(data.get("qwen_menu_x", self.qwen_menu_x.get()))
                self.qwen_menu_y.set(data.get("qwen_menu_y", self.qwen_menu_y.get()))
                self.qwen_input_x.set(data.get("qwen_input_x", self.qwen_input_x.get()))
                self.qwen_input_y.set(data.get("qwen_input_y", self.qwen_input_y.get()))
                self.qwen_send_x.set(data.get("qwen_send_x", self.qwen_send_x.get()))
                self.qwen_send_y.set(data.get("qwen_send_y", self.qwen_send_y.get()))
                self.qwen_read_x.set(data.get("qwen_read_x", self.qwen_read_x.get()))
                self.qwen_read_y.set(data.get("qwen_read_y", self.qwen_read_y.get()))
                self.qwen_record_extra.set(data.get("qwen_record_extra", self.qwen_record_extra.get()))
                self.music_path.set(data.get("music_path", self.music_path.get()))
                self.music_volume.set(data.get("music_volume", self.music_volume.get()))
                self.logo_path.set(data.get("logo_path", self.logo_path.get()))
                self.logo_position.set(data.get("logo_position", self.logo_position.get()) or self.logo_position.get())
                self.logo_size.set(data.get("logo_size", self.logo_size.get()))
                self.tts_voice_ref_path.set(data.get("tts_voice_ref_path", self.tts_voice_ref_path.get()))
            except json.JSONDecodeError:
                pass

    def _save_config(self, show_status: bool = True) -> None:
        self.script_text_value = self._script_text_content()
        data = {
            "pexels_key": self.pexels_key.get().strip(),
            "groq_key": self.groq_key.get().strip(),
            "video_title": self.video_title.get().strip(),
            "script_text": self.script_text_value,
            "script_prompt": self.script_prompt_value.get().strip(),
            "script_lines": self._config_script_lines(),
            "output_dir": self.output_dir.get().strip(),
            "video_extra_after_audio": self.video_extra_after_audio.get().strip(),
            "subtitle_enabled": self.subtitle_enabled.get().strip(),
            "subtitle_position": self.subtitle_position.get().strip(),
            "subtitle_color": self.subtitle_color.get().strip(),
            "subtitle_highlight_color": self.subtitle_highlight_color.get().strip(),
            "subtitle_size": self.subtitle_size.get().strip(),
            "subtitle_background": self.subtitle_background.get().strip(),
            "subtitle_background_color": self.subtitle_background_color.get().strip(),
            "subtitle_outline_color": self.subtitle_outline_color.get().strip(),
            "subtitle_font": self.subtitle_font.get().strip(),
            "subtitle_preview_text": self.subtitle_preview_text.get().strip(),
            "qwen_shortcut": self.qwen_shortcut.get().strip(),
            "qwen_response_wait": self.qwen_response_wait.get().strip(),
            "qwen_send_wait": self.qwen_send_wait.get().strip(),
            "qwen_menu_wait": self.qwen_menu_wait.get().strip(),
            "qwen_menu_x": self.qwen_menu_x.get().strip(),
            "qwen_menu_y": self.qwen_menu_y.get().strip(),
            "qwen_input_x": self.qwen_input_x.get().strip(),
            "qwen_input_y": self.qwen_input_y.get().strip(),
            "qwen_send_x": self.qwen_send_x.get().strip(),
            "qwen_send_y": self.qwen_send_y.get().strip(),
            "qwen_read_x": self.qwen_read_x.get().strip(),
            "qwen_read_y": self.qwen_read_y.get().strip(),
            "qwen_record_extra": self.qwen_record_extra.get().strip(),
            "music_path": self.music_path.get().strip(),
            "music_volume": self.music_volume.get().strip(),
            "logo_path": self.logo_path.get().strip(),
            "logo_position": self.logo_position.get().strip(),
            "logo_size": self.logo_size.get().strip(),
            "tts_voice_ref_path": self.tts_voice_ref_path.get().strip(),
        }
        CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        if show_status:
            self.status_text.set("Configurações salvas no perfil do usuário.")

    def _script_text_content(self) -> str:
        if hasattr(self, "script_text"):
            return self.script_text.get("1.0", "end-1c")
        return self.script_text_value

    @staticmethod
    def _config_lines(raw_lines: Any) -> list[ScriptLine]:
        if not isinstance(raw_lines, list):
            return []
        lines: list[ScriptLine] = []
        for item in raw_lines:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            if text:
                media_url = str(item.get("media_url", "")).strip()
                lines.append(ScriptLine(text=text, media_url=media_url))
        return lines

    def _all_media_urls(self) -> set[str]:
        return {line.media_url.strip() for line in self.lines if line.media_url.strip()} | getattr(self, "used_media_urls", set())

    def _config_script_lines(self) -> list[dict[str, str]]:
        existing = {line.text: line.media_url for line in self.lines}
        phrases = [line.strip() for line in self.script_text_value.splitlines() if line.strip()]
        if phrases:
            return [{"text": phrase, "media_url": existing.get(phrase, "")} for phrase in phrases]
        return [{"text": line.text, "media_url": line.media_url} for line in self.lines]

    def _on_close(self) -> None:
        try:
            self._save_config(show_status=False)
        finally:
            self.root.destroy()

    def _refresh_lines(self) -> None:
        existing = {line.text: line.media_url for line in self.lines}
        phrases = [line.strip() for line in self.script_text.get("1.0", END).splitlines() if line.strip()]
        self.lines = [ScriptLine(text=phrase, media_url=existing.get(phrase, "")) for phrase in phrases]
        self._render_lines()
        self._save_config(show_status=False)
        self.status_text.set(f"{len(self.lines)} frase(s) sincronizada(s).")

    def _render_lines(self) -> None:
        if not hasattr(self, "lines_frame"):
            return
        for child in self.lines_frame.winfo_children():
            child.destroy()
        if not self.lines:
            Label(self.lines_frame, text="Nenhuma frase no roteiro ainda.", bg="#f3f5fb", fg="#657084", font=("Segoe UI", 10)).pack(anchor="w", padx=8, pady=8)
            return
        for index, line in enumerate(self.lines):
            row = Frame(self.lines_frame, bg="#ffffff", padx=12, pady=10)
            row.pack(fill=X, pady=(0, 8))
            text_area = Frame(row, bg="#ffffff")
            text_area.pack(side=LEFT, fill=BOTH, expand=True)
            Label(text_area, text=f"{index + 1}. {line.text}", bg="#ffffff", fg="#111827", anchor="w", justify=LEFT, wraplength=560, font=("Segoe UI", 10, "bold")).pack(fill=X, anchor="w")
            media_label = line.media_url if line.media_url else "Sem link manual: o app buscará automaticamente no Pexels."
            Label(text_area, text=media_label, bg="#ffffff", fg="#657084", anchor="w", justify=LEFT, wraplength=500, font=("Segoe UI", 9)).pack(fill=X, anchor="w", pady=(4, 0))
            preview = self._media_preview_widget(row, line.media_url)
            preview.pack(side=RIGHT, padx=(12, 0))
            buttons = Frame(row, bg="#ffffff")
            buttons.pack(side=RIGHT, padx=(12, 0))
            Button(buttons, text="Colar link", command=lambda idx=index: self._paste_line_link(idx), bg="#5b6cff", fg="#ffffff", activebackground="#4657e8", activeforeground="#ffffff", relief="flat", padx=12, pady=8, font=("Segoe UI", 9, "bold")).pack(side=LEFT)
            Button(buttons, text="Gerar outro video", command=lambda idx=index: self._start_single_video_update(idx), bg="#eef1ff", fg="#27319f", relief="flat", padx=12, pady=8, font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(8, 0))
            Button(buttons, text="Editar", command=lambda idx=index: self._edit_line_link(idx), bg="#eef1ff", fg="#27319f", relief="flat", padx=12, pady=8, font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(8, 0))

    def _media_preview_widget(self, parent: Frame, media_url: str) -> Frame:
        preview = Frame(parent, bg="#eef1f8", width=92, height=116, padx=4, pady=4)
        preview.pack_propagate(False)
        clean_url = media_url.strip()
        if not clean_url:
            Label(preview, text="Preview\nPexels", bg="#eef1f8", fg="#8b95a7", justify="center", font=("Segoe UI", 8, "bold")).pack(fill=BOTH, expand=True)
            return preview

        # O preview usa a mesma área para links do Pexels e imagens coladas da área de transferência.
        image = self._load_media_preview(clean_url)
        if image:
            Label(preview, image=image, bg="#eef1f8").pack(fill=BOTH, expand=True)
        elif clean_url in self.media_preview_failed:
            Label(preview, text="Sem\npreview", bg="#eef1f8", fg="#8b95a7", justify="center", font=("Segoe UI", 8, "bold")).pack(fill=BOTH, expand=True)
        else:
            Label(preview, text="Carregando\npreview", bg="#eef1f8", fg="#8b95a7", justify="center", font=("Segoe UI", 8, "bold")).pack(fill=BOTH, expand=True)
            self._start_media_preview_load(clean_url)
        return preview

    def _load_media_preview(self, media_url: str) -> ImageTk.PhotoImage | None:
        if media_url in self.media_preview_images:
            return self.media_preview_images[media_url]
        image_bytes = self.media_preview_bytes.get(media_url)
        local_path = self._local_media_path(media_url)
        if not image_bytes and local_path and local_path.suffix.lower() in IMAGE_EXTENSIONS:
            try:
                # Imagens locais/coladas já estão no disco; ler direto evita uma chamada HTTP desnecessária.
                image_bytes = local_path.read_bytes()
                self.media_preview_bytes[media_url] = image_bytes
            except OSError:
                image_bytes = None
        if not image_bytes:
            return None
        try:
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            image.thumbnail((84, 108))
            photo = ImageTk.PhotoImage(image)
            self.media_preview_images[media_url] = photo
            return photo
        except Exception:
            self.media_preview_failed.add(media_url)
            return None

    def _start_media_preview_load(self, media_url: str) -> None:
        local_path = self._local_media_path(media_url)
        if local_path:
            self.media_preview_failed.add(media_url)
            return
        if media_url in self.media_preview_loading or media_url in self.media_preview_failed:
            return
        self.media_preview_loading.add(media_url)
        api_key = self.pexels_key.get().strip()

        def worker() -> None:
            image_bytes: bytes | None = None
            try:
                preview_url = self._media_preview_url(media_url, api_key)
                if preview_url:
                    response = requests.get(preview_url, timeout=8)
                    response.raise_for_status()
                    image_bytes = response.content
            except Exception:
                image_bytes = None

            def finish() -> None:
                self.media_preview_loading.discard(media_url)
                if image_bytes:
                    self.media_preview_bytes[media_url] = image_bytes
                    self.media_preview_failed.discard(media_url)
                else:
                    self.media_preview_failed.add(media_url)
                self._render_lines()

            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _media_preview_url(self, media_url: str, api_key: str | None = None) -> str:
        parsed = urllib.parse.urlparse(media_url)
        suffix = Path(parsed.path).suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            return media_url
        if "pexels.com" not in parsed.netloc:
            return ""

        match = re.search(r"(\d+)(?:/)?$", parsed.path)
        clean_api_key = api_key if api_key is not None else self.pexels_key.get().strip()
        if match and clean_api_key:
            media_id = match.group(1)
            headers = {"Authorization": clean_api_key}
            try:
                if "/video" in parsed.path:
                    response = requests.get(f"https://api.pexels.com/videos/videos/{media_id}", headers=headers, timeout=8)
                    response.raise_for_status()
                    return response.json().get("image", "") or self._pexels_page_preview_url(media_url)
                response = requests.get(f"https://api.pexels.com/v1/photos/{media_id}", headers=headers, timeout=8)
                response.raise_for_status()
                src = response.json().get("src", {})
                return src.get("medium") or src.get("large") or src.get("large2x") or self._pexels_page_preview_url(media_url)
            except Exception:
                return self._pexels_page_preview_url(media_url)
        return self._pexels_page_preview_url(media_url)

    @staticmethod
    def _pexels_page_preview_url(media_url: str) -> str:
        try:
            response = requests.get(media_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            response.raise_for_status()
        except Exception:
            return ""

        for meta_tag in re.findall(r"<meta[^>]+>", response.text, flags=re.IGNORECASE):
            if not re.search(r"(?:og:image|twitter:image)", meta_tag, flags=re.IGNORECASE):
                continue
            content_match = re.search(r'''content=["']([^"']+)["']''', meta_tag, flags=re.IGNORECASE)
            if not content_match:
                content_match = re.search(r'''content=([^\s>]+)''', meta_tag, flags=re.IGNORECASE)
            if content_match:
                return html.unescape(content_match.group(1))
        return ""

    @staticmethod
    def _local_media_path(media_url: str) -> Path | None:
        clean_url = media_url.strip()
        if not clean_url:
            return None
        parsed = urllib.parse.urlparse(clean_url)
        if parsed.scheme == "file":
            path = Path(urllib.parse.unquote(parsed.path))
        elif parsed.scheme and len(parsed.scheme) == 1:
            # No Windows, caminhos como C:\foto.png podem ser interpretados como scheme pelo urlparse.
            path = Path(clean_url).expanduser()
        elif parsed.scheme:
            return None
        else:
            path = Path(clean_url).expanduser()
        if path.exists() and path.suffix.lower() in LOCAL_MEDIA_EXTENSIONS:
            return path
        return None

    @staticmethod
    def _image_to_png_bytes(image: Image.Image) -> bytes:
        output = BytesIO()
        # PNG preserva bem imagens copiadas sem depender do formato original da área de transferência.
        image.save(output, format="PNG")
        return output.getvalue()

    @classmethod
    def _clipboard_image_bytes_from_value(cls, clipboard_value: Any) -> bytes | None:
        if isinstance(clipboard_value, Image.Image):
            return cls._image_to_png_bytes(clipboard_value)
        if isinstance(clipboard_value, (list, tuple)):
            for item in clipboard_value:
                local_path = cls._local_media_path(str(item))
                if local_path and local_path.suffix.lower() in IMAGE_EXTENSIONS:
                    with Image.open(local_path) as image:
                        return cls._image_to_png_bytes(image.convert("RGBA"))
        return None

    def _clipboard_image_bytes(self) -> bytes | None:
        try:
            # ImageGrab.grabclipboard lê imagens reais no clipboard (não apenas texto como pyperclip).
            clipboard_value = ImageGrab.grabclipboard()
        except Exception:
            return None
        return self._clipboard_image_bytes_from_value(clipboard_value)

    def _save_clipboard_image(self, image_bytes: bytes, index: int) -> str:
        CLIPBOARD_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"frase_{index + 1:03d}_{int(time.time() * 1000)}.png"
        output_path = CLIPBOARD_MEDIA_DIR / filename
        output_path.write_bytes(image_bytes)
        return str(output_path)

    def _paste_line_link(self, index: int) -> None:
        image_bytes = self._clipboard_image_bytes()
        if image_bytes:
            media_path = self._save_clipboard_image(image_bytes, index)
            self.used_media_urls.add(media_path)
            self.lines[index].media_url = media_path
            self.media_preview_bytes[media_path] = image_bytes
            self.media_preview_images.pop(media_path, None)
            self.media_preview_failed.discard(media_path)
            self._render_lines()
            self._save_config(show_status=False)
            self.status_text.set(f"Imagem colada na frase {index + 1}.")
            return

        try:
            link = pyperclip.paste().strip()
        except Exception:
            link = ""
        if not link:
            messagebox.showerror(APP_TITLE, "A área de transferência está vazia. Copie um link do Pexels ou uma imagem e clique em Colar link.")
            return
        self.used_media_urls.add(link)
        self.lines[index].media_url = link
        self._render_lines()
        self._save_config(show_status=False)
        self.status_text.set(f"Link colado na frase {index + 1}.")

    def _edit_line_link(self, index: int) -> None:
        line = self.lines[index]

        dialog = Toplevel(self.root)
        dialog.title("Link Pexels")
        dialog.geometry("640x200")
        dialog.configure(bg="#ffffff")
        dialog.transient(self.root)
        dialog.grab_set()
        Label(dialog, text=line.text, bg="#ffffff", fg="#111827", wraplength=580, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20, pady=(18, 8))
        Label(dialog, text="Cole um link de vídeo/foto do Pexels ou deixe vazio para busca automática.", bg="#ffffff", fg="#657084", font=("Segoe UI", 9)).pack(anchor="w", padx=20, pady=(0, 8))
        value = StringVar(value=line.media_url)
        Entry(dialog, textvariable=value, bd=0, bg="#f3f5fb", fg="#111827", font=("Segoe UI", 10)).pack(fill=X, padx=20, ipady=9)

        def save() -> None:
            media_url = value.get().strip()
            if media_url:
                self.used_media_urls.add(media_url)
            self.lines[index].media_url = media_url
            self._render_lines()
            self._save_config(show_status=False)
            dialog.destroy()

        Button(dialog, text="Salvar link", command=save, bg="#5b6cff", fg="#ffffff", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(anchor="e", padx=20, pady=18)

    def _start_single_video_update(self, index: int) -> None:
        self._refresh_lines()
        if index < 0 or index >= len(self.lines):
            messagebox.showerror(APP_TITLE, "Não encontrei essa frase no roteiro sincronizado.")
            return
        if not self.pexels_key.get().strip():
            messagebox.showerror(APP_TITLE, "Informe a chave de API do Pexels na aba APIs.")
            self._show_tab("apis")
            return
        if not self.groq_key.get().strip():
            messagebox.showerror(APP_TITLE, "Informe a chave de API do Groq na aba APIs.")
            self._show_tab("apis")
            return
        self.progress.configure(value=0, maximum=1)
        self.progress_text.set("Gerando outro video...")
        self.status_text.set(f"Procurando outro video para a frase {index + 1}...")
        threading.Thread(target=self._single_video_update_worker, args=(index,), daemon=True).start()

    def _single_video_update_worker(self, index: int) -> None:
        try:
            line = self.lines[index]
            query = self._groq_single_pexels_query(index)
            media_url = self._search_pexels(query, exclude_urls=self._all_media_urls())
            self.used_media_urls.update({line.media_url, media_url})
            self.lines[index].media_url = media_url
            self.root.after(0, self._render_lines)
            self.root.after(0, lambda: self._save_config(show_status=False))
            self.message_queue.put(("step", f"Outro video aplicado na frase {index + 1}."))
            self.message_queue.put(("status", f"Outro video aplicado na frase {index + 1}."))
        except Exception as exc:  # noqa: BLE001 - show desktop-friendly error
            self.message_queue.put(("error", str(exc)))

    def _script_subject_keywords(self) -> str:
        title = self.video_title.get().strip()
        text = " ".join([title, *(line.text for line in self.lines)])
        words = re.findall(r"[A-Za-zÀ-ÿ0-9]+", text)
        stopwords = {
            "a", "o", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das", "e", "em", "no", "na", "nos", "nas",
            "para", "por", "com", "sem", "sobre", "que", "se", "ao", "aos", "mais", "menos", "muito", "muita", "muitos", "muitas",
            "video", "vídeo", "roteiro", "frase", "hoje", "vamos", "falar", "te", "provar", "esse", "essa", "este", "esta",
        }
        keywords: list[str] = []
        for word in words:
            clean = word.strip()
            if len(clean) < 3 or clean.lower() in stopwords:
                continue
            if clean.lower() not in {item.lower() for item in keywords}:
                keywords.append(clean)
            if len(keywords) >= 5:
                break
        return ", ".join(keywords or ([title] if title else []))

    def _ensure_subject_in_query(self, query: str) -> str:
        clean_query = " ".join(str(query).split()).strip(' ,.;:[]{}"\'')
        subject = self.video_title.get().strip()
        if not subject:
            return clean_query
        subject_terms = [word.lower() for word in re.findall(r"[A-Za-zÀ-ÿ0-9]+", subject) if len(word) >= 3]
        subject_aliases = {"china": ["chinese", "great wall", "beijing", "shanghai"]}
        expanded_terms = [term for term in subject_terms]
        for term in subject_terms:
            expanded_terms.extend(subject_aliases.get(term, []))
        query_lower = clean_query.lower()
        if any(term in query_lower for term in expanded_terms):
            return clean_query
        subject_prefix = " ".join(subject.split()[:3])
        return f"{subject_prefix} {clean_query}".strip()

    def _groq_single_pexels_query(self, index: int) -> str:
        context = "\n".join(f"{line_index}. {line.text}" for line_index, line in enumerate(self.lines, start=1))
        current_url = self.lines[index].media_url.strip() or "sem video atual"
        prompt = (
            "Crie uma nova pesquisa para encontrar um video vertical no Pexels para a frase indicada. "
            "A busca DEVE manter o assunto principal do título/roteiro. Por exemplo, se o título for China, todas as buscas devem conter China ou um local/símbolo claramente chinês. "
            "Use a frase apenas para escolher o tipo de cena dentro desse assunto, e gere uma busca diferente da tentativa anterior. "
            "A pesquisa deve estar em inglês, ter 3 a 7 palavras, ser visual, concreta e adequada ao Pexels. "
            "Responda somente JSON válido no formato {\"query\":\"...\"}.\n\n"
            f"Título do vídeo / assunto principal: {self.video_title.get().strip() or 'video'}\n"
            f"Palavras-chave do assunto: {self._script_subject_keywords()}\n"
            f"Frase selecionada ({index + 1}): {self.lines[index].text}\n"
            f"Video atual a evitar: {current_url}\n"
            f"Roteiro completo:\n{context}"
        )
        content = self._groq_chat_content(
            messages=[
                {"role": "system", "content": "Você cria buscas curtas e variadas para vídeos de banco de imagem."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.55,
            max_tokens=180,
        )
        try:
            data = self._json_object_from_text(content)
            query = str(data.get("query", "")).strip()
        except json.JSONDecodeError:
            query = self._clean_script_line(content.splitlines()[0] if content.splitlines() else content)
        query = self._ensure_subject_in_query(query)
        if not query:
            raise RuntimeError("O Groq não retornou uma pesquisa para o novo video.")
        return query

    def _start_video_update(self) -> None:
        self._refresh_lines()
        if not self.lines:
            messagebox.showerror(APP_TITLE, "Adicione pelo menos uma frase ao roteiro.")
            return
        if not self.pexels_key.get().strip():
            messagebox.showerror(APP_TITLE, "Informe a chave de API do Pexels na aba APIs.")
            self._show_tab("apis")
            return
        if not self.groq_key.get().strip():
            messagebox.showerror(APP_TITLE, "Informe a chave de API do Groq na aba APIs.")
            self._show_tab("apis")
            return
        self._save_config()
        self.progress.configure(value=0, maximum=max(len(self.lines), 1))
        self.progress_text.set("Atualizando videos...")
        self.status_text.set("Gerando pesquisas com Groq...")
        threading.Thread(target=self._update_videos_worker, daemon=True).start()

    def _update_videos_worker(self) -> None:
        try:
            phrases = [line.text for line in self.lines]
            queries = self._groq_pexels_queries(phrases)
            for index, (line, query) in enumerate(zip(self.lines, queries, strict=True), start=1):
                self._queue_status(f"Pesquisando vídeo {index}/{len(self.lines)}: {query}", step=True)
                media_url = self._search_pexels(query, exclude_urls=self._all_media_urls())
                self.used_media_urls.add(media_url)
                self.lines[index - 1].media_url = media_url
                self.root.after(0, self._render_lines)
            self.root.after(0, lambda: self._save_config(show_status=False))
            self.message_queue.put(("done", "Videos atualizados com links do Pexels e previews em carregamento."))
        except Exception as exc:  # noqa: BLE001 - show desktop-friendly error
            self.message_queue.put(("error", str(exc)))

    def _groq_pexels_queries(self, phrases: list[str]) -> list[str]:
        context = "\n".join(f"{index}. {phrase}" for index, phrase in enumerate(phrases, start=1))
        prompt = (
            "Você vai criar pesquisas para encontrar vídeos verticais no Pexels. "
            "Todas as pesquisas DEVEM manter o assunto principal do título/roteiro. Por exemplo, se o vídeo é sobre China, busque China, Chinese city, Great Wall, Chinese culture etc.; não use cenas genéricas sem China. "
            "Use cada frase apenas para variar o tipo de cena dentro desse mesmo assunto principal. "
            "As pesquisas devem estar em inglês, com 3 a 7 palavras, visuais, concretas e adequadas ao Pexels. "
            "Responda somente JSON válido no formato {\"queries\":[...]} com exatamente uma pesquisa para cada frase.\n\n"
            f"Título do vídeo / assunto principal: {self.video_title.get().strip() or 'video'}\n"
            f"Palavras-chave do assunto: {self._script_subject_keywords()}\n"
            f"Roteiro:\n{context}"
        )
        content = self._groq_chat_content(
            messages=[
                {"role": "system", "content": "Você cria termos de busca curtos para bancos de vídeos."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=512,
        )
        try:
            data = self._json_object_from_text(content)
        except json.JSONDecodeError:
            raise RuntimeError("O Groq não retornou JSON com as pesquisas de vídeo.")
        queries = data.get("queries")
        if not isinstance(queries, list):
            raise RuntimeError("O Groq não retornou a lista 'queries'.")
        clean_queries = [self._ensure_subject_in_query(str(query).strip()) for query in queries if str(query).strip()]
        if len(clean_queries) != len(phrases):
            raise RuntimeError("O Groq retornou uma quantidade diferente de pesquisas em relação às frases do roteiro.")
        return clean_queries

    def _choose_output_dir(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.output_dir.get() or str(Path.home()))
        if folder:
            self.output_dir.set(folder)
            self._save_config()

    def _start_generation(self) -> None:
        self._refresh_lines()
        if not self.lines:
            messagebox.showerror(APP_TITLE, "Adicione pelo menos uma frase ao roteiro.")
            return
        if not self.pexels_key.get().strip():
            messagebox.showerror(APP_TITLE, "Informe a chave de API do Pexels na aba APIs.")
            self._show_tab("apis")
            return
        out_dir = Path(self.output_dir.get()).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        self._save_config()
        self.progress.configure(value=0, maximum=max(len(self.lines) * 3 + 1, 1))
        self.progress_text.set("Gerando...")
        thread = threading.Thread(target=self._generate_video_worker, daemon=True)
        thread.start()

    def _queue_status(self, text: str, step: bool = False) -> None:
        self.message_queue.put(("step" if step else "status", text))

    def _process_queue(self) -> None:
        try:
            while True:
                kind, text = self.message_queue.get_nowait()
                if kind == "status":
                    self.status_text.set(text)
                elif kind == "step":
                    self.status_text.set(text)
                    self.progress.configure(value=float(self.progress["value"]) + 1)
                elif kind == "done":
                    self.progress_text.set("Concluído")
                    messagebox.showinfo(APP_TITLE, text)
                elif kind == "error":
                    self.progress_text.set("Erro")
                    messagebox.showerror(APP_TITLE, text)
        except queue.Empty:
            pass
        self.root.after(120, self._process_queue)

    def _generate_video_worker(self) -> None:
        try:
            with tempfile.TemporaryDirectory(prefix="videogenerator_") as tmp:
                workdir = Path(tmp)
                ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
                clips: list[Path] = []
                audio_paths: list[Path] = []
                for index, line in enumerate(self.lines, start=1):
                    self._queue_status(f"Gerando áudio {index}/{len(self.lines)}...", step=True)
                    audio_path = workdir / f"audio_{index:03d}.wav"
                    self._generate_tts(line.text, audio_path)
                    audio_paths.append(audio_path)

                for index, (line, audio_path) in enumerate(zip(self.lines, audio_paths, strict=True), start=1):
                    self._queue_status(f"Baixando mídia {index}/{len(self.lines)}...", step=True)
                    media_path = self._download_media(line, workdir, index)

                    self._queue_status(f"Criando cena {index}/{len(self.lines)}...", step=True)
                    clip_path = workdir / f"clip_{index:03d}.mp4"
                    self._create_clip(ffmpeg, media_path, audio_path, clip_path, line.text)
                    clips.append(clip_path)

                self._queue_status("Unindo cenas...", step=True)
                final_path = Path(self.output_dir.get()).expanduser() / f"{self._safe_filename(self.video_title.get())}.mp4"
                self._concat_clips(ffmpeg, clips, final_path, workdir)
                self.message_queue.put(("done", f"Vídeo gerado em:\n{final_path}"))
        except Exception as exc:  # noqa: BLE001 - show desktop-friendly error
            self.message_queue.put(("error", str(exc)))

    def _generate_tts(self, text: str, output_path: Path) -> None:
        """Gera áudio usando Kokoro TTS localmente."""
        if not KOKORO_AVAILABLE:
            raise RuntimeError("Kokoro não está instalado. Instale com: pip install kokoro")
        
        if not self.tts_model_loaded:
            raise RuntimeError("Modelo Kokoro não carregado. Carregue o modelo na aba Audio primeiro.")
        
        try:
            # Mapeia o código de idioma para o formato do Kokoro
            lang_mapping = {
                "pt-br": "p",
                "en-us": "a",
                "en-gb": "b",
                "es-es": "e",
                "fr-fr": "f",
                "de-de": "g",
                "it-it": "i",
                "ja-jp": "j",
                "zh-cn": "z"
            }
            lang_code = lang_mapping.get(self.tts_language.get().lower(), "p")
            
            # Carrega o modelo
            model = KModel()
            # Extrai apenas o nome da voz (sem a descrição)
            voice_full = self.tts_voice_name.get().strip()
            voice_name = voice_full.split()[0] if voice_full else "af_heart"
            
            # Nota: A versão atual do Kokoro (0.9.4) não suporta clonagem de voz
            # a partir de áudio de referência. Apenas vozes pré-treinadas (.pt) são suportadas.
            if self.tts_voice_ref_path.get().strip():
                self._queue_status("Aviso: Clonagem por áudio não disponível nesta versão do Kokoro.", step=True)
            
            # Cria pipeline com modelo
            pipeline = KPipeline(lang_code=lang_code, model=model)
            
            # Gera áudio com Kokoro
            generator = pipeline(text, voice=voice_name)
            
            # Salva o áudio gerado
            with wave.open(str(output_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                
                for chunk in generator:
                    # Converte float32 para int16
                    # Na nova versao do Kokoro, chunk é um objeto Result com propriedade audio
                    if hasattr(chunk, 'audio') and chunk.audio is not None:
                        audio_tensor = chunk.audio
                    elif hasattr(chunk, 'numpy'):
                        audio_tensor = chunk
                    else:
                        audio_tensor = torch.from_numpy(chunk)
                    
                    audio_data = (audio_tensor * 32767).to(torch.int16).numpy()
                    wf.writeframes(audio_data.tobytes())
            
            self._queue_status(f"Áudio gerado: {text[:50]}...", step=True)
            
        except MemoryError:
            raise RuntimeError("Memória insuficiente para gerar áudio. Tente fechar outros programas.")
        except Exception as e:
            raise RuntimeError(f"Erro ao gerar áudio com Kokoro: {e}")

        chunk_seconds = 0.25
        silence_limit = 1.25
        silence_threshold = 0.003
        minimum_record_seconds = min(max(duration * 0.45, 3.0), duration)
        chunks: list[np.ndarray] = []
        speech_started = False
        silent_time = 0.0
        elapsed = 0.0

        def consume_chunk(chunk: np.ndarray) -> bool:
            nonlocal speech_started, silent_time, elapsed
            chunks.append(chunk)
            level = self._audio_level(chunk)
            if level > silence_threshold:
                speech_started = True
                silent_time = 0.0
            elif speech_started:
                silent_time += chunk_seconds
            elapsed += chunk_seconds
            return bool(speech_started and elapsed >= minimum_record_seconds and silent_time >= silence_limit)

        if getattr(self, "_loopback_thread_running", False):
            with self._loopback_lock:
                self._loopback_chunks = []
                self._loopback_collecting = True
            if on_ready is not None:
                on_ready()
            try:
                while elapsed < duration:
                    time.sleep(chunk_seconds)
                    with self._loopback_lock:
                        pending = self._loopback_chunks
                        self._loopback_chunks = []
                    should_stop = False
                    for chunk in pending:
                        should_stop = consume_chunk(chunk) or should_stop
                    if should_stop:
                        break
            finally:
                with self._loopback_lock:
                    self._loopback_collecting = False
                    pending = self._loopback_chunks
                    self._loopback_chunks = []
                for chunk in pending:
                    consume_chunk(chunk)
        else:
            chunk_frames = int(sample_rate * chunk_seconds)
            microphone = self._default_loopback_microphone()
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="data discontinuity in recording.*")
                with microphone.recorder(samplerate=sample_rate) as recorder:
                    if on_ready is not None:
                        on_ready()
                    while elapsed < duration:
                        if consume_chunk(recorder.record(numframes=chunk_frames)):
                            break

        audio = np.concatenate(chunks) if chunks else np.zeros(int(sample_rate * 0.5), dtype=np.float32)
        audio = self._best_mono_audio(audio)
        audio = self._trim_silence(audio, threshold=silence_threshold)
        validation_level = self._audio_validation_level(audio)
        audio = self._normalize_recorded_audio(audio)
        audio = np.clip(audio, -1.0, 1.0)
        pcm = (audio * 32767).astype(np.int16)
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm.tobytes())
        return validation_level

    @staticmethod
    def _best_mono_audio(audio: np.ndarray) -> np.ndarray:
        if audio.ndim <= 1:
            return audio
        channel_rms = np.sqrt(np.mean(np.square(audio), axis=0))
        strongest_channel = int(np.argmax(channel_rms))
        return audio[:, strongest_channel]

    @staticmethod
    def _audio_level(audio: np.ndarray) -> float:
        if audio.size == 0:
            return 0.0
        if audio.ndim <= 1:
            return float(np.sqrt(np.mean(np.square(audio))))
        channel_rms = np.sqrt(np.mean(np.square(audio), axis=0))
        return float(np.max(channel_rms))

    @staticmethod
    def _audio_validation_level(audio: np.ndarray) -> float:
        if audio.size == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(np.square(audio))))
        peak = float(np.max(np.abs(audio)))
        return max(rms, peak * 0.1)

    @staticmethod
    def _normalize_recorded_audio(audio: np.ndarray, target_rms: float = 0.08, max_gain: float = 20.0) -> np.ndarray:
        if audio.size == 0:
            return audio
        rms = float(np.sqrt(np.mean(np.square(audio))))
        peak = float(np.max(np.abs(audio)))
        if rms <= 0.0 or peak <= 0.0001:
            return audio
        gain = min(max(target_rms / rms, 1.0), max_gain)
        if peak * gain > 0.95:
            gain = 0.95 / peak
        return audio * max(gain, 1.0)

    def _estimated_tts_duration(self, text: str) -> float:
        extra = self._safe_float(self.qwen_record_extra.get(), 2.0, 0.0, 30.0)
        return max(8.0, len(text) * 0.12 + extra)

    @staticmethod
    def _trim_silence(audio: np.ndarray, threshold: float = 0.012, padding: int = 4800) -> np.ndarray:
        if audio.size == 0:
            return audio
        loud = np.where(np.abs(audio) > threshold)[0]
        if loud.size == 0:
            return audio
        start = max(int(loud[0]) - padding, 0)
        end = min(int(loud[-1]) + padding, audio.size - 1)
        return audio[start : end + 1]

    def _qwen_coordinates_ready(self) -> bool:
        values = [
            self.qwen_input_x.get(),
            self.qwen_input_y.get(),
            self.qwen_send_x.get(),
            self.qwen_send_y.get(),
            self.qwen_menu_x.get(),
            self.qwen_menu_y.get(),
            self.qwen_read_x.get(),
            self.qwen_read_y.get(),
        ]
        return all(self._safe_int(value, 0, 0, 10000) > 0 for value in values)

    def _download_media(self, line: ScriptLine, workdir: Path, index: int) -> Path:
        media_url = line.media_url.strip()
        if not media_url:
            media_url = self._search_pexels(line.text, exclude_urls=self._all_media_urls())
            self.used_media_urls.add(media_url)
            self.lines[index - 1].media_url = media_url
            self.root.after(0, self._render_lines)
        local_path = self._local_media_path(media_url)
        if local_path:
            # Imagens coladas ficam salvas localmente e podem entrar direto no FFmpeg.
            return local_path
        media_url = self._resolve_pexels_page_url(media_url)
        parsed = urllib.parse.urlparse(media_url)
        suffix = Path(parsed.path).suffix or ".mp4"
        output_path = workdir / f"media_{index:03d}{suffix.split('?')[0]}"
        with requests.get(media_url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with output_path.open("wb") as file:
                shutil.copyfileobj(response.raw, file)
        return output_path

    def _resolve_pexels_page_url(self, media_url: str) -> str:
        parsed = urllib.parse.urlparse(media_url)
        if "pexels.com" not in parsed.netloc or Path(parsed.path).suffix:
            return media_url

        match = re.search(r"(\d+)(?:/)?$", parsed.path)
        if not match:
            return media_url

        media_id = match.group(1)
        headers = {"Authorization": self.pexels_key.get().strip()}
        if "/video" in parsed.path:
            response = requests.get(f"https://api.pexels.com/videos/videos/{media_id}", headers=headers, timeout=30)
            response.raise_for_status()
            files = response.json().get("video_files", [])
            if files:
                best_files = sorted(files, key=lambda item: (item.get("width", 0) < item.get("height", 0), item.get("height", 0)), reverse=True)
                return best_files[0]["link"]
        else:
            response = requests.get(f"https://api.pexels.com/v1/photos/{media_id}", headers=headers, timeout=30)
            response.raise_for_status()
            src = response.json().get("src", {})
            if src.get("large2x"):
                return src["large2x"]
        return media_url

    def _search_pexels(self, query: str, exclude_urls: set[str] | None = None) -> str:
        headers = {"Authorization": self.pexels_key.get().strip()}
        excluded = {self._media_identity(url) for url in (exclude_urls or set()) if url.strip()}
        first_candidate = ""

        def remember_candidate(url: str) -> str | None:
            nonlocal first_candidate
            clean_url = url.strip()
            if not clean_url:
                return None
            if not first_candidate:
                first_candidate = clean_url
            if self._media_identity(clean_url) not in excluded:
                return clean_url
            return None

        video_response = requests.get(
            "https://api.pexels.com/videos/search",
            headers=headers,
            params={"query": query, "per_page": 8, "orientation": "portrait"},
            timeout=30,
        )
        video_response.raise_for_status()
        videos = video_response.json().get("videos", [])
        for video in videos:
            candidate = remember_candidate(str(video.get("url", "")))
            if candidate:
                return candidate
            files = video.get("video_files", [])
            portrait_files = sorted(files, key=lambda item: (item.get("width", 0) < item.get("height", 0), item.get("height", 0)), reverse=True)
            for media_file in portrait_files:
                candidate = remember_candidate(str(media_file.get("link", "")))
                if candidate:
                    return candidate

        photo_response = requests.get(
            "https://api.pexels.com/v1/search",
            headers=headers,
            params={"query": query, "per_page": 8, "orientation": "portrait"},
            timeout=30,
        )
        photo_response.raise_for_status()
        photos = photo_response.json().get("photos", [])
        for photo in photos:
            candidate = remember_candidate(str(photo.get("url", "") or photo.get("src", {}).get("large2x", "")))
            if candidate:
                return candidate
        if first_candidate and not excluded:
            return first_candidate
        raise RuntimeError(f"Nenhuma mídia nova encontrada no Pexels para: {query}")

    @staticmethod
    def _media_identity(media_url: str) -> str:
        parsed = urllib.parse.urlparse(media_url.strip())
        match = re.search(r"(\d+)(?:/)?$", parsed.path)
        if "pexels.com" in parsed.netloc and match:
            return f"pexels:{match.group(1)}"
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", "")).rstrip("/")

    def _logo_file_path(self) -> Path | None:
        clean_path = self.logo_path.get().strip()
        if not clean_path:
            return None
        path = Path(clean_path).expanduser()
        if path.exists() and path.suffix.lower() == ".png" and self._logo_size_fraction() > 0:
            return path
        return None

    def _logo_size_fraction(self) -> float:
        return self._safe_float(self.logo_size.get(), 20.0, 0.0, 100.0) / 100.0

    def _logo_overlay_expression(self) -> tuple[str, str]:
        margin = 36
        position = self.logo_position.get().lower()
        x = str(margin) if "esquerdo" in position else f"W-w-{margin}"
        y = str(margin) if "superior" in position else f"H-h-{margin}"
        return x, y

    def _logo_preview_coordinates(self, canvas_width: int, canvas_height: int, logo_width: int, logo_height: int, margin: int) -> tuple[int, int]:
        position = self.logo_position.get().lower()
        x = margin if "esquerdo" in position else canvas_width - logo_width - margin
        y = margin if "superior" in position else canvas_height - logo_height - margin
        return max(0, x), max(0, y)

    def _create_clip(self, ffmpeg: str, media_path: Path, audio_path: Path, clip_path: Path, subtitle_text: str) -> None:
        audio_duration = self._audio_duration(audio_path)
        image_exts = {".jpg", ".jpeg", ".png", ".webp"}
        is_image = media_path.suffix.lower() in image_exts
        media_duration = 0.0 if is_image else self._media_duration(ffmpeg, media_path)
        extra_after_audio = self._safe_float(self.video_extra_after_audio.get(), 1.0, 0.0, 60.0)
        if media_duration > audio_duration:
            duration = min(media_duration, audio_duration + extra_after_audio)
        elif media_duration > 0:
            duration = audio_duration
        else:
            duration = audio_duration
        video_filter = self._video_filter(subtitle_text, clip_path.with_suffix(".subtitle.ass"), duration, audio_duration)
        logo_path = self._logo_file_path()
        if logo_path:
            logo_width = max(1, int(1080 * self._logo_size_fraction()))
            logo_x, logo_y = self._logo_overlay_expression()
            filter_complex = (
                f"[0:v:0]{video_filter},trim=duration={duration:.3f},setpts=PTS-STARTPTS[base];"
                f"[2:v:0]format=rgba,scale={logo_width}:-1[logo];"
                f"[base][logo]overlay={logo_x}:{logo_y}:format=auto[v];"
                f"[1:a:0]apad,atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[a]"
            )
        else:
            filter_complex = (
                f"[0:v:0]{video_filter},trim=duration={duration:.3f},setpts=PTS-STARTPTS[v];"
                f"[1:a:0]apad,atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[a]"
            )
        if is_image:
            cmd = [
                ffmpeg,
                "-y",
                "-loop",
                "1",
                "-t",
                f"{duration:.3f}",
                "-i",
                str(media_path),
                "-i",
                str(audio_path),
            ]
            if logo_path:
                cmd.extend(["-loop", "1", "-i", str(logo_path)])
            cmd.extend([
                "-filter_complex",
                filter_complex,
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-r",
                FPS,
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                str(clip_path),
            ])
        else:
            cmd = [ffmpeg, "-y"]
            if media_duration <= 0 or media_duration < duration - 0.05:
                cmd.extend(["-stream_loop", "-1"])
            cmd.extend(
                [
                    "-i",
                    str(media_path),
                    "-i",
                    str(audio_path),
                ]
            )
            if logo_path:
                cmd.extend(["-loop", "1", "-i", str(logo_path)])
            cmd.extend(
                [
                    "-t",
                    f"{duration:.3f}",
                    "-filter_complex",
                    filter_complex,
                    "-map",
                    "[v]",
                    "-map",
                    "[a]",
                    "-r",
                    FPS,
                    "-c:v",
                    "libx264",
                    "-c:a",
                    "aac",
                    str(clip_path),
                ]
            )
        self._run_ffmpeg(cmd)

    def _video_filter(
        self,
        subtitle_text: str,
        subtitle_file: Path | None = None,
        clip_duration: float = 0.0,
        speech_duration: float = 0.0,
    ) -> str:
        base_filter = f"scale={VIDEO_SIZE}:force_original_aspect_ratio=increase,crop={VIDEO_SIZE},setsar=1,format=yuv420p"
        if self.subtitle_enabled.get() != "Sim":
            return base_filter
        wrapped_text, font_size, line_spacing, box_border = self._subtitle_layout(subtitle_text)
        if subtitle_file is None:
            subtitle_file = Path(tempfile.gettempdir()) / "videogenerator_subtitle.ass"
        self._write_progressive_subtitle_file(
            subtitle_file,
            subtitle_text,
            max(clip_duration, speech_duration, 0.1),
            max(min(speech_duration, clip_duration or speech_duration), 0.1),
            font_size,
            line_spacing,
            box_border,
        )
        subtitle_path = self._escape_filter_file_path(subtitle_file)
        return f"{base_filter},subtitles='{subtitle_path}'"

    def _write_progressive_subtitle_file(
        self,
        subtitle_file: Path,
        subtitle_text: str,
        clip_duration: float,
        speech_duration: float,
        font_size: int,
        line_spacing: int,
        box_border: int,
    ) -> None:
        words = subtitle_text.split()
        if not words:
            subtitle_file.write_text("", encoding="utf-8")
            return
        font = self.subtitle_font.get().strip() or "Arial Black"
        primary = self._ass_color(self.subtitle_color.get(), "#FFFFFF")
        highlight = self._ass_color(self.subtitle_highlight_color.get(), "#FFD84D")
        outline = self._ass_color(self.subtitle_outline_color.get(), "#000000")
        back = self._ass_color(self.subtitle_background_color.get(), "#000000", alpha="70")
        border_style = 3 if self.subtitle_background.get() == "Sim" else 1
        outline_width = max(1, box_border if border_style == 3 else 3)
        alignment = self._ass_alignment()
        margin_v = self._ass_margin_v()
        spacing = -max(0, int(font_size * 0.10) - line_spacing)
        speech_duration = max(0.1, min(speech_duration, clip_duration))
        word_duration = max(speech_duration / len(words), 0.04)
        events: list[str] = []
        for index in range(len(words)):
            start = index * word_duration
            end = min((index + 1) * word_duration, speech_duration)
            if end <= start:
                end = start + 0.05
            highlighted_text = self._highlighted_subtitle_text(words, index, font_size, primary, highlight)
            events.append(
                f"Dialogue: 0,{self._ass_timestamp(start)},{self._ass_timestamp(end)},Default,,0,0,0,,{highlighted_text}"
            )
        if clip_duration > speech_duration + 0.05:
            # Após a narração terminar, a frase continua inteira na tela sem palavra destacada durante o respiro da cena.
            normal_text = self._highlighted_subtitle_text(words, None, font_size, primary, highlight)
            events.append(
                f"Dialogue: 0,{self._ass_timestamp(speech_duration)},{self._ass_timestamp(clip_duration)},Default,,0,0,0,,{normal_text}"
            )
        ass_text = "\n".join(
            [
                "[Script Info]",
                "ScriptType: v4.00+",
                "PlayResX: 1080",
                "PlayResY: 1920",
                "ScaledBorderAndShadow: yes",
                "WrapStyle: 2",
                "",
                "[V4+ Styles]",
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
                f"Style: Default,{font},{font_size},{primary},{highlight},{outline},{back},-1,0,0,0,100,100,{spacing},0,{border_style},{outline_width},0,{alignment},80,80,{margin_v},1",
                "",
                "[Events]",
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
                *events,
                "",
            ]
        )
        subtitle_file.write_text(ass_text, encoding="utf-8")

    def _highlighted_subtitle_text(
        self,
        words: list[str],
        highlight_index: int | None,
        font_size: int,
        primary: str,
        highlight: str,
    ) -> str:
        lines = self._subtitle_word_lines(words, font_size)
        rendered_lines: list[str] = []
        for line in lines:
            rendered_words: list[str] = []
            for word_index, word in line:
                escaped_word = self._escape_ass_text(word)
                if word_index == highlight_index:
                    # Overrides ASS trocam apenas a cor da palavra atual e voltam para a cor normal no próximo token.
                    rendered_words.append(f"{{\\c{highlight}&}}{escaped_word}{{\\c{primary}&}}")
                else:
                    rendered_words.append(escaped_word)
            rendered_lines.append(" ".join(rendered_words))
        return r"\N".join(rendered_lines)

    @staticmethod
    def _subtitle_word_lines(words: list[str], font_size: int) -> list[list[tuple[int, str]]]:
        max_chars = max(20, min(48, int(980 / max(font_size * 0.48, 1))))
        lines: list[list[tuple[int, str]]] = []
        current: list[tuple[int, str]] = []
        for index, word in enumerate(words):
            candidate = [*current, (index, word)]
            candidate_text = " ".join(item_word for _item_index, item_word in candidate)
            if current and len(candidate_text) > max_chars:
                lines.append(current)
                current = [(index, word)]
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    def _ass_alignment(self) -> int:
        position = self.subtitle_position.get()
        if position == "Topo":
            return 8
        if position == "Centro":
            return 5
        return 2

    def _ass_margin_v(self) -> int:
        position = self.subtitle_position.get()
        if position == "Topo":
            return 120
        if position == "Centro":
            return 0
        return 240

    @staticmethod
    def _ass_timestamp(seconds: float) -> str:
        safe_seconds = max(seconds, 0.0)
        hours = int(safe_seconds // 3600)
        minutes = int((safe_seconds % 3600) // 60)
        whole_seconds = int(safe_seconds % 60)
        centiseconds = int(round((safe_seconds - int(safe_seconds)) * 100))
        if centiseconds >= 100:
            whole_seconds += 1
            centiseconds = 0
        return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centiseconds:02d}"

    @staticmethod
    def _escape_ass_text(value: str) -> str:
        return value.replace("{", "(").replace("}", ")")

    def _ass_color(self, value: str, fallback: str, alpha: str = "00") -> str:
        color = self._normalize_color(value, fallback)
        red = color[1:3]
        green = color[3:5]
        blue = color[5:7]
        return f"&H{alpha}{blue}{green}{red}"


    def _subtitle_y_expression(self) -> str:
        position = self.subtitle_position.get()
        if position == "Topo":
            return "max(80\\,min(h*0.10\\,h-text_h-80))"
        if position == "Centro":
            return "max(80\\,min((h-text_h)/2\\,h-text_h-80))"
        return "max(80\\,min(h-text_h-h*0.14\\,h-text_h-80))"

    def _subtitle_layout(self, value: str) -> tuple[str, int, int, int]:
        requested_size = self._safe_int(self.subtitle_size.get(), 64, 1, 160)
        position = self.subtitle_position.get()
        max_text_height = 1100 if position == "Centro" else 520
        max_text_height = min(max_text_height, 1920 - 160)
        for font_size in range(requested_size, 23, -2):
            wrapped = self._wrap_subtitle_text(value, font_size)
            line_count = max(1, wrapped.count("\n") + 1)
            line_spacing = max(0, int(font_size * 0.025))
            box_border = max(8, min(18, int(font_size * 0.24)))
            estimated_height = line_count * font_size + max(0, line_count - 1) * line_spacing + box_border * 2 + 8
            if estimated_height <= max_text_height:
                return wrapped, font_size, line_spacing, box_border
        font_size = 24
        return self._wrap_subtitle_text(value, font_size), font_size, 0, 8

    @staticmethod
    def _wrap_subtitle_text(value: str, font_size: int) -> str:
        text = " ".join(value.split())
        if not text:
            return value
        max_chars = max(20, min(48, int(980 / max(font_size * 0.48, 1))))
        lines: list[str] = []
        current = ""
        for word in text.split(" "):
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > max_chars:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return "\n".join(lines)

    @staticmethod
    def _escape_drawtext(value: str) -> str:
        return value.replace("\\", "\\\\").replace("\n", "\\n").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")

    @staticmethod
    def _escape_drawtext_file_path(value: Path) -> str:
        return value.resolve().as_posix().replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

    @staticmethod
    def _escape_filter_file_path(value: Path) -> str:
        return value.resolve().as_posix().replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

    @staticmethod
    def _ffmpeg_color(value: str, fallback: str) -> str:
        color = value.strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            return "0x" + color[1:]
        if re.fullmatch(r"0x[0-9a-fA-F]{6}", color):
            return color
        return fallback

    @staticmethod
    def _normalize_color(value: str, fallback: str) -> str:
        color = value.strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            return color
        return fallback

    @staticmethod
    def _safe_int(value: str, default: int, minimum: int, maximum: int) -> int:
        try:
            number = int(value)
        except ValueError:
            return default
        return min(max(number, minimum), maximum)

    @staticmethod
    def _safe_float(value: str, default: float, minimum: float, maximum: float) -> float:
        try:
            number = float(value.replace(",", "."))
        except ValueError:
            return default
        return min(max(number, minimum), maximum)

    @staticmethod
    def _safe_filename(value: str) -> str:
        name = re.sub(r"[\\/:*?\"<>|]+", "", value.strip())
        name = re.sub(r"\s+", "_", name).strip("._")
        return name or "video_gerado"

    def _concat_clips(self, ffmpeg: str, clips: list[Path], final_path: Path, workdir: Path) -> None:
        temp_output = workdir / "final_without_music.mp4"
        if len(clips) == 1:
            shutil.copy2(clips[0], temp_output)
        else:
            cmd = [ffmpeg, "-y"]
            for clip in clips:
                cmd.extend(["-i", str(clip)])

            filter_parts: list[str] = []
            concat_inputs = ""
            for index in range(len(clips)):
                filter_parts.append(f"[{index}:v:0]setpts=PTS-STARTPTS,scale={VIDEO_SIZE},setsar=1,fps={FPS},format=yuv420p[v{index}]")
                filter_parts.append(f"[{index}:a:0]asetpts=PTS-STARTPTS,aresample=async=1:first_pts=0[a{index}]")
                concat_inputs += f"[v{index}][a{index}]"
            filter_complex = ";".join(filter_parts) + f";{concat_inputs}concat=n={len(clips)}:v=1:a=1[v][a]"

            cmd.extend(
                [
                    "-filter_complex",
                    filter_complex,
                    "-map",
                    "[v]",
                    "-map",
                    "[a]",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    str(temp_output),
                ]
            )
            self._run_ffmpeg(cmd)

        music_file = Path(self.music_path.get()).expanduser()
        volume = self._safe_int(self.music_volume.get(), 20, 0, 100) / 100
        if not self.music_path.get().strip() or not music_file.exists() or volume <= 0:
            shutil.copy2(temp_output, final_path)
            return

        mixed_output = workdir / "final_with_music.mp4"
        mix_cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(temp_output),
            "-stream_loop",
            "-1",
            "-i",
            str(music_file),
            "-filter_complex",
            f"[0:a]volume=1.0[narration];[1:a]volume={volume:.2f}[music];[narration][music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]",
            "-map",
            "0:v:0",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(mixed_output),
        ]
        self._run_ffmpeg(mix_cmd)
        shutil.copy2(mixed_output, final_path)

    def _run_ffmpeg(self, cmd: list[str]) -> None:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr[-2000:] or "FFmpeg falhou sem mensagem de erro.")

    def _media_duration(self, ffmpeg: str, media_path: Path) -> float:
        result = subprocess.run([ffmpeg, "-hide_banner", "-i", str(media_path)], capture_output=True, text=True, check=False)
        output = result.stderr + "\n" + result.stdout
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
        if not match:
            return 0.0
        hours, minutes, seconds = match.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    @staticmethod
    def _audio_duration(audio_path: Path) -> float:
        with wave.open(str(audio_path), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            return frames / float(rate)


if __name__ == "__main__":
    VideoGeneratorApp().run()
