# AtendimentoBot

Bot de atendimento ao cliente no Telegram com RAG (Retrieval-Augmented Generation) e dois perfis de acesso:

- **admin**: configura a empresa, o agente, os documentos e gera o link de atendimento
- **cliente**: entra pelo link enviado pelo admin e usa o bot apenas para conversar

## Documentação para usuários

- Guia do usuário: [docs/guia-do-usuario.md](docs/guia-do-usuario.md)

## Funcionalidades

- Onboarding guiado para configuração da empresa e agente
- RAG com Google Gemini que ajusta o tamanho da resposta conforme a complexidade da pergunta
- Indexação de documentos em `.pdf`, `.docx`, `.pptx`, `.txt`, `.md` e `.csv`
- FAQ com correspondência inteligente (matching por similaridade)
- Gestão de documentos via painel inline (`/documentos`)
- Imagem personalizada do agente (`/imagem`)
- Horário de atendimento e fallback para atendimento humano
- Pausar/ativar agente por usuário
- Deep links para vincular clientes ao atendimento
- Menu de comandos dinâmico por perfil (admin vs cliente)
- Histórico de conversas registrado em banco de dados
- Validação e sanitização de entradas do usuário
- Rate limiting por usuário para proteção contra abuso
- Limites de tamanho para uploads de documentos e imagens

## Arquitetura

```
main.py                  → Ponto de entrada, configura polling
config.py                → Caminhos, diretórios, versão
database.py              → CRUD assíncrono com aiosqlite
rag_chain.py             → Pipeline RAG com LangChain + Gemini
vector_store.py          → Indexação e busca FAISS
document_processor.py    → Extração de texto multi-formato
bot_profile_photo.py     → Gestão de imagens do agente
telegram_commands.py     → Menu nativo do Telegram por perfil
validators.py            → Validação e sanitização de entradas
rate_limiter.py          → Rate limiting em memória por usuário
handlers/                → Pacote de handlers do bot
├── __init__.py          → Montagem dos handlers e get_handlers()
├── common.py            → Estados, utilitários, teclados compartilhados
├── onboarding.py        → Registro de empresa e onboarding
├── documents.py         → Upload e gestão de documentos
├── images.py            → Gestão de imagem do agente
├── faq.py               → Gestão de FAQs
├── settings.py          → Horário, fallback, edição, pausar/ativar
├── panel.py             → Painel, status, ajuda, link e callbacks
└── agent.py             → Interação com o agente via RAG
tests/                   → Suite de testes automatizados
```

## Requisitos

- Python 3.11 a 3.13
- `TELEGRAM_BOT_TOKEN` (obtido com [@BotFather](https://t.me/BotFather))
- `GOOGLE_API_KEY` (obtida em [Google AI Studio](https://aistudio.google.com/app/apikey))

## Instalação

```bash
python3 -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Para desenvolvimento (testes, linting):

```bash
python -m pip install -r requirements-dev.txt
```

## Configuração

Crie o `.env` a partir do `.env.example`:

```bash
cp .env.example .env   # Linux/macOS
copy .env.example .env  # Windows
```

Edite o `.env`:

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

## Testes

```bash
# Rodar todos os testes
python -m pytest tests/ -v

# Com cobertura
python -m pytest tests/ -v --cov=. --cov-report=term-missing

# Testes específicos
python -m pytest tests/test_validators.py -v
python -m pytest tests/test_rate_limiter.py -v
python -m pytest tests/test_database.py -v
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

1. O admin abre o bot no Telegram e envia `/start`
2. O admin faz o onboarding da empresa (nome, assistente, saudação, instruções)
3. O admin envia documentos, configura FAQ, horário, fallback e imagem
4. O admin usa `/link` para gerar o link dos clientes
5. O admin envia esse link aos clientes
6. O cliente abre o link e usa o bot somente para conversar

## Comandos

| Comando | Descrição |
|---------|-----------|
| `/start` | Iniciar configuração (admin) ou abrir atendimento (cliente) |
| `/meuid` | Mostrar o ID do Telegram do usuário atual |
| `/painel` | Painel de gerenciamento com todas as opções |
| `/link` | Gerar o link de atendimento para clientes |
| `/upload` | Enviar novos documentos |
| `/documentos` | Gerenciar a base de conhecimento |
| `/imagem` | Atualizar a imagem do agente |
| `/pausar` | Pausar o agente |
| `/ativar` | Ativar o agente |
| `/horario` | Definir horário de atendimento |
| `/fallback` | Definir contato humano de fallback |
| `/faq` | Gerenciar perguntas frequentes |
| `/editar` | Editar configuração do agente |
| `/status` | Ver status atual |
| `/reset` | Reconfigurar do zero |
| `/ajuda` | Ver ajuda rápida |

Clientes não usam comandos de gestão. Depois de entrarem pelo link, o menu `/` mostra apenas as opções básicas do cliente, incluindo `/meuid` para informar o próprio ID quando necessário.

## Segurança

- Tokens de deep link gerados com `secrets.token_urlsafe(16)`
- Queries SQL parametrizadas (sem SQL injection)
- Validação e sanitização de todas as entradas do usuário
- Rate limiting por usuário em mensagens, uploads e FAQs
- Limites de tamanho para documentos (20 MB) e imagens (10 MB)
- Sanitização de nomes de arquivo contra path traversal
- Isolamento de dados por empresa (cada admin vê apenas seus dados)
- Variáveis sensíveis em `.env` (nunca commitadas)
- Limites máximos de documentos (50) e FAQs (100) por empresa

## Troubleshooting

| Problema | Solução |
|----------|---------|
| `TELEGRAM_BOT_TOKEN não configurado` | Verifique se o `.env` existe e contém o token |
| `GOOGLE_API_KEY não configurado` | Adicione a chave no `.env` |
| Bot não responde | Verifique se o token é válido com `@BotFather` |
| Documento não processado | Verifique se o formato é suportado e o arquivo tem texto selecionável |
| Erro ao gerar resposta | Verifique a `GOOGLE_API_KEY` e o modelo configurado |
| Rate limit atingido | Aguarde alguns segundos e tente novamente |
| Menu do Telegram desatualizado | Use `/start` para sincronizar os comandos |

## Limites

| Recurso | Limite |
|---------|--------|
| Tamanho máximo de documento | 20 MB |
| Tamanho máximo de imagem | 10 MB |
| Documentos por empresa | 50 |
| FAQs por empresa | 100 |
| Nome da empresa | 100 caracteres |
| Nome do assistente | 60 caracteres |
| Saudação | 500 caracteres |
| Instruções | 2.000 caracteres |
| Mensagem do usuário | 4.000 caracteres |
| Mensagens por minuto (por usuário) | 20 |
| Uploads por minuto (por usuário) | 10 |

## Licença

Projeto privado. Todos os direitos reservados.
