from __future__ import annotations

import json
import queue
import time
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.parse
import wave
from dataclasses import dataclass
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, Button, Canvas, Entry, Frame, Label, StringVar, Text, Tk, Toplevel, filedialog, messagebox, ttk

import imageio_ffmpeg
import numpy as np
import pyautogui
import pyperclip
import requests
import soundcard as sc

APP_TITLE = "VideoGenerator"
CONFIG_FILE = Path.home() / ".videogenerator_config.json"
VIDEO_SIZE = "1080:1920"
FPS = "30"


@dataclass
class ScriptLine:
    text: str
    media_url: str = ""


class VideoGeneratorApp:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1040x760")
        self.root.minsize(900, 660)
        self.root.configure(bg="#f6f7fb")

        self.pexels_key = StringVar()
        self.video_title = StringVar(value="video_gerado")
        self.output_dir = StringVar(value=str(Path.home() / "Videos"))
        self.subtitle_enabled = StringVar(value="Sim")
        self.subtitle_position = StringVar(value="Baixo")
        self.subtitle_color = StringVar(value="#FFFFFF")
        self.subtitle_size = StringVar(value="64")
        self.subtitle_background = StringVar(value="Sim")
        self.subtitle_background_color = StringVar(value="#000000")
        self.subtitle_outline_color = StringVar(value="#000000")
        self.subtitle_font = StringVar(value="Arial")
        self.subtitle_preview_text = StringVar(value="Hoje vamos falar sobre a China.")
        self.chatgpt_shortcut = StringVar(value="alt+c")
        self.chatgpt_response_wait = StringVar(value="8")
        self.chatgpt_send_wait = StringVar(value="1")
        self.chatgpt_menu_wait = StringVar(value="1")
        self.chatgpt_menu_x = StringVar(value="0")
        self.chatgpt_menu_y = StringVar(value="0")
        self.chatgpt_send_x = StringVar(value="0")
        self.chatgpt_send_y = StringVar(value="0")
        self.chatgpt_read_x = StringVar(value="0")
        self.chatgpt_read_y = StringVar(value="0")
        self.chatgpt_record_extra = StringVar(value="2")
        self.music_path = StringVar(value="")
        self.music_volume = StringVar(value="20")
        self.status_text = StringVar(value="Pronto.")
        self.progress_text = StringVar(value="")
        self.lines: list[ScriptLine] = []
        self.message_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.tabs: dict[str, Frame] = {}
        self.nav_buttons: dict[str, Button] = {}
        self.active_tab = ""

        self._configure_style()
        self._load_config()
        self._build_ui()
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
        ttk.Label(parent, text="A chave do Pexels fica salva localmente no seu usuário do Windows.", style="Muted.TLabel").pack(anchor="w", pady=(4, 22))

        self._labeled_entry(parent, "Pexels API", self.pexels_key, show="*")

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
        self.script_text.insert("1.0", "Hoje vamos falar sobre a China.\nEsse país é incrível.\nVamos te provar.")

        actions = Frame(parent, bg="#ffffff", pady=12)
        actions.pack(fill=X)
        Button(actions, text="Atualizar roteiro", command=self._refresh_lines, bg="#eef1ff", fg="#27319f", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(side=LEFT)

    def _build_video_tab(self, parent: Frame) -> None:
        top = Frame(parent, bg="#ffffff")
        top.pack(fill=X)
        ttk.Label(top, text="Video", style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, text="Escolha o link do Pexels para cada frase ou deixe vazio para buscar automaticamente pela frase.", style="Muted.TLabel").pack(anchor="w", pady=(4, 12))

        actions = Frame(parent, bg="#ffffff")
        actions.pack(fill=X, pady=(0, 12))
        Button(actions, text="Sincronizar frases do roteiro", command=self._refresh_lines, bg="#eef1ff", fg="#27319f", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        Button(actions, text="Escolher pasta de saída", command=self._choose_output_dir, bg="#eef1ff", fg="#27319f", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(side=LEFT, padx=(10, 0))
        Label(actions, textvariable=self.output_dir, bg="#ffffff", fg="#657084", font=("Segoe UI", 9)).pack(side=LEFT, padx=(12, 0))

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
        size = self._safe_int(self.subtitle_size.get(), 30, 12, 96)
        preview_size = max(10, int(size * 0.38))
        position = self.subtitle_position.get()
        y = {"Topo": 96, "Centro": 250, "Baixo": 405}.get(position, 405)
        color = self._normalize_color(self.subtitle_color.get(), "#FFFFFF")
        bg_color = self._normalize_color(self.subtitle_background_color.get(), "#000000")
        outline_color = self._normalize_color(self.subtitle_outline_color.get(), "#000000")
        font = self.subtitle_font.get().strip() or "Arial"

        if self.subtitle_background.get() == "Sim":
            canvas.create_rectangle(24, y - 46, 276, y + 46, fill=bg_color, outline="")
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, -2), (-2, 2), (2, 2)]:
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
            "Fluxo usado: abrir o ChatGPT pelo atalho, enviar 'Apenas repita isso: [frase]', "
            "clicar no botão de enviar, aguardar resposta, clicar nos 3 pontinhos, esperar 1 segundo, clicar em 'Ler em voz alta' e gravar o áudio do sistema."
        )
        Label(content, text=instructions, bg="#ffffff", fg="#657084", wraplength=760, justify=LEFT, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 14))

        shortcut_card = Frame(content, bg="#f8f9fd", padx=14, pady=12)
        shortcut_card.pack(fill=X, pady=(0, 12))
        self._entry_row(shortcut_card, "Atalho para abrir o ChatGPT", self.chatgpt_shortcut, "Padrão: alt+c. Separe teclas com +, por exemplo: ctrl+shift+g.")
        self._entry_row(shortcut_card, "Esperar antes de enviar (segundos)", self.chatgpt_send_wait, "Tempo para o app do ChatGPT focar no campo de mensagem antes de clicar no botão de enviar.")
        self._entry_row(shortcut_card, "Aguardar resposta do ChatGPT (segundos)", self.chatgpt_response_wait, "Tempo antes de clicar nos 3 pontinhos.")
        self._entry_row(shortcut_card, "Esperar após 3 pontinhos (segundos)", self.chatgpt_menu_wait, "Padrão: 1 segundo antes de clicar em Ler em voz alta.")

        coords_card = Frame(content, bg="#f8f9fd", padx=14, pady=12)
        coords_card.pack(fill=X, pady=(0, 12))
        Label(coords_card, text="Coordenadas dos cliques", bg="#f8f9fd", fg="#111827", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))
        coords = Frame(coords_card, bg="#f8f9fd")
        coords.pack(fill=X)
        left = Frame(coords, bg="#f8f9fd")
        left.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10))
        right = Frame(coords, bg="#f8f9fd")
        right.pack(side=LEFT, fill=BOTH, expand=True)
        self._entry_row(left, "X dos 3 pontinhos", self.chatgpt_menu_x, "Clique no menu da resposta do ChatGPT.")
        self._entry_row(right, "Y dos 3 pontinhos", self.chatgpt_menu_y, "Use a coordenada da tela em pixels.")

        coords_send = Frame(coords_card, bg="#f8f9fd")
        coords_send.pack(fill=X)
        left_send = Frame(coords_send, bg="#f8f9fd")
        left_send.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10))
        right_send = Frame(coords_send, bg="#f8f9fd")
        right_send.pack(side=LEFT, fill=BOTH, expand=True)
        self._entry_row(left_send, "X do botão Enviar", self.chatgpt_send_x, "Clique no botão de enviar mensagem do ChatGPT.")
        self._entry_row(right_send, "Y do botão Enviar", self.chatgpt_send_y, "Use a coordenada da tela em pixels.")

        coords_read = Frame(coords_card, bg="#f8f9fd")
        coords_read.pack(fill=X)
        left_read = Frame(coords_read, bg="#f8f9fd")
        left_read.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10))
        right_read = Frame(coords_read, bg="#f8f9fd")
        right_read.pack(side=LEFT, fill=BOTH, expand=True)
        self._entry_row(left_read, "X do Ler em voz alta", self.chatgpt_read_x, "Clique na opção do menu.")
        self._entry_row(right_read, "Y do Ler em voz alta", self.chatgpt_read_y, "Use a coordenada da tela em pixels.")

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
                self.video_title.set(data.get("video_title", self.video_title.get()))
                self.output_dir.set(data.get("output_dir", self.output_dir.get()))
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
                self.chatgpt_send_x.set(data.get("chatgpt_send_x", self.chatgpt_send_x.get()))
                self.chatgpt_send_y.set(data.get("chatgpt_send_y", self.chatgpt_send_y.get()))
                self.chatgpt_read_x.set(data.get("chatgpt_read_x", self.chatgpt_read_x.get()))
                self.chatgpt_read_y.set(data.get("chatgpt_read_y", self.chatgpt_read_y.get()))
                self.chatgpt_record_extra.set(data.get("chatgpt_record_extra", self.chatgpt_record_extra.get()))
                self.music_path.set(data.get("music_path", self.music_path.get()))
                self.music_volume.set(data.get("music_volume", self.music_volume.get()))
            except json.JSONDecodeError:
                pass

    def _save_config(self) -> None:
        data = {
            "pexels_key": self.pexels_key.get().strip(),
            "video_title": self.video_title.get().strip(),
            "output_dir": self.output_dir.get().strip(),
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
            "chatgpt_send_x": self.chatgpt_send_x.get().strip(),
            "chatgpt_send_y": self.chatgpt_send_y.get().strip(),
            "chatgpt_read_x": self.chatgpt_read_x.get().strip(),
            "chatgpt_read_y": self.chatgpt_read_y.get().strip(),
            "chatgpt_record_extra": self.chatgpt_record_extra.get().strip(),
            "music_path": self.music_path.get().strip(),
            "music_volume": self.music_volume.get().strip(),
        }
        CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.status_text.set("Configurações salvas no perfil do usuário.")

    def _refresh_lines(self) -> None:
        existing = {line.text: line.media_url for line in self.lines}
        phrases = [line.strip() for line in self.script_text.get("1.0", END).splitlines() if line.strip()]
        self.lines = [ScriptLine(text=phrase, media_url=existing.get(phrase, "")) for phrase in phrases]
        self._render_lines()
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
            Label(text_area, text=media_label, bg="#ffffff", fg="#657084", anchor="w", justify=LEFT, wraplength=560, font=("Segoe UI", 9)).pack(fill=X, anchor="w", pady=(4, 0))
            Button(row, text="Link Pexels", command=lambda idx=index: self._edit_line_link(idx), bg="#eef1ff", fg="#27319f", relief="flat", padx=12, pady=8, font=("Segoe UI", 9, "bold")).pack(side=RIGHT, padx=(12, 0))

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
            self.lines[index].media_url = value.get().strip()
            self._render_lines()
            dialog.destroy()

        Button(dialog, text="Salvar link", command=save, bg="#5b6cff", fg="#ffffff", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(anchor="e", padx=20, pady=18)

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
        if not self._chatgpt_coordinates_ready():
            messagebox.showerror(APP_TITLE, "Configure as coordenadas do botão Enviar, dos 3 pontinhos e do Ler em voz alta na aba Audio.")
            self._show_tab("audio")
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
                for index, line in enumerate(self.lines, start=1):
                    self._queue_status(f"Gerando áudio {index}/{len(self.lines)}...", step=True)
                    audio_path = workdir / f"audio_{index:03d}.wav"
                    self._generate_tts(line.text, audio_path)

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
        prompt = f"Apenas repita isso: {text}"
        shortcut_keys = [part.strip().lower() for part in self.chatgpt_shortcut.get().split("+") if part.strip()]
        if not shortcut_keys:
            shortcut_keys = ["alt", "c"]

        pyautogui.hotkey(*shortcut_keys)
        time.sleep(self._safe_float(self.chatgpt_send_wait.get(), 1.0, 0.2, 10.0))
        pyperclip.copy(prompt)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)
        send_x = self._safe_int(self.chatgpt_send_x.get(), 0, 0, 10000)
        send_y = self._safe_int(self.chatgpt_send_y.get(), 0, 0, 10000)
        pyautogui.click(send_x, send_y)

        wait_seconds = self._safe_float(self.chatgpt_response_wait.get(), 8.0, 1.0, 120.0)
        time.sleep(wait_seconds)

        menu_x = self._safe_int(self.chatgpt_menu_x.get(), 0, 0, 10000)
        menu_y = self._safe_int(self.chatgpt_menu_y.get(), 0, 0, 10000)
        read_x = self._safe_int(self.chatgpt_read_x.get(), 0, 0, 10000)
        read_y = self._safe_int(self.chatgpt_read_y.get(), 0, 0, 10000)
        pyautogui.click(menu_x, menu_y)
        time.sleep(self._safe_float(self.chatgpt_menu_wait.get(), 1.0, 0.2, 10.0))
        pyautogui.click(read_x, read_y)
        time.sleep(0.1)

        record_duration = self._estimated_tts_duration(text)
        self._record_system_audio(output_path, record_duration)

    def _record_system_audio(self, output_path: Path, duration: float) -> None:
        sample_rate = 48000
        chunk_seconds = 0.25
        chunk_frames = int(sample_rate * chunk_seconds)
        silence_limit = 1.25
        silence_threshold = 0.01
        chunks: list[np.ndarray] = []
        speech_started = False
        silent_time = 0.0
        elapsed = 0.0

        speaker = sc.default_speaker()
        microphone = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        with microphone.recorder(samplerate=sample_rate) as recorder:
            while elapsed < duration:
                chunk = recorder.record(numframes=chunk_frames)
                chunks.append(chunk)
                mono_chunk = chunk.mean(axis=1) if chunk.ndim > 1 else chunk
                level = float(np.sqrt(np.mean(np.square(mono_chunk)))) if mono_chunk.size else 0.0
                if level > silence_threshold:
                    speech_started = True
                    silent_time = 0.0
                elif speech_started:
                    silent_time += chunk_seconds
                elapsed += chunk_seconds
                if speech_started and elapsed > 1.0 and silent_time >= silence_limit:
                    break

        audio = np.concatenate(chunks) if chunks else np.zeros(int(sample_rate * 0.5), dtype=np.float32)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        audio = self._trim_silence(audio)
        audio = np.clip(audio, -1.0, 1.0)
        pcm = (audio * 32767).astype(np.int16)
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm.tobytes())

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
            media_url = self._search_pexels(line.text)
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

    def _search_pexels(self, query: str) -> str:
        headers = {"Authorization": self.pexels_key.get().strip()}
        video_response = requests.get(
            "https://api.pexels.com/videos/search",
            headers=headers,
            params={"query": query, "per_page": 1, "orientation": "portrait"},
            timeout=30,
        )
        video_response.raise_for_status()
        videos = video_response.json().get("videos", [])
        if videos:
            files = videos[0].get("video_files", [])
            portrait_files = sorted(files, key=lambda item: (item.get("width", 0) < item.get("height", 0), item.get("height", 0)), reverse=True)
            if portrait_files:
                return portrait_files[0]["link"]

        photo_response = requests.get(
            "https://api.pexels.com/v1/search",
            headers=headers,
            params={"query": query, "per_page": 1, "orientation": "portrait"},
            timeout=30,
        )
        photo_response.raise_for_status()
        photos = photo_response.json().get("photos", [])
        if photos:
            return photos[0]["src"]["large2x"]
        raise RuntimeError(f"Nenhuma mídia encontrada no Pexels para: {query}")

    def _create_clip(self, ffmpeg: str, media_path: Path, audio_path: Path, clip_path: Path, subtitle_text: str) -> None:
        duration = self._audio_duration(audio_path)
        video_filter = self._video_filter(subtitle_text)
        image_exts = {".jpg", ".jpeg", ".png", ".webp"}
        if media_path.suffix.lower() in image_exts:
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
                "-vf",
                video_filter,
                "-r",
                FPS,
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-shortest",
                str(clip_path),
            ]
        else:
            cmd = [
                ffmpeg,
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(media_path),
                "-i",
                str(audio_path),
                "-t",
                f"{duration:.3f}",
                "-vf",
                video_filter,
                "-r",
                FPS,
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-shortest",
                str(clip_path),
            ]
        self._run_ffmpeg(cmd)

    def _video_filter(self, subtitle_text: str) -> str:
        base_filter = f"scale={VIDEO_SIZE}:force_original_aspect_ratio=increase,crop={VIDEO_SIZE},format=yuv420p"
        if self.subtitle_enabled.get() != "Sim":
            return base_filter
        text = self._escape_drawtext(subtitle_text)
        font = self._escape_drawtext(self.subtitle_font.get().strip() or "Arial")
        font_size = self._safe_int(self.subtitle_size.get(), 64, 12, 160)
        font_color = self._ffmpeg_color(self.subtitle_color.get(), "0xFFFFFF")
        y_expr = self._subtitle_y_expression()
        box_enabled = "1" if self.subtitle_background.get() == "Sim" else "0"
        box_color = self._ffmpeg_color(self.subtitle_background_color.get(), "0x000000")
        outline_color = self._ffmpeg_color(self.subtitle_outline_color.get(), "0x000000")
        drawtext = (
            "drawtext="
            f"font='{font}':"
            f"text='{text}':"
            f"fontcolor={font_color}:"
            f"fontsize={font_size}:"
            f"box={box_enabled}:"
            f"boxcolor={box_color}@0.70:"
            "boxborderw=24:"
            "borderw=3:"
            f"bordercolor={outline_color}:"
            "line_spacing=12:"
            "x=(w-text_w)/2:"
            f"y={y_expr}"
        )
        return f"{base_filter},{drawtext}"

    def _subtitle_y_expression(self) -> str:
        position = self.subtitle_position.get()
        if position == "Topo":
            return "h*0.12"
        if position == "Centro":
            return "(h-text_h)/2"
        return "h-text_h-h*0.14"

    @staticmethod
    def _escape_drawtext(value: str) -> str:
        return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")

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
        list_file = workdir / "clips.txt"
        list_file.write_text("".join(f"file '{clip.as_posix()}'\n" for clip in clips), encoding="utf-8")
        temp_output = workdir / "final_without_music.mp4"
        cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(temp_output)]
        self._run_ffmpeg(cmd)

        music_file = Path(self.music_path.get()).expanduser()
        if not self.music_path.get().strip() or not music_file.exists():
            shutil.copy2(temp_output, final_path)
            return

        volume = self._safe_int(self.music_volume.get(), 20, 0, 100) / 100
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
            f"[1:a]volume={volume:.2f}[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[a]",
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

    @staticmethod
    def _audio_duration(audio_path: Path) -> float:
        with wave.open(str(audio_path), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            return frames / float(rate)


if __name__ == "__main__":
    VideoGeneratorApp().run()
