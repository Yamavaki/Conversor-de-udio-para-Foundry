@echo off
chcp 65001 >nul
title Conversor de Audio para Foundry
cd /d "%~dp0"

set PY=
where py >nul 2>nul && set PY=py
if not defined PY (where python >nul 2>nul && set PY=python)
if not defined PY (
  echo Python nao encontrado. Instale em https://www.python.org/downloads/
  echo Marque "Add python.exe to PATH" na instalacao.
  pause
  exit /b
)

echo Python encontrado:
%PY% --version
echo.
echo Atualizando componentes (o YouTube muda sempre, isso mantem o download funcionando)...
%PY% -m pip install --upgrade --disable-pip-version-check "yt-dlp[default]" imageio-ffmpeg
if errorlevel 1 (
  echo.
  echo [AVISO] Falha ao instalar yt-dlp / imageio-ffmpeg. Veja a mensagem acima.
)
%PY% -m pip install --upgrade --disable-pip-version-check deno >nul 2>nul
if errorlevel 1 echo [AVISO] Nao consegui instalar o Deno. Alguns videos podem falhar.

echo.
echo Abrindo o programa... (pode deixar esta janela aberta enquanto usa)
%PY% "conversor_audio_foundry.py"
if errorlevel 1 (
  echo.
  echo ============================================================
  echo  O programa fechou com erro. Tire um print desta janela
  echo  ou mande o arquivo erro.log que esta nesta mesma pasta.
  echo ============================================================
  pause
)
