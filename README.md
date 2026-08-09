# VideoGenerator

Aplicativo desktop para Windows que transforma um roteiro em vídeo vertical automaticamente.

## Funcionalidades

- Geração de roteiro com IA (Groq)
- Busca automática de vídeos e imagens (Pexels API)
- Narração em português com gravação de áudio do sistema
- Legendas personalizáveis com destaque de palavras
- Adição de logo e música de fundo
- Exportação em formato vertical (1080x1920)

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

No Linux/macOS, use `source .venv/bin/activate`.

## Como usar

1. **APIs**: Informe suas chaves do Pexels e Groq
2. **Roteiro**: Digite o título e gere o roteiro automaticamente ou escreva manualmente (uma frase por linha)
3. **Vídeo**: Atualize os vídeos para cada frase ou cole links do Pexels manualmente
4. **Legendas**: Configure posição, cores, tamanho e fonte das legendas
5. **Logo**: Adicione uma imagem PNG como marca d'água
6. **Áudio**: Configure a automação do Qwen para narração
7. **Música**: Selecione uma trilha sonora e ajuste o volume
8. Clique em **Gerar vídeo** para criar o arquivo final

## Gerar executável (.exe)

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name VideoGenerator app.py
```

O arquivo será criado em `dist/VideoGenerator.exe`.
