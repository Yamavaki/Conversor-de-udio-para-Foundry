# Conversor de Áudio para Foundry

App para Windows que baixa áudio do YouTube (ou converte arquivos do PC) direto para **.ogg leve**, pronto para subir na Forge / Foundry VTT sem gastar espaço à toa.

## Como usar

1. Instale o [Python](https://www.python.org/downloads/) e marque **"Add python.exe to PATH"** na instalação.
2. Baixe `conversor_audio_foundry.py` e `Iniciar.bat` e deixe os dois na mesma pasta.
3. Dê dois cliques no **Iniciar.bat**. Ele instala e atualiza sozinho o que precisa: yt-dlp, ffmpeg e Deno.

Deixe a janela preta aberta enquanto usa o programa. Se der algum erro, ele aparece nela e fica salvo em `erro.log`.

## O que faz

- **Links do YouTube**, um por linha. Link de vídeo com Mix/playlist baixa só aquele vídeo; ligue **"Baixar a playlist inteira"** para pegar todos.
- **Arquivos do PC**: mp3, wav, flac, m4a, vídeos…
- **Para que é o áudio**:

  | Preset | Qualidade | Tamanho aproximado |
  |---|---|---|
  | Música | 64 kbps, estéreo | 0,5 MB por minuto |
  | Ambiente | 48 kbps, estéreo | 0,35 MB por minuto |
  | Efeito | 48 kbps, mono | bem leve |
  | Voz | 32 kbps, mono | 0,25 MB por minuto |
  | Alta qualidade | 96 kbps, estéreo | 0,7 MB por minuto |

- **Formato**:
  - **Opus (.ogg)** é o recomendado: menor arquivo com o melhor som.
  - **Vorbis (.ogg)** serve para aparelhos antigos.
- **Duração**: Inteiro, 15 s, 30 s, 1 min ou 2 min, ou um trecho exato (início e fim). Só o pedaço escolhido é baixado, então mesmo de um vídeo de horas sai em segundos.
- **Ajustes**:
  - igualar o volume entre as faixas;
  - cortar o silêncio das pontas;
  - fade de 2 s no fim;
  - nome de arquivo seguro para a Forge, sem acento, espaço ou maiúscula.

Use músicas royalty-free ou com licença que permita o uso.
