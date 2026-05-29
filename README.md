# VideoGenerator

Aplicativo desktop minimalista para Windows que transforma um roteiro em um vídeo sequencial usando:

- **Google Gemini API** para gerar a narração de cada frase.
- **Pexels API** para buscar ou baixar vídeos/fotos relacionados a cada frase.
- **FFmpeg** (via `imageio-ffmpeg`) para montar o vídeo final.

## Como executar em desenvolvimento

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

No Linux/macOS use `source .venv/bin/activate` no lugar do comando de ativação do Windows.

## Como gerar um `.exe` para Windows

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name VideoGenerator app.py
```

O executável será criado em `dist/VideoGenerator.exe`.

## Uso

1. Abra o app.
2. Na aba **APIs**, informe a chave do Google Gemini e a chave do Pexels.
3. Na aba **Roteiro**, escreva uma frase por linha.
4. Clique em **Atualizar lista de frases**.
5. Opcionalmente, clique em **Link Pexels** ao lado de uma frase para colar uma URL manual.
6. Escolha a pasta de saída.
7. Clique em **Gerar vídeo**.

Se uma frase não tiver link manual, o app pesquisa no Pexels pela própria frase e usa o primeiro vídeo/foto encontrado.
