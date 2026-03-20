# AtendimentoBot

Bot de atendimento no Telegram com onboarding por usuário, RAG com Gemini e upload de documentos.

## O que faz

- Cada usuário configura o próprio agente com `/start`
- Indexa documentos em `.pdf`, `.docx`, `.pptx`, `.txt`, `.md` e `.csv`
- Permite gerenciar a base com `/documentos`
- Permite definir a imagem do próprio agente com `/imagem`
- Permite pausar/ativar o agente por usuário
- Permite configurar horário, fallback humano e FAQs próprias
- Permite testar o agente no próprio chat

## Requisitos

- Python 3.11 a 3.13
- `TELEGRAM_BOT_TOKEN`
- `GOOGLE_API_KEY`

## Instalação

```bash
python3 -m venv .venv

# Ubuntu 24.04 / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
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

## VS Code

No Ubuntu 24.04, o projeto já vem pronto para abrir no VS Code:

- selecione a pasta do projeto no VS Code
- use a interpreter `.venv/bin/python`
- rode `F5` com a configuração `AtendimentoBot`
- ou execute as tasks `Instalar dependências`, `Executar bot` e `Gerar binário Linux`

## Executável

```powershell
.\build_exe.bat
```

O binário final fica em `dist\AtendimentoBot.exe`.

Se existir um `.env` na raiz do projeto durante o build, ele será embutido no `.exe`. Nesse caso, basta dar dois cliques em `AtendimentoBot.exe` para subir o bot.

No Ubuntu 24.04, para gerar o binário Linux:

```bash
bash build_bin.sh
```

O binário final fica em `dist/AtendimentoBot`.

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
- `/imagem` atualizar a imagem do agente
- `/pausar` pausar o agente
- `/ativar` ativar o agente
- `/horario` definir horário de atendimento
- `/fallback` definir contato humano
- `/faq` gerenciar perguntas frequentes
- `/editar` editar configuração
- `/status` ver status atual
- `/reset` reconfigurar do zero
- `/ajuda` ver ajuda rápida
