from __future__ import annotations

import json
import os
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

# Configurações globais
APP_TITLE = "VideoGenerator Pro"
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
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        self.root.configure(bg="#f0f0f0")

        # Variáveis de configuração
        self.pexels_key = StringVar()
        self.groq_key = StringVar()
        self.logo_path = StringVar(value="")
        self.logo_position = StringVar(value="Superior Direito")
        self.logo_size = StringVar(value="15")
        self.logo_text = StringVar(value="")
        self.logo_text_font = StringVar(value="Arial")
        self.logo_text_size = StringVar(value="24")
        self.logo_text_offset = StringVar(value="12")
        self.script_lines: list[ScriptLine] = []
        self.is_generating = False
        self.stop_flag = threading.Event()

        # Criar diretórios
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        LOGO_DIR.mkdir(parents=True, exist_ok=True)

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
                self.logo_text_size.set(cfg.get("logo_text_size", "24"))
                self.logo_text_offset.set(cfg.get("logo_text_offset", "12"))
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
        # Estilo das abas
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TNotebook', background='#f0f0f0')
        style.configure('TNotebook.Tab', padding=[15, 8], font=('Segoe UI', 11))
        style.configure('TNotebook.Tab', background='#e0e0e0')
        style.map('TNotebook.Tab', background=[('selected', '#4CAF50')], foreground=[('selected', 'white')])

        # Notebook (abas)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # Aba 1: Configurações
        self.tab_config = Frame(self.notebook, bg="#f0f0f0")
        self.notebook.add(self.tab_config, text="⚙️ Configurações")
        self.setup_config_tab()

        # Aba 2: Roteiro
        self.tab_script = Frame(self.notebook, bg="#f0f0f0")
        self.notebook.add(self.tab_script, text="📝 Roteiro")
        self.setup_script_tab()

        # Aba 3: Logo
        self.tab_logo = Frame(self.notebook, bg="#f0f0f0")
        self.notebook.add(self.tab_logo, text="🖼️ Logo")
        self.setup_logo_tab()

        # Aba 4: Gerar Vídeo
        self.tab_generate = Frame(self.notebook, bg="#f0f0f0")
        self.notebook.add(self.tab_generate, text="🎬 Gerar Vídeo")
        self.setup_generate_tab()

    def setup_config_tab(self) -> None:
        container = Frame(self.tab_config, bg="#f0f0f0")
        container.pack(padx=30, pady=30, fill=X)

        # Título
        title = Label(container, text="Configurações das APIs", font=("Segoe UI", 16, "bold"), bg="#f0f0f0", fg="#333")
        title.pack(anchor="w", pady=(0, 20))

        # API Pexels
        frame1 = Frame(container, bg="#fff", relief="raised", borderwidth=1)
        frame1.pack(fill=X, pady=10, padx=5)
        
        lbl1 = Label(frame1, text="🔑 Chave da API Pexels:", font=("Segoe UI", 11), bg="#fff")
        lbl1.grid(row=0, column=0, sticky="w", pady=15, padx=15)
        entry1 = Entry(frame1, textvariable=self.pexels_key, width=50, show="*", font=("Segoe UI", 10))
        entry1.grid(row=0, column=1, pady=15, padx=10, ipady=5)

        # API Groq
        frame2 = Frame(container, bg="#fff", relief="raised", borderwidth=1)
        frame2.pack(fill=X, pady=10, padx=5)
        
        lbl2 = Label(frame2, text="🔑 Chave da API Groq:", font=("Segoe UI", 11), bg="#fff")
        lbl2.grid(row=0, column=0, sticky="w", pady=15, padx=15)
        entry2 = Entry(frame2, textvariable=self.groq_key, width=50, show="*", font=("Segoe UI", 10))
        entry2.grid(row=0, column=1, pady=15, padx=10, ipady=5)

        # Botão salvar
        btn_frame = Frame(container, bg="#f0f0f0")
        btn_frame.pack(pady=30)
        
        btn = Button(btn_frame, text="💾 Salvar Configurações", command=self.save_config, 
                     bg="#4CAF50", fg="white", font=("Segoe UI", 12, "bold"), padx=20, pady=10)
        btn.pack()

        # Informações
        info = Label(container, text="💡 Obtenha suas chaves em: pexels.com/api e console.groq.com", 
                     font=("Segoe UI", 10), bg="#f0f0f0", fg="#666")
        info.pack(pady=10)

    def setup_script_tab(self) -> None:
        # Frame superior - Prompt
        top_frame = Frame(self.tab_script, bg="#f0f0f0")
        top_frame.pack(fill=X, padx=20, pady=15)

        lbl = Label(top_frame, text="✨ Prompt para gerar roteiro com IA:", 
                    font=("Segoe UI", 12, "bold"), bg="#f0f0f0", fg="#333")
        lbl.pack(anchor="w", pady=(0, 8))

        self.prompt_entry = Text(top_frame, height=2, width=100, font=("Segoe UI", 11))
        self.prompt_entry.pack(fill=X, pady=5)
        self.prompt_entry.insert(END, "Crie um roteiro curto sobre curiosidades de viagens")

        btn_frame = Frame(top_frame, bg="#f0f0f0")
        btn_frame.pack(fill=X, pady=8)

        btn = Button(btn_frame, text="🤖 Gerar Roteiro com IA", 
                     command=self.generate_script_with_ai, 
                     bg="#2196F3", fg="white", font=("Segoe UI", 11, "bold"), padx=15, pady=8)
        btn.pack(side=LEFT)

        # Frame central - Editor de roteiro
        mid_frame = Frame(self.tab_script, bg="#f0f0f0")
        mid_frame.pack(fill=BOTH, expand=True, padx=20, pady=10)

        lbl = Label(mid_frame, text="📄 Editar roteiro (uma frase por linha):", 
                    font=("Segoe UI", 12, "bold"), bg="#f0f0f0", fg="#333")
        lbl.pack(anchor="w", pady=(0, 8))

        self.script_text = Text(mid_frame, height=12, width=100, font=("Consolas", 11))
        self.script_text.pack(fill=BOTH, expand=True, pady=5)
        self.script_text.insert(END, DEFAULT_SCRIPT)

        # Frame inferior - Botões
        bot_frame = Frame(self.tab_script, bg="#f0f0f0")
        bot_frame.pack(fill=X, padx=20, pady=10)

        btn1 = Button(bot_frame, text="📂 Carregar Roteiro", 
                      command=self.load_script_file, 
                      bg="#9E9E9E", fg="white", font=("Segoe UI", 10), padx=12, pady=6)
        btn1.pack(side=LEFT, padx=3)

        btn2 = Button(bot_frame, text="💾 Salvar Roteiro", 
                      command=self.save_script_file, 
                      bg="#9E9E9E", fg="white", font=("Segoe UI", 10), padx=12, pady=6)
        btn2.pack(side=LEFT, padx=3)

    def setup_logo_tab(self) -> None:
        # Canvas com scrollbar para a aba Logo
        canvas = Canvas(self.tab_logo, bg="#f0f0f0", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.tab_logo, orient="vertical", command=canvas.yview)
        
        inner_frame = Frame(canvas, bg="#f0f0f0")
        
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
        container = Frame(inner_frame, bg="#f0f0f0", padx=30, pady=20)
        container.pack(fill=X)

        row = 0
        
        # Seção 1: Arquivo da Logo
        section1 = Frame(container, bg="#fff", relief="raised", borderwidth=1)
        section1.pack(fill=X, pady=10)
        
        lbl_title = Label(section1, text="🖼️ Arquivo da Logo", 
                         font=("Segoe UI", 13, "bold"), bg="#fff", fg="#333")
        lbl_title.grid(row=0, column=0, columnspan=2, sticky="w", pady=15, padx=15)
        
        path_frame = Frame(section1, bg="#fff")
        path_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=10, padx=15)
        
        self.logo_path_label = Label(path_frame, text=self.logo_path.get() or "Nenhuma logo selecionada", 
                                     font=("Segoe UI", 9), bg="#f5f5f5", relief="sunken", anchor="w", width=70)
        self.logo_path_label.pack(side=LEFT, fill=X, expand=True, ipady=5)
        
        btn1 = Button(path_frame, text="Selecionar...", command=self.select_logo, 
                      bg="#2196F3", fg="white", font=("Segoe UI", 9))
        btn1.pack(side=LEFT, padx=5)
        
        btn2 = Button(path_frame, text="Limpar", command=self.clear_logo, 
                      bg="#f44336", fg="white", font=("Segoe UI", 9))
        btn2.pack(side=LEFT, padx=5)
        
        # Preview da logo
        self.logo_preview_label = Label(section1, text="", bg="#fff")
        self.logo_preview_label.grid(row=2, column=0, columnspan=2, pady=15, padx=15)
        
        # Seção 2: Posição e Tamanho
        section2 = Frame(container, bg="#fff", relief="raised", borderwidth=1)
        section2.pack(fill=X, pady=10)
        
        lbl_pos = Label(section2, text="📍 Posição da Logo", 
                       font=("Segoe UI", 13, "bold"), bg="#fff", fg="#333")
        lbl_pos.grid(row=0, column=0, columnspan=2, sticky="w", pady=15, padx=15)
        
        positions = ["Superior Esquerdo", "Superior Direito", "Inferior Esquerdo", "Inferior Direito"]
        combo = ttk.Combobox(section2, textvariable=self.logo_position, values=positions, 
                            state="readonly", width=30, font=("Segoe UI", 10))
        combo.grid(row=1, column=0, sticky="w", pady=10, padx=15)
        
        lbl_size = Label(section2, text="📏 Tamanho da Logo (%):", 
                        font=("Segoe UI", 11), bg="#fff")
        lbl_size.grid(row=2, column=0, sticky="w", pady=10, padx=15)
        
        scale1 = ttk.Scale(section2, from_=5, to=40, variable=self.logo_size, orient="horizontal", length=200)
        scale1.grid(row=2, column=1, sticky="w", pady=10)
        
        size_lbl = Label(section2, textvariable=self.logo_size, font=("Segoe UI", 10), bg="#fff")
        size_lbl.grid(row=2, column=2, sticky="w", padx=10)
        
        # Seção 3: Texto abaixo da Logo
        section3 = Frame(container, bg="#fff", relief="raised", borderwidth=1)
        section3.pack(fill=X, pady=10)
        
        lbl_text = Label(section3, text="📝 Texto abaixo da Logo", 
                        font=("Segoe UI", 13, "bold"), bg="#fff", fg="#333")
        lbl_text.grid(row=0, column=0, columnspan=2, sticky="w", pady=15, padx=15)
        
        lbl_entry = Label(section3, text="Conteúdo do texto:", font=("Segoe UI", 11), bg="#fff")
        lbl_entry.grid(row=1, column=0, sticky="w", pady=8, padx=15)
        
        entry_text = Entry(section3, textvariable=self.logo_text, width=40, font=("Segoe UI", 10))
        entry_text.grid(row=1, column=1, sticky="w", pady=8, ipady=5)
        
        lbl_font = Label(section3, text="Fonte:", font=("Segoe UI", 11), bg="#fff")
        lbl_font.grid(row=2, column=0, sticky="w", pady=8, padx=15)
        
        fonts = ["Arial", "Segoe UI", "Times New Roman", "Courier New", "Verdana", "Georgia"]
        combo_font = ttk.Combobox(section3, textvariable=self.logo_text_font, values=fonts, 
                                  state="readonly", width=30, font=("Segoe UI", 10))
        combo_font.grid(row=2, column=1, sticky="w", pady=8)
        
        lbl_fsize = Label(section3, text="Tamanho da fonte:", font=("Segoe UI", 11), bg="#fff")
        lbl_fsize.grid(row=3, column=0, sticky="w", pady=8, padx=15)
        
        scale2 = ttk.Scale(section3, from_=10, to=50, variable=self.logo_text_size, orient="horizontal", length=200)
        scale2.grid(row=3, column=1, sticky="w", pady=8)
        
        font_size_lbl = Label(section3, textvariable=self.logo_text_size, font=("Segoe UI", 10), bg="#fff")
        font_size_lbl.grid(row=3, column=2, sticky="w", padx=10)
        
        lbl_offset = Label(section3, text="Distância do texto (px):", font=("Segoe UI", 11), bg="#fff")
        lbl_offset.grid(row=4, column=0, sticky="w", pady=8, padx=15)
        
        scale3 = ttk.Scale(section3, from_=-20, to=50, variable=self.logo_text_offset, orient="horizontal", length=200)
        scale3.grid(row=4, column=1, sticky="w", pady=8)
        
        offset_lbl = Label(section3, textvariable=self.logo_text_offset, font=("Segoe UI", 10), bg="#fff")
        offset_lbl.grid(row=4, column=2, sticky="w", padx=10)
        
        # Botão salvar
        btn_frame = Frame(container, bg="#f0f0f0")
        btn_frame.pack(pady=20)
        
        btn = Button(btn_frame, text="💾 Salvar Configurações da Logo", 
                     command=self.save_logo_config, 
                     bg="#4CAF50", fg="white", font=("Segoe UI", 11, "bold"), padx=20, pady=10)
        btn.pack()

    def setup_generate_tab(self) -> None:
        frame = Frame(self.tab_generate, bg="#f0f0f0")
        frame.pack(fill=BOTH, expand=True, padx=20, pady=20)

        # Status
        status_frame = Frame(frame, bg="#fff", relief="raised", borderwidth=1)
        status_frame.pack(fill=X, pady=10)
        
        self.status_label = Label(status_frame, text="✅ Pronto para gerar", 
                                  font=("Segoe UI", 13, "bold"), bg="#fff", fg="#333")
        self.status_label.pack(anchor="w", pady=15, padx=15)
        
        self.progress_label = Label(status_frame, text="", 
                                    font=("Segoe UI", 10), bg="#fff", fg="#666")
        self.progress_label.pack(anchor="w", pady=5, padx=15)

        # Log
        log_frame = Frame(frame, bg="#f0f0f0")
        log_frame.pack(fill=BOTH, expand=True, pady=15)
        
        lbl = Label(log_frame, text="📋 Log de Processamento:", 
                    font=("Segoe UI", 11, "bold"), bg="#f0f0f0", fg="#333")
        lbl.pack(anchor="w", pady=(0, 8))
        
        self.log_text = Text(log_frame, height=15, width=100, font=("Consolas", 9), 
                             bg="#fff", relief="sunken")
        self.log_text.pack(fill=BOTH, expand=True, pady=5)

        # Botões
        btn_frame = Frame(frame, bg="#f0f0f0")
        btn_frame.pack(fill=X, pady=15)
        
        self.generate_btn = Button(btn_frame, text="▶️ Gerar Vídeo", 
                                   command=self.start_generation, 
                                   bg="#4CAF50", fg="white", 
                                   font=("Segoe UI", 13, "bold"), padx=25, pady=12)
        self.generate_btn.pack(side=LEFT, padx=5)
        
        self.stop_btn = Button(btn_frame, text="⏹️ Parar", 
                               command=self.stop_generation, 
                               bg="#f44336", fg="white", 
                               font=("Segoe UI", 13, "bold"), padx=25, pady=12, state="disabled")
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

    def log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(END, f"[{timestamp}] {message}\n")
        self.log_text.see(END)
        self.root.update_idletasks()

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
        
        system_prompt = """Você é um roteirista profissional para vídeos curtos verticais (TikTok/Reels/Shorts).
Crie um roteiro ENGAGANTE e DINÂMICO com frases curtas e impactantes.
IMPORTANTE: Retorne APENAS o roteiro, uma frase por linha, sem numeração, sem marcadores, sem explicações.
Máximo de 8 frases."""

        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Crie um roteiro curto e envolvente sobre: {prompt}"}
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }

        try:
            resp = requests.post("https://api.groq.com/openai/v1/chat/completions", 
                               headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            
            data = resp.json()
            script = data["choices"][0]["message"]["content"].strip()
            
            # Limpar formatação indesejada
            lines = []
            for line in script.split("\n"):
                line = re.sub(r"^\d+[\.\)]\s*", "", line.strip())
                line = re.sub(r"^[-•*]\s*", "", line.strip())
                if line:
                    lines.append(line)
            
            self.script_text.delete("1.0", END)
            self.script_text.insert(END, "\n".join(lines))
            
            self.log(f"Roteiro gerado com sucesso! {len(lines)} frases.")
            
        except Exception as e:
            self.log(f"Erro ao gerar roteiro: {e}")
            messagebox.showerror("Erro", f"Falha ao gerar roteiro:\n{e}")

    def load_script_file(self) -> None:
        filetypes = [("Arquivos de texto", "*.txt")]
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
        filetypes = [("Arquivos de texto", "*.txt")]
        path = filedialog.asksaveasfilename(title="Salvar Roteiro", filetypes=filetypes, defaultextension=".txt")
        if path:
            try:
                content = self.script_text.get("1.0", END).strip()
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.log(f"Roteiro salvo: {path}")
            except Exception as e:
                messagebox.showerror("Erro", f"Falha ao salvar roteiro:\n{e}")

    def start_generation(self) -> None:
        script_content = self.script_text.get("1.0", END).strip()
        if not script_content:
            messagebox.showwarning("Atenção", "O roteiro está vazio.")
            return

        pexels_key = self.pexels_key.get().strip()
        if not pexels_key:
            messagebox.showwarning("Atenção", "Configure sua chave da API Pexels em Configurações.")
            return

        self.is_generating = True
        self.stop_flag.clear()
        
        self.generate_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_label.config(text="⏳ Gerando vídeo...", fg="#FF9800")
        self.log_text.delete("1.0", END)
        
        thread = threading.Thread(target=self.generation_thread, args=(script_content, pexels_key))
        thread.daemon = True
        thread.start()

    def stop_generation(self) -> None:
        self.stop_flag.set()
        self.is_generating = False
        self.log("⚠️ Geração interrompida pelo usuário")
        self.generate_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status_label.config(text="⏹️ Geração interrompida", fg="#f44336")

    def generation_thread(self, script_content: str, pexels_key: str) -> None:
        temp_dir = tempfile.mkdtemp(prefix="videogenerator_")
        
        try:
            lines = [l.strip() for l in script_content.split("\n") if l.strip()]
            self.log(f"Iniciando geração com {len(lines)} frases...")
            
            video_paths = []
            audio_paths = []
            subtitle_paths = []
            
            for i, line in enumerate(lines):
                if self.stop_flag.is_set():
                    break
                    
                self.log(f"Processando frase {i+1}/{len(lines)}: '{line[:50]}...'")
                
                # Gerar áudio TTS
                audio_path = os.path.join(temp_dir, f"audio_{i:03d}.wav")
                if self.generate_tts_audio(line, audio_path):
                    audio_paths.append(audio_path)
                    self.log(f"  ✓ Áudio gerado")
                else:
                    self.log(f"  ✗ Falha ao gerar áudio")
                    continue
                
                # Buscar vídeo no Pexels
                video_path = os.path.join(temp_dir, f"video_{i:03d}.mp4")
                video_url = self.search_pexels_video(line, pexels_key)
                if video_url and self.download_video(video_url, video_path):
                    video_paths.append(video_path)
                    self.log(f"  ✓ Vídeo baixado")
                else:
                    self.log(f"  ⚠ Vídeo não encontrado (usará tela preta)")
                    video_paths.append("")
                
                # Gerar legenda
                subtitle_path = os.path.join(temp_dir, f"subtitle_{i:03d}.ass")
                self.generate_subtitle_file(subtitle_path, line, audio_path)
                subtitle_paths.append(subtitle_path)
                self.log(f"  ✓ Legenda gerada")
            
            if not audio_paths:
                self.log("❌ Nenhum áudio foi gerado. Cancelando.")
                self.root.after(0, lambda: self.status_label.config(text="❌ Erro na geração", fg="#f44336"))
                return
            
            # Concatenar áudios
            concatenated_audio = os.path.join(temp_dir, "concatenated_audio.wav")
            self.concatenate_audios(audio_paths, concatenated_audio)
            self.log("✓ Áudios concatenados")
            
            # Gerar legenda única
            full_subtitle = os.path.join(temp_dir, "full_subtitle.ass")
            full_text = " ".join(lines)
            self.generate_subtitle_file(full_subtitle, full_text, concatenated_audio)
            self.log("✓ Legenda completa gerada")
            
            # Renderizar vídeo final
            output_path = filedialog.asksaveasfilename(
                title="Salvar Vídeo Final",
                defaultextension=".mp4",
                filetypes=[("MP4", "*.mp4")]
            )
            
            if not output_path:
                self.log("⚠️ Usuário cancelou o salvamento")
                return
            
            self.log("🎬 Renderizando vídeo final...")
            
            if self.render_final_video(temp_dir, video_paths, concatenated_audio, full_subtitle, output_path):
                self.log(f"✅ Vídeo salvo com sucesso: {output_path}")
                self.root.after(0, lambda: self.status_label.config(text="✅ Vídeo gerado com sucesso!", fg="#4CAF50"))
                self.root.after(0, lambda: messagebox.showinfo("Sucesso", f"Vídeo gerado!\n\n{output_path}"))
            else:
                self.log("❌ Erro na renderização final")
                self.root.after(0, lambda: self.status_label.config(text="❌ Erro na renderização", fg="#f44336"))
                
        except Exception as e:
            self.log(f"❌ Erro crítico: {e}")
            self.root.after(0, lambda: self.status_label.config(text="❌ Erro crítico", fg="#f44336"))
        finally:
            self.is_generating = False
            self.root.after(0, lambda: self.generate_btn.config(state="normal"))
            self.root.after(0, lambda: self.stop_btn.config(state="disabled"))
            
            # Limpar temp dir
            try:
                shutil.rmtree(temp_dir)
            except:
                pass

    def generate_tts_audio(self, text: str, output_path: str) -> bool:
        """Gera áudio usando pyttsx3 (offline)"""
        try:
            import pyttsx3
            
            engine = pyttsx3.init()
            
            # Configurar voz em português
            voices = engine.getProperty('voices')
            pt_voice = None
            for voice in voices:
                if 'brazil' in voice.id.lower() or 'portuguese' in voice.id.lower() or 'br' in voice.id.lower():
                    pt_voice = voice
                    break
            
            if pt_voice:
                engine.setProperty('voice', pt_voice.id)
            
            engine.setProperty('rate', 150)  # Velocidade
            engine.setProperty('volume', 1.0)
            
            # Limpar texto
            clean_text = re.sub(r'\s+', ' ', text).strip()
            
            engine.save_to_file(clean_text, output_path)
            engine.runAndWait()
            
            # Verificar se arquivo foi criado
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
            
            # Fallback: criar silêncio
            sample_rate = 22050
            duration = max(1.0, len(clean_text) * 0.08)
            samples = int(sample_rate * duration)
            audio_data = np.zeros(samples, dtype=np.float32)
            sf.write(output_path, audio_data, sample_rate)
            return True
            
        except Exception as e:
            self.log(f"Erro TTS: {e}")
            # Fallback
            try:
                sample_rate = 22050
                duration = max(1.0, len(text) * 0.08)
                samples = int(sample_rate * duration)
                audio_data = np.zeros(samples, dtype=np.float32)
                sf.write(output_path, audio_data, sample_rate)
                return True
            except:
                return False

    def concatenate_audios(self, audio_paths: list, output_path: str) -> bool:
        """Concatena múltiplos arquivos de áudio"""
        try:
            all_audio = []
            sample_rate = None
            
            for ap in audio_paths:
                if os.path.exists(ap):
                    data, sr = sf.read(ap)
                    if sample_rate is None:
                        sample_rate = sr
                    elif sr != sample_rate:
                        # Resample se necessário
                        from scipy import signal
                        num_samples = int(len(data) * sample_rate / sr)
                        data = signal.resample(data, num_samples)
                    all_audio.append(data)
            
            if all_audio:
                concatenated = np.concatenate(all_audio)
                sf.write(output_path, concatenated, sample_rate)
                return True
            
            return False
        except Exception as e:
            self.log(f"Erro na concatenação: {e}")
            return False

    def search_pexels_video(self, query: str, api_key: str) -> str | None:
        """Busca vídeo no Pexels"""
        try:
            headers = {"Authorization": api_key}
            params = {"query": query, "per_page": 1, "orientation": "portrait"}
            
            resp = requests.get("https://api.pexels.com/videos/search", 
                              headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            
            data = resp.json()
            if data.get("videos"):
                video = data["videos"][0]
                files = video.get("video_files", [])
                for f in sorted(files, key=lambda x: x.get("width", 0), reverse=True):
                    if f.get("link"):
                        return f["link"]
        except Exception as e:
            self.log(f"Erro Pexels: {e}")
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
            self.log(f"Erro download: {e}")
            return False

    def generate_subtitle_file(self, output_path: str, text: str, audio_path: str) -> None:
        """Gera arquivo de legendas ASS sincronizado"""
        words = text.split()
        total_words = len(words)
        
        # Obter duração real do áudio
        audio_duration = 5.0
        try:
            with wave.open(audio_path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                audio_duration = frames / float(rate)
        except Exception as e:
            self.log(f"Aviso: Não foi possível ler duração do áudio")
        
        # Timing offset para sincronização (150ms de antecipação)
        timing_offset = 0.15
        word_duration = audio_duration / total_words if total_words > 0 else 1.0
        
        ass_content = f"""[Script Info]
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

    def render_final_video(self, temp_dir: str, video_paths: list, audio_path: str, 
                          subtitle_path: str, output_path: str) -> bool:
        """Renderiza vídeo final com FFmpeg"""
        try:
            filters = []
            inputs = []
            
            # Input de áudio
            inputs.extend(["-i", audio_path])
            
            # Inputs de vídeo
            valid_videos = [v for v in video_paths if v]
            for vp in valid_videos:
                inputs.extend(["-i", vp])
            
            # Se não há vídeos, criar tela preta
            if not valid_videos:
                color_filter = f"color=black:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d=5"
                filters.append(f"[0:v]{color_filter}[bg]")
                base_input = "[bg]"
            else:
                # Concatenar vídeos
                concat_inputs = "".join([f"[{i}:v]" for i in range(len(valid_videos))])
                filters.append(f"{concat_inputs}concat=n={len(valid_videos)}:v=1:a=0[outv]")
                base_input = "[outv]"
            
            # Escalar e adicionar legendas
            scale_filter = f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}"
            
            # Adicionar logo se existir
            logo_path = self.logo_path.get().strip()
            if logo_path and Path(logo_path).exists():
                logo_size_pct = float(self.logo_size.get()) / 100
                logo_w = int(VIDEO_WIDTH * logo_size_pct)
                
                pos = self.logo_position.get()
                if "Direito" in pos:
                    x_expr = f"W-w-36"
                else:
                    x_expr = "36"
                
                if "Superior" in pos:
                    y_expr = "36"
                else:
                    y_expr = f"H-h-36"
                
                # Primeiro escala e adiciona legendas
                subtitle_escaped = subtitle_path.replace("\\", "\\\\")
                filters.append(f"[0:v]{scale_filter},subtitles='{subtitle_escaped}'[base]")
                
                # Overlay da logo
                logo_index = len(valid_videos)
                filters.append(f"[base][{logo_index}:v]overlay={x_expr}:{y_expr}:shortest=1[with_logo]")
                
                # Adicionar texto abaixo da logo
                logo_text = self.logo_text.get().strip()
                if logo_text:
                    font_name = self.logo_text_font.get()
                    font_size = int(self.logo_text_size.get())
                    text_offset = int(self.logo_text_offset.get())
                    
                    y_text = f"{y_expr}+h+{text_offset}"
                    
                    # Usar (w-text_w)/2 para centralizar
                    filters.append(
                        f"[with_logo]drawtext=text='{logo_text}':fontcolor=white:fontsize={font_size}:x=(w-text_w)/2:y={y_text}:font='{font_name}'[r]"
                    )
                    video_output = "[r]"
                else:
                    video_output = "[with_logo]"
                
                inputs.extend(["-i", logo_path])
            else:
                subtitle_escaped = subtitle_path.replace("\\", "\\\\")
                filters.append(f"[0:v]{scale_filter},subtitles='{subtitle_escaped}'[final]")
                video_output = "[final]"
            
            filter_complex = ";".join(filters)
            
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
                self.log(f"FFmpeg error: {result.stderr}")
                return False
            
            return True
            
        except Exception as e:
            self.log(f"Erro renderização: {e}")
            return False

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    app = VideoGeneratorApp()
    app.run()
