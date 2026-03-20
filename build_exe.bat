@echo off
setlocal

if not exist ".venv\Scripts\python.exe" (
    echo Ambiente virtual .venv nao encontrado.
    exit /b 1
)

echo Instalando PyInstaller...
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 exit /b 1

echo Gerando executavel unico...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean AtendimentoBot.spec
if errorlevel 1 exit /b 1

echo Build concluido em dist\AtendimentoBot.exe
