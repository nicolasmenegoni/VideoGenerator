from __future__ import annotations

import json
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, Button, Canvas, Entry, Frame, Label, StringVar, Text, Tk, filedialog, messagebox, ttk
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageGrab, ImageTk
import requests
import soundcard as sc
import soundfile as sf
import sounddevice as sd

APP_TITLE = "VideoGenerator"
CONFIG_FILE = Path.home() / ".videogenerator_config.json"
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = "30"
GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_SCRIPT = "Hoje vamos falar sobre a China.\nEsse país é incrível.\nVamos te provar."
MEDIA_DIR = Path.home() / ".videogenerator_media"
LOGO_DIR = Path.home() / ".videogenerator_logos"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class ScriptLine:
    text: str
    media_url: str = ""


class VideoGeneratorApp:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1100x750")
        self.root.minsize(950, 650)
        self.root.configure(bg="#f5f5f5")

        # Variáveis de configuração
        self.pexels_key = StringVar()
        self.groq_key = StringVar()
        self.logo_path = StringVar(value="")
        self.logo_position = StringVar(value="Superior Direito")
        self.logo_size = StringVar(value="15")
        self.logo_text = StringVar(value="")
        self.logo_text_font = StringVar(value="Arial")
        self.logo_text_size = StringVar(value="20")
        self.logo_text_offset = StringVar(value="10")
        self.script_lines: list[ScriptLine] = []
        self.is_generating = False
        self.stop_flag = threading.Event()

        self.load_config()
        self.setup_ui()

    def load_config(self) -> None:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.pexels_key.set(cfg.get("pexels_key", ""))
                self.groq_key.set(cfg.get("groq_key", ""))
                self.logo_path.set(cfg.get("logo_path", ""))
                self.logo_position.set(cfg.get("logo_position", "Superior Direito"))
                self.logo_size.set(cfg.get("logo_size", "15"))
                self.logo_text.set(cfg.get("logo_text", ""))
                self.logo_text_font.set(cfg.get("logo_text_font", "Arial"))
                self.logo_text_size.set(cfg.get("logo_text_size", "20"))
                self.logo_text_offset.set(cfg.get("logo_text_offset", "10"))
            except Exception:
                pass

    def save_config(self) -> None:
        cfg = {
            "pexels_key": self.pexels_key.get(),
            "groq_key": self.groq_key.get(),
            "logo_path": self.logo_path.get(),
            "logo_position": self.logo_position.get(),
            "logo_size": self.logo_size.get(),
            "logo_text": self.logo_text.get(),
            "logo_text_font": self.logo_text_font.get(),
            "logo_text_size": self.logo_text_size.get(),
            "logo_text_offset": self.logo_text_offset.get(),
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

    def setup_ui(self) -> None:
        # Notebook (abas)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=BOTH, expand=True, padx=5, pady=5)

        # Aba 1: Configurações
        self.tab_config = Frame(self.notebook, bg="#f5f5f5")
        self.notebook.add(self.tab_config, text="  Configurações  ")
        self.setup_config_tab()

        # Aba 2: Roteiro
        self.tab_script = Frame(self.notebook, bg="#f5f5f5")
        self.notebook.add(self.tab_script, text="  Roteiro  ")
        self.setup_script_tab()

        # Aba 3: Logo
        self.tab_logo = Frame(self.notebook, bg="#f5f5f5")
        self.notebook.add(self.tab_logo, text="  Logo  ")
        self.setup_logo_tab()

        # Aba 4: Gerar Vídeo
        self.tab_generate = Frame(self.notebook, bg="#f5f5f5")
        self.notebook.add(self.tab_generate, text="  Gerar Vídeo  ")
        self.setup_generate_tab()

    def setup_config_tab(self) -> None:
        frame = Frame(self.tab_config, bg="#f5f5f5")
        frame.pack(padx=20, pady=20, fill=X)

        # API Keys
        lbl = Label(frame, text="Chave da API Pexels:", font=("Segoe UI", 11), bg="#f5f5f5")
        lbl.grid(row=0, column=0, sticky="w", pady=8)
        entry = Entry(frame, textvariable=self.pexels_key, width=50, show="*")
        entry.grid(row=0, column=1, pady=8, padx=5)

        lbl = Label(frame, text="Chave da API Groq:", font=("Segoe UI", 11), bg="#f5f5f5")
        lbl.grid(row=1, column=0, sticky="w", pady=8)
        entry = Entry(frame, textvariable=self.groq_key, width=50, show="*")
        entry.grid(row=1, column=1, pady=8, padx=5)

        btn = Button(frame, text="Salvar Configurações", command=self.save_config, bg="#4CAF50", fg="white", font=("Segoe UI", 10, "bold"))
        btn.grid(row=2, column=0, columnspan=2, pady=20)

        info = Label(frame, text="Dica: Obtenha suas chaves em pexels.com/api e console.groq.com", font=("Segoe UI", 9), bg="#f5f5f5", fg="#666")
        info.grid(row=3, column=0, columnspan=2)

    def setup_script_tab(self) -> None:
        # Frame superior - Prompt
        top_frame = Frame(self.tab_script, bg="#f5f5f5")
        top_frame.pack(fill=X, padx=15, pady=10)

        lbl = Label(top_frame, text="Prompt para gerar roteiro:", font=("Segoe UI", 11, "bold"), bg="#f5f5f5")
        lbl.pack(anchor="w")

        self.prompt_entry = Text(top_frame, height=2, width=80, font=("Segoe UI", 10))
        self.prompt_entry.pack(fill=X, pady=5)

        btn_frame = Frame(top_frame, bg="#f5f5f5")
        btn_frame.pack(fill=X, pady=5)

        btn = Button(btn_frame, text="Gerar Roteiro com IA", command=self.generate_script_with_ai, bg="#2196F3", fg="white", font=("Segoe UI", 10, "bold"))
        btn.pack(side=LEFT)

        # Frame central - Editor de roteiro
        mid_frame = Frame(self.tab_script, bg="#f5f5f5")
        mid_frame.pack(fill=BOTH, expand=True, padx=15, pady=5)

        lbl = Label(mid_frame, text="Editar roteiro (uma frase por linha):", font=("Segoe UI", 11, "bold"), bg="#f5f5f5")
        lbl.pack(anchor="w")

        self.script_text = Text(mid_frame, height=12, width=80, font=("Segoe UI", 10))
        self.script_text.pack(fill=BOTH, expand=True, pady=5)
        self.script_text.insert(END, DEFAULT_SCRIPT)

        # Frame inferior - Botões
        bot_frame = Frame(self.tab_script, bg="#f5f5f5")
        bot_frame.pack(fill=X, padx=15, pady=10)

        btn = Button(bot_frame, text="Carregar Roteiro", command=self.load_script_file, bg="#9E9E9E", fg="white", font=("Segoe UI", 10))
        btn.pack(side=LEFT, padx=2)

        btn = Button(bot_frame, text="Salvar Roteiro", command=self.save_script_file, bg="#9E9E9E", fg="white", font=("Segoe UI", 10))
        btn.pack(side=LEFT, padx=2)

    def setup_logo_tab(self) -> None:
        # Canvas com scrollbar
        canvas = Canvas(self.tab_logo, bg="#f5f5f5", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.tab_logo, orient="vertical", command=canvas.yview)
        
        inner_frame = Frame(canvas, bg="#f5f5f5")
        
        canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=RIGHT, fill=Y)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        
        canvas_window = canvas.create_window((0, 0), window=inner_frame, anchor="nw")
        
        def on_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
            canvas.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        inner_frame.bind("<Configure>", on_configure)
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # Conteúdo do frame interno
        container = Frame(inner_frame, bg="#f5f5f5", padx=20, pady=15)
        container.pack(fill=X)

        row = 0
        
        # Selecionar logo
        lbl = Label(container, text="Arquivo da Logo:", font=("Segoe UI", 11, "bold"), bg="#f5f5f5")
        lbl.grid(row=row, column=0, sticky="w", pady=8)
        row += 1

        path_frame = Frame(container, bg="#f5f5f5")
        path_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=5)
        row += 1

        self.logo_path_label = Label(path_frame, text=self.logo_path.get() or "Nenhuma logo selecionada", font=("Segoe UI", 9), bg="#fff", relief="sunken", anchor="w", width=60)
        self.logo_path_label.pack(side=LEFT, fill=X, expand=True)

        btn = Button(path_frame, text="Selecionar...", command=self.select_logo, bg="#2196F3", fg="white", font=("Segoe UI", 9))
        btn.pack(side=LEFT, padx=5)

        btn = Button(path_frame, text="Limpar", command=self.clear_logo, bg="#f44336", fg="white", font=("Segoe UI", 9))
        btn.pack(side=LEFT, padx=5)

        # Preview da logo
        self.logo_preview_label = Label(container, text="", bg="#f5f5f5")
        self.logo_preview_label.grid(row=row, column=0, columnspan=2, pady=10)
        row += 1

        # Posição
        lbl = Label(container, text="Posição da Logo:", font=("Segoe UI", 11), bg="#f5f5f5")
        lbl.grid(row=row, column=0, sticky="w", pady=8)
        row += 1

        positions = ["Superior Esquerdo", "Superior Direito", "Inferior Esquerdo", "Inferior Direito"]
        combo = ttk.Combobox(container, textvariable=self.logo_position, values=positions, state="readonly", width=30)
        combo.grid(row=row, column=0, sticky="w", pady=5)
        row += 1

        # Tamanho
        lbl = Label(container, text="Tamanho da Logo (%):", font=("Segoe UI", 11), bg="#f5f5f5")
        lbl.grid(row=row, column=0, sticky="w", pady=8)
        row += 1

        scale = ttk.Scale(container, from_=5, to=40, variable=self.logo_size, orient="horizontal", length=200)
        scale.grid(row=row, column=0, sticky="w", pady=5)
        
        size_lbl = Label(container, textvariable=self.logo_size, font=("Segoe UI", 10), bg="#f5f5f5")
        size_lbl.grid(row=row, column=1, sticky="w", padx=10)
        row += 1

        # Texto abaixo da logo
        sep = ttk.Separator(container, orient="horizontal")
        sep.grid(row=row, column=0, columnspan=2, sticky="ew", pady=15)
        row += 1

        lbl = Label(container, text="Texto abaixo da Logo:", font=("Segoe UI", 11, "bold"), bg="#f5f5f5")
        lbl.grid(row=row, column=0, sticky="w", pady=8)
        row += 1

        entry = Entry(container, textvariable=self.logo_text, width=40, font=("Segoe UI", 10))
        entry.grid(row=row, column=0, sticky="w", pady=5)
        row += 1

        # Fonte do texto
        lbl = Label(container, text="Fonte do Texto:", font=("Segoe UI", 11), bg="#f5f5f5")
        lbl.grid(row=row, column=0, sticky="w", pady=8)
        row += 1

        fonts = ["Arial", "Segoe UI", "Times New Roman", "Courier New", "Verdana", "Georgia"]
        combo = ttk.Combobox(container, textvariable=self.logo_text_font, values=fonts, state="readonly", width=30)
        combo.grid(row=row, column=0, sticky="w", pady=5)
        row += 1

        # Tamanho da fonte
        lbl = Label(container, text="Tamanho da Fonte:", font=("Segoe UI", 11), bg="#f5f5f5")
        lbl.grid(row=row, column=0, sticky="w", pady=8)
        row += 1

        scale = ttk.Scale(container, from_=10, to=50, variable=self.logo_text_size, orient="horizontal", length=200)
        scale.grid(row=row, column=0, sticky="w", pady=5)
        
        font_size_lbl = Label(container, textvariable=self.logo_text_size, font=("Segoe UI", 10), bg="#f5f5f5")
        font_size_lbl.grid(row=row, column=1, sticky="w", padx=10)
        row += 1

        # Offset vertical
        lbl = Label(container, text="Distância do Texto (px):", font=("Segoe UI", 11), bg="#f5f5f5")
        lbl.grid(row=row, column=0, sticky="w", pady=8)
        row += 1

        scale = ttk.Scale(container, from_=-20, to=50, variable=self.logo_text_offset, orient="horizontal", length=200)
        scale.grid(row=row, column=0, sticky="w", pady=5)
        
        offset_lbl = Label(container, textvariable=self.logo_text_offset, font=("Segoe UI", 10), bg="#f5f5f5")
        offset_lbl.grid(row=row, column=1, sticky="w", padx=10)
        row += 1

        # Botão salvar
        btn = Button(container, text="Salvar Configurações da Logo", command=self.save_logo_config, bg="#4CAF50", fg="white", font=("Segoe UI", 10, "bold"))
        btn.grid(row=row, column=0, columnspan=2, pady=20)

    def setup_generate_tab(self) -> None:
        frame = Frame(self.tab_generate, bg="#f5f5f5")
        frame.pack(fill=BOTH, expand=True, padx=20, pady=20)

        # Status
        self.status_label = Label(frame, text="Pronto para gerar", font=("Segoe UI", 12, "bold"), bg="#f5f5f5", fg="#333")
        self.status_label.pack(anchor="w", pady=10)

        # Progresso
        self.progress_label = Label(frame, text="", font=("Segoe UI", 10), bg="#f5f5f5", fg="#666")
        self.progress_label.pack(anchor="w", pady=5)

        # Log
        log_frame = Frame(frame, bg="#f5f5f5")
        log_frame.pack(fill=BOTH, expand=True, pady=10)

        lbl = Label(log_frame, text="Log de Processamento:", font=("Segoe UI", 10, "bold"), bg="#f5f5f5")
        lbl.pack(anchor="w")

        self.log_text = Text(log_frame, height=15, width=80, font=("Consolas", 9), bg="#fff", relief="sunken")
        self.log_text.pack(fill=BOTH, expand=True, pady=5)

        # Botões
        btn_frame = Frame(frame, bg="#f5f5f5")
        btn_frame.pack(fill=X, pady=10)

        self.generate_btn = Button(btn_frame, text="▶ Gerar Vídeo", command=self.start_generation, bg="#4CAF50", fg="white", font=("Segoe UI", 12, "bold"), padx=20, pady=10)
        self.generate_btn.pack(side=LEFT, padx=5)

        self.stop_btn = Button(btn_frame, text="⏹ Parar", command=self.stop_generation, bg="#f44336", fg="white", font=("Segoe UI", 12, "bold"), padx=20, pady=10, state="disabled")
        self.stop_btn.pack(side=LEFT, padx=5)

    def select_logo(self) -> None:
        filetypes = [("Imagens", "*.jpg *.jpeg *.png *.webp")]
        path = filedialog.askopenfilename(title="Selecionar Logo", filetypes=filetypes)
        if path:
            self.logo_path.set(path)
            self.logo_path_label.config(text=path)
            self.show_logo_preview(path)

    def clear_logo(self) -> None:
        self.logo_path.set("")
        self.logo_path_label.config(text="Nenhuma logo selecionada")
        self.logo_preview_label.config(text="", image="")
        self._preview_image = None

    def show_logo_preview(self, path: str) -> None:
        try:
            img = Image.open(path)
            img.thumbnail((200, 100), Image.Resampling.LANCZOS)
            self._preview_image = ImageTk.PhotoImage(img)
            self.logo_preview_label.config(image=self._preview_image, text="")
        except Exception as e:
            self.logo_preview_label.config(text=f"Erro ao carregar: {e}")

    def save_logo_config(self) -> None:
        self.save_config()
        messagebox.showinfo("Sucesso", "Configurações da logo salvas!")

    def generate_script_with_ai(self) -> None:
        prompt = self.prompt_entry.get("1.0", END).strip()
        if not prompt:
            messagebox.showwarning("Atenção", "Digite um prompt para gerar o roteiro.")
            return

        groq_key = self.groq_key.get().strip()
        if not groq_key:
            messagebox.showwarning("Atenção", "Configure sua chave da API Groq em Configurações.")
            return

        self.log("Gerando roteiro com IA...")
        headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": "Você é um roteirista profissional. Crie um roteiro curto e envolvente para vídeo de redes sociais (até 60 segundos). Retorne APENAS o roteiro, uma frase por linha, sem numeração ou marcadores."},
                {"role": "user", "content": f"Crie um roteiro sobre: {prompt}"}
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }

        try:
            resp = requests.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            script = result["choices"][0]["message"]["content"].strip()
            
            # Limpar formatação
            lines = [line.strip() for line in script.split("\n") if line.strip() and not line.strip().startswith(("1.", "2.", "3.", "-", "*", "•"))]
            lines = [re.sub(r"^\d+[\.\)]\s*", "", line).strip() for line in lines]
            
            self.script_text.delete("1.0", END)
            self.script_text.insert(END, "\n".join(lines))
            self.log("Roteiro gerado com sucesso!")
        except Exception as e:
            self.log(f"Erro ao gerar roteiro: {e}")
            messagebox.showerror("Erro", f"Falha ao gerar roteiro:\n{e}")

    def load_script_file(self) -> None:
        filetypes = [("Texto", "*.txt")]
        path = filedialog.askopenfilename(title="Carregar Roteiro", filetypes=filetypes)
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.script_text.delete("1.0", END)
                self.script_text.insert(END, content)
                self.log(f"Roteiro carregado: {path}")
            except Exception as e:
                messagebox.showerror("Erro", f"Falha ao carregar roteiro:\n{e}")

    def save_script_file(self) -> None:
        filetypes = [("Texto", "*.txt")]
        path = filedialog.asksaveasfilename(title="Salvar Roteiro", filetypes=filetypes, defaultextension=".txt")
        if path:
            try:
                content = self.script_text.get("1.0", END).strip()
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.log(f"Roteiro salvo: {path}")
            except Exception as e:
                messagebox.showerror("Erro", f"Falha ao salvar roteiro:\n{e}")

    def log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(END, f"[{timestamp}] {message}\n")
        self.log_text.see(END)
        self.root.update_idletasks()

    def start_generation(self) -> None:
        script_content = self.script_text.get("1.0", END).strip()
        if not script_content:
            messagebox.showwarning("Atenção", "O roteiro está vazio.")
            return

        self.script_lines = [ScriptLine(text=line.strip()) for line in script_content.split("\n") if line.strip()]
        if not self.script_lines:
            messagebox.showwarning("Atenção", "Nenhuma linha válida no roteiro.")
            return

        self.is_generating = True
        self.stop_flag.clear()
        self.generate_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_label.config(text="Gerando vídeo...", fg="#2196F3")
        self.progress_label.config(text="Iniciando processo...")
        self.log_text.delete("1.0", END)
        self.log("=== Início da Geração ===")

        thread = threading.Thread(target=self.generate_video_thread, daemon=True)
        thread.start()

    def stop_generation(self) -> None:
        self.stop_flag.set()
        self.is_generating = False
        self.log("Parando geração...")

    def generate_video_thread(self) -> None:
        temp_dir = tempfile.mkdtemp(prefix="videogen_")
        try:
            self.log(f"Diretório temporário: {temp_dir}")
            
            # Etapa 1: Gerar áudio TTS
            self.progress_label.config(text="Etapa 1/4: Gerando áudio...")
            self.log("Gerando áudio com TTS...")
            
            full_text = " ".join([line.text for line in self.script_lines])
            audio_path = Path(temp_dir) / "audio.wav"
            
            if not self.generate_tts_audio(full_text, str(audio_path)):
                raise Exception("Falha na geração do áudio TTS")
            
            self.log(f"Áudio gerado: {audio_path}")

            # Etapa 2: Buscar vídeos do Pexels
            self.progress_label.config(text="Etapa 2/4: Buscando vídeos...")
            self.log("Buscando vídeos no Pexels...")
            
            video_paths = []
            pexels_key = self.pexels_key.get().strip()
            
            for i, line in enumerate(self.script_lines):
                if self.stop_flag.is_set():
                    raise Exception("Geração interrompida pelo usuário")
                
                if pexels_key and line.media_url == "":
                    # Buscar vídeo baseado no texto da linha
                    search_query = line.text[:50]
                    video_url = self.search_pexels_video(search_query, pexels_key)
                    if video_url:
                        local_path = Path(temp_dir) / f"clip_{i:03d}.mp4"
                        if self.download_video(video_url, str(local_path)):
                            video_paths.append(str(local_path))
                            self.log(f"Vídeo {i+1}: {search_query[:30]}...")
                        else:
                            video_paths.append(None)
                    else:
                        video_paths.append(None)
                elif line.media_url:
                    # URL já fornecida
                    local_path = Path(temp_dir) / f"clip_{i:03d}.mp4"
                    if self.download_video(line.media_url, str(local_path)):
                        video_paths.append(str(local_path))
                    else:
                        video_paths.append(None)
                else:
                    video_paths.append(None)

            # Etapa 3: Gerar legendas ASS
            self.progress_label.config(text="Etapa 3/4: Gerando legendas...")
            self.log("Gerando arquivo de legendas...")
            
            subtitle_path = Path(temp_dir) / "subtitles.ass"
            self.generate_subtitle_file(str(subtitle_path), full_text, str(audio_path))
            self.log(f"Legendas geradas: {subtitle_path}")

            # Etapa 4: Montar vídeo final com FFmpeg
            self.progress_label.config(text="Etapa 4/4: Renderizando vídeo...")
            self.log("Renderizando vídeo final com FFmpeg...")
            
            output_path = Path.home() / f"video_final_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
            
            if self.render_final_video(temp_dir, video_paths, str(audio_path), str(subtitle_path), str(output_path)):
                self.log(f"✅ Vídeo gerado com sucesso: {output_path}")
                self.progress_label.config(text="Concluído!")
                self.status_label.config(text="Vídeo gerado com sucesso!", fg="#4CAF50")
                messagebox.showinfo("Sucesso", f"Vídeo gerado:\n{output_path}")
            else:
                raise Exception("Falha na renderização do vídeo")

        except Exception as e:
            self.log(f"❌ Erro: {e}")
            self.status_label.config(text="Erro na geração", fg="#f44336")
            self.progress_label.config(text="Falhou")
            if not self.stop_flag.is_set():
                messagebox.showerror("Erro", f"Falha na geração do vídeo:\n{e}")
        finally:
            self.is_generating = False
            self.generate_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            
            # Limpar diretório temporário
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

    def generate_tts_audio(self, text: str, output_path: str) -> bool:
        """Gera áudio usando pyttsx3 ou sistema TTS disponível"""
        try:
            import pyttsx3
            
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            
            # Tentar voz em português
            for voice in voices:
                if "brazil" in voice.name.lower() or "portuguese" in voice.name.lower() or "br-" in voice.id.lower():
                    engine.setProperty("voice", voice.id)
                    break
            
            engine.setProperty("rate", 160)
            engine.setProperty("volume", 1.0)
            
            # Salvar em arquivo temporário e converter
            temp_wav = output_path + ".temp.wav"
            engine.save_to_file(text, temp_wav)
            engine.runAndWait()
            
            # Converter para formato adequado se necessário
            if Path(temp_wav).exists():
                shutil.move(temp_wav, output_path)
                return True
            
        except ImportError:
            self.log("pyttsx3 não instalado. Usando fallback...")
        except Exception as e:
            self.log(f"Erro TTS: {e}")
        
        # Fallback: criar arquivo WAV silencioso como placeholder
        try:
            sample_rate = 22050
            duration = max(1.0, len(text) * 0.08)  # Estimativa de duração
            samples = int(sample_rate * duration)
            audio_data = np.zeros(samples, dtype=np.float32)
            sf.write(output_path, audio_data, sample_rate)
            return True
        except Exception as e:
            self.log(f"Erro no fallback de áudio: {e}")
            return False

    def search_pexels_video(self, query: str, api_key: str) -> str | None:
        """Busca vídeo no Pexels"""
        try:
            headers = {"Authorization": api_key}
            params = {"query": query, "per_page": 1, "orientation": "portrait"}
            
            resp = requests.get("https://api.pexels.com/videos/search", headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            
            data = resp.json()
            if data.get("videos"):
                video = data["videos"][0]
                files = video.get("video_files", [])
                for f in sorted(files, key=lambda x: x.get("width", 0), reverse=True):
                    if f.get("link"):
                        return f["link"]
        except Exception as e:
            self.log(f"Erro ao buscar Pexels: {e}")
        return None

    def download_video(self, url: str, output_path: str) -> bool:
        """Baixa vídeo de URL"""
        try:
            resp = requests.get(url, stream=True, timeout=30)
            resp.raise_for_status()
            
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if self.stop_flag.is_set():
                        return False
                    f.write(chunk)
            return True
        except Exception as e:
            self.log(f"Erro ao baixar vídeo: {e}")
            return False

    def generate_subtitle_file(self, output_path: str, text: str, audio_path: str) -> None:
        """Gera arquivo de legendas no formato ASS com timing sincronizado"""
        words = text.split()
        total_words = len(words)
        
        # Obter duração real do áudio
        audio_duration = 5.0  # Default
        try:
            with wave.open(audio_path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                audio_duration = frames / float(rate)
        except Exception as e:
            self.log(f"Aviso: Não foi possível ler duração do áudio: {e}")
        
        # Calcular duração por palavra com offset para sincronização
        # Offset negativo adianta as legendas
        timing_offset = 0.15  # 150ms de antecipação
        word_duration = audio_duration / total_words if total_words > 0 else 1.0
        
        ass_content = """[Script Info]
Title: Generated Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,28,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,2,10,10,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        current_time = 0.0
        for i, word in enumerate(words):
            # Aplicar offset para sincronizar melhor com o áudio
            start = max(0, current_time - timing_offset)
            end = current_time + word_duration
            
            start_str = self.format_ass_time(start)
            end_str = self.format_ass_time(end)
            
            ass_content += f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{word}\n"
            current_time += word_duration
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

    def format_ass_time(self, seconds: float) -> str:
        """Formata tempo em formato ASS (H:MM:SS.cc)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        centiseconds = int((secs % 1) * 100)
        return f"{hours}:{minutes:02d}:{int(secs):02d}.{centiseconds:02d}"

    def render_final_video(self, temp_dir: str, video_paths: list, audio_path: str, subtitle_path: str, output_path: str) -> bool:
        """Renderiza vídeo final usando FFmpeg"""
        try:
            # Construir filtro complexo
            filters = []
            inputs = []
            
            # Input de áudio
            inputs.extend(["-i", audio_path])
            
            # Inputs de vídeo
            valid_videos = [v for v in video_paths if v]
            for vp in valid_videos:
                inputs.extend(["-i", vp])
            
            # Se não há vídeos válidos, criar tela preta
            if not valid_videos:
                color_filter = f"color=black:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d=5"
                filters.append(f"[0:v]{color_filter}[bg]")
                video_input = "[bg]"
            else:
                # Concatenar vídeos
                concat_inputs = "".join([f"[{i}:v]" for i in range(len(valid_videos))])
                filters.append(f"{concat_inputs}concat=n={len(valid_videos)}:v=1:a=0[outv]")
                video_input = "[outv]"
            
            # Escalar e adicionar legendas
            scale_filter = f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}"
            
            # Adicionar logo se existir
            logo_path = self.logo_path.get().strip()
            if logo_path and Path(logo_path).exists():
                logo_size_pct = float(self.logo_size.get()) / 100
                logo_w = int(VIDEO_WIDTH * logo_size_pct)
                
                pos = self.logo_position.get()
                if "Direito" in pos:
                    x_expr = f"W-w-20"
                else:
                    x_expr = "20"
                
                if "Superior" in pos:
                    y_expr = "20"
                else:
                    y_expr = f"H-h-20"
                
                # Primeiro escala e adiciona legendas
                filters.append(f"[0:v]{scale_filter},subtitles='{subtitle_path.replace(chr(92), chr(92)*2)}'[base]")
                
                # Depois overlay da logo
                filters.append(f"[base][{len(valid_videos)}:v]overlay={x_expr}:{y_expr}:shortest=1[final]")
                video_output = "[final]"
                inputs.extend(["-i", logo_path])
            else:
                filters.append(f"[0:v]{scale_filter},subtitles='{subtitle_path.replace(chr(92), chr(92)*2)}'[final]")
                video_output = "[final]"
            
            filter_complex = ";".join(filters)
            
            # Comando FFmpeg
            cmd = [
                "ffmpeg", "-y",
                *inputs,
                "-filter_complex", filter_complex,
                "-map", video_output,
                "-map", "0:a",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                output_path
            ]
            
            self.log(f"Executando FFmpeg...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                self.log(f"FFmpeg stderr: {result.stderr}")
                return False
            
            return True
            
        except Exception as e:
            self.log(f"Erro na renderização: {e}")
            return False

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    app = VideoGeneratorApp()
    app.run()
