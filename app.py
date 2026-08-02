from __future__ import annotations

import json
import queue
import threading
import requests
import re
from dataclasses import dataclass
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, Button, Canvas, Entry, Frame, Label, StringVar, Text, Tk, messagebox, ttk
from tkinter import font as tkfont

APP_TITLE = "VideoGenerator Lite"
CONFIG_FILE = Path.home() / ".videogenerator_lite_config.json"
DEFAULT_SCRIPT = "Hoje vamos falar sobre a China.\nEsse país é incrível.\nVamos te provar."

@dataclass
class ScriptLine:
    text: str
    media_url: str = ""


class VideoGeneratorApp:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("900x650")
        self.root.minsize(800, 550)
        self.root.configure(bg="#f5f5f5")

        # Variáveis principais
        self.pexels_key = StringVar()
        self.groq_key = StringVar()
        self.video_title = StringVar(value="meu_video")
        self.script_text_value = DEFAULT_SCRIPT
        self.status_text = StringVar(value="Pronto.")
        
        self.lines: list[ScriptLine] = []
        self.message_queue: queue.Queue = queue.Queue()
        
        self._build_ui()
        self._load_config()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._process_queue)

    def run(self) -> None:
        self.root.mainloop()

    def _build_ui(self) -> None:
        # Container principal
        main = Frame(self.root, bg="#f5f5f5", padx=20, pady=15)
        main.pack(fill=BOTH, expand=True)

        # Header simples
        header = Frame(main, bg="#f5f5f5")
        header.pack(fill=X, pady=(0, 15))
        Label(header, text="VideoGenerator Lite", bg="#f5f5f5", fg="#333", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        Label(header, text="Simples, rápido e funcional", bg="#f5f5f5", fg="#666", font=("Segoe UI", 9)).pack(anchor="w")

        # Navegação por tabs
        nav = Frame(main, bg="#e0e0e0", pady=5)
        nav.pack(fill=X, pady=(0, 10))
        
        self.tabs_btn = {}
        for tab_id, label in [("apis", "APIs"), ("script", "Roteiro"), ("video", "Vídeo")]:
            btn = Button(nav, text=label, command=lambda t=tab_id: self._show_tab(t),
                        relief="flat", padx=20, pady=8, font=("Segoe UI", 10))
            btn.pack(side=LEFT, padx=5)
            self.tabs_btn[tab_id] = btn

        # Área de conteúdo
        self.content = Frame(main, bg="white", relief="flat", bd=1)
        self.content.pack(fill=BOTH, expand=True, pady=(0, 10))

        # Criar frames das tabs
        self.tab_frames = {}
        self.tab_frames["apis"] = Frame(self.content, bg="white", padx=20, pady=20)
        self.tab_frames["script"] = Frame(self.content, bg="white", padx=20, pady=20)
        self.tab_frames["video"] = Frame(self.content, bg="white", padx=20, pady=20)

        self._build_api_tab(self.tab_frames["apis"])
        self._build_script_tab(self.tab_frames["script"])
        self._build_video_tab(self.tab_frames["video"])

        self._show_tab("script")

        # Footer com status
        footer = Frame(main, bg="#f5f5f5")
        footer.pack(fill=X)
        Label(footer, textvariable=self.status_text, bg="#f5f5f5", fg="#555", font=("Segoe UI", 9)).pack(side=LEFT)

    def _show_tab(self, tab_id: str) -> None:
        # Esconder todas as tabs
        for frame in self.tab_frames.values():
            frame.pack_forget()
        
        # Mostrar tab selecionada
        self.tab_frames[tab_id].pack(fill=BOTH, expand=True)
        
        # Atualizar botões
        for key, btn in self.tabs_btn.items():
            if key == tab_id:
                btn.configure(bg="#4a90d9", fg="white", font=("Segoe UI", 10, "bold"))
            else:
                btn.configure(bg="#e0e0e0", fg="#333", font=("Segoe UI", 10))

    def _build_api_tab(self, parent: Frame) -> None:
        Label(parent, text="Configurar APIs", bg="white", fg="#333", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 15))
        
        # Pexels API
        Label(parent, text="Pexels API Key:", bg="white", fg="#444", font=("Segoe UI", 10)).pack(anchor="w", pady=(5, 5))
        Entry(parent, textvariable=self.pexels_key, show="*", bd=1, relief="solid", bg="#fafafa", font=("Segoe UI", 11)).pack(fill=X, ipady=5)
        
        # Groq API
        Label(parent, text="Groq API Key:", bg="white", fg="#444", font=("Segoe UI", 10)).pack(anchor="w", pady=(15, 5))
        Entry(parent, textvariable=self.groq_key, show="*", bd=1, relief="solid", bg="#fafafa", font=("Segoe UI", 11)).pack(fill=X, ipady=5)
        
        # Botão salvar
        Button(parent, text="Salvar Configurações", command=self._save_config, 
              bg="#4a90d9", fg="white", relief="flat", padx=20, pady=8, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(20, 0))

    def _build_script_tab(self, parent: Frame) -> None:
        Label(parent, text="Roteiro do Vídeo", bg="white", fg="#333", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 10))
        
        # Título do vídeo
        Label(parent, text="Título do vídeo:", bg="white", fg="#444", font=("Segoe UI", 10)).pack(anchor="w", pady=(10, 5))
        Entry(parent, textvariable=self.video_title, bd=1, relief="solid", bg="#fafafa", font=("Segoe UI", 11)).pack(fill=X, ipady=5)
        
        # Roteiro
        Label(parent, text="Roteiro (uma frase por linha):", bg="white", fg="#444", font=("Segoe UI", 10)).pack(anchor="w", pady=(15, 5))
        
        script_frame = Frame(parent, bg="white")
        script_frame.pack(fill=BOTH, expand=True)
        
        self.script_text = Text(script_frame, height=12, wrap="word", bd=1, relief="solid", 
                               bg="#fafafa", fg="#333", insertbackground="#333", font=("Segoe UI", 11), padx=10, pady=10)
        scrollbar = ttk.Scrollbar(script_frame, orient="vertical", command=self.script_text.yview)
        self.script_text.configure(yscrollcommand=scrollbar.set)
        
        self.script_text.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        self.script_text.insert("1.0", self.script_text_value)
        
        # Botões de ação
        btn_frame = Frame(parent, bg="white")
        btn_frame.pack(fill=X, pady=(15, 0))
        
        Button(btn_frame, text="Gerar Roteiro com IA", command=self._generate_script, 
              bg="#4a90d9", fg="white", relief="flat", padx=20, pady=8, font=("Segoe UI", 10, "bold")).pack(side=LEFT, padx=(0, 10))
        
        Button(btn_frame, text="Atualizar Linhas", command=self._refresh_lines, 
              bg="#e0e0e0", fg="#333", relief="flat", padx=20, pady=8, font=("Segoe UI", 10)).pack(side=LEFT)

    def _build_video_tab(self, parent: Frame) -> None:
        Label(parent, text="Configurações de Vídeo", bg="white", fg="#333", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 15))
        
        info = Frame(parent, bg="#e8f4fd", padx=15, pady=10)
        info.pack(fill=X, pady=(0, 15))
        Label(info, text="Configure os vídeos para cada linha do roteiro.", bg="#e8f4fd", fg="#333", font=("Segoe UI", 10)).pack()
        
        # Lista de linhas (canvas scrollable)
        list_frame = Frame(parent, bg="white")
        list_frame.pack(fill=BOTH, expand=True)
        
        self.lines_canvas = Canvas(list_frame, bd=0, highlightthickness=0, bg="#fafafa")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.lines_canvas.yview)
        self.lines_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.lines_frame = Frame(self.lines_canvas, bg="#fafafa")
        self.lines_window = self.lines_canvas.create_window((0, 0), window=self.lines_frame, anchor="nw")
        
        scrollbar.pack(side=RIGHT, fill=Y)
        self.lines_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        
        self.lines_frame.bind("<Configure>", lambda e: self.lines_canvas.configure(scrollregion=self.lines_canvas.bbox("all")))
        self.lines_canvas.bind("<Configure>", lambda e: self.lines_canvas.itemconfig(self.lines_window, width=e.width))

    def _refresh_lines(self) -> None:
        # Limpar frame
        for widget in self.lines_frame.winfo_children():
            widget.destroy()
        
        # Obter texto do script
        script_content = self.script_text.get("1.0", END).strip()
        lines_list = [line.strip() for line in script_content.split("\n") if line.strip()]
        
        self.lines = [ScriptLine(text=line) for line in lines_list]
        
        # Criar widgets para cada linha
        for idx, line_obj in enumerate(self.lines):
            row = Frame(self.lines_frame, bg="#fafafa", pady=5)
            row.pack(fill=X, padx=5, pady=2)
            
            # Número da linha
            Label(row, text=f"{idx + 1}.", bg="#fafafa", fg="#666", font=("Segoe UI", 10, "bold"), width=3).pack(side=LEFT)
            
            # Texto da linha
            Label(row, text=line_obj.text[:50] + "..." if len(line_obj.text) > 50 else line_obj.text, 
                 bg="white", fg="#333", font=("Segoe UI", 10), relief="solid", bd=1, padx=10, pady=5).pack(side=LEFT, fill=X, expand=True, padx=(0, 10))
            
            # Campo URL
            Entry(row, textvariable=StringVar(value=line_obj.media_url), bd=1, relief="solid", 
                 bg="#fafafa", font=("Segoe UI", 9), width=30).pack(side=LEFT)

    def _generate_script(self) -> None:
        title = self.video_title.get().strip()
        if not title:
            messagebox.showwarning(APP_TITLE, "Digite um título para o vídeo!")
            return
        
        if not self.groq_key.get().strip():
            messagebox.showwarning(APP_TITLE, "Configure a API Key do Groq na aba APIs!")
            self._show_tab("apis")
            return
        
        self.status_text.set("Gerando roteiro...")
        threading.Thread(target=self._generate_script_worker, args=(title,), daemon=True).start()

    def _generate_script_worker(self, title: str) -> None:
        try:
            prompt = f"Crie um roteiro curto para um vídeo vertical em português do Brasil sobre: {title}. O roteiro deve ter de 5 a 8 frases curtas, naturais para narração. Cada frase em uma linha separada. Sem numeração, marcadores ou texto extra."
            
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.groq_key.get().strip()}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": "Você cria roteiros curtos para vídeos."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500,
                },
                timeout=30,
            )
            
            if response.status_code >= 400:
                raise RuntimeError(f"Erro da API: {response.status_code}")
            
            content = response.json()["choices"][0]["message"]["content"]
            lines = [line.strip() for line in content.split("\n") if line.strip() and not line.strip().startswith(("-", "*", "•"))]
            
            if lines:
                self.root.after(0, lambda: self._apply_script(lines))
                self.message_queue.put(("status", "Roteiro gerado com sucesso!"))
            else:
                self.message_queue.put(("error", "Roteiro vazio retornado pela API"))
                
        except Exception as e:
            self.message_queue.put(("error", str(e)))

    def _apply_script(self, lines: list[str]) -> None:
        self.script_text.delete("1.0", END)
        self.script_text.insert("1.0", "\n".join(lines))
        self._refresh_lines()
        self._show_tab("video")

    def _save_config(self) -> None:
        config = {
            "pexels_key": self.pexels_key.get(),
            "groq_key": self.groq_key.get(),
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            self.status_text.set("Configurações salvas!")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Erro ao salvar: {e}")

    def _load_config(self) -> None:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                self.pexels_key.set(config.get("pexels_key", ""))
                self.groq_key.set(config.get("groq_key", ""))
            except Exception:
                pass

    def _process_queue(self) -> None:
        try:
            while True:
                msg_type, msg = self.message_queue.get_nowait()
                if msg_type == "error":
                    messagebox.showerror(APP_TITLE, msg)
                    self.status_text.set("Erro!")
                elif msg_type == "status":
                    self.status_text.set(msg)
        except queue.Empty:
            pass
        self.root.after(100, self._process_queue)

    def _on_close(self) -> None:
        # Salvar script atual
        self.script_text_value = self.script_text.get("1.0", END).strip()
        self._save_config()
        self.root.destroy()


def main():
    app = VideoGeneratorApp()
    app.run()


if __name__ == "__main__":
    main()
