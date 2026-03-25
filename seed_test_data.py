"""
Script de seed para popular o banco de dados com dados de teste.
Usa apenas sqlite3 nativo (sem dependências externas).
"""

import secrets
import sqlite3
from typing import Any

DB_PATH_ORIGINAL = "/sessions/exciting-festive-hypatia/mnt/agente-atendimento-ao-cliente/data/bot.db"
DB_PATH = "/tmp/bot_seed.db"  # Trabalha em cópia local para evitar problemas de I/O no FS Windows

# ─────────────────────────────────────────────
# DADOS DE TESTE
# ─────────────────────────────────────────────

EMPRESAS: list[dict[str, Any]] = [
    {
        "nome": "TechStore Brasil",
        "telegram_user_id": 100000001,
        "nome_bot": "TechBot",
        "saudacao": "Olá! Bem-vindo à TechStore Brasil! 🖥️ Como posso te ajudar hoje?",
        "instrucoes": (
            "Você é o TechBot, assistente virtual da TechStore Brasil, loja especializada em "
            "eletrônicos e tecnologia. Ajude clientes com dúvidas sobre produtos, preços, "
            "garantia, entrega e suporte técnico. Seja sempre educado e técnico."
        ),
        "horario_atendimento": "Seg-Sex 08h-20h | Sáb 09h-17h",
        "fallback_contato": "suporte@techstore.com.br | (11) 4002-8922",
        "clientes": [
            {"telegram_user_id": 200000001, "nome": "Carlos Mendes"},
            {"telegram_user_id": 200000002, "nome": "Fernanda Lima"},
            {"telegram_user_id": 200000003, "nome": "Rafael Oliveira"},
            {"telegram_user_id": 200000004, "nome": "Juliana Costa"},
            {"telegram_user_id": 200000005, "nome": "Bruno Alves"},
        ],
        "faqs": [
            ("Qual o prazo de entrega?", "Entregamos em todo o Brasil. Capitais: 2-3 dias úteis. Interior: 5-7 dias úteis. Frete grátis acima de R$ 299!"),
            ("Vocês aceitam parcelamento?", "Sim! Parcelamos em até 12x sem juros no cartão de crédito. Aceitamos PIX com 5% de desconto."),
            ("Qual a política de garantia?", "Todos os produtos têm garantia mínima de 1 ano. Produtos nacionais contam com garantia estendida do fabricante."),
            ("Como faço para trocar um produto?", "Você tem 7 dias para solicitar troca ou devolução após o recebimento. Acesse Minha Conta > Pedidos > Solicitar Troca."),
            ("Vocês têm loja física?", "Temos lojas em São Paulo (Paulista e Shopping Ibirapuera), Rio de Janeiro (Botafogo) e Belo Horizonte (Savassi)."),
        ],
        "conversas": [
            (200000001, "Quero saber o preço do iPhone 15", "O iPhone 15 128GB está disponível por R$ 5.499 em até 12x sem juros. Temos nas cores preto, rosa e amarelo. Posso verificar o estoque para sua região!"),
            (200000002, "Qual notebook vocês recomendam até 3 mil reais?", "Para até R$ 3.000 recomendo o Acer Aspire 5 (i5, 8GB RAM, SSD 512GB) por R$ 2.799 ou o Lenovo IdeaPad 3 (Ryzen 5, 8GB, SSD 256GB) por R$ 2.499. Ambos excelentes para uso no dia a dia!"),
            (200000003, "Meu pedido #45123 não chegou ainda", "Vou verificar para você! O pedido #45123 está em rota de entrega pela transportadora. Previsão: amanhã até 18h. Caso não receba, entre em contato pelo nosso 0800."),
            (200000004, "Vocês vendem peças para notebook?", "Sim! Trabalhamos com memórias RAM, SSDs, baterias e telas para os principais modelos. Qual é o modelo do seu notebook?"),
            (200000005, "Tem desconto para comprar 10 unidades de fone?", "Claro! Para compras corporativas acima de 5 unidades oferecemos 10-15% de desconto. Vou te passar para nosso setor comercial. 📧 comercial@techstore.com.br"),
        ],
        "documentos": [
            "catalogo_techstore_2024.pdf",
            "politica_devolucao.pdf",
            "manual_garantia.pdf",
        ],
    },
    {
        "nome": "Clínica Saúde & Vida",
        "telegram_user_id": 100000002,
        "nome_bot": "SaúdeBot",
        "saudacao": "Olá! Bem-vindo à Clínica Saúde & Vida 🏥 Sou o SaúdeBot. Como posso ajudar?",
        "instrucoes": (
            "Você é o SaúdeBot da Clínica Saúde & Vida. Ajude pacientes com informações sobre "
            "agendamento de consultas, especialidades disponíveis, planos de saúde aceitos, "
            "localização e horários. NUNCA forneça diagnósticos médicos. Seja empático e cuidadoso."
        ),
        "horario_atendimento": "Seg-Sex 07h-19h | Sáb 07h-13h",
        "fallback_contato": "atendimento@clinicasaudaevida.com.br | (21) 3322-5500",
        "clientes": [
            {"telegram_user_id": 200000006, "nome": "Maria Souza"},
            {"telegram_user_id": 200000007, "nome": "João Pedro Santos"},
            {"telegram_user_id": 200000008, "nome": "Ana Paula Ferreira"},
            {"telegram_user_id": 200000009, "nome": "Roberto Nascimento"},
        ],
        "faqs": [
            ("Como agendar uma consulta?", "Você pode agendar pelo nosso app, site clinicasaudaevida.com.br, pelo WhatsApp (21) 99988-7766 ou presencialmente. Temos horários de segunda a sábado!"),
            ("Quais planos de saúde vocês aceitam?", "Aceitamos: Unimed, Bradesco Saúde, SulAmérica, Amil, Porto Seguro, Hapvida, NotreDame e convênios estaduais. Consulte disponibilidade por especialidade."),
            ("Quais especialidades estão disponíveis?", "Clínica Geral, Cardiologia, Dermatologia, Ginecologia, Ortopedia, Pediatria, Psiquiatria, Neurologia, Endocrinologia e mais. Total de 28 especialidades!"),
            ("Qual o valor de uma consulta particular?", "Consultas particulares variam de R$ 180 a R$ 380 dependendo da especialidade. Clínica Geral: R$ 180. Especialistas: a partir de R$ 250."),
            ("Vocês fazem exames laboratoriais?", "Sim! Temos laboratório próprio com mais de 300 tipos de exames. Resultados online em até 24h para a maioria dos exames de rotina."),
            ("Como cancelar ou remarcar consulta?", "Cancele ou remarca com até 24h de antecedência pelo app, site ou telefone. Cancelamentos com menos de 24h podem gerar taxa de R$ 50."),
        ],
        "conversas": [
            (200000006, "Preciso agendar consulta com cardiologista", "Com certeza! Temos disponibilidade com o Dr. Ricardo Fonseca (Cardiologista) na próxima quinta-feira às 14h30 ou sexta às 09h. Qual prefere? Aceita qual plano de saúde?"),
            (200000007, "Tenho Unimed, vocês aceitam?", "Sim, aceitamos Unimed! Para confirmar a cobertura da sua consulta, precisamos do número do seu cartão. Qual especialidade deseja?"),
            (200000008, "Qual o endereço da clínica?", "Estamos na Rua das Flores, 450 - Botafogo, Rio de Janeiro (RJ). 🗺️ Fácil acesso pelo metrô Botafogo (Saída 2). Estacionamento disponível no local."),
            (200000009, "Posso fazer exame de sangue sem agendamento?", "Sim! Para exames laboratoriais não é necessário agendamento. Atendemos de segunda a sexta das 07h às 11h para coleta em jejum. Lembre de trazer a solicitação médica!"),
        ],
        "documentos": [
            "tabela_planos_aceitos.pdf",
            "guia_do_paciente.pdf",
            "exames_disponiveis.pdf",
        ],
    },
    {
        "nome": "Academia FitPower",
        "telegram_user_id": 100000003,
        "nome_bot": "FitBot",
        "saudacao": "E aí! 💪 Bem-vindo à Academia FitPower! Sou o FitBot. Bora treinar?",
        "instrucoes": (
            "Você é o FitBot da Academia FitPower. Ajude membros e interessados com informações "
            "sobre planos, horários, modalidades, personal trainers e promoções. "
            "Seja animado, motivador e use linguagem descontraída!"
        ),
        "horario_atendimento": "Seg-Sex 05h30-23h | Sab-Dom 07h-20h",
        "fallback_contato": "fitpower@academia.com | (31) 9988-7766",
        "clientes": [
            {"telegram_user_id": 200000010, "nome": "Lucas Pereira"},
            {"telegram_user_id": 200000011, "nome": "Camila Rodrigues"},
            {"telegram_user_id": 200000012, "nome": "Diego Martins"},
            {"telegram_user_id": 200000013, "nome": "Isabela Torres"},
            {"telegram_user_id": 200000014, "nome": "Thiago Barbosa"},
            {"telegram_user_id": 200000015, "nome": "Patrícia Gomes"},
        ],
        "faqs": [
            ("Quais são os planos disponíveis?", "Temos 3 planos: Básico R$89/mês (musculação + cardio), Plus R$129/mês (+ aulas coletivas), Premium R$189/mês (ilimitado + personal 2x/mês). Anual com 2 meses grátis! 🎉"),
            ("Quais modalidades vocês oferecem?", "Musculação, Spinning, Zumba, Yoga, Pilates, Boxe, CrossFit, Natação, Funcional e Dança. São mais de 80 aulas por semana!"),
            ("Vocês têm personal trainer?", "Sim! Contamos com 12 personal trainers especializados. Preços: R$ 120/sessão avulsa ou pacotes a partir de R$ 350 (4 sessões). Avaliação física inclusa!"),
            ("Como faço para me matricular?", "Você pode se matricular presencialmente, pelo nosso app FitPower ou WhatsApp. Traga RG e CPF. Primeira semana GRÁTIS para novos alunos! 🆓"),
            ("Tem estacionamento?", "Sim! Estacionamento gratuito para alunos por até 2 horas. Fica no subsolo do prédio, acesso pela Rua Auxiliadora."),
        ],
        "conversas": [
            (200000010, "Quanto custa o plano mensal?", "Boa pergunta! 💪 Nosso plano Básico é R$89/mes com acesso à musculação e cardio. Se quiser aulas coletivas, o Plus é R$129. E o Premium inclui personal trainer por R$189. Qual se encaixa pra você?"),
            (200000011, "Tem aula de yoga?", "SIM! 🧘‍♀️ Temos aulas de Yoga toda semana: Seg/Qua/Sex às 07h e 19h, e Sáb às 09h. Todas as turmas com instrutoras certificadas. Vem experimentar, primeira aula é free!"),
            (200000012, "Qual o horário de funcionamento?", "Abrimos cedo e fechamos tarde! ⏰ Seg-Sex: 05h30 às 23h. Sab-Dom: 07h às 20h. Nunca vai ser desculpa falta de horário 😄"),
            (200000013, "Vocês têm nutricionista?", "Temos parceria com 3 nutricionistas esportivas que atendem na própria academia! Consulta avulsa R$150 ou inclusa no plano Premium. Quer agendar uma avaliação?"),
            (200000014, "Minha mensalidade vence amanhã, posso pagar pelo PIX?", "Claro! Chave PIX: fitpower@academia.com (CNPJ). Após o pagamento, manda o comprovante aqui que a gente confirma na hora! 💚"),
            (200000015, "Vocês têm aula de natação para criança?", "Temos natação infantil para crianças de 3 a 12 anos! 🏊‍♂️ Turmas: 3-5 anos (adaptação), 6-8 anos e 9-12 anos. Aulas Ter/Qui/Sáb de manhã. Quer mais info?"),
        ],
        "documentos": [
            "tabela_planos_fitpower.pdf",
            "grade_horarios_aulas.pdf",
            "regulamento_academia.pdf",
        ],
    },
]


# ─────────────────────────────────────────────
# FUNÇÕES AUXILIARES
# ─────────────────────────────────────────────

def gerar_link_token(conn: sqlite3.Connection) -> str:
    """Gera um link_token único."""
    while True:
        token = secrets.token_urlsafe(16)
        cur = conn.execute("SELECT 1 FROM empresas WHERE link_token = ? LIMIT 1", (token,))
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
            nome_bot TEXT DEFAULT 'Assistente',
            saudacao TEXT DEFAULT 'Olá! Como posso ajudar você hoje?',
            instrucoes TEXT DEFAULT 'Você é um assistente de atendimento ao cliente.',
            ativo INTEGER NOT NULL DEFAULT 1,
            horario_atendimento TEXT DEFAULT '',
            fallback_contato TEXT DEFAULT '',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


def limpar_dados_teste(conn: sqlite3.Connection):
    """Remove dados de teste existentes."""
    ids_admin = [e["telegram_user_id"] for e in EMPRESAS]
    ids_cliente = [c["telegram_user_id"] for e in EMPRESAS for c in e["clientes"]]

    placeholders = ",".join("?" * len(ids_admin))
    cur = conn.execute(f"SELECT id FROM empresas WHERE telegram_user_id IN ({placeholders})", ids_admin)
    empresa_ids = [r[0] for r in cur.fetchall()]

    if empresa_ids:
        ph = ",".join("?" * len(empresa_ids))
        conn.execute(f"DELETE FROM conversas WHERE empresa_id IN ({ph})", empresa_ids)
        conn.execute(f"DELETE FROM faqs WHERE empresa_id IN ({ph})", empresa_ids)
        conn.execute(f"DELETE FROM documentos WHERE empresa_id IN ({ph})", empresa_ids)
        conn.execute(f"DELETE FROM clientes_empresa WHERE empresa_id IN ({ph})", empresa_ids)
        conn.execute(f"DELETE FROM empresas WHERE id IN ({ph})", empresa_ids)

    if ids_cliente:
        ph2 = ",".join("?" * len(ids_cliente))
        conn.execute(f"DELETE FROM clientes_empresa WHERE cliente_telegram_user_id IN ({ph2})", ids_cliente)

    conn.commit()
    print("  ✓ Dados de teste anteriores removidos")


def criar_empresa(conn: sqlite3.Connection, dados: dict) -> int:
    """Cria empresa e retorna o ID."""
    token = gerar_link_token(conn)
    cur = conn.execute(
        """INSERT INTO empresas (nome, telegram_user_id, link_token, nome_bot, saudacao,
           instrucoes, ativo, horario_atendimento, fallback_contato)
           VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
        (dados["nome"], dados["telegram_user_id"], token, dados["nome_bot"],
         dados["saudacao"], dados["instrucoes"], dados["horario_atendimento"],
         dados["fallback_contato"]),
    )
    conn.commit()
    if cur.lastrowid is None:
        raise RuntimeError("Falha ao obter o ID gerado para a empresa de teste.")
    return cur.lastrowid


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


def registrar_documentos(conn: sqlite3.Connection, empresa_id: int, documentos: list):
    """Registra documentos fictícios."""
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


if __name__ == "__main__":
    import shutil
    # Copia o banco original para trabalhar localmente
    shutil.copy2(DB_PATH_ORIGINAL, DB_PATH)
    print(f"📋 Cópia do banco criada em {DB_PATH}")

    main()

    # Copia de volta para o destino original
    shutil.copy2(DB_PATH, DB_PATH_ORIGINAL)
    print(f"✅ Banco atualizado copiado de volta para:\n   {DB_PATH_ORIGINAL}\n")
