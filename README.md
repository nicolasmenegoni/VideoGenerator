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
5. Na aba **Video**, copie um link do Pexels e clique em **Colar link** ao lado da frase para aplicar direto da área de transferência; o app carrega o preview pequeno da foto/vídeo em segundo plano quando consegue resolver a miniatura, sem travar a lista. Use **Editar** se quiser ajustar manualmente, ou deixe vazio para busca automática.
6. Na aba **Video**, escolha a pasta de saída.
7. Na aba **Legendas**, configure posição, cor, tamanho, fundo, cor do contorno e fonte. Digite uma frase de teste para ver o preview atualizar em tempo real, ou use **Legendas Desligadas** para renderizar sem legendas.
8. Na aba **Audio**, configure a automação do app do ChatGPT: atalho para abrir o app, tempo antes da primeira captura, tempo de espera da resposta, espera depois do menu e tempo extra/máximo de gravação. Não é necessário configurar coordenadas: o app captura a janela do ChatGPT e identifica automaticamente o campo de texto, o botão **Enviar**, os **3 pontinhos** da resposta e a opção **Ler em voz alta**. Depois de enviar a mensagem, ele aguarda o tempo configurado (padrão: 8 segundos) e então procura os **3 pontinhos**. No Windows, durante a gravação o app silencia temporariamente outras sessões de áudio pelo mixer do Windows, preservando somente a sessão da janela ativa do ChatGPT, ChatGPT Desktop/WebView e navegadores comuns quando o ChatGPT estiver aberto no browser; depois restaura os volumes. A gravação é armada antes de clicar em **Ler em voz alta** para não perder o começo da fala, tenta parar automaticamente ao detectar silêncio depois da fala e, se o áudio gravado sair silencioso, tenta repetir a leitura uma vez preservando sessões desconhecidas que às vezes são usadas pelo ChatGPT Desktop.
9. Na aba **Musica**, selecione uma música do PC e ajuste o volume da trilha; o padrão é **20%**. Use volume **0** para não misturar música e manter somente a narração.
10. Use o botão fixo **Gerar vídeo**, que fica sempre visível na parte inferior do app.

Se uma frase não tiver link manual, o app pesquisa no Pexels pela própria frase e usa o primeiro vídeo/foto encontrado. Para cada frase, o app abre o ChatGPT pelo atalho configurado, captura a janela ativa, localiza o campo de mensagem e o botão **Enviar** pela imagem, escreve `Apenas repita isso com aspas: "[frase]"`, espera o tempo configurado para a resposta (padrão: 8 segundos), procura os **3 pontinhos** abaixo do texto, abre o menu, identifica a área nova do menu para acionar **Ler em voz alta** e grava o áudio do sistema até detectar silêncio. Cada frase também é aplicada como legenda na cena correspondente, junto do áudio e da mídia selecionada. Se uma música for selecionada, ela toca durante todo o vídeo no volume configurado.
