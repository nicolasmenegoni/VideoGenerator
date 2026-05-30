# VideoGenerator

Aplicativo desktop minimalista para Windows que transforma um roteiro em um vídeo sequencial usando:

- **App do ChatGPT** para gerar e ler em voz alta a narração de cada frase.
- **Gravação do áudio do sistema** para salvar a voz lida pelo ChatGPT.
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
2. Na aba **APIs**, informe a chave do Pexels.
3. Na aba **Roteiro**, preencha o **Titulo** e escreva uma frase por linha. O título será usado como nome do arquivo `.mp4`.
4. Clique em **Atualizar roteiro** para sincronizar as frases.
5. Na aba **Video**, clique em **Link Pexels** ao lado de cada frase para colar uma URL manual, ou deixe vazio para busca automática.
6. Na aba **Video**, escolha a pasta de saída.
7. Na aba **Legendas**, configure posição, cor, tamanho, fundo, cor do contorno e fonte. Digite uma frase de teste para ver o preview atualizar em tempo real, ou use **Legendas Desligadas** para renderizar sem legendas.
8. Na aba **Audio**, configure a automação do app do ChatGPT: atalho para abrir o app, tempo antes de enviar, tempo de espera da resposta, coordenadas do botão **Enviar**, coordenadas dos **3 pontinhos**, espera depois do menu, coordenadas de **Ler em voz alta** e tempo extra/máximo de gravação. A gravação tenta parar automaticamente ao detectar silêncio depois da fala.
9. Na aba **Musica**, selecione uma música do PC e ajuste o volume da trilha; o padrão é **20%**.
10. Use o botão fixo **Gerar vídeo**, que fica sempre visível na parte inferior do app.

Se uma frase não tiver link manual, o app pesquisa no Pexels pela própria frase e usa o primeiro vídeo/foto encontrado. Para cada frase, o app abre o ChatGPT pelo atalho configurado, escreve `Apenas repita isso: [frase]`, clica no botão **Enviar**, espera a resposta, clica nos **3 pontinhos**, espera mais 1 segundo, aciona **Ler em voz alta** pelas coordenadas configuradas e grava o áudio do sistema até detectar silêncio. Cada frase também é aplicada como legenda na cena correspondente, junto do áudio e da mídia selecionada. Se uma música for selecionada, ela toca durante todo o vídeo no volume configurado.
