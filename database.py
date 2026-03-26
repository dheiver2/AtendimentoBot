import json
import secrets
import sqlite3
from typing import Any

import aiosqlite

from config import DB_PATH


def _erro_tabela_inexistente(exc: sqlite3.OperationalError, tabela: str) -> bool:
    return f"no such table: {tabela}".lower() in str(exc).lower()


def _coerce_lastrowid(valor: int | None) -> int:
    """Normaliza IDs gerados pelo SQLite para inteiro válido."""
    if valor is None:
        raise RuntimeError("Falha ao obter o ID gerado pelo banco.")
    return valor


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

    if "admin_link_token" not in colunas:
        await db.execute("ALTER TABLE empresas ADD COLUMN admin_link_token TEXT")

    if "instruction_template_key" not in colunas:
        await db.execute("ALTER TABLE empresas ADD COLUMN instruction_template_key TEXT")

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
                (await _gerar_link_token_unico(db, "link_token"), row[0]),
            )

    if "admin_link_token" in colunas:
        cursor = await db.execute("""
            SELECT id
            FROM empresas
            WHERE admin_link_token IS NULL OR TRIM(admin_link_token) = ''
        """)
        rows = await cursor.fetchall()
        for row in rows:
            await db.execute(
                "UPDATE empresas SET admin_link_token = ? WHERE id = ?",
                (await _gerar_link_token_unico(db, "admin_link_token"), row[0]),
            )

    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_empresas_telegram_user_id
        ON empresas(telegram_user_id)
    """)
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_empresas_link_token
        ON empresas(link_token)
    """)
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_empresas_admin_link_token
        ON empresas(admin_link_token)
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
    await db.execute("ALTER TABLE clientes_empresa RENAME TO clientes_empresa_migracao")
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
        FROM clientes_empresa_migracao
        """
    )
    await db.execute("DROP TABLE clientes_empresa_migracao")


async def _garantir_tabela_clientes_empresa(db: aiosqlite.Connection):
    """Garante a tabela de vínculo entre clientes e empresa/admin."""
    await _criar_tabela_clientes_empresa(db)
    colunas = await _obter_colunas_tabela(db, "clientes_empresa")

    colunas_esperadas = {"id", "empresa_id", "cliente_telegram_user_id", "criado_em"}
    if not colunas_esperadas.issubset(colunas):
        await _recriar_tabela_clientes_empresa(db, colunas)


async def _garantir_tabela_empresa_admins(db: aiosqlite.Connection):
    """Garante a tabela de vínculo entre empresas e admins adicionais."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS empresa_admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            usuario_id INTEGER NOT NULL UNIQUE,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id)
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_empresa_admins_empresa_id
        ON empresa_admins(empresa_id)
    """)
    await db.execute("""
        INSERT OR IGNORE INTO empresa_admins (empresa_id, usuario_id)
        SELECT id, telegram_user_id
        FROM empresas
        WHERE telegram_user_id IS NOT NULL
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


def _gerar_link_token() -> str:
    """Gera um token curto e seguro para links do bot."""
    return secrets.token_urlsafe(16)


async def _gerar_link_token_unico(
    db: aiosqlite.Connection,
    coluna: str = "link_token",
) -> str:
    """Gera um token único para a coluna informada da tabela empresas."""
    while True:
        token = _gerar_link_token()
        cursor = await db.execute(
            f"SELECT 1 FROM empresas WHERE {coluna} = ? LIMIT 1",
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
        await _garantir_colunas_empresas(db)
        await _garantir_tabela_clientes_empresa(db)
        await _garantir_tabela_empresa_admins(db)
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
            CREATE INDEX IF NOT EXISTS idx_conversas_empresa_usuario_id
            ON conversas(empresa_id, usuario_telegram_id, id DESC)
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS feedback_respostas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversa_id INTEGER NOT NULL UNIQUE,
                empresa_id INTEGER NOT NULL,
                usuario_telegram_id INTEGER NOT NULL,
                canal TEXT NOT NULL DEFAULT 'telegram',
                resposta_bot TEXT NOT NULL DEFAULT '',
                avaliacao INTEGER DEFAULT NULL,
                comentario TEXT DEFAULT '',
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversa_id) REFERENCES conversas(id),
                FOREIGN KEY (empresa_id) REFERENCES empresas(id)
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_feedback_respostas_empresa_criado
            ON feedback_respostas(empresa_id, criado_em)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_sessions (
                sender TEXT PRIMARY KEY,
                state TEXT DEFAULT NULL,
                data_json TEXT NOT NULL DEFAULT '{}',
                identidade_visual_enviada INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_whatsapp_sessions_updated_at
            ON whatsapp_sessions(updated_at)
        """)
        await db.commit()


async def criar_empresa(nome: str, telegram_user_id: int) -> int:
    """Cria uma nova empresa e retorna o ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        link_token = await _gerar_link_token_unico(db, "link_token")
        admin_link_token = await _gerar_link_token_unico(db, "admin_link_token")
        cursor = await db.execute(
            """
            INSERT INTO empresas (nome, telegram_user_id, link_token, admin_link_token)
            VALUES (?, ?, ?, ?)
            """,
            (nome, telegram_user_id, link_token, admin_link_token),
        )
        empresa_id = _coerce_lastrowid(cursor.lastrowid)
        await db.execute(
            "INSERT OR IGNORE INTO empresa_admins (empresa_id, usuario_id) VALUES (?, ?)",
            (empresa_id, telegram_user_id),
        )
        await db.commit()
        return empresa_id


async def obter_empresa_por_admin(telegram_user_id: int) -> dict | None:
    """Busca empresa pelo ID do admin, incluindo admins vinculados por link."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT *
            FROM empresas e
            WHERE e.telegram_user_id = ?
               OR EXISTS (
                    SELECT 1
                    FROM empresa_admins a
                    WHERE a.empresa_id = e.id AND a.usuario_id = ?
               )
            ORDER BY CASE WHEN e.telegram_user_id = ? THEN 0 ELSE 1 END, e.id ASC
            LIMIT 1
            """,
            (telegram_user_id, telegram_user_id, telegram_user_id),
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None


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


async def listar_empresas() -> list[dict]:
    """Lista todas as empresas cadastradas."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM empresas ORDER BY id ASC",
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


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


async def obter_empresa_por_admin_link_token(admin_link_token: str) -> dict | None:
    """Busca empresa pelo token de acesso administrativo."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM empresas WHERE admin_link_token = ?",
            (admin_link_token,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def adicionar_admin_empresa(empresa_id: int, usuario_id: int):
    """Vincula um admin adicional à empresa e remove eventual vínculo como cliente."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM clientes_empresa WHERE cliente_telegram_user_id = ?",
            (usuario_id,),
        )
        await db.execute(
            "INSERT OR IGNORE INTO empresa_admins (empresa_id, usuario_id) VALUES (?, ?)",
            (empresa_id, usuario_id),
        )
        await db.commit()


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
        return bool(cursor.rowcount > 0)


async def obter_empresa_do_usuario(telegram_user_id: int) -> dict | None:
    """Resolve a empresa do usuário, priorizando o papel de admin."""
    empresa = await obter_empresa_por_admin(telegram_user_id)
    if empresa:
        empresa["_usuario_admin"] = True
        return empresa

    empresa = await obter_empresa_do_cliente(telegram_user_id)
    if empresa:
        empresa["_usuario_admin"] = False
        return empresa
    return None


async def usuario_e_admin_da_empresa(empresa_id: int, usuario_id: int) -> bool:
    """Retorna se o usuário é admin da empresa informada."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT 1
            FROM empresas e
            WHERE e.id = ?
              AND (
                    e.telegram_user_id = ?
                    OR EXISTS (
                        SELECT 1
                        FROM empresa_admins a
                        WHERE a.empresa_id = e.id AND a.usuario_id = ?
                    )
              )
            LIMIT 1
            """,
            (empresa_id, usuario_id, usuario_id),
        )
        return bool(await cursor.fetchone())


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
            SELECT usuario_id
            FROM empresa_admins
            WHERE usuario_id IS NOT NULL
            ORDER BY usuario_id
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
        "instruction_template_key",
        "ativo",
        "horario_atendimento",
        "fallback_contato",
    }
    campos = {k: v for k, v in kwargs.items() if k in campos_permitidos}
    if "instrucoes" in campos and "instruction_template_key" not in kwargs:
        campos["instruction_template_key"] = None
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
            return int(existente["id"])

        cursor = await db.execute(
            "INSERT INTO documentos (empresa_id, nome_arquivo) VALUES (?, ?)",
            (empresa_id, nome_arquivo),
        )
        await db.commit()
        return _coerce_lastrowid(cursor.lastrowid)


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
        return bool(cursor.rowcount > 0)


async def registrar_conversa(
    empresa_id: int,
    usuario_telegram_id: int,
    mensagem: str,
    resposta: str,
) -> int:
    """Registra uma conversa no histórico."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO conversas (empresa_id, usuario_telegram_id, mensagem_usuario, resposta_bot) VALUES (?, ?, ?, ?)",
            (empresa_id, usuario_telegram_id, mensagem, resposta),
        )
        await db.commit()
        return _coerce_lastrowid(cursor.lastrowid)


async def listar_conversas_recentes(
    empresa_id: int,
    usuario_telegram_id: int,
    limite: int = 6,
) -> list[dict]:
    """Lista os turnos mais recentes do usuário na empresa, em ordem cronológica."""
    limite_normalizado = max(1, min(int(limite), 12))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT *
            FROM conversas
            WHERE empresa_id = ?
              AND usuario_telegram_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (empresa_id, usuario_telegram_id, limite_normalizado),
        )
        rows = [dict(row) for row in await cursor.fetchall()]

    rows.reverse()
    return rows


async def criar_feedback_resposta(
    conversa_id: int,
    empresa_id: int,
    usuario_telegram_id: int,
    *,
    canal: str,
    resposta_bot: str,
) -> int:
    """Cria o registro de feedback associado a uma resposta do bot."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT OR IGNORE INTO feedback_respostas (
                conversa_id,
                empresa_id,
                usuario_telegram_id,
                canal,
                resposta_bot
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (conversa_id, empresa_id, usuario_telegram_id, canal, resposta_bot),
        )
        await db.commit()
        if cursor.rowcount and cursor.lastrowid is not None:
            return _coerce_lastrowid(cursor.lastrowid)

        cursor = await db.execute(
            "SELECT id FROM feedback_respostas WHERE conversa_id = ?",
            (conversa_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise RuntimeError("Falha ao obter o feedback persistido.")
        return int(row[0])


async def registrar_feedback_resposta(
    feedback_id: int,
    avaliacao: int,
    comentario: str = "",
) -> bool:
    """Registra o feedback positivo/negativo da resposta, apenas uma vez."""
    if avaliacao not in {-1, 1}:
        raise ValueError("Avaliacao invalida. Use 1 para positivo ou -1 para negativo.")

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            UPDATE feedback_respostas
            SET avaliacao = ?,
                comentario = ?,
                atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
              AND avaliacao IS NULL
            """,
            (avaliacao, comentario, feedback_id),
        )
        await db.commit()
        return bool(cursor.rowcount > 0)


async def obter_feedback_resposta(feedback_id: int) -> dict | None:
    """Busca um feedback específico pelo ID interno."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM feedback_respostas WHERE id = ?",
            (feedback_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def salvar_sessao_whatsapp(
    sender: str,
    *,
    state: str | None,
    data: dict[str, Any],
    identidade_visual_enviada: bool,
    updated_at: float,
) -> None:
    """Persiste a sessão conversacional do WhatsApp para sobreviver a reinícios."""
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO whatsapp_sessions (
                    sender,
                    state,
                    data_json,
                    identidade_visual_enviada,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(sender) DO UPDATE SET
                    state = excluded.state,
                    data_json = excluded.data_json,
                    identidade_visual_enviada = excluded.identidade_visual_enviada,
                    updated_at = excluded.updated_at
                """,
                (sender, state, payload, int(identidade_visual_enviada), updated_at),
            )
            await db.commit()
    except sqlite3.OperationalError as exc:
        if _erro_tabela_inexistente(exc, "whatsapp_sessions"):
            return
        raise


async def obter_sessao_whatsapp(sender: str) -> dict | None:
    """Carrega uma sessão persistida do WhatsApp."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM whatsapp_sessions WHERE sender = ?",
                (sender,),
            )
            row = await cursor.fetchone()
            if not row:
                return None

            sessao = dict(row)
            try:
                sessao["data"] = json.loads(sessao.pop("data_json") or "{}")
            except json.JSONDecodeError:
                sessao["data"] = {}
            return sessao
    except sqlite3.OperationalError as exc:
        if _erro_tabela_inexistente(exc, "whatsapp_sessions"):
            return None
        raise


async def remover_sessao_whatsapp(sender: str) -> bool:
    """Remove uma sessão persistida do WhatsApp."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "DELETE FROM whatsapp_sessions WHERE sender = ?",
                (sender,),
            )
            await db.commit()
            return bool(cursor.rowcount > 0)
    except sqlite3.OperationalError as exc:
        if _erro_tabela_inexistente(exc, "whatsapp_sessions"):
            return False
        raise


async def limpar_sessoes_whatsapp_expiradas(updated_before: float) -> int:
    """Limpa sessões persistidas que já passaram do TTL configurado."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "DELETE FROM whatsapp_sessions WHERE updated_at < ?",
                (updated_before,),
            )
            await db.commit()
            return int(cursor.rowcount)
    except sqlite3.OperationalError as exc:
        if _erro_tabela_inexistente(exc, "whatsapp_sessions"):
            return 0
        raise


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
        return _coerce_lastrowid(cursor.lastrowid)


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
        return bool(cursor.rowcount > 0)


async def limpar_faqs(empresa_id: int) -> int:
    """Remove todas as FAQs da empresa e retorna a quantidade removida."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM faqs WHERE empresa_id = ?",
            (empresa_id,),
        )
        await db.commit()
        return int(cursor.rowcount)


async def excluir_empresa_com_dados(empresa_id: int):
    """Remove empresa, documentos e histórico associados."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM metricas_atendimento WHERE empresa_id = ?", (empresa_id,))
        await db.execute("DELETE FROM feedback_respostas WHERE empresa_id = ?", (empresa_id,))
        await db.execute("DELETE FROM conversas WHERE empresa_id = ?", (empresa_id,))
        await db.execute("DELETE FROM faqs WHERE empresa_id = ?", (empresa_id,))
        await db.execute("DELETE FROM documentos WHERE empresa_id = ?", (empresa_id,))
        await db.execute("DELETE FROM clientes_empresa WHERE empresa_id = ?", (empresa_id,))
        await db.execute("DELETE FROM empresa_admins WHERE empresa_id = ?", (empresa_id,))
        await db.execute("DELETE FROM empresas WHERE id = ?", (empresa_id,))
        await db.commit()
