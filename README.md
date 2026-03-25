# AtendimentoBot

Bot de atendimento ao cliente com RAG (Retrieval-Augmented Generation), onboarding e atendimento via Telegram e suporte opcional ao WhatsApp Web por QR code.

Perfis atuais:

- **admin**: configura a empresa, o agente, os documentos e gera o link de atendimento
- **cliente**: entra pelo link enviado pelo admin e usa o bot apenas para conversar

## Documentação para usuários

- Guia do usuário: [docs/guia-do-usuario.md](docs/guia-do-usuario.md)

## Funcionalidades

- Onboarding guiado para configuração da empresa e agente
- RAG com OpenRouter e fallback entre modelos configurados no `.env`
- Indexação de documentos em `.pdf`, `.docx`, `.pptx`, `.txt`, `.md` e `.csv`
- FAQ com correspondência inteligente (matching por similaridade)
- Gestão de documentos via painel inline (`/documentos`)
- Imagem personalizada do agente (`/imagem`)
- Identidade visual por empresa na conversa do cliente
- Atendimento simultâneo via Telegram e WhatsApp Web
- Capa automática com imagem, nome e saudação da empresa
- Reenvio da identidade visual na primeira interação do cliente
- Horário de atendimento e fallback para atendimento humano
- Pausar/ativar agente por usuário
- Tokens e links para vincular clientes ao atendimento
- Menu de comandos dinâmico por perfil (admin vs cliente)
- Histórico de conversas registrado em banco de dados
- Validação e sanitização de entradas do usuário
- Rate limiting por usuário para proteção contra abuso
- Limites de tamanho para uploads de documentos e imagens

## Arquitetura

```
main.py                  → Ponto de entrada, configura polling
config.py                → Caminhos, diretórios, versão
agent_service.py         → Núcleo reutilizável do atendimento para Telegram/WhatsApp
database.py              → CRUD assíncrono com aiosqlite
rag_chain.py             → Pipeline RAG com LangChain + OpenRouter
vector_store.py          → Indexação e busca FAISS com embeddings locais
document_processor.py    → Extração de texto multi-formato
bot_profile_photo.py     → Gestão de imagens do agente
telegram_commands.py     → Menu nativo do Telegram por perfil
whatsapp_web_bridge.py   → Bridge HTTP local entre Python e WhatsApp Web
whatsapp_flow.py         → Fluxo conversacional e comandos do WhatsApp
scripts/whatsapp_bridge.js → Cliente do WhatsApp Web com QR code em terminal separado
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
- Node.js 18 ou superior
- `TELEGRAM_BOT_TOKEN` (obtido com [@BotFather](https://t.me/BotFather))
- `OPENROUTER_API_KEY` (obtida em [OpenRouter](https://openrouter.ai/keys))

## Instalação

```bash
python3 -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
npm install
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
OPENROUTER_API_KEY=sua_chave
OPENROUTER_MODELS=qwen/qwen3.5-plus-02-15,deepseek/deepseek-v3.2
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Opcional: WhatsApp Web via QR code
WHATSAPP_WEB_ENABLED=1
# Em Linux headless/servidor sem DISPLAY, use 0 e rode o bridge manualmente.
WHATSAPP_WEB_AUTO_LAUNCH=1
WHATSAPP_WEB_BRIDGE_HOST=127.0.0.1
WHATSAPP_WEB_BRIDGE_PORT=8010
WHATSAPP_WEB_BRIDGE_PATH=/bridge/whatsapp/message
WHATSAPP_WEB_BRIDGE_TOKEN=troque-por-um-token-local
WHATSAPP_WEB_CLIENT_HOST=127.0.0.1
WHATSAPP_WEB_CLIENT_PORT=8011
WHATSAPP_WEB_CLIENT_ID=atendimento-bot
WHATSAPP_WEB_SESSION_DIR=data/whatsapp-web-session
```

### WhatsApp Web

O projeto consegue operar no WhatsApp Web com paridade funcional ao fluxo principal: onboarding, configuração, FAQ, upload de documentos, imagem do agente, horário, fallback, status, reset e atendimento RAG.

Como funciona hoje:

- O Telegram continua funcionando normalmente com painel, callbacks e menu nativo.
- O WhatsApp expõe os mesmos fluxos por comandos de texto e mensagens de mídia.
- Admins podem configurar empresa, documentos, FAQ, imagem, horário, fallback e edições diretamente pelo WhatsApp.
- Clientes entram no atendimento enviando `/start TOKEN` para o mesmo número conectado no WhatsApp Web.
- Se existir apenas uma empresa cadastrada, o bridge ainda pode responder clientes sem vínculo explícito.
- Se existir mais de uma empresa, defina `WHATSAPP_DEFAULT_COMPANY_ID` ou `WHATSAPP_DEFAULT_COMPANY_LINK_TOKEN` no `.env` para o fallback automático.

Passo a passo:

1. Rode `npm install` uma vez na raiz do projeto.
2. Ative `WHATSAPP_WEB_ENABLED=1` no `.env`.
3. Suba o projeto com `python main.py`.
4. O app inicia o bridge Python e tenta abrir `npm run whatsapp:bridge` em um novo terminal.
   Em Linux sem sessao grafica, deixe `WHATSAPP_WEB_AUTO_LAUNCH=0` e rode o comando manualmente.
5. Escaneie o QR code exibido nesse novo terminal.
6. Depois da primeira autenticacao, a sessao fica salva em `data/whatsapp-web-session`.
7. Para administrar pelo WhatsApp, use comandos como `/start`, `/painel`, `/upload`, `/faq`, `/imagem`, `/status` e `/link`.
8. Para clientes, gere o token com `/link` e oriente o envio de `/start TOKEN`.

Observacoes:

- O terminal do WhatsApp precisa continuar aberto enquanto o atendimento estiver ativo.
- Se o novo terminal nao abrir automaticamente, execute `npm run whatsapp:bridge` manualmente em outro terminal.
- Em Linux headless, configure `WHATSAPP_WEB_AUTO_LAUNCH=0` para evitar a tentativa de abrir terminal grafico.
- O bridge atual trata texto, imagens do fluxo `/imagem` e documentos do fluxo `/upload` ou envio direto do admin.
- Conversas em grupo, newsletters e tipos de mídia nao tratados continuam fora do escopo.
- Se voce ativar apenas o WhatsApp e nao usar Telegram, o app continua permitindo onboarding e gerenciamento pelo proprio WhatsApp.

## Personalização Por Empresa

Antes de gerar o link e convidar clientes, cada empresa pode preparar um atendimento com identidade própria dentro do bot:

- Nome da empresa exibido nas boas-vindas e no vínculo do cliente
- Nome do assistente usado na apresentação e nas respostas
- Saudação personalizada para a entrada do cliente
- Imagem própria da empresa/agente
- Capa visual automática com imagem, nome da empresa e saudação
- Reenvio da identidade visual na primeira interação do cliente
- Documentos exclusivos da empresa para a base RAG
- FAQs exclusivas por empresa
- Instruções específicas de comportamento do agente
- Horário de atendimento próprio
- Contato humano de fallback próprio
- Link exclusivo para vincular clientes à empresa correta

Com isso, mesmo usando um único bot compartilhado, cada cliente entra em um atendimento com contexto, conteúdo e apresentação visual da empresa certa.

### Limites da personalização em um único bot

O sistema separa conteúdo, saudação, imagem, FAQs, documentos e identidade visual dentro da conversa, mas alguns elementos continuam globais no Telegram:

- Foto de perfil global do bot
- Username do bot
- Nome global do bot
- Fundo real do chat do Telegram

## Executar

```bash
python main.py
```

Se `WHATSAPP_WEB_ENABLED=1`, o mesmo comando sobe o polling do Telegram, ativa o bridge local do WhatsApp e tenta abrir outro terminal para o QR code.

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

1. O admin pode iniciar pelo Telegram ou pelo WhatsApp com `/start`
2. O admin faz o onboarding da empresa, envia documentos e ajusta FAQ, imagem, horário e fallback
3. O admin usa `/link` para gerar o acesso dos clientes
4. No Telegram, o cliente entra pelo deep link
5. No WhatsApp, o cliente envia `/start TOKEN`
6. Depois do vínculo, o cliente usa o chat apenas para conversar com o agente

## Comandos

| Comando | Descrição |
|---------|-----------|
| `/start` | Iniciar configuração (admin) ou abrir atendimento (cliente com token) |
| `/meuid` | Mostrar o identificador do usuário atual |
| `/painel` | Painel de gerenciamento com todas as opções |
| `/link` | Gerar o acesso de atendimento para clientes |
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

No WhatsApp, os fluxos administrativos usam comandos de texto em vez de botões inline. Clientes não usam comandos de gestão; depois do vínculo, basta conversar normalmente. `/meuid` continua disponível para suporte.

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
| `OPENROUTER_API_KEY não configurado` | Adicione a chave no `.env` |
| Bot não responde | Verifique se o token é válido com `@BotFather` |
| Documento não processado | Verifique se o formato é suportado e o arquivo tem texto selecionável |
| Erro ao gerar resposta | Verifique a `OPENROUTER_API_KEY`, os modelos configurados e se a base vetorial está indexada |
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
