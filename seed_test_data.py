"""
Script de seed para popular o banco de dados com dados de demonstração.

Os nomes das empresas cadastradas são reais e conhecidas. FAQs, conversas,
documentos e parte dos horários são ilustrativos para testes locais do projeto.
Quando informado explicitamente, o fallback de contato pode refletir canais
oficiais públicos do site da empresa.
"""

from __future__ import annotations

import secrets
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from config import DB_PATH as PROJECT_DB_PATH

DB_PATH_ORIGINAL = Path(PROJECT_DB_PATH)
DB_PATH = Path(tempfile.gettempdir()) / "atendimento_bot_seed.db"

# ─────────────────────────────────────────────
# DADOS DE TESTE
# ─────────────────────────────────────────────

EMPRESAS: list[dict[str, Any]] = [
    {
        "nome": "Apple",
        "telegram_user_id": 100000001,
        "nome_bot": "AppleCare Bot",
        "saudacao": (
            "Olá! Bem-vindo ao atendimento de demonstração da Apple. "
            "Sou o AppleCare Bot. Como posso ajudar?"
        ),
        "instrucoes": (
            "Você é o AppleCare Bot, assistente de demonstração inspirado no "
            "atendimento ao cliente da Apple. Ajude com dúvidas sobre pedidos, "
            "garantia, acessórios, configurações básicas e suporte inicial para "
            "iPhone, Mac, iPad e Apple Watch. Deixe claro quando um caso precisar "
            "de análise humana."
        ),
        "horario_atendimento": "Atendimento ilustrativo: todos os dias, 09h-18h",
        "fallback_contato": "Encaminhamento humano pelos canais oficiais da Apple (seed ilustrativa).",
        "clientes": [
            {"telegram_user_id": 200000001, "nome": "Carlos Mendes"},
            {"telegram_user_id": 200000002, "nome": "Fernanda Lima"},
            {"telegram_user_id": 200000003, "nome": "Rafael Oliveira"},
            {"telegram_user_id": 200000004, "nome": "Juliana Costa"},
        ],
        "faqs": [
            (
                "Como acompanho meu pedido?",
                "Na seed de demonstração, oriente o cliente a consultar o status no app, site ou e-mail de confirmação do pedido.",
            ),
            (
                "Como funciona troca ou devolução?",
                "O fluxo ilustrativo considera solicitação dentro do prazo informado no pedido, com análise e instruções de coleta ou postagem.",
            ),
            (
                "Meu iPhone está descarregando rápido. O que posso fazer?",
                "Sugira verificar saúde da bateria, atualizar o iOS, revisar apps em segundo plano e, se necessário, encaminhar para suporte especializado.",
            ),
            (
                "Vocês vendem acessórios originais?",
                "Sim. Neste cenário de teste, o atendimento considera acessórios originais e orienta a compatibilidade por modelo.",
            ),
            (
                "Posso retirar uma compra em loja?",
                "Quando a modalidade estiver disponível no pedido de demonstração, a retirada é liberada após aprovação do pagamento e aviso ao cliente.",
            ),
        ],
        "conversas": [
            (
                200000001,
                "Meu iPhone esquenta durante carga rápida, isso é normal?",
                "No fluxo de demonstração, informamos que algum aquecimento pode ocorrer. Oriente a usar carregador compatível, retirar capas muito espessas e observar se o comportamento persiste.",
            ),
            (
                200000002,
                "Quero trocar uma capa que comprei para o iPhone errado",
                "Sem problema. Posso registrar uma solicitação de troca ilustrativa e orientar o envio do item conforme o pedido.",
            ),
            (
                200000003,
                "Meu MacBook não está reconhecendo o carregador",
                "Vamos começar com um diagnóstico inicial: revisar tomada, cabo, adaptador e tentar outra porta compatível antes de encaminhar para avaliação humana.",
            ),
            (
                200000004,
                "Tem pulseira para Apple Watch de 41 mm?",
                "Neste ambiente de demonstração, sim. Posso indicar modelos compatíveis e orientar a conferir cor, material e prazo de entrega no catálogo.",
            ),
        ],
        "documentos": [
            "guia_applecare_seed.pdf",
            "politica_troca_apple_seed.pdf",
            "catalogo_acessorios_apple_seed.pdf",
        ],
    },
    {
        "nome": "Samsung",
        "telegram_user_id": 100000002,
        "nome_bot": "Samsung Care Demo",
        "saudacao": (
            "Olá! Você está no atendimento de demonstração da Samsung. "
            "Sou o Samsung Care Demo. Em que posso ajudar?"
        ),
        "instrucoes": (
            "Você é um assistente de demonstração inspirado no suporte da Samsung. "
            "Ajude com dúvidas sobre smartphones, TVs, eletrodomésticos, garantia, "
            "entrega e configuração inicial de produtos. Priorize orientações objetivas "
            "e encaminhe casos técnicos complexos para o suporte humano."
        ),
        "horario_atendimento": "Atendimento ilustrativo: seg-sáb, 08h-20h",
        "fallback_contato": "Encaminhamento humano pelos canais oficiais da Samsung (seed ilustrativa).",
        "clientes": [
            {"telegram_user_id": 200000005, "nome": "Bruno Alves"},
            {"telegram_user_id": 200000006, "nome": "Marina Souza"},
            {"telegram_user_id": 200000007, "nome": "João Pedro Santos"},
            {"telegram_user_id": 200000008, "nome": "Ana Paula Ferreira"},
        ],
        "faqs": [
            (
                "Como acompanho a entrega do meu pedido?",
                "Na seed, o cliente recebe orientação para consultar o código de rastreio e o painel do pedido nos canais digitais da marca.",
            ),
            (
                "Minha TV chegou sem configuração inicial. O que faço?",
                "Explique o passo a passo básico de instalação e, se necessário, encaminhe para suporte técnico humano.",
            ),
            (
                "Como funciona a garantia?",
                "O atendimento de demonstração informa cobertura conforme categoria do produto e necessidade de comprovante de compra para análise.",
            ),
            (
                "Vocês fazem instalação de ar-condicionado?",
                "Neste cenário de teste, o assistente orienta contratação ou agendamento conforme disponibilidade informada no pedido.",
            ),
            (
                "Posso cancelar uma compra após o pagamento?",
                "Sim, o fluxo ilustrativo prevê solicitação de cancelamento e confirmação conforme o status logístico do pedido.",
            ),
        ],
        "conversas": [
            (
                200000005,
                "Meu Galaxy não está carregando rápido",
                "Vamos validar cabo, carregador, porta USB e a opção de carga rápida nas configurações antes de acionar o suporte humano.",
            ),
            (
                200000006,
                "Comprei uma lava e seca e quero saber se já saiu para entrega",
                "Posso consultar o status ilustrativo do pedido e informar a última atualização logística disponível na seed.",
            ),
            (
                200000007,
                "A TV chegou mas não conectou no Wi-Fi",
                "Posso orientar o reinício da rede, a verificação de senha e uma nova tentativa de pareamento antes do encaminhamento técnico.",
            ),
            (
                200000008,
                "Quero trocar a cor do meu celular comprado ontem",
                "Se o pedido ainda estiver elegível no fluxo de demonstração, posso abrir uma solicitação de troca e orientar os próximos passos.",
            ),
        ],
        "documentos": [
            "guia_primeiros_passos_samsung_seed.pdf",
            "politica_garantia_samsung_seed.pdf",
            "catalogo_linha_galaxy_seed.pdf",
        ],
    },
    {
        "nome": "Magazine Luiza",
        "telegram_user_id": 100000003,
        "nome_bot": "Assistente Magalu Demo",
        "saudacao": (
            "Olá! Bem-vindo ao atendimento de demonstração da Magazine Luiza. "
            "Sou a Assistente Magalu Demo. Como posso ajudar?"
        ),
        "instrucoes": (
            "Você é uma assistente de demonstração inspirada no atendimento da "
            "Magazine Luiza. Ajude com dúvidas sobre compras online, retirada em "
            "loja, entrega, trocas, pagamentos e ofertas. Mantenha um tom cordial "
            "e direto."
        ),
        "horario_atendimento": "Atendimento ilustrativo: seg-dom, 08h-22h",
        "fallback_contato": "Encaminhamento humano pelos canais oficiais da Magazine Luiza (seed ilustrativa).",
        "clientes": [
            {"telegram_user_id": 200000009, "nome": "Roberto Nascimento"},
            {"telegram_user_id": 200000010, "nome": "Lucas Pereira"},
            {"telegram_user_id": 200000011, "nome": "Camila Rodrigues"},
            {"telegram_user_id": 200000012, "nome": "Diego Martins"},
            {"telegram_user_id": 200000013, "nome": "Isabela Torres"},
        ],
        "faqs": [
            (
                "Como acompanho meu pedido?",
                "No cenário da seed, o cliente acompanha pelo número do pedido e recebe atualizações de separação, transporte e entrega.",
            ),
            (
                "Posso retirar em loja?",
                "Quando a compra foi marcada para retirada, o atendimento orienta a aguardar a confirmação de disponibilidade antes de ir à loja.",
            ),
            (
                "Como solicito troca ou devolução?",
                "A demonstração prevê abertura pelo pedido, análise do motivo e geração das instruções logísticas correspondentes.",
            ),
            (
                "Vocês aceitam PIX e cartão?",
                "Sim. O atendimento de teste informa meios de pagamento digitais usuais e prazos de aprovação ilustrativos.",
            ),
            (
                "A nota fiscal fica disponível onde?",
                "Na seed, a nota pode ser acessada no painel do pedido ou enviada novamente ao e-mail cadastrado.",
            ),
        ],
        "conversas": [
            (
                200000009,
                "Meu pedido de geladeira está parado há dois dias",
                "Vou consultar o andamento ilustrativo do transporte e confirmar a próxima atualização prevista para a entrega.",
            ),
            (
                200000010,
                "Quero saber se esse notebook tem retirada em loja",
                "Posso verificar a modalidade disponível no pedido de demonstração e orientar sobre prazo para retirada.",
            ),
            (
                200000011,
                "Paguei por PIX mas ainda não apareceu confirmação",
                "No ambiente de seed, a orientação é aguardar a compensação do pagamento e validar os dados do comprovante caso o status não mude.",
            ),
            (
                200000012,
                "Recebi um produto diferente do que comprei",
                "Posso registrar uma ocorrência ilustrativa e seguir com as etapas de troca ou devolução do pedido.",
            ),
            (
                200000013,
                "Tem oferta para montar cozinha completa?",
                "Neste atendimento de demonstração, posso sugerir kits, categorias relacionadas e encaminhar para o time comercial quando necessário.",
            ),
        ],
        "documentos": [
            "politica_entrega_magalu_seed.pdf",
            "guia_retirada_loja_magalu_seed.pdf",
            "faq_pagamentos_magalu_seed.pdf",
        ],
    },
    {
        "nome": "Natura",
        "telegram_user_id": 100000004,
        "nome_bot": "Natura Atendimento Demo",
        "saudacao": (
            "Olá! Você está no atendimento de demonstração da Natura. "
            "Sou o Natura Atendimento Demo. Em que posso ajudar?"
        ),
        "instrucoes": (
            "Você é um assistente de demonstração inspirado na Natura. Ajude com "
            "dúvidas sobre perfumes, refis, kits, pedidos, presentes e cuidados "
            "com produtos. Mantenha um tom acolhedor e consultivo."
        ),
        "horario_atendimento": "Atendimento ilustrativo: seg-sáb, 09h-19h",
        "fallback_contato": "Encaminhamento humano pelos canais oficiais da Natura (seed ilustrativa).",
        "clientes": [
            {"telegram_user_id": 200000014, "nome": "Thiago Barbosa"},
            {"telegram_user_id": 200000015, "nome": "Patricia Gomes"},
            {"telegram_user_id": 200000016, "nome": "Beatriz Ramos"},
            {"telegram_user_id": 200000017, "nome": "Gustavo Farias"},
        ],
        "faqs": [
            (
                "Como acompanho um pedido?",
                "O atendimento ilustrativo orienta o cliente a usar o número do pedido para consultar separação, envio e entrega.",
            ),
            (
                "Vocês têm refil para essa linha?",
                "Neste cenário de demonstração, o assistente verifica se a linha possui refil e sugere a opção correspondente.",
            ),
            (
                "Posso trocar um presente?",
                "Sim. A seed considera análise do item, estado do produto e prazo para orientar a troca.",
            ),
            (
                "Como montar um kit para presente?",
                "O bot pode sugerir combinações de fragrância, corpo e banho conforme perfil da pessoa presenteada.",
            ),
            (
                "Como saber se um produto é indicado para pele sensível?",
                "O atendimento de teste orienta a leitura da descrição do item e recomenda validar composição e modo de uso antes da compra.",
            ),
        ],
        "conversas": [
            (
                200000014,
                "Quero montar um presente para aniversario",
                "Posso sugerir um kit ilustrativo com fragrância, hidratante e sabonetes, ajustando a faixa de preço desejada.",
            ),
            (
                200000015,
                "Meu pedido chegou com a caixa amassada",
                "Posso registrar a ocorrência na seed e orientar a análise do conteúdo para eventual troca.",
            ),
            (
                200000016,
                "Tem refil do meu perfume favorito?",
                "Vou verificar a linha na base de demonstração e indicar as opções de compra disponíveis.",
            ),
            (
                200000017,
                "Preciso de uma sugestao de presente mais neutro",
                "Posso recomendar combinações ilustrativas com itens de banho, cuidados pessoais e fragrâncias leves.",
            ),
        ],
        "documentos": [
            "catalogo_presentes_natura_seed.pdf",
            "guia_refis_natura_seed.pdf",
            "politica_trocas_natura_seed.pdf",
        ],
    },
    {
        "nome": "iFood",
        "telegram_user_id": 100000005,
        "nome_bot": "iFood Suporte Demo",
        "saudacao": (
            "Olá! Bem-vindo ao atendimento de demonstração do iFood. "
            "Sou o iFood Suporte Demo. Como posso ajudar?"
        ),
        "instrucoes": (
            "Você é um assistente de demonstração inspirado no iFood. Ajude com "
            "pedidos em andamento, cupons, atrasos, entregas, itens faltantes, "
            "cancelamentos e reembolsos. Seja objetivo e orientado à resolução."
        ),
        "horario_atendimento": "Atendimento ilustrativo: todos os dias, 07h-23h",
        "fallback_contato": "Encaminhamento humano pelos canais oficiais do iFood (seed ilustrativa).",
        "clientes": [
            {"telegram_user_id": 200000018, "nome": "Larissa Monteiro"},
            {"telegram_user_id": 200000019, "nome": "Pedro Henrique"},
            {"telegram_user_id": 200000020, "nome": "Amanda Duarte"},
            {"telegram_user_id": 200000021, "nome": "Felipe Nogueira"},
        ],
        "faqs": [
            (
                "Meu pedido está atrasado. O que fazer?",
                "No fluxo de demonstração, o cliente pode acompanhar a rota, conferir o tempo estimado e solicitar ajuda se o prazo extrapolar o previsto.",
            ),
            (
                "Como cancelo um pedido?",
                "A seed considera cancelamento conforme a etapa do pedido e informa quando a análise precisa ser feita pelo parceiro ou suporte humano.",
            ),
            (
                "Recebi item faltando. Como resolvo?",
                "O atendimento orienta registrar a ocorrência no pedido para análise de estorno, crédito ou novo envio, conforme o caso.",
            ),
            (
                "Como uso cupom?",
                "No ambiente de teste, o cupom é aplicado antes da finalização do pagamento, respeitando regras de elegibilidade informadas no checkout.",
            ),
            (
                "Quando acontece o reembolso?",
                "O bot de demonstração explica que o prazo depende do meio de pagamento e da aprovação da solicitação.",
            ),
        ],
        "conversas": [
            (
                200000018,
                "Meu pedido saiu para entrega mas nao chegou",
                "Vou verificar o status ilustrativo da rota e, se necessário, abrir um chamado de apoio para o pedido.",
            ),
            (
                200000019,
                "O restaurante mandou bebida errada",
                "Posso registrar a divergência do item e orientar a análise para crédito, estorno ou ajuste do pedido.",
            ),
            (
                200000020,
                "Tem cupom para primeira compra?",
                "Neste cenário de seed, posso orientar onde consultar cupons elegíveis antes de concluir o pedido.",
            ),
            (
                200000021,
                "Pedi cancelamento e ainda nao tive retorno",
                "Vou consultar o chamado ilustrativo e informar o próximo passo previsto para a tratativa.",
            ),
        ],
        "documentos": [
            "fluxo_cancelamento_ifood_seed.pdf",
            "faq_reembolsos_ifood_seed.pdf",
            "guia_pedidos_ifood_seed.pdf",
        ],
    },
    {
        "nome": "Smart Datacenter",
        "telegram_user_id": 100000006,
        "nome_bot": "Smart Datacenter Assistente",
        "saudacao": (
            "Olá! Bem-vindo à Smart Datacenter. Sou o assistente virtual da Smart "
            "e posso ajudar com Cloud, IA, Cibersegurança e Workspace."
        ),
        "instrucoes": (
            "Você é o assistente virtual da Smart Datacenter. A empresa oferece "
            "soluções integradas de Cloud, Inteligência Artificial, Data Center, "
            "Cibersegurança e Workspace, com infraestrutura brasileira e soberana. "
            "Ajude com dúvidas sobre cloud privada, backup e recuperação, DRaaS, "
            "BaaS, hospedagem de ambientes críticos, SOC/NOC, conformidade LGPD, "
            "virtualização de estações de trabalho e projetos de IA. Quando a "
            "solicitação exigir negociação comercial, escopo técnico detalhado ou "
            "acionamento humano, direcione para os canais oficiais da empresa."
        ),
        "horario_atendimento": (
            "Contato comercial pelo site e canais oficiais; o site não informa horário de atendimento."
        ),
        "fallback_contato": (
            "contato@smartdatacenter.com.br | (11) 4160-5955 | (79) 3021-8400 | "
            "WhatsApp (79) 9830-9921"
        ),
        "clientes": [
            {"telegram_user_id": 200000022, "nome": "Renata Moraes"},
            {"telegram_user_id": 200000023, "nome": "Eduardo Carvalho"},
            {"telegram_user_id": 200000024, "nome": "Paulo Henrique Lima"},
            {"telegram_user_id": 200000025, "nome": "Vanessa Albuquerque"},
        ],
        "faqs": [
            (
                "Quais soluções a Smart Datacenter oferece?",
                "A Smart Datacenter organiza suas soluções em verticais como Data Center, Cibersegurança, Inteligência Artificial e Workspace, com ofertas integradas sob demanda.",
            ),
            (
                "A infraestrutura é brasileira?",
                "Sim. No atendimento configurado para esta empresa, a Smart destaca infraestrutura física no Brasil, com soberania, privacidade e aderência à LGPD.",
            ),
            (
                "Vocês oferecem backup e recuperação?",
                "Sim. A Smart Datacenter divulga serviços como Cloud Backup, BaaS e DRaaS sob demanda para resiliência e continuidade operacional.",
            ),
            (
                "Vocês atendem empresas e governos?",
                "Sim. A comunicação institucional da Smart Datacenter apresenta soluções de Cloud, IA e Cibersegurança para empresas e governos.",
            ),
            (
                "Como falar com o time comercial?",
                "Você pode solicitar contato pelo site oficial ou usar os canais cadastrados: contato@smartdatacenter.com.br, (11) 4160-5955, (79) 3021-8400 e WhatsApp (79) 9830-9921.",
            ),
        ],
        "conversas": [
            (
                200000022,
                "Preciso migrar meu ambiente para uma cloud soberana",
                "Posso iniciar um levantamento do seu cenário e direcionar sua demanda para uma proposta personalizada de cloud privada ou híbrida com foco em soberania e conformidade.",
            ),
            (
                200000023,
                "Vocês possuem SOC 24x7?",
                "Sim. A Smart Datacenter divulga SOC 24x7 e NOC com SLA configurável dentro da vertical de cibersegurança. Se quiser, posso registrar seu interesse para contato comercial.",
            ),
            (
                200000024,
                "Quero virtualizar as estações de trabalho da equipe",
                "A Smart também atua com Workspace e estações de trabalho virtuais. Posso coletar quantidade de usuários, aplicações e requisitos de segurança para encaminhar ao time comercial.",
            ),
            (
                200000025,
                "Vocês apoiam projetos com IA e GPUs dedicadas?",
                "Sim. O site institucional menciona infraestrutura para criação, treinamento e execução de modelos de IA, incluindo workstations virtuais com GPUs de última geração.",
            ),
        ],
        "documentos": [
            "portfolio_smart_datacenter_seed.pdf",
            "solucoes_ciberseguranca_smart_seed.pdf",
            "contatos_smart_datacenter_seed.pdf",
        ],
    },
]


# ─────────────────────────────────────────────
# FUNÇÕES AUXILIARES
# ─────────────────────────────────────────────

def gerar_token_unico(conn: sqlite3.Connection, coluna: str) -> str:
    """Gera um token único para a coluna informada."""
    while True:
        token = secrets.token_urlsafe(16)
        cur = conn.execute(f"SELECT 1 FROM empresas WHERE {coluna} = ? LIMIT 1", (token,))
        if not cur.fetchone():
            return token


def init_db(conn: sqlite3.Connection):
    """Cria as tabelas necessárias se não existirem."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telegram_user_id INTEGER NOT NULL UNIQUE,
            link_token TEXT NOT NULL UNIQUE,
            admin_link_token TEXT NOT NULL UNIQUE,
            nome_bot TEXT DEFAULT 'Assistente',
            saudacao TEXT DEFAULT 'Olá! Como posso ajudar você hoje?',
            instrucoes TEXT DEFAULT 'Você é um assistente de atendimento ao cliente. Responda de forma educada e profissional.',
            instruction_template_key TEXT DEFAULT NULL,
            ativo INTEGER NOT NULL DEFAULT 1,
            horario_atendimento TEXT DEFAULT '',
            fallback_contato TEXT DEFAULT '',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS empresa_admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            usuario_id INTEGER NOT NULL UNIQUE,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clientes_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            cliente_telegram_user_id INTEGER NOT NULL UNIQUE,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            nome_arquivo TEXT NOT NULL,
            carregado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id)
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_documentos_empresa_arquivo
        ON documentos(empresa_id, nome_arquivo)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            usuario_telegram_id INTEGER NOT NULL,
            mensagem_usuario TEXT NOT NULL,
            resposta_bot TEXT NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS faqs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            pergunta TEXT NOT NULL,
            resposta TEXT NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id)
        )
    """)
    conn.commit()


def validar_integridade(conn: sqlite3.Connection):
    """Valida a integridade do banco antes da persistência."""
    resultado = conn.execute("PRAGMA integrity_check").fetchone()
    status = resultado[0] if resultado else "integrity_check sem retorno"
    if status != "ok":
        raise RuntimeError(f"Falha na integridade do banco de trabalho: {status}")


def limpar_dados_teste(conn: sqlite3.Connection):
    """Remove dados de seed existentes sem tocar em empresas de outros usuários."""
    ids_admin = [e["telegram_user_id"] for e in EMPRESAS]
    ids_cliente = [c["telegram_user_id"] for e in EMPRESAS for c in e["clientes"]]

    placeholders = ",".join("?" * len(ids_admin))
    cur = conn.execute(
        f"SELECT id FROM empresas WHERE telegram_user_id IN ({placeholders})",
        ids_admin,
    )
    empresa_ids = [r[0] for r in cur.fetchall()]

    if empresa_ids:
        ph = ",".join("?" * len(empresa_ids))
        conn.execute(f"DELETE FROM conversas WHERE empresa_id IN ({ph})", empresa_ids)
        conn.execute(f"DELETE FROM faqs WHERE empresa_id IN ({ph})", empresa_ids)
        conn.execute(f"DELETE FROM documentos WHERE empresa_id IN ({ph})", empresa_ids)
        conn.execute(f"DELETE FROM clientes_empresa WHERE empresa_id IN ({ph})", empresa_ids)
        conn.execute(f"DELETE FROM empresa_admins WHERE empresa_id IN ({ph})", empresa_ids)
        conn.execute(f"DELETE FROM empresas WHERE id IN ({ph})", empresa_ids)

    if ids_admin:
        conn.execute(
            f"DELETE FROM empresa_admins WHERE usuario_id IN ({placeholders})",
            ids_admin,
        )

    if ids_cliente:
        ph2 = ",".join("?" * len(ids_cliente))
        conn.execute(
            f"DELETE FROM clientes_empresa WHERE cliente_telegram_user_id IN ({ph2})",
            ids_cliente,
        )

    conn.commit()
    print("  ✓ Dados de seed anteriores removidos")


def criar_empresa(conn: sqlite3.Connection, dados: dict[str, Any]) -> int:
    """Cria empresa e retorna o ID."""
    link_token = gerar_token_unico(conn, "link_token")
    admin_link_token = gerar_token_unico(conn, "admin_link_token")
    cur = conn.execute(
        """
        INSERT INTO empresas (
            nome,
            telegram_user_id,
            link_token,
            admin_link_token,
            nome_bot,
            saudacao,
            instrucoes,
            instruction_template_key,
            ativo,
            horario_atendimento,
            fallback_contato
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            dados["nome"],
            dados["telegram_user_id"],
            link_token,
            admin_link_token,
            dados["nome_bot"],
            dados["saudacao"],
            dados["instrucoes"],
            dados.get("instruction_template_key"),
            dados["horario_atendimento"],
            dados["fallback_contato"],
        ),
    )

    if cur.lastrowid is None:
        raise RuntimeError("Falha ao obter o ID gerado para a empresa de seed.")

    empresa_id = int(cur.lastrowid)
    conn.execute(
        "INSERT OR IGNORE INTO empresa_admins (empresa_id, usuario_id) VALUES (?, ?)",
        (empresa_id, dados["telegram_user_id"]),
    )
    conn.commit()
    return empresa_id


def vincular_clientes(conn: sqlite3.Connection, empresa_id: int, clientes: list):
    """Vincula clientes à empresa."""
    for c in clientes:
        conn.execute(
            "INSERT OR REPLACE INTO clientes_empresa (empresa_id, cliente_telegram_user_id) VALUES (?, ?)",
            (empresa_id, c["telegram_user_id"]),
        )
    conn.commit()


def criar_faqs(conn: sqlite3.Connection, empresa_id: int, faqs: list):
    """Cria FAQs para a empresa."""
    for pergunta, resposta in faqs:
        conn.execute(
            "INSERT INTO faqs (empresa_id, pergunta, resposta) VALUES (?, ?, ?)",
            (empresa_id, pergunta, resposta),
        )
    conn.commit()


def registrar_conversas(conn: sqlite3.Connection, empresa_id: int, conversas: list):
    """Registra conversas históricas."""
    for usuario_id, mensagem, resposta in conversas:
        conn.execute(
            "INSERT INTO conversas (empresa_id, usuario_telegram_id, mensagem_usuario, resposta_bot) VALUES (?, ?, ?, ?)",
            (empresa_id, usuario_id, mensagem, resposta),
        )
    conn.commit()


def registrar_documentos(conn: sqlite3.Connection, empresa_id: int, documentos: list[str]):
    """Registra documentos exemplificativos."""
    for nome_arquivo in documentos:
        conn.execute(
            "INSERT OR IGNORE INTO documentos (empresa_id, nome_arquivo) VALUES (?, ?)",
            (empresa_id, nome_arquivo),
        )
    conn.commit()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("\n" + "=" * 65)
    print("  🌱 SEED DE DADOS DE TESTE — Agente de Atendimento ao Cliente")
    print("=" * 65)
    print("  Empresas reais famosas com conteúdo de atendimento ilustrativo")
    print(f"\n📂 Banco (trabalho): {DB_PATH}")
    print(f"📂 Banco (destino) : {DB_PATH_ORIGINAL}\n")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("⚙️  Inicializando tabelas...")
    init_db(conn)
    print("  ✓ Tabelas OK\n")

    print("🧹 Limpando dados de teste anteriores...")
    limpar_dados_teste(conn)
    print()

    resultados = []

    for dados in EMPRESAS:
        print(f"🏢 Criando empresa: {dados['nome']}")

        empresa_id = criar_empresa(conn, dados)
        print(f"  ✓ Empresa criada (ID: {empresa_id}, Admin ID: {dados['telegram_user_id']})")

        vincular_clientes(conn, empresa_id, dados["clientes"])
        print(f"  ✓ {len(dados['clientes'])} clientes vinculados")

        criar_faqs(conn, empresa_id, dados["faqs"])
        print(f"  ✓ {len(dados['faqs'])} FAQs criadas")

        registrar_conversas(conn, empresa_id, dados["conversas"])
        print(f"  ✓ {len(dados['conversas'])} conversas registradas")

        registrar_documentos(conn, empresa_id, dados["documentos"])
        print(f"  ✓ {len(dados['documentos'])} documentos registrados")

        row = conn.execute("SELECT * FROM empresas WHERE id = ?", (empresa_id,)).fetchone()
        link_token = dict(row)["link_token"] if row else "N/A"

        total_clientes = conn.execute(
            "SELECT COUNT(*) FROM clientes_empresa WHERE empresa_id = ?", (empresa_id,)
        ).fetchone()[0]

        resultados.append({
            "nome": dados["nome"],
            "empresa_id": empresa_id,
            "admin_telegram_id": dados["telegram_user_id"],
            "link_token": link_token,
            "total_clientes": total_clientes,
            "total_faqs": len(dados["faqs"]),
            "total_conversas": len(dados["conversas"]),
            "total_documentos": len(dados["documentos"]),
            "clientes": dados["clientes"],
        })
        print()

    conn.close()

    # ─────────────────────────────────────────────
    # RELATÓRIO FINAL
    # ─────────────────────────────────────────────
    print("=" * 65)
    print("  ✅ SEED CONCLUÍDO — RESUMO DOS DADOS CRIADOS")
    print("=" * 65)

    total_clientes_geral = sum(r["total_clientes"] for r in resultados)
    total_faqs_geral = sum(r["total_faqs"] for r in resultados)
    total_conversas_geral = sum(r["total_conversas"] for r in resultados)
    total_docs_geral = sum(r["total_documentos"] for r in resultados)

    print("\n📊 Totais gerais:")
    print(f"   Empresas   : {len(resultados)}")
    print(f"   Clientes   : {total_clientes_geral}")
    print(f"   FAQs       : {total_faqs_geral}")
    print(f"   Conversas  : {total_conversas_geral}")
    print(f"   Documentos : {total_docs_geral}")
    print()

    for r in resultados:
        print(f"┌─ 🏢 {r['nome']} (ID Banco: {r['empresa_id']})")
        print(f"│   Admin Telegram ID : {r['admin_telegram_id']}")
        print(f"│   Link Token        : {r['link_token']}")
        print(f"│   Link Telegram     : https://t.me/<seu_bot>?start={r['link_token']}")
        print(f"│   Clientes ({r['total_clientes']})        FAQs ({r['total_faqs']})   Conversas ({r['total_conversas']})")
        print("│")
        for c in r["clientes"]:
            print(f"│   👤 {c['nome']:25s} → Telegram ID: {c['telegram_user_id']}")
        print(f"└{'─' * 55}")
        print()

    print("🚀 Dados prontos para testes!")
    print("   • Use os Admin Telegram IDs para simular o painel de administração")
    print("   • Use os IDs dos clientes para simular conversas de usuários")
    print("   • Os link tokens permitem que clientes se vinculem via deep link")
    print("=" * 65 + "\n")


def preparar_banco_trabalho() -> bool:
    """Cria um banco de trabalho íntegro a partir do banco local, quando existir."""
    if DB_PATH.exists():
        DB_PATH.unlink()

    if not DB_PATH_ORIGINAL.exists():
        return False

    origem = sqlite3.connect(DB_PATH_ORIGINAL)
    trabalho = sqlite3.connect(DB_PATH)

    try:
        script = "\n".join(origem.iterdump())
        if script.strip():
            trabalho.executescript(script)
            trabalho.commit()
        validar_integridade(trabalho)
        return True
    finally:
        trabalho.close()
        origem.close()


def criar_backup_banco_original() -> Path | None:
    """Preserva o banco anterior antes de sobrescrevê-lo."""
    if not DB_PATH_ORIGINAL.exists():
        return None

    backup_path = DB_PATH_ORIGINAL.with_name(
        f"{DB_PATH_ORIGINAL.name}.bak-{datetime.now():%Y%m%d-%H%M%S}"
    )
    shutil.copy2(DB_PATH_ORIGINAL, backup_path)
    return backup_path


if __name__ == "__main__":
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    if preparar_banco_trabalho():
        print(f"📋 Banco de trabalho recuperado e criado em {DB_PATH}")
    else:
        print(f"⚠️ Banco original não encontrado em {DB_PATH_ORIGINAL}. Um novo banco será criado.")

    try:
        main()
        with sqlite3.connect(DB_PATH) as conn:
            validar_integridade(conn)

        backup_path = criar_backup_banco_original()
        if backup_path:
            print(f"🗂️ Backup do banco anterior salvo em:\n   {backup_path}")

        DB_PATH_ORIGINAL.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DB_PATH, DB_PATH_ORIGINAL)
        print(f"✅ Banco atualizado copiado de volta para:\n   {DB_PATH_ORIGINAL}\n")
    finally:
        if DB_PATH.exists():
            DB_PATH.unlink()
