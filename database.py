import secrets

import aiosqlite
from config import DB_PATH


async def _obter_colunas_tabela(db: aiosqlite.Connection, nome_tabela: str) -> set[str]:
    """Retorna o conjunto de colunas atuais de uma tabela."""
    cursor = await db.execute(f"PRAGMA table_info({nome_tabela})")
    rows = await cursor.fetchall()
    return {row[1] for row in rows}


async def _obter_colunas_empresas(db: aiosqlite.Connection) -> set[str]:
    """Retorna o conjunto de colunas atuais da tabela empresas."""
    return await _obter_colunas_tabela(db, "empresas")


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

    if "link_token" not in colunas:
        await db.execute("ALTER TABLE empresas ADD COLUMN link_token TEXT")

    colunas = await _obter_colunas_empresas(db)
    if "link_token" in colunas:
        cursor = await db.execute("""
            SELECT id
            FROM empresas
            WHERE link_token IS NULL OR TRIM(link_token) = ''
        """)
        rows = await cursor.fetchall()
        for row in rows:
            await db.execute(
                "UPDATE empresas SET link_token = ? WHERE id = ?",
                (await _gerar_link_token_unico(db), row[0]),
            )

    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_empresas_telegram_user_id
        ON empresas(telegram_user_id)
    """)
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_empresas_link_token
        ON empresas(link_token)
    """)


async def _criar_tabela_clientes_empresa(db: aiosqlite.Connection):
    """Cria a tabela de vínculo entre clientes e empresa com o schema atual."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS clientes_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            cliente_telegram_user_id INTEGER NOT NULL UNIQUE,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id)
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_clientes_empresa_empresa_id
        ON clientes_empresa(empresa_id)
    """)


async def _recriar_tabela_clientes_empresa(db: aiosqlite.Connection, colunas_existentes: set[str]):
    """Recria a tabela de clientes preservando dados de schemas antigos."""
    await db.execute("ALTER TABLE clientes_empresa RENAME TO clientes_empresa_legado")
    await _criar_tabela_clientes_empresa(db)

    coluna_usuario = (
        "cliente_telegram_user_id"
        if "cliente_telegram_user_id" in colunas_existentes
        else "telegram_user_id"
    )
    coluna_data = (
        "criado_em"
        if "criado_em" in colunas_existentes
        else "vinculado_em"
        if "vinculado_em" in colunas_existentes
        else None
    )

    colunas_destino = ["empresa_id", "cliente_telegram_user_id"]
    colunas_origem = ["empresa_id", coluna_usuario]
    if coluna_data:
        colunas_destino.append("criado_em")
        colunas_origem.append(coluna_data)

    await db.execute(
        f"""
        INSERT OR IGNORE INTO clientes_empresa ({", ".join(colunas_destino)})
        SELECT {", ".join(colunas_origem)}
        FROM clientes_empresa_legado
        """
    )
    await db.execute("DROP TABLE clientes_empresa_legado")


async def _garantir_tabela_clientes_empresa(db: aiosqlite.Connection):
    """Garante a tabela de vínculo entre clientes e empresa/admin."""
    await _criar_tabela_clientes_empresa(db)
    colunas = await _obter_colunas_tabela(db, "clientes_empresa")

    colunas_esperadas = {"id", "empresa_id", "cliente_telegram_user_id", "criado_em"}
    if not colunas_esperadas.issubset(colunas):
        await _recriar_tabela_clientes_empresa(db, colunas)


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


def _gerar_link_token() -> str:
    """Gera um token curto e seguro para deep link do Telegram."""
    return secrets.token_urlsafe(16)


async def _gerar_link_token_unico(db: aiosqlite.Connection) -> str:
    """Gera um link token único para a tabela de empresas."""
    while True:
        token = _gerar_link_token()
        cursor = await db.execute(
            "SELECT 1 FROM empresas WHERE link_token = ? LIMIT 1",
            (token,),
        )
        if not await cursor.fetchone():
            return token


async def init_db():
    """Inicializa o banco de dados com as tabelas necessárias."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS empresas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL UNIQUE,
                link_token TEXT NOT NULL UNIQUE,
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
        await _garantir_tabela_clientes_empresa(db)
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS metricas_atendimento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                decisao TEXT DEFAULT '',
                total_segundos REAL NOT NULL,
                usou_rag INTEGER DEFAULT 0,
                cache_hit INTEGER DEFAULT 0,
                sucesso INTEGER NOT NULL DEFAULT 1,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id)
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_metricas_atendimento_empresa_criado
            ON metricas_atendimento(empresa_id, criado_em)
        """)
        await db.commit()


async def criar_empresa(nome: str, telegram_user_id: int) -> int:
    """Cria uma nova empresa e retorna o ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        link_token = await _gerar_link_token_unico(db)
        cursor = await db.execute(
            "INSERT INTO empresas (nome, telegram_user_id, link_token) VALUES (?, ?, ?)",
            (nome, telegram_user_id, link_token),
        )
        await db.commit()
        return cursor.lastrowid


async def obter_empresa_por_admin(telegram_user_id: int) -> dict | None:
    """Busca empresa pelo ID do Telegram do admin."""
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


async def obter_empresa_por_usuario(telegram_user_id: int) -> dict | None:
    """Mantém compatibilidade buscando a empresa do admin pelo usuário."""
    return await obter_empresa_por_admin(telegram_user_id)


async def obter_empresa_por_id(empresa_id: int) -> dict | None:
    """Busca empresa pelo ID interno."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM empresas WHERE id = ?",
            (empresa_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def obter_empresa_por_link_token(link_token: str) -> dict | None:
    """Busca empresa pelo token compartilhável do link Telegram."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM empresas WHERE link_token = ?",
            (link_token,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def vincular_cliente_empresa(empresa_id: int, cliente_telegram_user_id: int):
    """Vincula ou move um cliente para a empresa do admin."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id
            FROM clientes_empresa
            WHERE cliente_telegram_user_id = ?
            """,
            (cliente_telegram_user_id,),
        )
        existente = await cursor.fetchone()
        if existente:
            await db.execute(
                """
                UPDATE clientes_empresa
                SET empresa_id = ?
                WHERE cliente_telegram_user_id = ?
                """,
                (empresa_id, cliente_telegram_user_id),
            )
        else:
            await db.execute(
                """
                INSERT INTO clientes_empresa (empresa_id, cliente_telegram_user_id)
                VALUES (?, ?)
                """,
                (empresa_id, cliente_telegram_user_id),
            )
        await db.commit()


async def obter_empresa_do_cliente(cliente_telegram_user_id: int) -> dict | None:
    """Busca a empresa associada a um cliente."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT e.*
            FROM clientes_empresa c
            JOIN empresas e ON e.id = c.empresa_id
            WHERE c.cliente_telegram_user_id = ?
            """,
            (cliente_telegram_user_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def desvincular_cliente(cliente_telegram_user_id: int) -> bool:
    """Remove o vínculo de um cliente com sua empresa."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM clientes_empresa WHERE cliente_telegram_user_id = ?",
            (cliente_telegram_user_id,),
        )
        await db.commit()
        return cursor.rowcount > 0


async def obter_empresa_do_usuario(telegram_user_id: int) -> dict | None:
    """Resolve a empresa do usuário, priorizando o papel de admin."""
    empresa = await obter_empresa_por_admin(telegram_user_id)
    if empresa:
        return empresa
    return await obter_empresa_do_cliente(telegram_user_id)


async def contar_clientes_empresa(empresa_id: int) -> int:
    """Conta quantos clientes estão vinculados à empresa."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM clientes_empresa WHERE empresa_id = ?",
            (empresa_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def listar_ids_admins() -> list[int]:
    """Lista os chat IDs dos admins cadastrados."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT telegram_user_id
            FROM empresas
            WHERE telegram_user_id IS NOT NULL
            ORDER BY telegram_user_id
            """
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows if row and row[0] is not None]


async def listar_ids_clientes() -> list[int]:
    """Lista os chat IDs dos clientes vinculados a algum admin."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT cliente_telegram_user_id
            FROM clientes_empresa
            WHERE cliente_telegram_user_id IS NOT NULL
            ORDER BY cliente_telegram_user_id
            """
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows if row and row[0] is not None]


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


async def registrar_metrica_atendimento_db(
    empresa_id: int,
    decisao: str,
    total_segundos: float,
    usou_rag: bool,
    sucesso: bool,
):
    """Persiste uma métrica de atendimento concluído."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO metricas_atendimento (
                empresa_id, tipo, decisao, total_segundos, usou_rag, sucesso
            ) VALUES (?, 'atendimento', ?, ?, ?, ?)
            """,
            (empresa_id, decisao, total_segundos, int(usou_rag), int(sucesso)),
        )
        await db.commit()


async def registrar_metrica_rag_db(
    empresa_id: int,
    total_segundos: float,
    cache_hit: bool,
    sucesso: bool,
):
    """Persiste uma métrica de execução do RAG."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO metricas_atendimento (
                empresa_id, tipo, total_segundos, cache_hit, sucesso
            ) VALUES (?, 'rag', ?, ?, ?)
            """,
            (empresa_id, total_segundos, int(cache_hit), int(sucesso)),
        )
        await db.commit()


async def listar_metricas_empresa(empresa_id: int, janela_horas: int = 24) -> list[dict]:
    """Lista métricas recentes da empresa."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT *
            FROM metricas_atendimento
            WHERE empresa_id = ?
              AND criado_em >= datetime('now', ?)
            ORDER BY id DESC
            """,
            (empresa_id, f"-{janela_horas} hours"),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


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
        await db.execute("DELETE FROM metricas_atendimento WHERE empresa_id = ?", (empresa_id,))
        await db.execute("DELETE FROM conversas WHERE empresa_id = ?", (empresa_id,))
        await db.execute("DELETE FROM faqs WHERE empresa_id = ?", (empresa_id,))
        await db.execute("DELETE FROM documentos WHERE empresa_id = ?", (empresa_id,))
        await db.execute("DELETE FROM clientes_empresa WHERE empresa_id = ?", (empresa_id,))
        await db.execute("DELETE FROM empresas WHERE id = ?", (empresa_id,))
        await db.commit()
