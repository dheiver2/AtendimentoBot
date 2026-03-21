"""Handlers de upload e gestão de documentos."""
import logging
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import (
    excluir_documento,
    listar_documentos,
    obter_documento_por_id,
    registrar_documento,
)
from config import PDFS_DIR
from document_processor import (
    arquivo_suportado,
    listar_formatos_suportados,
    processar_documento,
    processar_documento_salvo,
)
from rate_limiter import limiter_upload, verificar_rate_limit
from validators import InputValidationError, MAX_DOCUMENTOS_POR_EMPRESA
from vector_store import adicionar_documentos, substituir_documentos

from .common import (
    AGUARDANDO_DOCUMENTO,
    _editar_ou_responder,
    _obter_empresa_admin_ou_responder,
)

logger = logging.getLogger(__name__)


def _caminho_documento(empresa_id: int, nome_arquivo: str) -> str:
    """Retorna o caminho absoluto do documento salvo no disco."""
    return os.path.join(PDFS_DIR, str(empresa_id), nome_arquivo)


def _rotulo_documento(nome_arquivo: str, indice: int) -> str:
    """Gera um rótulo curto para um documento na interface."""
    extensao = os.path.splitext(nome_arquivo)[1].lower()
    base = os.path.splitext(nome_arquivo)[0]
    if len(base) > 18:
        base = f"{base[:15]}..."
    return f"{indice}. {base}{extensao}"


def _teclado_documentos(documentos: list[dict]) -> InlineKeyboardMarkup:
    """Retorna o teclado inline de gestão da base de conhecimento."""
    botoes = [
        [
            InlineKeyboardButton("📄 Upload", callback_data="painel_upload"),
            InlineKeyboardButton("🔁 Reindexar Base", callback_data="docs_reindexar"),
        ],
        [
            InlineKeyboardButton("🔄 Atualizar", callback_data="docs_refresh"),
            InlineKeyboardButton("⬅️ Painel", callback_data="docs_painel"),
        ],
    ]

    for indice, documento in enumerate(documentos, 1):
        rotulo = _rotulo_documento(documento["nome_arquivo"], indice)
        botoes.append(
            [
                InlineKeyboardButton(f"🔄 {rotulo}", callback_data=f"docs_reprocessar:{documento['id']}"),
                InlineKeyboardButton(f"🗑 {indice}", callback_data=f"docs_excluir:{documento['id']}"),
            ]
        )

    return InlineKeyboardMarkup(botoes)


def _resumo_reindexacao(quantidade_processada: int, avisos: list[str]) -> str:
    """Formata o resumo de uma reindexação para o usuário."""
    linhas = [f"📊 Base atualizada com {quantidade_processada} documento(s) válido(s)."]
    if avisos:
        linhas.append("")
        linhas.append("⚠️ Avisos:")
        for aviso in avisos[:3]:
            linhas.append(f"- {aviso}")
        if len(avisos) > 3:
            linhas.append(f"- ... e mais {len(avisos) - 3} aviso(s).")
    return "\n".join(linhas)


async def _reindexar_base_empresa(empresa_id: int) -> tuple[int, list[str]]:
    """Reconstrói o índice vetorial da empresa a partir dos documentos salvos."""
    documentos = await listar_documentos(empresa_id)
    documentos_processados: list[tuple[list[str], dict]] = []
    avisos: list[str] = []

    for documento in documentos:
        caminho = _caminho_documento(empresa_id, documento["nome_arquivo"])
        if not os.path.exists(caminho):
            avisos.append(f"{documento['nome_arquivo']}: arquivo não encontrado no disco.")
            continue

        try:
            chunks = processar_documento_salvo(caminho)
        except Exception as e:
            avisos.append(f"{documento['nome_arquivo']}: {e}")
            continue

        documentos_processados.append(
            (
                chunks,
                {
                    "arquivo": documento["nome_arquivo"],
                    "documento_id": documento["id"],
                },
            )
        )

    substituir_documentos(empresa_id, documentos_processados)
    return len(documentos_processados), avisos


async def cmd_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o fluxo de upload de documentos."""
    mensagem = update.effective_message
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return ConversationHandler.END

    context.user_data["empresa_upload_id"] = empresa["id"]
    formatos = listar_formatos_suportados()
    await mensagem.reply_text(
        "📄 Envio de documentos\n\n"
        "Envie seus arquivos agora. Você pode enviar vários, um de cada vez.\n"
        f"Formatos aceitos: {formatos}.\n"
        "Quando terminar, envie /pronto.\n"
        "Se preferir, também pode mandar documentos diretamente fora deste modo e eles serão processados.",
    )
    return AGUARDANDO_DOCUMENTO


async def _processar_documento_enviado(
    update: Update,
    empresa_id: int,
    modo_upload: bool,
):
    """Processa um documento enviado e responde ao usuário."""
    documento = update.message.document
    nome_arquivo = documento.file_name or ""

    if not documento or not arquivo_suportado(nome_arquivo):
        await update.message.reply_text(
            f"⚠️ Formato não suportado. Envie um destes formatos: {listar_formatos_suportados()}."
        )
        return AGUARDANDO_DOCUMENTO if modo_upload else None

    # Rate limiting
    rate_msg = verificar_rate_limit(limiter_upload, update.effective_user.id)
    if rate_msg:
        await update.message.reply_text(rate_msg)
        return AGUARDANDO_DOCUMENTO if modo_upload else None

    # Verificar limite de documentos por empresa
    docs_existentes = await listar_documentos(empresa_id)
    if len(docs_existentes) >= MAX_DOCUMENTOS_POR_EMPRESA:
        await update.message.reply_text(
            f"⚠️ Limite de {MAX_DOCUMENTOS_POR_EMPRESA} documentos por empresa atingido.\n"
            "Exclua documentos antigos com /documentos antes de enviar novos."
        )
        return AGUARDANDO_DOCUMENTO if modo_upload else None

    await update.message.reply_text("⏳ Processando documento...")

    try:
        arquivo = await documento.get_file()
        conteudo = await arquivo.download_as_bytearray()
        arquivo_existia = os.path.exists(_caminho_documento(empresa_id, nome_arquivo))

        chunks = processar_documento(empresa_id, nome_arquivo, bytes(conteudo))
        await registrar_documento(empresa_id, nome_arquivo)

        if arquivo_existia:
            quantidade_processada, avisos = await _reindexar_base_empresa(empresa_id)
            resumo = _resumo_reindexacao(quantidade_processada, avisos)
            mensagem_sucesso = (
                f"✅ {nome_arquivo} atualizado com sucesso!\n"
                f"{resumo}\n\n"
                + (
                    "Envie mais arquivos ou /pronto para finalizar."
                    if modo_upload
                    else "Você pode enviar mais documentos ou já testar o agente com uma pergunta."
                )
            )
            await update.message.reply_text(mensagem_sucesso)
            return AGUARDANDO_DOCUMENTO if modo_upload else None

        adicionar_documentos(empresa_id, chunks, {"arquivo": nome_arquivo})

        mensagem_sucesso = (
            f"✅ {nome_arquivo} processado com sucesso!\n"
            f"📊 {len(chunks)} trechos indexados.\n\n"
            + (
                "Envie mais arquivos ou /pronto para finalizar."
                if modo_upload
                else "Você pode enviar mais documentos ou já testar o agente com uma pergunta."
            )
        )

        await update.message.reply_text(mensagem_sucesso)
    except (ValueError, InputValidationError) as e:
        await update.message.reply_text(f"⚠️ {e}")
    except Exception as e:
        logger.error("Erro ao processar documento: %s", e, exc_info=True)
        await update.message.reply_text("❌ Erro ao processar o documento. Tente novamente.")

    return AGUARDANDO_DOCUMENTO if modo_upload else None


async def receber_documento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe e processa um documento no fluxo guiado de upload."""
    empresa_id = context.user_data.get("empresa_upload_id")
    if not empresa_id:
        await update.message.reply_text("❌ Erro interno. Use /upload novamente.")
        return ConversationHandler.END

    return await _processar_documento_enviado(update, empresa_id, modo_upload=True)


async def receber_documento_direto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa documentos enviados diretamente no chat, sem exigir /upload."""
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return

    await _processar_documento_enviado(update, empresa["id"], modo_upload=False)


async def finalizar_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finaliza o fluxo de upload."""
    context.user_data.pop("empresa_upload_id", None)
    await update.message.reply_text(
        "✅ **Upload concluído!**\n\n"
        "Seus documentos foram indexados e o bot já pode responder perguntas baseadas neles.\n"
        "Você pode voltar a usar /upload a qualquer momento para adicionar novos arquivos.\n"
        "Use /status para ver o estado do seu bot ou envie uma pergunta para testar.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cmd_documentos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra a gestão da base de conhecimento da empresa."""
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return

    docs = await listar_documentos(empresa["id"])
    if not docs:
        await _editar_ou_responder(
            update,
            (
                f"📭 Base de conhecimento — {empresa['nome']}\n\n"
                "Nenhum documento enviado ainda.\n"
                "Use /upload ou envie arquivos diretamente neste chat para começar."
            ),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("📄 Upload", callback_data="painel_upload"),
                        InlineKeyboardButton("⬅️ Painel", callback_data="docs_painel"),
                    ]
                ]
            ),
        )
        return

    linhas = [
        f"📚 Base de conhecimento — {empresa['nome']}\n",
        "Use os botões abaixo para reprocessar, excluir ou reindexar a base.\n",
    ]
    for i, doc in enumerate(docs, 1):
        linhas.append(f"{i}. {doc['nome_arquivo']} — {doc['carregado_em']}")

    await _editar_ou_responder(
        update,
        "\n".join(linhas),
        reply_markup=_teclado_documentos(docs),
    )


async def docs_painel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Volta para o painel principal a partir da gestão da base."""
    await update.callback_query.answer()
    from .panel import cmd_painel
    await cmd_painel(update, context)


async def docs_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Atualiza a visão da base de conhecimento."""
    await update.callback_query.answer()
    await cmd_documentos(update, context)


async def docs_reindexar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reconstrói toda a base de conhecimento da empresa."""
    query = update.callback_query
    await query.answer()

    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return

    try:
        quantidade_processada, avisos = await _reindexar_base_empresa(empresa["id"])
        await query.message.reply_text(
            "✅ Base reindexada com sucesso.\n"
            f"{_resumo_reindexacao(quantidade_processada, avisos)}"
        )
        await cmd_documentos(update, context)
    except Exception as e:
        logger.error("Erro ao reindexar base da empresa %s: %s", empresa["id"], e, exc_info=True)
        await query.message.reply_text("❌ Não foi possível reindexar a base agora. Tente novamente.")


async def docs_reprocessar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reprocessa um documento e reconstrói a base da empresa."""
    query = update.callback_query
    await query.answer()

    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return

    documento_id = int(query.data.split(":", 1)[1])
    documento = await obter_documento_por_id(empresa["id"], documento_id)
    if not documento:
        await query.message.reply_text("⚠️ Documento não encontrado.")
        await cmd_documentos(update, context)
        return

    caminho = _caminho_documento(empresa["id"], documento["nome_arquivo"])
    if not os.path.exists(caminho):
        await query.message.reply_text("⚠️ O arquivo não foi encontrado no disco.")
        await cmd_documentos(update, context)
        return

    try:
        quantidade_processada, avisos = await _reindexar_base_empresa(empresa["id"])
        await query.message.reply_text(
            f"✅ Documento reprocessado: {documento['nome_arquivo']}\n"
            f"{_resumo_reindexacao(quantidade_processada, avisos)}"
        )
        await cmd_documentos(update, context)
    except Exception as e:
        logger.error("Erro ao reprocessar documento %s: %s", documento_id, e, exc_info=True)
        await query.message.reply_text("❌ Não foi possível reprocessar esse documento agora. Tente novamente.")


async def docs_excluir_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exclui um documento da base e reconstrói o índice da empresa."""
    query = update.callback_query
    await query.answer()

    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return

    documento_id = int(query.data.split(":", 1)[1])
    documento = await obter_documento_por_id(empresa["id"], documento_id)
    if not documento:
        await query.message.reply_text("⚠️ Documento não encontrado.")
        await cmd_documentos(update, context)
        return

    caminho = _caminho_documento(empresa["id"], documento["nome_arquivo"])

    try:
        if os.path.exists(caminho):
            os.remove(caminho)

        removido = await excluir_documento(empresa["id"], documento_id)
        if not removido:
            await query.message.reply_text("⚠️ Documento não encontrado.")
            await cmd_documentos(update, context)
            return

        quantidade_processada, avisos = await _reindexar_base_empresa(empresa["id"])
        await query.message.reply_text(
            f"🗑 Documento excluído: {documento['nome_arquivo']}\n"
            f"{_resumo_reindexacao(quantidade_processada, avisos)}"
        )
        await cmd_documentos(update, context)
    except Exception as e:
        logger.error("Erro ao excluir documento %s: %s", documento_id, e, exc_info=True)
        await query.message.reply_text("❌ Não foi possível excluir esse documento agora. Tente novamente.")
