# AtendimentoBot

Bot de atendimento no Telegram com onboarding por usuário, RAG com Gemini e upload de documentos.

## O que faz

- Cada usuário configura o próprio agente com `/start`
- Indexa documentos em `.pdf`, `.docx`, `.pptx`, `.txt`, `.md` e `.csv`
- Permite gerenciar a base com `/documentos`
- Permite trocar a foto do bot com `/imagem`
- Permite testar o agente no próprio chat

Observação: a foto do perfil do bot é global para esse bot do Telegram.

## Requisitos

- Python 3.11 a 3.13
- `TELEGRAM_BOT_TOKEN`
- `GOOGLE_API_KEY`

## Instalação

```bash
python -m venv .venv

# Linux / Mac
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

Crie o `.env` a partir do `.env.example`:

```bash
cp .env.example .env
```

No Windows:

```bat
copy .env.example .env
```

## Configuração

```env
TELEGRAM_BOT_TOKEN=seu_token
GOOGLE_API_KEY=sua_chave
GOOGLE_GENERATION_MODEL=gemini-2.5-flash
GOOGLE_EMBEDDING_MODEL=models/gemini-embedding-001
```

## Executar

```bash
python main.py
```

## Executável

```powershell
.\build_exe.bat
```

O binário final fica em `dist\AtendimentoBot.exe`. Deixe o `.env` na mesma pasta do executável.

## Uso

1. Abra o bot no Telegram e envie `/start`
2. Faça o onboarding
3. Envie documentos
4. Faça perguntas no chat para testar

## Comandos

- `/start` iniciar ou abrir o agente
- `/painel` abrir o painel principal
- `/upload` enviar novos documentos
- `/documentos` gerenciar a base
- `/imagem` trocar a foto do bot
- `/editar` editar configuração
- `/status` ver status atual
- `/reset` reconfigurar do zero
- `/ajuda` ver ajuda rápida
