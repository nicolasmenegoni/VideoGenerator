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
from io import BytesIO
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, Button, Canvas, Entry, Frame, Label, StringVar, Text, Tk, Toplevel, filedialog, messagebox, ttk

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageTk
import pyautogui
import pyperclip
import requests
import soundcard as sc

APP_TITLE = "VideoGenerator"
CONFIG_FILE = Path.home() / ".videogenerator_config.json"
VIDEO_SIZE = "1080:1920"
FPS = "30"
GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_SCRIPT_TEXT = "Hoje vamos falar sobre a China.\nEsse país é incrível.\nVamos te provar."


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
        self.video_title = StringVar(value="video_gerado")
        self.output_dir = StringVar(value=str(Path.home() / "Videos"))
        self.video_extra_after_audio = StringVar(value="1")
        self.subtitle_enabled = StringVar(value="Sim")
        self.subtitle_position = StringVar(value="Baixo")
        self.subtitle_color = StringVar(value="#FFFFFF")
        self.subtitle_size = StringVar(value="64")
        self.subtitle_background = StringVar(value="Sim")
        self.subtitle_background_color = StringVar(value="#000000")
        self.subtitle_outline_color = StringVar(value="#000000")
        self.subtitle_font = StringVar(value="Arial Black")
        self.subtitle_preview_text = StringVar(value="Hoje vamos falar sobre a China.")
        self.chatgpt_shortcut = StringVar(value="alt+c")
        self.chatgpt_response_wait = StringVar(value="8")
        self.chatgpt_send_wait = StringVar(value="1")
        self.chatgpt_menu_wait = StringVar(value="1")
        self.chatgpt_menu_x = StringVar(value="0")
        self.chatgpt_menu_y = StringVar(value="0")
        self.chatgpt_input_x = StringVar(value="0")
        self.chatgpt_input_y = StringVar(value="0")
        self.chatgpt_send_x = StringVar(value="0")
        self.chatgpt_send_y = StringVar(value="0")
        self.chatgpt_read_x = StringVar(value="0")
        self.chatgpt_read_y = StringVar(value="0")
        self.chatgpt_record_extra = StringVar(value="2")
        self.music_path = StringVar(value="")
        self.music_volume = StringVar(value="20")
        self.status_text = StringVar(value="Pronto.")
        self.progress_text = StringVar(value="")
        self.chatgpt_window_ready = False
        self.media_preview_images: dict[str, ImageTk.PhotoImage] = {}
        self.media_preview_bytes: dict[str, bytes] = {}
        self.media_preview_loading: set[str] = set()
        self.media_preview_failed: set[str] = set()
        self.script_text_value = DEFAULT_SCRIPT_TEXT
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
        Label(header, text="Gere vídeos verticais com ChatGPT, Pexels e legendas em poucos cliques.", bg="#f6f7fb", fg="#657084", font=("Segoe UI", 10)).pack(anchor="w")

        nav = Frame(shell, bg="#eef1f8", padx=6, pady=6)
        nav.pack(fill=X, pady=(0, 12))
        self._add_nav_button(nav, "apis", "APIs")
        self._add_nav_button(nav, "roteiro", "Roteiro")
        self._add_nav_button(nav, "video", "Video")
        self._add_nav_button(nav, "legendas", "Legendas")
        self._add_nav_button(nav, "audio", "Audio")
        self._add_nav_button(nav, "musica", "Musica")

        self.content = Frame(shell, bg="#ffffff")
        self.content.pack(fill=BOTH, expand=True)

        self.tabs["apis"] = Frame(self.content, bg="#ffffff", padx=24, pady=24)
        self.tabs["roteiro"] = Frame(self.content, bg="#ffffff", padx=24, pady=24)
        self.tabs["video"] = Frame(self.content, bg="#ffffff", padx=24, pady=24)
        self.tabs["legendas"] = Frame(self.content, bg="#ffffff", padx=24, pady=24)
        self.tabs["audio"] = Frame(self.content, bg="#ffffff", padx=24, pady=24)
        self.tabs["musica"] = Frame(self.content, bg="#ffffff", padx=24, pady=24)

        self._build_api_tab(self.tabs["apis"])
        self._build_script_tab(self.tabs["roteiro"])
        self._build_video_tab(self.tabs["video"])
        self._build_subtitles_tab(self.tabs["legendas"])
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
        ttk.Label(parent, text="As chaves do Pexels e do Groq ficam salvas localmente no seu usuário do Windows.", style="Muted.TLabel").pack(anchor="w", pady=(4, 22))

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

        self.script_text = Text(parent, height=12, wrap="word", bd=0, bg="#f3f5fb", fg="#111827", insertbackground="#111827", font=("Segoe UI", 11), padx=14, pady=12)
        self.script_text.pack(fill=BOTH, expand=True)
        self.script_text.insert("1.0", self.script_text_value)

        actions = Frame(parent, bg="#ffffff", pady=12)
        actions.pack(fill=X)
        Button(actions, text="Atualizar roteiro", command=self._refresh_lines, bg="#eef1ff", fg="#27319f", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        Button(actions, text="Gerar roteiro", command=self._start_script_generation, bg="#5b6cff", fg="#ffffff", activebackground="#4657e8", activeforeground="#ffffff", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(side=LEFT, padx=(10, 0))

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
        threading.Thread(target=self._generate_script_worker, args=(title,), daemon=True).start()

    def _generate_script_worker(self, title: str) -> None:
        try:
            lines = self._groq_script_lines(title)
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

    def _groq_script_lines(self, title: str) -> list[str]:
        prompt = (
            "Crie um roteiro curto para um vídeo vertical em português do Brasil com base no título informado. "
            "O roteiro deve ter de 6 a 10 frases curtas, naturais para narração em voz alta, com gancho no começo e fechamento no final. "
            "Cada frase deve funcionar como uma cena separada do vídeo. "
            "Não use numeração, marcadores, emojis, markdown, aspas, chaves, colchetes ou título dentro das frases. "
            "Responda somente com as frases finais, uma por linha, sem JSON e sem texto extra.\n\n"
            f"Título: {title}"
        )
        content = self._groq_chat_content(
            messages=[
                {"role": "system", "content": "Você cria roteiros curtos para vídeos verticais em português do Brasil."},
                {"role": "user", "content": prompt},
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
            self.subtitle_size,
            self.subtitle_background,
            self.subtitle_background_color,
            self.subtitle_outline_color,
            self.subtitle_font,
            self.subtitle_preview_text,
        ]:
            variable.trace_add("write", lambda *_args: self._update_subtitle_preview())
        self._update_subtitle_preview()

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
        bg_color = self._normalize_color(self.subtitle_background_color.get(), "#000000")
        outline_color = self._normalize_color(self.subtitle_outline_color.get(), "#000000")
        font = self.subtitle_font.get().strip() or "Arial"

        box_padding = max(8, preview_size * 2)
        if self.subtitle_background.get() == "Sim":
            canvas.create_rectangle(24, y - box_padding, 276, y + box_padding, fill=bg_color, outline="")
        outline_offset = max(1, min(2, preview_size // 8 or 1))
        for dx, dy in [(-outline_offset, 0), (outline_offset, 0), (0, -outline_offset), (0, outline_offset), (-outline_offset, -outline_offset), (outline_offset, -outline_offset), (-outline_offset, outline_offset), (outline_offset, outline_offset)]:
            canvas.create_text(150 + dx, y + dy, text=text, fill=outline_color, font=(font, preview_size, "bold"), width=230, justify="center")
        canvas.create_text(150, y, text=text, fill=color, font=(font, preview_size, "bold"), width=230, justify="center")

    def _build_audio_tab(self, parent: Frame) -> None:
        top = Frame(parent, bg="#ffffff")
        top.pack(fill=X)
        ttk.Label(top, text="Audio", style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, text="Configure a automação do app do ChatGPT para gerar e gravar a narração.", style="Muted.TLabel").pack(anchor="w", pady=(4, 12))

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

        instructions = (
            "Fluxo usado: abrir o ChatGPT pelo atalho, capturar a janela, localizar automaticamente o campo de texto "
            "e o botão Enviar pela imagem, enviar 'Apenas repita isso com aspas: [frase]', esperar a resposta pelo tempo configurado, "
            "aguardar todo esse tempo e só então procurar os 3 pontinhos novos da última resposta (horizontal ou vertical), abrir o menu, "
            "identificar a área nova e clicar em 'Ler em voz alta'."
        )
        Label(content, text=instructions, bg="#ffffff", fg="#657084", wraplength=760, justify=LEFT, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 14))

        shortcut_card = Frame(content, bg="#f8f9fd", padx=14, pady=12)
        shortcut_card.pack(fill=X, pady=(0, 12))
        self._entry_row(shortcut_card, "Atalho para abrir o ChatGPT", self.chatgpt_shortcut, "Padrão: alt+c. Separe teclas com +, por exemplo: ctrl+shift+g.")
        self._entry_row(shortcut_card, "Esperar antes de capturar/enviar (segundos)", self.chatgpt_send_wait, "Tempo para o app do ChatGPT abrir antes da captura automática da janela.")
        self._entry_row(shortcut_card, "Tempo de espera da resposta (segundos)", self.chatgpt_response_wait, "Padrão: 8 segundos antes de procurar os 3 pontinhos novos da última resposta.")
        self._entry_row(shortcut_card, "Esperar após 3 pontinhos (segundos)", self.chatgpt_menu_wait, "Padrão: 1 segundo antes de capturar o menu e clicar em Ler em voz alta.")

        auto_card = Frame(content, bg="#f8f9fd", padx=14, pady=12)
        auto_card.pack(fill=X, pady=(0, 12))
        Label(auto_card, text="Detecção automática pela janela", bg="#f8f9fd", fg="#111827", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))
        Label(
            auto_card,
            text=(
                "Não é mais necessário informar coordenadas. Deixe o app do ChatGPT visível em tema escuro: "
                "o VideoGenerator captura a janela ativa, encontra o campo de mensagem, o botão Enviar, "
                "os 3 pontinhos novos da última resposta e a opção Ler em voz alta automaticamente."
            ),
            bg="#f8f9fd",
            fg="#657084",
            wraplength=720,
            justify=LEFT,
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        recording_card = Frame(content, bg="#f8f9fd", padx=14, pady=12)
        recording_card.pack(fill=X, pady=(0, 12))
        self._entry_row(recording_card, "Tempo extra de gravação (segundos)", self.chatgpt_record_extra, "O app estima a duração pela quantidade de caracteres e soma esse extra.")
        Label(recording_card, text="Dica: se as últimas opções não aparecerem, use a barra de rolagem desta aba.", bg="#f8f9fd", fg="#657084", font=("Segoe UI", 9)).pack(anchor="w")

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
                self.subtitle_size.set(data.get("subtitle_size", self.subtitle_size.get()))
                self.subtitle_background.set(data.get("subtitle_background", self.subtitle_background.get()))
                self.subtitle_background_color.set(data.get("subtitle_background_color", self.subtitle_background_color.get()))
                self.subtitle_outline_color.set(data.get("subtitle_outline_color", self.subtitle_outline_color.get()))
                self.subtitle_font.set(data.get("subtitle_font", self.subtitle_font.get()))
                self.subtitle_preview_text.set(data.get("subtitle_preview_text", self.subtitle_preview_text.get()))
                self.chatgpt_shortcut.set(data.get("chatgpt_shortcut", self.chatgpt_shortcut.get()))
                self.chatgpt_response_wait.set(data.get("chatgpt_response_wait", self.chatgpt_response_wait.get()))
                self.chatgpt_send_wait.set(data.get("chatgpt_send_wait", self.chatgpt_send_wait.get()))
                self.chatgpt_menu_wait.set(data.get("chatgpt_menu_wait", self.chatgpt_menu_wait.get()))
                self.chatgpt_menu_x.set(data.get("chatgpt_menu_x", self.chatgpt_menu_x.get()))
                self.chatgpt_menu_y.set(data.get("chatgpt_menu_y", self.chatgpt_menu_y.get()))
                self.chatgpt_input_x.set(data.get("chatgpt_input_x", self.chatgpt_input_x.get()))
                self.chatgpt_input_y.set(data.get("chatgpt_input_y", self.chatgpt_input_y.get()))
                self.chatgpt_send_x.set(data.get("chatgpt_send_x", self.chatgpt_send_x.get()))
                self.chatgpt_send_y.set(data.get("chatgpt_send_y", self.chatgpt_send_y.get()))
                self.chatgpt_read_x.set(data.get("chatgpt_read_x", self.chatgpt_read_x.get()))
                self.chatgpt_read_y.set(data.get("chatgpt_read_y", self.chatgpt_read_y.get()))
                self.chatgpt_record_extra.set(data.get("chatgpt_record_extra", self.chatgpt_record_extra.get()))
                self.music_path.set(data.get("music_path", self.music_path.get()))
                self.music_volume.set(data.get("music_volume", self.music_volume.get()))
            except json.JSONDecodeError:
                pass

    def _save_config(self, show_status: bool = True) -> None:
        self.script_text_value = self._script_text_content()
        data = {
            "pexels_key": self.pexels_key.get().strip(),
            "groq_key": self.groq_key.get().strip(),
            "video_title": self.video_title.get().strip(),
            "script_text": self.script_text_value,
            "script_lines": self._config_script_lines(),
            "output_dir": self.output_dir.get().strip(),
            "video_extra_after_audio": self.video_extra_after_audio.get().strip(),
            "subtitle_enabled": self.subtitle_enabled.get().strip(),
            "subtitle_position": self.subtitle_position.get().strip(),
            "subtitle_color": self.subtitle_color.get().strip(),
            "subtitle_size": self.subtitle_size.get().strip(),
            "subtitle_background": self.subtitle_background.get().strip(),
            "subtitle_background_color": self.subtitle_background_color.get().strip(),
            "subtitle_outline_color": self.subtitle_outline_color.get().strip(),
            "subtitle_font": self.subtitle_font.get().strip(),
            "subtitle_preview_text": self.subtitle_preview_text.get().strip(),
            "chatgpt_shortcut": self.chatgpt_shortcut.get().strip(),
            "chatgpt_response_wait": self.chatgpt_response_wait.get().strip(),
            "chatgpt_send_wait": self.chatgpt_send_wait.get().strip(),
            "chatgpt_menu_wait": self.chatgpt_menu_wait.get().strip(),
            "chatgpt_menu_x": self.chatgpt_menu_x.get().strip(),
            "chatgpt_menu_y": self.chatgpt_menu_y.get().strip(),
            "chatgpt_input_x": self.chatgpt_input_x.get().strip(),
            "chatgpt_input_y": self.chatgpt_input_y.get().strip(),
            "chatgpt_send_x": self.chatgpt_send_x.get().strip(),
            "chatgpt_send_y": self.chatgpt_send_y.get().strip(),
            "chatgpt_read_x": self.chatgpt_read_x.get().strip(),
            "chatgpt_read_y": self.chatgpt_read_y.get().strip(),
            "chatgpt_record_extra": self.chatgpt_record_extra.get().strip(),
            "music_path": self.music_path.get().strip(),
            "music_volume": self.music_volume.get().strip(),
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
        if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
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

    def _paste_line_link(self, index: int) -> None:
        link = pyperclip.paste().strip()
        if not link:
            messagebox.showerror(APP_TITLE, "A área de transferência está vazia. Copie um link do Pexels e clique em Colar link.")
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

    def _groq_single_pexels_query(self, index: int) -> str:
        context = "\n".join(f"{line_index}. {line.text}" for line_index, line in enumerate(self.lines, start=1))
        current_url = self.lines[index].media_url.strip() or "sem video atual"
        prompt = (
            "Crie uma nova pesquisa para encontrar um video vertical no Pexels para a frase indicada. "
            "Use o contexto completo do roteiro, mas gere uma busca diferente da tentativa anterior. "
            "A pesquisa deve estar em inglês, ter 2 a 6 palavras, ser visual e concreta. "
            "Responda somente JSON válido no formato {\"query\":\"...\"}.\n\n"
            f"Título do vídeo: {self.video_title.get().strip() or 'video'}\n"
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
            "Use o contexto completo do roteiro, mas gere uma pesquisa específica para cada frase. "
            "As pesquisas devem estar em inglês, com 2 a 6 palavras, visuais, concretas, sem nomes protegidos quando houver alternativa genérica. "
            "Responda somente JSON válido no formato {\"queries\":[...]} com exatamente uma pesquisa para cada frase.\n\n"
            f"Título do vídeo: {self.video_title.get().strip() or 'video'}\n"
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
        clean_queries = [str(query).strip() for query in queries if str(query).strip()]
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
        self.chatgpt_window_ready = False
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
                with self._continuous_loopback_recorder():
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
        quoted_text = text.replace('"', "'")
        prompt = f'Apenas repita isso com aspas: "{quoted_text}"'
        shortcut_keys = [part.strip().lower() for part in self.chatgpt_shortcut.get().split("+") if part.strip()]
        if not shortcut_keys:
            shortcut_keys = ["alt", "c"]

        if not self.chatgpt_window_ready:
            pyautogui.hotkey(*shortcut_keys)
            time.sleep(self._safe_float(self.chatgpt_send_wait.get(), 1.0, 0.2, 10.0))
            self.chatgpt_window_ready = True
        else:
            time.sleep(0.25)
        pyautogui.press("esc")
        time.sleep(0.15)
        pyautogui.hotkey("ctrl", "end")
        time.sleep(0.15)

        initial_capture = self._capture_chatgpt_window()
        composer = self._find_chatgpt_composer(initial_capture.image)
        input_point = self._to_screen(initial_capture, self._composer_input_point(composer))
        pyautogui.click(input_point.x, input_point.y)
        time.sleep(0.2)
        pyperclip.copy(prompt)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)

        typed_capture = self._capture_chatgpt_window()
        typed_composer = self._find_chatgpt_composer(typed_capture.image)
        send_point = self._to_screen(typed_capture, self._find_chatgpt_send_button(typed_capture.image, typed_composer))
        pyautogui.click(send_point.x, send_point.y)
        time.sleep(0.75)
        sent_capture = self._capture_chatgpt_window()

        wait_seconds = self._safe_float(self.chatgpt_response_wait.get(), 8.0, 1.0, 120.0)
        response_capture, local_menu_point = self._wait_for_response_more_button(sent_capture, wait_seconds)
        menu_point = self._to_screen(response_capture, local_menu_point)
        record_duration = self._estimated_tts_duration(text)

        self._play_read_aloud_and_record(response_capture, menu_point, output_path, record_duration)

    def _play_read_aloud_and_record(
        self,
        response_capture: WindowCapture,
        menu_point: ScreenPoint,
        output_path: Path,
        record_duration: float,
    ) -> float:
        pyautogui.click(menu_point.x, menu_point.y)
        time.sleep(self._safe_float(self.chatgpt_menu_wait.get(), 1.0, 0.2, 10.0))
        menu_capture = self._capture_chatgpt_window()
        read_point = self._to_screen(menu_capture, self._find_read_aloud_point(response_capture.image, menu_capture.image, menu_point, menu_capture))
        def start_read_aloud() -> None:
            pyautogui.click(read_point.x, read_point.y)
            time.sleep(0.05)

        return self._record_system_audio(output_path, record_duration, on_ready=start_read_aloud)

    def _capture_chatgpt_window(self) -> WindowCapture:
        window = None
        try:
            if hasattr(pyautogui, "getActiveWindow"):
                window = pyautogui.getActiveWindow()
        except Exception:
            window = None

        if window and getattr(window, "width", 0) > 200 and getattr(window, "height", 0) > 200:
            left = max(int(window.left), 0)
            top = max(int(window.top), 0)
            width = int(window.width)
            height = int(window.height)
            return WindowCapture(pyautogui.screenshot(region=(left, top, width, height)), left, top)

        return WindowCapture(pyautogui.screenshot(), 0, 0)

    @staticmethod
    def _to_screen(capture: WindowCapture, point: ScreenPoint) -> ScreenPoint:
        return ScreenPoint(capture.offset_x + point.x, capture.offset_y + point.y)

    @staticmethod
    def _image_array(image: Any) -> np.ndarray:
        if hasattr(image, "convert"):
            image = image.convert("RGB")
        array = np.asarray(image)
        if array.ndim == 2:
            array = np.repeat(array[:, :, None], 3, axis=2)
        if array.shape[2] > 3:
            array = array[:, :, :3]
        return array.astype(np.int16)

    def _find_chatgpt_composer(self, image: Any) -> ScreenBounds:
        array = self._image_array(image)
        height, width, _ = array.shape
        channels_spread = array.max(axis=2) - array.min(axis=2)
        gray_mask = (
            (array[:, :, 0] >= 16)
            & (array[:, :, 0] <= 82)
            & (array[:, :, 1] >= 16)
            & (array[:, :, 1] <= 82)
            & (array[:, :, 2] >= 16)
            & (array[:, :, 2] <= 82)
            & (channels_spread <= 18)
        )
        gray_mask[: int(height * 0.45), :] = False

        row_counts = gray_mask.sum(axis=1)
        row_threshold = max(80, int(width * 0.25))
        segments: list[tuple[int, int]] = []
        segment_start: int | None = None
        for row, count in enumerate(row_counts):
            if count >= row_threshold and segment_start is None:
                segment_start = row
            elif count < row_threshold and segment_start is not None:
                if row - segment_start >= 35:
                    segments.append((segment_start, row))
                segment_start = None
        if segment_start is not None and height - segment_start >= 35:
            segments.append((segment_start, height))
        if not segments:
            return self._fallback_chatgpt_composer(width, height)

        top, bottom = max(segments, key=lambda item: item[1])
        band = gray_mask[top:bottom, :]
        col_counts = band.sum(axis=0)
        col_threshold = max(20, int((bottom - top) * 0.25))
        cols = np.where(col_counts >= col_threshold)[0]
        if cols.size == 0:
            return self._fallback_chatgpt_composer(width, height)
        left = max(int(cols[0]), int(width * 0.02))
        right = min(int(cols[-1]) + 1, int(width * 0.98))
        if bottom - top < 35 or right - left < max(120, int(width * 0.25)):
            return self._fallback_chatgpt_composer(width, height)
        return ScreenBounds(left, int(top), right, int(bottom))

    @staticmethod
    def _fallback_chatgpt_composer(width: int, height: int) -> ScreenBounds:
        return ScreenBounds(
            max(12, int(width * 0.035)),
            max(0, height - max(120, int(height * 0.16))),
            min(width - 12, int(width * 0.965)),
            max(1, height - max(24, int(height * 0.04))),
        )

    @staticmethod
    def _composer_input_point(composer: ScreenBounds) -> ScreenPoint:
        return ScreenPoint(composer.left + min(max(composer.width // 4, 80), 180), composer.top + composer.height // 2)

    def _find_chatgpt_send_button(self, image: Any, composer: ScreenBounds) -> ScreenPoint:
        array = self._image_array(image)
        search_left = composer.left + int(composer.width * 0.68)
        search = array[composer.top : composer.bottom, search_left : composer.right]
        white_mask = (search[:, :, 0] >= 225) & (search[:, :, 1] >= 225) & (search[:, :, 2] >= 225)
        ys, xs = np.where(white_mask)
        if ys.size:
            components = self._components(white_mask, min_area=60)
            if components:
                best = max(components, key=lambda bounds: bounds.width * bounds.height)
                return ScreenPoint(search_left + best.center.x, composer.top + best.center.y)
            return ScreenPoint(search_left + int(np.median(xs)), composer.top + int(np.median(ys)))
        return ScreenPoint(composer.right - 36, composer.top + composer.height // 2)

    def _wait_for_response_more_button(self, before_capture: WindowCapture, timeout: float) -> tuple[WindowCapture, ScreenPoint]:
        before_candidates = self._response_more_candidates(before_capture.image)
        time.sleep(max(timeout, 1.0))

        capture = self._capture_chatgpt_window()
        after_candidates = self._response_more_candidates(capture.image)
        best_candidate = (
            self._best_new_more_candidate(before_candidates, after_candidates)
            or self._best_changed_more_candidate(before_capture.image, capture.image, after_candidates)
        )
        if best_candidate is not None:
            return capture, best_candidate

        settle_deadline = time.monotonic() + 3.0
        while time.monotonic() < settle_deadline:
            time.sleep(0.35)
            capture = self._capture_chatgpt_window()
            after_candidates = self._response_more_candidates(capture.image)
            best_candidate = (
                self._best_new_more_candidate(before_candidates, after_candidates)
                or self._best_changed_more_candidate(before_capture.image, capture.image, after_candidates)
            )
            if best_candidate is not None:
                return capture, best_candidate

        if after_candidates:
            return capture, self._select_response_more_candidate(capture.image, after_candidates)

        raise RuntimeError(
            "Não consegui localizar os 3 pontinhos da resposta do ChatGPT depois da espera configurada. "
            "Aumente o tempo de espera da resposta na aba Audio se o ChatGPT ainda estiver escrevendo."
        )

    def _find_response_more_button(self, image: Any) -> ScreenPoint:
        candidates = self._response_more_candidates(image)
        if not candidates:
            raise RuntimeError("Não consegui localizar os 3 pontinhos da resposta do ChatGPT na captura da janela.")
        return self._select_response_more_candidate(image, candidates)

    def _response_more_candidates(self, image: Any) -> list[ScreenPoint]:
        array = self._image_array(image)
        height, _, _ = array.shape
        channels_spread = array.max(axis=2) - array.min(axis=2)
        bright_mask = (
            (array[:, :, 0] >= 140)
            & (array[:, :, 1] >= 140)
            & (array[:, :, 2] >= 140)
            & (channels_spread <= 70)
        )
        bright_mask[: int(height * 0.14), :] = False
        try:
            composer = self._find_chatgpt_composer(image)
            if composer.top > int(height * 0.60):
                bright_mask[max(composer.top - 4, 0) :, :] = False
            else:
                bright_mask[int(height * 0.82) :, :] = False
        except RuntimeError:
            bright_mask[int(height * 0.82) :, :] = False

        tiny = [
            component
            for component in self._components(bright_mask, min_area=2)
            if 1 <= component.width <= 14
            and 1 <= component.height <= 14
            and component.width * component.height <= 130
        ]
        centers = [component.center for component in tiny]
        candidates: list[ScreenPoint] = []

        def add_candidate(candidate: ScreenPoint) -> None:
            if not any(abs(candidate.x - existing.x) <= 3 and abs(candidate.y - existing.y) <= 3 for existing in candidates):
                candidates.append(candidate)

        for first in centers:
            horizontal_neighbors = [point for point in centers if abs(point.y - first.y) <= 6 and 3 <= point.x - first.x <= 34]
            for second in horizontal_neighbors:
                third_options = [point for point in centers if abs(point.y - first.y) <= 6 and 3 <= point.x - second.x <= 34]
                for third in third_options:
                    span = third.x - first.x
                    first_gap = second.x - first.x
                    second_gap = third.x - second.x
                    if 8 <= span <= 52 and max(first_gap, second_gap) <= min(first_gap, second_gap) * 2.6:
                        add_candidate(ScreenPoint((first.x + third.x) // 2, int(round((first.y + second.y + third.y) / 3))))

            vertical_neighbors = [point for point in centers if abs(point.x - first.x) <= 6 and 3 <= point.y - first.y <= 34]
            for second in vertical_neighbors:
                third_options = [point for point in centers if abs(point.x - first.x) <= 6 and 3 <= point.y - second.y <= 34]
                for third in third_options:
                    span = third.y - first.y
                    first_gap = second.y - first.y
                    second_gap = third.y - second.y
                    if 8 <= span <= 52 and max(first_gap, second_gap) <= min(first_gap, second_gap) * 2.6:
                        add_candidate(ScreenPoint(int(round((first.x + second.x + third.x) / 3)), (first.y + third.y) // 2))
        return candidates

    def _select_response_more_candidate(self, image: Any, candidates: list[ScreenPoint]) -> ScreenPoint:
        bottom_y = max(point.y for point in candidates)
        bottom_row = [point for point in candidates if abs(point.y - bottom_y) <= 8]
        return max(bottom_row, key=lambda point: point.x)

    @staticmethod
    def _best_new_more_candidate(before_candidates: list[ScreenPoint], after_candidates: list[ScreenPoint]) -> ScreenPoint | None:
        new_candidates = [
            candidate
            for candidate in after_candidates
            if not any(abs(candidate.x - before.x) <= 10 and abs(candidate.y - before.y) <= 10 for before in before_candidates)
        ]
        if not new_candidates:
            if before_candidates:
                before_bottom = max(point.y for point in before_candidates)
                lower_candidates = [candidate for candidate in after_candidates if candidate.y > before_bottom + 12]
                if lower_candidates:
                    return max(lower_candidates, key=lambda point: (point.y, point.x))
            return None
        return max(new_candidates, key=lambda point: (point.y, point.x))

    def _best_changed_more_candidate(self, before_image: Any, after_image: Any, candidates: list[ScreenPoint]) -> ScreenPoint | None:
        before = self._image_array(before_image)
        after = self._image_array(after_image)
        min_height = min(before.shape[0], after.shape[0])
        min_width = min(before.shape[1], after.shape[1])
        diff = np.abs(after[:min_height, :min_width] - before[:min_height, :min_width]).max(axis=2)
        scored_candidates: list[tuple[int, ScreenPoint]] = []
        for point in candidates:
            left = max(point.x - 60, 0)
            right = min(point.x + 60, min_width)
            top = max(point.y - 50, 0)
            bottom = min(point.y + 35, min_height)
            if right <= left or bottom <= top:
                continue
            score = int((diff[top:bottom, left:right] > 28).sum())
            if score >= 80:
                scored_candidates.append((score, point))
        if not scored_candidates:
            return None
        return max(scored_candidates, key=lambda item: (item[0], item[1].y))[1]

    def _find_read_aloud_point(self, before_image: Any, after_image: Any, clicked_menu_point: ScreenPoint, after_capture: WindowCapture) -> ScreenPoint:
        before = self._image_array(before_image)
        after = self._image_array(after_image)
        min_height = min(before.shape[0], after.shape[0])
        min_width = min(before.shape[1], after.shape[1])
        diff = np.abs(after[:min_height, :min_width] - before[:min_height, :min_width]).max(axis=2)
        changed_mask = diff > 25
        components = [component for component in self._components(changed_mask, min_area=120) if component.width > 30 and component.height > 12]

        local_click = ScreenPoint(clicked_menu_point.x - after_capture.offset_x, clicked_menu_point.y - after_capture.offset_y)
        if components:
            nearby = [
                component
                for component in components
                if abs(component.center.x - local_click.x) <= 320 and abs(component.center.y - local_click.y) <= 320
            ]
            component = max(nearby or components, key=lambda bounds: bounds.width * bounds.height)
            read_x = component.left + min(max(int(component.width * 0.28), 70), component.width - 12)
            read_y = component.bottom - min(max(component.height // 7, 24), 36)
            return ScreenPoint(read_x, read_y)

        return ScreenPoint(local_click.x + 90, max(local_click.y - 55, 0))

    @staticmethod
    def _components(mask: np.ndarray, min_area: int = 1) -> list[ScreenBounds]:
        height, width = mask.shape
        visited = np.zeros(mask.shape, dtype=bool)
        components: list[ScreenBounds] = []
        for y in range(height):
            xs = np.where(mask[y] & ~visited[y])[0]
            for x_start in xs:
                if visited[y, x_start] or not mask[y, x_start]:
                    continue
                stack = [(int(x_start), y)]
                visited[y, x_start] = True
                min_x = max_x = int(x_start)
                min_y = max_y = y
                area = 0
                while stack:
                    x, current_y = stack.pop()
                    area += 1
                    min_x = min(min_x, x)
                    max_x = max(max_x, x)
                    min_y = min(min_y, current_y)
                    max_y = max(max_y, current_y)
                    for nx in (x - 1, x, x + 1):
                        for ny in (current_y - 1, current_y, current_y + 1):
                            if nx == x and ny == current_y:
                                continue
                            if 0 <= nx < width and 0 <= ny < height and not visited[ny, nx] and mask[ny, nx]:
                                visited[ny, nx] = True
                                stack.append((nx, ny))
                if area >= min_area:
                    components.append(ScreenBounds(min_x, min_y, max_x + 1, max_y + 1))
        return components

    def _default_loopback_microphone(self) -> Any:
        speaker = sc.default_speaker()
        speaker_name = str(getattr(speaker, "name", speaker))
        try:
            microphone = sc.get_microphone(id=speaker_name, include_loopback=True)
            if microphone is not None:
                return microphone
        except Exception:
            pass

        microphones = list(sc.all_microphones(include_loopback=True))
        speaker_words = {word for word in re.split(r"\W+", speaker_name.lower()) if len(word) >= 3}
        loopback_microphones = [microphone for microphone in microphones if "loopback" in str(getattr(microphone, "name", microphone)).lower()]
        for microphone in loopback_microphones or microphones:
            microphone_name = str(getattr(microphone, "name", microphone)).lower()
            if speaker_words and any(word in microphone_name for word in speaker_words):
                return microphone
        if loopback_microphones:
            return loopback_microphones[0]
        if microphones:
            return microphones[0]
        raise RuntimeError("Não encontrei um dispositivo de gravação loopback para capturar o áudio do sistema.")

    @contextmanager
    def _continuous_loopback_recorder(self):
        sample_rate = 48000
        chunk_seconds = 0.25
        chunk_frames = int(sample_rate * chunk_seconds)
        if getattr(self, "_loopback_thread_running", False):
            yield
            return

        microphone = self._default_loopback_microphone()
        stop_event = threading.Event()
        lock = threading.Lock()
        self._loopback_chunks: list[np.ndarray] = []
        self._loopback_collecting = False
        self._loopback_lock = lock
        self._loopback_sample_rate = sample_rate
        self._loopback_chunk_seconds = chunk_seconds
        self._loopback_thread_running = True

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="data discontinuity in recording.*")
            with microphone.recorder(samplerate=sample_rate) as recorder:
                def drain_loop() -> None:
                    while not stop_event.is_set():
                        try:
                            chunk = recorder.record(numframes=chunk_frames)
                        except Exception:
                            if not stop_event.is_set():
                                time.sleep(chunk_seconds)
                            continue
                        with lock:
                            if self._loopback_collecting:
                                self._loopback_chunks.append(chunk)

                thread = threading.Thread(target=drain_loop, daemon=True)
                thread.start()
                try:
                    yield
                finally:
                    stop_event.set()
                    thread.join(timeout=2.0)
                    self._loopback_thread_running = False
                    self._loopback_collecting = False
                    self._loopback_chunks = []

    def _record_system_audio(self, output_path: Path, duration: float, on_ready: Callable[[], None] | None = None) -> float:
        sample_rate = 48000
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
        extra = self._safe_float(self.chatgpt_record_extra.get(), 2.0, 0.0, 30.0)
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

    def _chatgpt_coordinates_ready(self) -> bool:
        values = [
            self.chatgpt_input_x.get(),
            self.chatgpt_input_y.get(),
            self.chatgpt_send_x.get(),
            self.chatgpt_send_y.get(),
            self.chatgpt_menu_x.get(),
            self.chatgpt_menu_y.get(),
            self.chatgpt_read_x.get(),
            self.chatgpt_read_y.get(),
        ]
        return all(self._safe_int(value, 0, 0, 10000) > 0 for value in values)

    def _download_media(self, line: ScriptLine, workdir: Path, index: int) -> Path:
        media_url = line.media_url.strip()
        if not media_url:
            media_url = self._search_pexels(line.text, exclude_urls=self._all_media_urls())
            self.used_media_urls.add(media_url)
            self.lines[index - 1].media_url = media_url
            self.root.after(0, self._render_lines)
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
        video_filter = self._video_filter(subtitle_text, clip_path.with_suffix(".subtitle.txt"))
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

    def _video_filter(self, subtitle_text: str, subtitle_file: Path | None = None) -> str:
        base_filter = f"scale={VIDEO_SIZE}:force_original_aspect_ratio=increase,crop={VIDEO_SIZE},setsar=1,format=yuv420p"
        if self.subtitle_enabled.get() != "Sim":
            return base_filter
        font = self._escape_drawtext(self.subtitle_font.get().strip() or "Arial")
        wrapped_text, font_size, line_spacing, box_border = self._subtitle_layout(subtitle_text)
        if subtitle_file is None:
            subtitle_file = Path(tempfile.gettempdir()) / "videogenerator_subtitle.txt"
        subtitle_file.write_text(wrapped_text, encoding="utf-8")
        textfile = self._escape_drawtext_file_path(subtitle_file)
        font_color = self._ffmpeg_color(self.subtitle_color.get(), "0xFFFFFF")
        y_expr = self._subtitle_y_expression()
        box_enabled = "1" if self.subtitle_background.get() == "Sim" else "0"
        box_color = self._ffmpeg_color(self.subtitle_background_color.get(), "0x000000")
        outline_color = self._ffmpeg_color(self.subtitle_outline_color.get(), "0x000000")
        drawtext = (
            "drawtext="
            f"font='{font}':"
            f"textfile='{textfile}':"
            f"fontcolor={font_color}:"
            f"fontsize={font_size}:"
            f"box={box_enabled}:"
            f"boxcolor={box_color}@0.70:"
            f"boxborderw={box_border}:"
            "borderw=3:"
            f"bordercolor={outline_color}:"
            f"line_spacing={line_spacing}:"
            "fix_bounds=1:"
            "x=max(80\\,min((w-text_w)/2\\,w-text_w-80)):"
            f"y={y_expr}"
        )
        return f"{base_filter},{drawtext}"

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
