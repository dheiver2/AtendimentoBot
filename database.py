import aiosqlite
from config import DB_PATH


async def _obter_colunas_empresas(db: aiosqlite.Connection) -> set[str]:
    """Retorna o conjunto de colunas atuais da tabela empresas."""
    cursor = await db.execute("PRAGMA table_info(empresas)")
    rows = await cursor.fetchall()
    return {row[1] for row in rows}


async def _garantir_colunas_empresas(db: aiosqlite.Connection):
    """Garante colunas novas na tabela empresas, inclusive em bancos antigos."""
    colunas = await _obter_colunas_empresas(db)

    if not colunas:
        return

    if "telegram_user_id" not in colunas:
        await db.execute("ALTER TABLE empresas ADD COLUMN telegram_user_id INTEGER")

        if "telegram_admin_id" in colunas:
            await db.execute("""
                UPDATE empresas
                SET telegram_user_id = telegram_admin_id
                WHERE telegram_user_id IS NULL
            """)

    colunas = await _obter_colunas_empresas(db)
    if "ativo" not in colunas:
        await db.execute("ALTER TABLE empresas ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1")

    if "horario_atendimento" not in colunas:
        await db.execute("ALTER TABLE empresas ADD COLUMN horario_atendimento TEXT DEFAULT ''")

    if "fallback_contato" not in colunas:
        await db.execute("ALTER TABLE empresas ADD COLUMN fallback_contato TEXT DEFAULT ''")

    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_empresas_telegram_user_id
        ON empresas(telegram_user_id)
    """)


async def _deduplicar_documentos(db: aiosqlite.Connection):
    """Remove registros duplicados de documentos, mantendo o mais recente por arquivo."""
    await db.execute("""
        DELETE FROM documentos
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM documentos
            GROUP BY empresa_id, nome_arquivo
        )
    """)


async def init_db():
    """Inicializa o banco de dados com as tabelas necessárias."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS empresas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL UNIQUE,
                nome_bot TEXT DEFAULT 'Assistente',
                saudacao TEXT DEFAULT 'Olá! Como posso ajudar você hoje?',
                instrucoes TEXT DEFAULT 'Você é um assistente de atendimento ao cliente. Responda de forma educada e profissional.',
                ativo INTEGER NOT NULL DEFAULT 1,
                horario_atendimento TEXT DEFAULT '',
                fallback_contato TEXT DEFAULT '',
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await _garantir_colunas_empresas(db)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS documentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                nome_arquivo TEXT NOT NULL,
                carregado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id)
            )
        """)
        await _deduplicar_documentos(db)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_documentos_empresa_arquivo
            ON documentos(empresa_id, nome_arquivo)
        """)
        await db.execute("""
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS faqs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                pergunta TEXT NOT NULL,
                resposta TEXT NOT NULL,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id)
            )
        """)
        await db.commit()


async def criar_empresa(nome: str, telegram_user_id: int) -> int:
    """Cria uma nova empresa e retorna o ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO empresas (nome, telegram_user_id) VALUES (?, ?)",
            (nome, telegram_user_id),
        )
        await db.commit()
        return cursor.lastrowid


async def obter_empresa_por_usuario(telegram_user_id: int) -> dict | None:
    """Busca empresa pelo ID do Telegram do usuário."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM empresas WHERE telegram_user_id = ?",
            (telegram_user_id,),
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None


async def atualizar_empresa(empresa_id: int, **kwargs):
    """Atualiza campos da empresa."""
    campos_permitidos = {
        "nome",
        "nome_bot",
        "saudacao",
        "instrucoes",
        "ativo",
        "horario_atendimento",
        "fallback_contato",
    }
    campos = {k: v for k, v in kwargs.items() if k in campos_permitidos}
    if not campos:
        return
    set_clause = ", ".join(f"{k} = ?" for k in campos)
    values = list(campos.values()) + [empresa_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE empresas SET {set_clause} WHERE id = ?",
            values,
        )
        await db.commit()


async def registrar_documento(empresa_id: int, nome_arquivo: str) -> int:
    """Registra um documento carregado ou atualiza seu timestamp se já existir."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id FROM documentos WHERE empresa_id = ? AND nome_arquivo = ?",
            (empresa_id, nome_arquivo),
        )
        existente = await cursor.fetchone()
        if existente:
            await db.execute(
                """
                UPDATE documentos
                SET carregado_em = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (existente["id"],),
            )
            await db.commit()
            return existente["id"]

        cursor = await db.execute(
            "INSERT INTO documentos (empresa_id, nome_arquivo) VALUES (?, ?)",
            (empresa_id, nome_arquivo),
        )
        await db.commit()
        return cursor.lastrowid


async def listar_documentos(empresa_id: int) -> list[dict]:
    """Lista documentos de uma empresa."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM documentos WHERE empresa_id = ? ORDER BY carregado_em DESC",
            (empresa_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def obter_documento_por_id(empresa_id: int, documento_id: int) -> dict | None:
    """Busca um documento específico da empresa."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM documentos WHERE empresa_id = ? AND id = ?",
            (empresa_id, documento_id),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def excluir_documento(empresa_id: int, documento_id: int) -> bool:
    """Exclui um documento específico da empresa."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM documentos WHERE empresa_id = ? AND id = ?",
            (empresa_id, documento_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def registrar_conversa(empresa_id: int, usuario_telegram_id: int, mensagem: str, resposta: str):
    """Registra uma conversa no histórico."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO conversas (empresa_id, usuario_telegram_id, mensagem_usuario, resposta_bot) VALUES (?, ?, ?, ?)",
            (empresa_id, usuario_telegram_id, mensagem, resposta),
        )
        await db.commit()


async def criar_faq(empresa_id: int, pergunta: str, resposta: str) -> int:
    """Cria uma FAQ da empresa e retorna o ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO faqs (empresa_id, pergunta, resposta) VALUES (?, ?, ?)",
            (empresa_id, pergunta, resposta),
        )
        await db.commit()
        return cursor.lastrowid


async def listar_faqs(empresa_id: int) -> list[dict]:
    """Lista as FAQs cadastradas por empresa."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM faqs WHERE empresa_id = ? ORDER BY id ASC",
            (empresa_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def excluir_faq(empresa_id: int, faq_id: int) -> bool:
    """Exclui uma FAQ da empresa."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM faqs WHERE empresa_id = ? AND id = ?",
            (empresa_id, faq_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def limpar_faqs(empresa_id: int) -> int:
    """Remove todas as FAQs da empresa e retorna a quantidade removida."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM faqs WHERE empresa_id = ?",
            (empresa_id,),
        )
        await db.commit()
        return cursor.rowcount


async def excluir_empresa_com_dados(empresa_id: int):
    """Remove empresa, documentos e histórico associados."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM conversas WHERE empresa_id = ?", (empresa_id,))
        await db.execute("DELETE FROM faqs WHERE empresa_id = ?", (empresa_id,))
        await db.execute("DELETE FROM documentos WHERE empresa_id = ?", (empresa_id,))
        await db.execute("DELETE FROM empresas WHERE id = ?", (empresa_id,))
        await db.commit()
