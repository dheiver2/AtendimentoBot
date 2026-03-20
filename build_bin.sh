#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "Ambiente virtual .venv nao encontrado em $(pwd)/.venv"
  echo "Crie-o com: python3 -m venv .venv"
  exit 1
fi

if ! command -v objdump >/dev/null 2>&1; then
  echo "objdump nao encontrado."
  echo "No Ubuntu 24.04 instale com: sudo apt update && sudo apt install -y binutils"
  exit 1
fi

if [ -f ".env" ]; then
  echo ".env encontrado. As credenciais atuais serao embutidas no binario."
else
  echo ".env nao encontrado. O binario exigira um .env externo ao lado do arquivo."
fi

echo "Instalando PyInstaller..."
.venv/bin/python -m pip install pyinstaller

echo "Gerando binario Linux..."
.venv/bin/python -m PyInstaller --noconfirm --clean AtendimentoBot.spec

echo "Build concluido em dist/AtendimentoBot"
