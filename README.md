# 🤖 Agente de Atendimento ao Cliente — Telegram Bot

Bot de configuração e teste de agentes de atendimento no Telegram, com **onboarding automático**, **RAG (Retrieval Augmented Generation)**, **Google Gemini** e upload contínuo de documentos.

Cada novo `user_id` do Telegram que inicia o bot passa pelo onboarding inicial e ganha uma configuração própria, com base de conhecimento isolada.

## Jornada do Usuário

1. **Início pelo link do bot**
   O usuário acessa o link do bot no Telegram e toca em **Start**.

2. **Configuração inicial**
   O bot coleta:
   - nome da empresa
   - nome do assistente
   - saudação inicial
   - instruções de comportamento

3. **Upload da base de conhecimento**
   O usuário envia documentos para formar a base usada nas respostas.

4. **Teste do agente**
   Após o upload, o próprio usuário pode enviar perguntas no chat para validar o comportamento do agente.

5. **Ajustes contínuos**
   O usuário pode editar a configuração, fazer `/upload`, mandar arquivos diretamente no chat e refinar o agente a qualquer momento.

6. **Imagem do bot**
   O usuário pode usar `/imagem` para trocar a foto do perfil do bot enviando uma foto ou arquivo de imagem.
   Como o projeto usa um único bot do Telegram, essa alteração é global e afeta todos os usuários.

## Arquitetura

```text
┌─────────────────────────────────────────────────────────┐
│  Telegram Bot                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Onboarding  │  │   Upload     │  │   Testes     │  │
│  │  por user_id │  │ de arquivos  │  │   do agente  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                 │           │
│  ┌──────▼─────────────────▼─────────────────▼────────┐  │
│  │              Handlers (handlers.py)               │  │
│  └──────────────────────┬────────────────────────────┘  │
│                         │                               │
│  ┌──────────────┐  ┌────▼─────────┐  ┌──────────────┐  │
│  │  Database    │  │ Doc Process  │  │  RAG Chain   │  │
│  │  (SQLite)    │  │ (PDF/Word/   │  │  (Gemini)    │  │
│  │              │  │ PPTX/Text)   │  │              │  │
│  └──────────────┘  └──────┬───────┘  └──────┬───────┘  │
│                           │                 │           │
│                    ┌──────▼─────────────────▼────────┐  │
│                    │   Vector Store (FAISS)          │  │
│                    │   + Google Embeddings           │  │
│                    └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Funcionalidades

- **Onboarding automático**: qualquer novo usuário que enviar `/start` inicia a configuração do seu agente.
- **Configuração isolada por usuário**: cada `user_id` do Telegram tem sua própria empresa, documentos e histórico.
- **Menu nativo do Telegram**: os principais comandos ficam disponíveis no botão Menu do chat.
- **Painel com ações rápidas**: `/painel` mostra botões inline para upload, imagem, documentos, edição, status, ajuda e reset.
- **Upload contínuo de documentos**: arquivos enviados viram a base de conhecimento do agente.
- **Gestão da base de conhecimento**: `/documentos` permite reprocessar arquivos, excluir documentos e reconstruir todo o índice.
- **Troca da foto do bot via comando**: `/imagem` recebe foto do Telegram ou arquivo de imagem e atualiza o perfil do bot.
- **Teste no próprio chat**: depois da configuração, o usuário pode validar respostas enviando perguntas de texto.
- **Edição de configurações**: nome da empresa, nome do assistente, saudação e instruções podem ser alterados depois.
- **Suporte a múltiplos formatos**: `.pdf`, `.docx`, `.pptx`, `.txt`, `.md` e `.csv`.
- **Suporte a múltiplos formatos de imagem**: `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp` e `.gif`, com conversão para JPG quando necessário.

## Pré-requisitos

- Python 3.11 a 3.13
- Conta no Telegram e um bot criado via [@BotFather](https://t.me/BotFather)
- Chave de API do Google Gemini ([Google AI Studio](https://aistudio.google.com/app/apikey))

## Instalação

### 1. Clone o repositório

```bash
git clone <seu-repositorio>
cd agente-atendimento-ao-cliente
```

### 2. Crie um ambiente virtual

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

No Windows, se você tiver Python 3.14 instalado, crie a `venv` explicitamente com Python 3.13:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure as variáveis de ambiente

```bash
copy .env.example .env
```

Edite o arquivo `.env` com suas credenciais:

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
GOOGLE_API_KEY=AIzaSy...
GOOGLE_GENERATION_MODEL=gemini-2.5-flash
GOOGLE_EMBEDDING_MODEL=models/gemini-embedding-001
```

**Como obter:**
- **TELEGRAM_BOT_TOKEN**: converse com [@BotFather](https://t.me/BotFather) no Telegram e crie um novo bot com `/newbot`
- **GOOGLE_API_KEY**: acesse [Google AI Studio](https://aistudio.google.com/app/apikey) e crie uma chave
- **GOOGLE_GENERATION_MODEL**: opcional; padrão recomendado para as respostas do agente
- **GOOGLE_EMBEDDING_MODEL**: opcional; padrão recomendado para indexação dos documentos

### 5. Execute o bot

```bash
python main.py
```

## Como Usar

### Fluxo inicial

1. Acesse o link do bot no Telegram e toque em **Start**.
2. Informe o **nome da empresa**.
3. Escolha o **nome do assistente**.
4. Defina a **mensagem de saudação**.
5. Adicione **instruções especiais** ou envie `/pular`.
6. Use o botão **Menu** do Telegram ou `/painel` para navegar pelas ações principais.
7. Envie documentos com `/upload` ou mande os arquivos diretamente no chat.
8. Faça novas cargas ao longo da conversa sempre que quiser atualizar a base.
9. Use `/documentos` quando quiser excluir arquivos, reprocessar documentos ou reconstruir toda a base.
10. Faça perguntas no próprio chat para testar o agente.
11. Se quiser trocar a foto do perfil do bot, use `/imagem` e envie a imagem.

Observação: a foto do perfil do bot no Telegram é única para esse bot. Se você usar `/imagem`, todos os usuários verão a nova foto.

### Comandos

| Comando | Descrição |
|---------|-----------|
| `/start` | Iniciar a configuração inicial |
| `/registrar` | Iniciar o cadastro da empresa |
| `/painel` | Visualizar o painel do agente |
| `/upload` | Enviar novos documentos durante a conversa |
| `/imagem` | Trocar a foto do perfil do bot |
| `/documentos` | Gerenciar a base de conhecimento |
| `/editar` | Editar configurações |
| `/reset` | Apagar a configuração atual e refazer o onboarding |
| `/status` | Ver o estado atual do agente |
| `/ajuda` | Listar comandos disponíveis |

## Estrutura do Projeto

```text
agente-atendimento-ao-cliente/
├── main.py
├── config.py
├── database.py
├── handlers.py
├── document_processor.py
├── vector_store.py
├── rag_chain.py
├── requirements.txt
├── .env.example
└── .gitignore
```

## Tecnologias

- **[python-telegram-bot](https://python-telegram-bot.org/)** — integração com a API do Telegram
- **[LangChain](https://langchain.com/)** — orquestração da aplicação com LLM
- **[Google Gemini](https://ai.google.dev/)** — geração de respostas
- **[FAISS](https://github.com/facebookresearch/faiss)** — busca vetorial
- **[PyPDF](https://pypdf.readthedocs.io/)** — extração de texto de PDFs
- **[python-docx](https://python-docx.readthedocs.io/)** — extração de texto de arquivos Word `.docx`
- **[python-pptx](https://python-pptx.readthedocs.io/)** — extração de texto de arquivos PowerPoint `.pptx`
- **[Pillow](https://python-pillow.org/)** — conversão de imagens para JPG antes do envio à Bot API
- **SQLite** — persistência local de configurações e histórico

## Licença

MIT
