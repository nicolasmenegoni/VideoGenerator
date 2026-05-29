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
3. Na aba **Roteiro**, preencha o **Titulo** e escreva uma frase por linha. O título será usado como nome do arquivo `.mp4`.
4. Clique em **Atualizar roteiro** para sincronizar as frases.
5. Na aba **Video**, clique em **Link Pexels** ao lado de cada frase para colar uma URL manual, ou deixe vazio para busca automática.
6. Na aba **Video**, escolha a pasta de saída.
7. Na aba **Legendas**, configure posição, cor, tamanho, fundo e fonte, usando o preview para visualizar o resultado.
8. Use o botão fixo **Gerar vídeo**, que fica sempre visível na parte inferior do app.

Se uma frase não tiver link manual, o app pesquisa no Pexels pela própria frase e usa o primeiro vídeo/foto encontrado. Cada frase também é aplicada como legenda na cena correspondente, junto do áudio e da mídia selecionada.
