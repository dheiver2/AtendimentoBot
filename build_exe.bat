@echo off
setlocal

if not exist ".venv\Scripts\python.exe" (
    echo Ambiente virtual .venv nao encontrado.
    exit /b 1
)

echo Instalando PyInstaller...
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 exit /b 1

if exist ".env" (
    echo .env encontrado. As credenciais atuais serao embutidas no executavel.
) else (
    echo .env nao encontrado. O executavel exigira um .env externo ao lado do arquivo.
)

echo Gerando executavel unico...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean AtendimentoBot.spec
if errorlevel 1 exit /b 1

echo Build concluido em dist\AtendimentoBot.exe
