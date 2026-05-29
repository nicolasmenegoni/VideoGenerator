from __future__ import annotations

import json
import os
import queue
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
import requests
from google import genai
from google.genai import types

APP_TITLE = "VideoGenerator"
CONFIG_FILE = Path.home() / ".videogenerator_config.json"
GEMINI_TTS_MODEL = "gemini-3.1-flash-tts-preview"
GEMINI_VOICE = "Kore"
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

        self.gemini_key = StringVar()
        self.pexels_key = StringVar()
        self.output_dir = StringVar(value=str(Path.home() / "Videos"))
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
        Label(header, text="Gere vídeos verticais com Gemini TTS + Pexels em poucos cliques.", bg="#f6f7fb", fg="#657084", font=("Segoe UI", 10)).pack(anchor="w")

        nav = Frame(shell, bg="#eef1f8", padx=6, pady=6)
        nav.pack(fill=X, pady=(0, 12))
        self._add_nav_button(nav, "apis", "APIs")
        self._add_nav_button(nav, "roteiro", "Roteiro")
        self._add_nav_button(nav, "video", "Video")

        self.content = Frame(shell, bg="#ffffff")
        self.content.pack(fill=BOTH, expand=True)

        self.tabs["apis"] = Frame(self.content, bg="#ffffff", padx=24, pady=24)
        self.tabs["roteiro"] = Frame(self.content, bg="#ffffff", padx=24, pady=24)
        self.tabs["video"] = Frame(self.content, bg="#ffffff", padx=24, pady=24)

        self._build_api_tab(self.tabs["apis"])
        self._build_script_tab(self.tabs["roteiro"])
        self._build_video_tab(self.tabs["video"])
        self._refresh_lines()
        self._show_tab("roteiro")

        bottom = Frame(shell, bg="#f6f7fb", pady=12)
        bottom.pack(fill=X)
        self.progress = ttk.Progressbar(bottom, mode="determinate", style="Horizontal.TProgressbar")
        self.progress.pack(fill=X, pady=(0, 10))
        Button(bottom, text="Gerar vídeo", command=self._start_generation, bg="#5b6cff", fg="#ffffff", activebackground="#4657e8", activeforeground="#ffffff", relief="flat", padx=18, pady=13, font=("Segoe UI", 13, "bold")).pack(fill=X)

        footer = Frame(shell, bg="#f6f7fb", pady=(8, 0))
        footer.pack(fill=X)
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
        ttk.Label(parent, text="As chaves ficam salvas localmente no seu usuário do Windows.", style="Muted.TLabel").pack(anchor="w", pady=(4, 22))

        self._labeled_entry(parent, "Google Gemini API", self.gemini_key, show="*")
        self._labeled_entry(parent, "Pexels API", self.pexels_key, show="*")

        Button(parent, text="Salvar chaves", command=self._save_config, bg="#111827", fg="#ffffff", activebackground="#2a3446", activeforeground="#ffffff", relief="flat", padx=18, pady=10, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(16, 0))

    def _build_script_tab(self, parent: Frame) -> None:
        top = Frame(parent, bg="#ffffff")
        top.pack(fill=X)
        ttk.Label(top, text="Roteiro", style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, text="Digite uma frase por linha. Depois vá para a aba Video para escolher as mídias do Pexels.", style="Muted.TLabel").pack(anchor="w", pady=(4, 12))

        self.script_text = Text(parent, height=14, wrap="word", bd=0, bg="#f3f5fb", fg="#111827", insertbackground="#111827", font=("Segoe UI", 11), padx=14, pady=12)
        self.script_text.pack(fill=BOTH, expand=True)
        self.script_text.insert("1.0", "Hoje vamos falar sobre a China.\nEsse país é incrível.\nVamos te provar.")

        actions = Frame(parent, bg="#ffffff", pady=12)
        actions.pack(fill=X)
        Button(actions, text="Atualizar roteiro", command=self._refresh_lines, bg="#eef1ff", fg="#27319f", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        Button(actions, text="Ir para Video", command=lambda: self._show_tab("video"), bg="#eef1ff", fg="#27319f", relief="flat", padx=14, pady=9, font=("Segoe UI", 10, "bold")).pack(side=LEFT, padx=(10, 0))

    def _build_video_tab(self, parent: Frame) -> None:
        top = Frame(parent, bg="#ffffff")
        top.pack(fill=X)
        ttk.Label(top, text="Video", style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, text="Escolha o link do Pexels para cada frase ou deixe vazio para buscar automaticamente pela frase.", style="Muted.TLabel").pack(anchor="w", pady=(4, 12))

        actions = Frame(parent, bg="#ffffff", pady=(0, 12))
        actions.pack(fill=X)
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

    def _labeled_entry(self, parent: Frame, text: str, variable: StringVar, show: str | None = None) -> None:
        Label(parent, text=text, bg="#ffffff", fg="#111827", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        Entry(parent, textvariable=variable, show=show, bd=0, bg="#f3f5fb", fg="#111827", insertbackground="#111827", font=("Segoe UI", 11)).pack(fill=X, ipady=10, pady=(6, 14))

    def _load_config(self) -> None:
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                self.gemini_key.set(data.get("gemini_key", ""))
                self.pexels_key.set(data.get("pexels_key", ""))
                self.output_dir.set(data.get("output_dir", self.output_dir.get()))
            except json.JSONDecodeError:
                pass

    def _save_config(self) -> None:
        data = {"gemini_key": self.gemini_key.get().strip(), "pexels_key": self.pexels_key.get().strip(), "output_dir": self.output_dir.get().strip()}
        CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.status_text.set("Chaves salvas com segurança no perfil do usuário.")

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
        if not self.gemini_key.get().strip() or not self.pexels_key.get().strip():
            messagebox.showerror(APP_TITLE, "Informe as duas chaves de API na aba APIs.")
            self._show_tab("apis")
            return
        out_dir = Path(self.output_dir.get()).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
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
                    self._create_clip(ffmpeg, media_path, audio_path, clip_path)
                    clips.append(clip_path)

                self._queue_status("Unindo cenas...", step=True)
                final_path = Path(self.output_dir.get()).expanduser() / "video_gerado.mp4"
                self._concat_clips(ffmpeg, clips, final_path, workdir)
                self.message_queue.put(("done", f"Vídeo gerado em:\n{final_path}"))
        except Exception as exc:  # noqa: BLE001 - show desktop-friendly error
            self.message_queue.put(("error", str(exc)))

    def _generate_tts(self, text: str, output_path: Path) -> None:
        os.environ["GEMINI_API_KEY"] = self.gemini_key.get().strip()
        client = genai.Client(api_key=self.gemini_key.get().strip())
        response = client.models.generate_content(
            model=GEMINI_TTS_MODEL,
            contents=f"Read clearly in Brazilian Portuguese: {text}",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=GEMINI_VOICE)
                    )
                ),
            ),
        )
        data = response.candidates[0].content.parts[0].inline_data.data
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            wav_file.writeframes(data)

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

    def _create_clip(self, ffmpeg: str, media_path: Path, audio_path: Path, clip_path: Path) -> None:
        duration = self._audio_duration(audio_path)
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
                f"scale={VIDEO_SIZE}:force_original_aspect_ratio=increase,crop={VIDEO_SIZE},format=yuv420p",
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
                f"scale={VIDEO_SIZE}:force_original_aspect_ratio=increase,crop={VIDEO_SIZE},format=yuv420p",
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

    def _concat_clips(self, ffmpeg: str, clips: list[Path], final_path: Path, workdir: Path) -> None:
        list_file = workdir / "clips.txt"
        list_file.write_text("".join(f"file '{clip.as_posix()}'\n" for clip in clips), encoding="utf-8")
        temp_output = workdir / "final.mp4"
        cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(temp_output)]
        self._run_ffmpeg(cmd)
        shutil.copy2(temp_output, final_path)

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
