"""Pacote de handlers do bot — exporta get_handlers() para o main.py."""
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .agent import interagir_com_agente
from .common import (
    AGUARDANDO_CONFIRMACAO_REGISTRO,
    AGUARDANDO_CONFIRMACAO_RESET,
    AGUARDANDO_DOCUMENTO,
    AGUARDANDO_FALLBACK,
    AGUARDANDO_FAQ_PERGUNTA,
    AGUARDANDO_FAQ_RESPOSTA,
    AGUARDANDO_HORARIO,
    AGUARDANDO_IMAGEM_BOT,
    AGUARDANDO_INSTRUCOES,
    AGUARDANDO_NOME_BOT,
    AGUARDANDO_NOME_EMPRESA,
    AGUARDANDO_SAUDACAO,
    EDITANDO_CAMPO,
)
from .documents import (
    cmd_documentos,
    cmd_upload,
    docs_excluir_callback,
    docs_refresh_callback,
    docs_reindexar_callback,
    docs_reprocessar_callback,
    docs_painel_callback,
    finalizar_upload,
    receber_documento,
    receber_documento_direto,
)
from .faq import (
    cmd_faq,
    faq_add_callback,
    faq_excluir_callback,
    faq_limpar_callback,
    faq_painel_callback,
    faq_refresh_callback,
    receber_faq_pergunta,
    receber_faq_resposta,
)
from .images import cmd_imagem, receber_imagem_bot
from .onboarding import (
    cancelar_registro,
    cmd_registrar,
    cmd_reset,
    cmd_sair,
    cmd_start,
    confirmar_registro_callback,
    pular_instrucoes,
    receber_instrucoes,
    receber_nome_bot,
    receber_nome_empresa,
    receber_saudacao,
    recomecar_registro_callback,
    reset_cancelar_callback,
    reset_confirmar_callback,
)
from .panel import (
    cmd_ajuda,
    cmd_link,
    cmd_painel,
    cmd_status,
    painel_ajuda_callback,
    painel_ativo_toggle_callback,
    painel_documentos_callback,
    painel_editar_callback,
    painel_fallback_callback,
    painel_faq_callback,
    painel_horario_callback,
    painel_imagem_callback,
    painel_refresh_callback,
    painel_reset_callback,
    painel_status_callback,
    painel_upload_callback,
)
from .settings import (
    cmd_ativar,
    cmd_editar,
    cmd_fallback,
    cmd_horario,
    cmd_pausar,
    editar_campo_callback,
    receber_fallback,
    receber_horario,
    receber_valor_editado,
)


def get_handlers() -> list:
    """Retorna todos os handlers do bot."""

    # ConversationHandler para onboarding da empresa do usuário
    registro_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CommandHandler("registrar", cmd_registrar),
            CommandHandler("reset", cmd_reset),
            CallbackQueryHandler(painel_reset_callback, pattern="^painel_reset$"),
        ],
        states={
            AGUARDANDO_NOME_EMPRESA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome_empresa)],
            AGUARDANDO_NOME_BOT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome_bot)],
            AGUARDANDO_SAUDACAO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_saudacao)],
            AGUARDANDO_INSTRUCOES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_instrucoes),
                CommandHandler("pular", pular_instrucoes),
            ],
            AGUARDANDO_CONFIRMACAO_REGISTRO: [
                CallbackQueryHandler(confirmar_registro_callback, pattern="^registro_confirmar$"),
                CallbackQueryHandler(recomecar_registro_callback, pattern="^registro_recomecar$"),
            ],
            AGUARDANDO_CONFIRMACAO_RESET: [
                CallbackQueryHandler(reset_confirmar_callback, pattern="^reset_confirmar$"),
                CallbackQueryHandler(reset_cancelar_callback, pattern="^reset_cancelar$"),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar_registro)],
        allow_reentry=True,
    )

    # ConversationHandler para upload de documentos
    upload_handler = ConversationHandler(
        entry_points=[
            CommandHandler("upload", cmd_upload),
            CallbackQueryHandler(painel_upload_callback, pattern="^painel_upload$"),
        ],
        states={
            AGUARDANDO_DOCUMENTO: [
                MessageHandler(filters.Document.ALL, receber_documento),
                CommandHandler("pronto", finalizar_upload),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar_registro)],
        allow_reentry=True,
    )

    # ConversationHandler para a imagem própria do agente
    imagem_handler = ConversationHandler(
        entry_points=[
            CommandHandler("imagem", cmd_imagem),
            CallbackQueryHandler(painel_imagem_callback, pattern="^painel_imagem$"),
        ],
        states={
            AGUARDANDO_IMAGEM_BOT: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receber_imagem_bot),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar_registro)],
        allow_reentry=True,
    )

    autonomia_handler = ConversationHandler(
        entry_points=[
            CommandHandler("horario", cmd_horario),
            CommandHandler("fallback", cmd_fallback),
            CommandHandler("faq", cmd_faq),
            CallbackQueryHandler(painel_horario_callback, pattern="^painel_horario$"),
            CallbackQueryHandler(painel_fallback_callback, pattern="^painel_fallback$"),
            CallbackQueryHandler(painel_faq_callback, pattern="^painel_faq$"),
            CallbackQueryHandler(faq_add_callback, pattern="^faq_add$"),
        ],
        states={
            AGUARDANDO_HORARIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_horario)],
            AGUARDANDO_FALLBACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_fallback)],
            AGUARDANDO_FAQ_PERGUNTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_faq_pergunta)],
            AGUARDANDO_FAQ_RESPOSTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_faq_resposta)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar_registro)],
        allow_reentry=True,
    )

    # ConversationHandler para edição
    editar_handler = ConversationHandler(
        entry_points=[
            CommandHandler("editar", cmd_editar),
            CallbackQueryHandler(painel_editar_callback, pattern="^painel_editar$"),
        ],
        states={
            EDITANDO_CAMPO: [
                CallbackQueryHandler(editar_campo_callback, pattern="^editar_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_valor_editado),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar_registro)],
    )

    return [
        CommandHandler("ajuda", cmd_ajuda),
        CommandHandler("link", cmd_link),
        CommandHandler("painel", cmd_painel),
        CommandHandler("documentos", cmd_documentos),
        CommandHandler("status", cmd_status),
        CommandHandler("pausar", cmd_pausar),
        CommandHandler("ativar", cmd_ativar),
        CommandHandler("sair", cmd_sair),
        CallbackQueryHandler(painel_refresh_callback, pattern="^painel_refresh$"),
        CallbackQueryHandler(painel_documentos_callback, pattern="^painel_documentos$"),
        CallbackQueryHandler(painel_status_callback, pattern="^painel_status$"),
        CallbackQueryHandler(painel_ajuda_callback, pattern="^painel_ajuda$"),
        CallbackQueryHandler(painel_ativo_toggle_callback, pattern="^painel_ativo_toggle$"),
        CallbackQueryHandler(docs_painel_callback, pattern="^docs_painel$"),
        CallbackQueryHandler(docs_refresh_callback, pattern="^docs_refresh$"),
        CallbackQueryHandler(docs_reindexar_callback, pattern="^docs_reindexar$"),
        CallbackQueryHandler(docs_reprocessar_callback, pattern=r"^docs_reprocessar:\d+$"),
        CallbackQueryHandler(docs_excluir_callback, pattern=r"^docs_excluir:\d+$"),
        CallbackQueryHandler(faq_painel_callback, pattern="^faq_painel$"),
        CallbackQueryHandler(faq_refresh_callback, pattern="^faq_refresh$"),
        CallbackQueryHandler(faq_limpar_callback, pattern="^faq_limpar$"),
        CallbackQueryHandler(faq_excluir_callback, pattern=r"^faq_excluir:\d+$"),
        registro_handler,
        upload_handler,
        imagem_handler,
        autonomia_handler,
        editar_handler,
        MessageHandler(filters.Document.ALL, receber_documento_direto),
        # Handler de interação com o agente — deve ser o último
        MessageHandler(filters.TEXT & ~filters.COMMAND, interagir_com_agente),
    ]
