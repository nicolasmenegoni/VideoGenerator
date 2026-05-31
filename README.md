# VideoGenerator

Aplicativo desktop minimalista para Windows que transforma um roteiro em um vídeo sequencial usando:

- **App do ChatGPT** para gerar e ler em voz alta a narração de cada frase.
- **Gravação do áudio do sistema** para salvar a voz lida pelo ChatGPT.
- **Pexels API** para buscar ou baixar vídeos/fotos relacionados a cada frase.
- **Groq API** para transformar cada frase, com o contexto completo do roteiro, em pesquisas melhores para o Pexels.
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
2. Na aba **APIs**, informe as chaves do Pexels e do Groq. O app salva localmente as chaves e demais configurações quando você clica em **Salvar chaves**, sincroniza o roteiro, gera/atualiza vídeos ou fecha a janela.
3. Na aba **Roteiro**, preencha o **Titulo** e escreva uma frase por linha. O título será usado como nome do arquivo `.mp4`. Se quiser criar o texto automaticamente, clique em **Gerar roteiro** para o Groq gerar frases curtas com base no título.
4. Clique em **Atualizar roteiro** para sincronizar as frases. O texto do roteiro gerado/manual e os links de mídia por frase são restaurados quando você fecha e abre o app novamente.
5. Na aba **Video**, clique em **Atualizar videos** para o Groq analisar cada frase junto com o contexto do roteiro, criar pesquisas visuais para o Pexels e preencher automaticamente os links e previews. Você também pode copiar um link do Pexels e clicar em **Colar link** ao lado da frase para aplicar direto da área de transferência; o app carrega o preview pequeno da foto/vídeo em segundo plano quando consegue resolver a miniatura, sem travar a lista. Use **Gerar outro video** em uma frase para pedir ao Groq uma nova busca e trocar apenas aquele item, use **Editar** se quiser ajustar manualmente, ou deixe vazio para busca automática.
6. Na aba **Video**, escolha a pasta de saída e ajuste o tempo extra após o áudio quando o vídeo encontrado for maior que a narração; o padrão é **1 segundo**.
7. Na aba **Legendas**, configure posição, cor, tamanho, fundo, cor do contorno e fonte. Digite uma frase de teste para ver o preview atualizar em tempo real, ou use **Legendas Desligadas** para renderizar sem legendas. Na renderização final, o app quebra linhas com margem segura, usa fonte padrão mais forte, espaçamento entre linhas compacto, reduz o tamanho quando a frase é longa e faz as palavras aparecerem progressivamente ao longo do áudio usando exatamente o texto da frase do roteiro em um arquivo temporário de legenda.
8. Na aba **Audio**, configure a automação do app do ChatGPT: atalho para abrir o app, tempo antes da primeira captura, tempo de espera da resposta, espera depois do menu e tempo extra/máximo de gravação. Não é necessário configurar coordenadas: o app captura a janela do ChatGPT e identifica automaticamente o campo de texto, o botão **Enviar**, os **3 pontinhos** da resposta e a opção **Ler em voz alta**. Depois de enviar a mensagem, ele aguarda integralmente o tempo configurado (padrão: 8 segundos) e só então compara a captura antes/depois da resposta para escolher os **3 pontinhos novos** da última resposta (horizontal ou vertical), evitando clicar nos menus de respostas anteriores. No Windows, durante a gravação o app não silencia mais sessões pelo mixer, porque o ChatGPT Desktop/WebView pode mudar de processo ou nome de janela; em vez disso ele grava o áudio que sai no dispositivo padrão do sistema por loopback. A gravação é armada antes de clicar em **Ler em voz alta** para não perder o começo da fala, mantém o loopback aberto e drenando durante a geração dos áudios para evitar descontinuidade entre a primeira e as próximas frases, tenta parar automaticamente ao detectar silêncio depois da fala, seleciona o canal de áudio mais forte e normaliza gravações baixas.
9. Na aba **Musica**, selecione uma música do PC e ajuste o volume da trilha; o padrão é **20%**. Use volume **0** para não misturar música e manter somente a narração.
10. Use o botão fixo **Gerar vídeo**, que fica sempre visível na parte inferior do app.

Na aba **Roteiro**, o botão **Gerar roteiro** usa o Groq para criar de 6 a 10 frases curtas em português a partir do título e preencher o campo de roteiro automaticamente. Se uma frase não tiver link manual, o app pesquisa no Pexels pela própria frase e usa o primeiro vídeo/foto encontrado. Ao clicar em **Atualizar videos**, o app usa o modelo `llama-3.3-70b-versatile` da Groq para gerar termos curtos em inglês para cada frase, considerando o título e todas as frases do roteiro, e então salva em cada item o link do resultado encontrado no Pexels. Para cada frase, o app abre o ChatGPT pelo atalho configurado, captura a janela ativa, localiza o campo de mensagem e o botão **Enviar** pela imagem, escreve `Apenas repita isso com aspas: "[frase]"`, espera integralmente o tempo configurado para a resposta (padrão: 8 segundos) e só então procura os **3 pontinhos novos** da última resposta, abre o menu, identifica a área nova do menu para acionar **Ler em voz alta** e grava o áudio do sistema até detectar silêncio. Cada frase também é aplicada como legenda progressiva na cena correspondente, junto do áudio e da mídia selecionada. Quando o vídeo do Pexels for maior que o áudio, a cena fica apenas pelo tempo do áudio mais o extra configurado na aba **Video**; se o vídeo for menor, ele continua repetindo até terminar a narração. Se uma música for selecionada, ela toca durante todo o vídeo no volume configurado.
