"""Handlers do painel de gerenciamento e status."""
import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from bot_profile_photo import empresa_tem_imagem, listar_formatos_imagem_suportados
from database import (
    contar_clientes_empresa,
    listar_documentos,
    listar_faqs,
    obter_empresa_do_cliente,
    obter_empresa_por_admin,
)
from document_processor import listar_formatos_suportados
from metrics import obter_resumo_metricas_empresa
from vector_store import empresa_tem_documentos

from .common import (
    _enviar_preview_imagem_empresa,
    _obter_empresa_admin_ou_responder,
    _teclado_painel,
)

logger = logging.getLogger(__name__)


async def _formatar_bloco_metricas(empresa_id: int) -> str:
    """Resume métricas recentes do atendimento para o admin."""
    resumo = await obter_resumo_metricas_empresa(empresa_id)
    if not resumo:
        return "📈 Métricas recentes: ainda sem dados nesta execução."

    atendimento = resumo["atendimentos"]
    rag = resumo["rag"]
    decisoes = atendimento["decisoes"]
    top_decisoes = sorted(decisoes.items(), key=lambda item: (-item[1], item[0]))[:3]
    decisoes_texto = ", ".join(f"{nome}={total}" for nome, total in top_decisoes) or "sem dados"

    linhas = [
        f"📈 Métricas recentes ({resumo['janela_horas']}h, máx. 200 eventos)",
        (
            f"Atendimentos: {atendimento['total']} | "
            f"média {atendimento['media_segundos']:.2f}s | "
            f"p95 {atendimento['p95_segundos']:.2f}s | "
            f"sucesso {atendimento['taxa_sucesso'] * 100:.0f}% | "
            f"RAG {atendimento['taxa_rag'] * 100:.0f}%"
        ),
        (
            f"RAG: {rag['total']} | "
            f"média {rag['media_segundos']:.2f}s | "
            f"p95 {rag['p95_segundos']:.2f}s | "
            f"cache hit {rag['taxa_cache_hit'] * 100:.0f}% | "
            f"sucesso {rag['taxa_sucesso'] * 100:.0f}%"
        ),
        f"Top decisões: {decisoes_texto}",
    ]
    return "\n".join(linhas)


async def cmd_painel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra o painel de gerenciamento."""
    mensagem = update.effective_message
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return

    docs = await listar_documentos(empresa["id"])
    faqs = await listar_faqs(empresa["id"])
    total_clientes = await contar_clientes_empresa(empresa["id"])
    tem_docs = empresa_tem_documentos(empresa["id"])
    tem_imagem = empresa_tem_imagem(empresa["id"])
    agente_ativo = bool(empresa.get("ativo", 1))

    if not agente_ativo:
        status_emoji = "⏸️"
        status_texto = "Pausado"
    elif tem_docs:
        status_emoji = "🟢"
        status_texto = "Pronto para teste"
    else:
        status_emoji = "🟡"
        status_texto = "Sem documentos — envie arquivos no chat ou use /upload"

    imagem_texto = "Configurada" if tem_imagem else "Não configurada"
    horario_texto = "Configurado" if empresa.get("horario_atendimento") else "Não configurado"
    fallback_texto = "Configurado" if empresa.get("fallback_contato") else "Não configurado"
    atendimento_texto = "Ativo" if agente_ativo else "Pausado"

    texto = (
        f"📊 Painel — {empresa['nome']}\n\n"
        f"🤖 Assistente: {empresa['nome_bot']}\n"
        f"👋 Saudação: {empresa['saudacao']}\n"
        f"⏱️ Atendimento: {atendimento_texto}\n"
        f"🖼️ Imagem: {imagem_texto}\n"
        f"🕒 Horário: {horario_texto}\n"
        f"🆘 Fallback: {fallback_texto}\n"
        f"👥 Clientes: {total_clientes}\n"
        f"❔ FAQs: {len(faqs)}\n"
        f"📄 Documentos: {len(docs)}\n"
        f"{status_emoji} Status: {status_texto}\n\n"
        f"Use os botões abaixo ou o Menu do Telegram para navegar.\n\n"
        f"Você pode enviar documentos diretamente neste chat, testar o agente com perguntas e usar /link para compartilhar com clientes."
    )
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(texto, reply_markup=_teclado_painel(empresa))
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
        return

    await mensagem.reply_text(texto, reply_markup=_teclado_painel(empresa))


async def cmd_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ajuda."""
    mensagem = update.effective_message
    user_id = update.effective_user.id
    empresa_admin = await obter_empresa_por_admin(user_id)
    empresa_cliente = await obter_empresa_do_cliente(user_id)
    formatos = listar_formatos_suportados()
    formatos_imagem = listar_formatos_imagem_suportados()
    if empresa_admin:
        texto = (
            "📋 Comandos do admin:\n\n"
            "/start — Abrir a configuração inicial\n"
            "/meuid — Mostrar seu ID do Telegram\n"
            "/link — Gerar o link de atendimento para os clientes\n"
            "/painel — Painel de gerenciamento\n"
            "/upload — Entrar no modo de envio de documentos\n"
            "/imagem — Atualizar a imagem do agente\n"
            "/pausar — Pausar o agente\n"
            "/ativar — Reativar o agente\n"
            "/horario — Configurar horário de atendimento\n"
            "/fallback — Configurar contato humano de fallback\n"
            "/faq — Gerenciar perguntas frequentes\n"
            "/documentos — Gerenciar a base de conhecimento\n"
            "/editar — Editar configurações do bot\n"
            "/reset — Apagar a configuração atual e começar de novo\n"
            "/status — Ver status do bot\n\n"
            f"Você pode enviar documentos diretamente neste chat a qualquer momento.\n"
            f"Formatos aceitos: {formatos}.\n"
            f"Para /imagem, envie foto do Telegram ou imagem em: {formatos_imagem}.\n"
            "Depois de configurar e enviar documentos, use /link para compartilhar o atendimento com seus clientes.\n"
            "Clientes entram pelo link e usam este bot só para conversar."
        )
    elif empresa_cliente:
        texto = (
            f"💬 Este chat está vinculado ao atendimento de {empresa_cliente['nome']}.\n\n"
            "Aqui você não precisa usar comandos de gestão.\n"
            "Basta enviar sua mensagem normalmente para conversar com o bot.\n\n"
            "Se precisar informar seu identificador ao atendimento, use /meuid.\n"
            "Se quiser sair deste atendimento, use /sair.\n"
            "Se precisar de um novo acesso, peça o link novamente ao atendimento."
        )
    else:
        texto = (
            "👋 Este bot possui dois perfis:\n\n"
            "- admin: configura a empresa, documentos, FAQ e horário\n"
            "- cliente: usa apenas o link enviado pelo admin para conversar\n\n"
            "Use /meuid para descobrir seu ID do Telegram.\n"
            "Se você é o admin, envie /start para iniciar a configuração."
        )
    await mensagem.reply_text(texto)


async def cmd_meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra o ID do usuário e do chat atual para facilitar suporte e testes."""
    mensagem = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not mensagem or not user or not chat:
        return

    texto = (
        "🆔 Seus identificadores neste bot:\n\n"
        f"Usuário Telegram: `{user.id}`\n"
        f"Chat atual: `{chat.id}`\n\n"
        "Envie esse número ao administrador se ele precisar vincular ou conferir seu acesso."
    )
    await mensagem.reply_text(texto, parse_mode="Markdown")


async def cmd_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gera o deep link que o admin envia para seus clientes."""
    from .common import _montar_link_atendimento

    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return

    bot_info = await context.bot.get_me()
    try:
        link = _montar_link_atendimento(bot_info.username or "", empresa["link_token"])
    except ValueError as exc:
        await update.effective_message.reply_text(f"❌ {exc}")
        return

    await update.effective_message.reply_text(
        f"🔗 Link de atendimento de {empresa['nome']}:\n{link}\n\n"
        "Envie esse link para seus clientes. Quando eles abrirem, poderão apenas conversar com o bot."
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra o status atual do bot."""
    mensagem = update.effective_message
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return

    tem_docs = empresa_tem_documentos(empresa["id"])
    docs = await listar_documentos(empresa["id"])
    faqs = await listar_faqs(empresa["id"])
    total_clientes = await contar_clientes_empresa(empresa["id"])
    tem_imagem = empresa_tem_imagem(empresa["id"])
    imagem_texto = "Configurada" if tem_imagem else "Não configurada"
    atendimento_texto = "Ativo" if bool(empresa.get("ativo", 1)) else "Pausado"
    horario_texto = empresa.get("horario_atendimento") or "Não configurado"
    fallback_texto = empresa.get("fallback_contato") or "Não configurado"

    if tem_docs:
        texto = (
            f"🟢 Agente CONFIGURADO\n\n"
            f"Empresa: {empresa['nome']}\n"
            f"Assistente: {empresa['nome_bot']}\n"
            f"Atendimento: {atendimento_texto}\n"
            f"Imagem: {imagem_texto}\n"
            f"Horário: {horario_texto}\n"
            f"Fallback: {fallback_texto}\n"
            f"Clientes vinculados: {total_clientes}\n"
            f"FAQs: {len(faqs)}\n"
            f"Documentos indexados: {len(docs)}\n\n"
            f"{await _formatar_bloco_metricas(empresa['id'])}\n\n"
            f"Seu agente já pode ser testado neste chat e compartilhado com /link."
        )
    else:
        texto = (
            f"🟡 Agente INCOMPLETO\n\n"
            f"Empresa: {empresa['nome']}\n"
            f"Atendimento: {atendimento_texto}\n"
            f"Imagem: {imagem_texto}\n"
            f"Horário: {horario_texto}\n"
            f"Fallback: {fallback_texto}\n"
            f"Clientes vinculados: {total_clientes}\n"
            f"FAQs: {len(faqs)}\n"
            f"Nenhum documento carregado.\n\n"
            f"{await _formatar_bloco_metricas(empresa['id'])}\n\n"
            f"Envie documentos neste chat ou use /upload para concluir a configuração."
        )
    await mensagem.reply_text(texto)
    if tem_imagem:
        await _enviar_preview_imagem_empresa(
            mensagem,
            empresa["id"],
            "Imagem atual do seu agente.",
        )


# ── Callbacks do painel ──

async def painel_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Atualiza o painel principal pelo botão inline."""
    await update.callback_query.answer()
    await cmd_painel(update, context)


async def painel_documentos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Abre a listagem de documentos a partir do painel."""
    await update.callback_query.answer()
    from .documents import cmd_documentos
    await cmd_documentos(update, context)


async def painel_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Abre o status a partir do painel."""
    await update.callback_query.answer()
    await cmd_status(update, context)


async def painel_ajuda_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Abre a ajuda a partir do painel."""
    await update.callback_query.answer()
    await cmd_ajuda(update, context)


async def painel_upload_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o upload a partir do painel."""
    await update.callback_query.answer()
    from .documents import cmd_upload
    return await cmd_upload(update, context)


async def painel_imagem_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia a troca de imagem a partir do painel."""
    await update.callback_query.answer()
    from .images import cmd_imagem
    return await cmd_imagem(update, context)


async def painel_faq_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Abre a gestão de FAQ a partir do painel."""
    await update.callback_query.answer()
    from .faq import cmd_faq
    return await cmd_faq(update, context)


async def painel_horario_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia a configuração de horário a partir do painel."""
    await update.callback_query.answer()
    from .settings import cmd_horario
    return await cmd_horario(update, context)


async def painel_fallback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia a configuração de fallback a partir do painel."""
    await update.callback_query.answer()
    from .settings import cmd_fallback
    return await cmd_fallback(update, context)


async def painel_ativo_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Alterna o estado ativo/pausado do agente pelo painel."""
    await update.callback_query.answer()
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return
    from .settings import _definir_status_agente
    await _definir_status_agente(update, context, ativo=not bool(empresa.get("ativo", 1)))


async def painel_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o reset a partir do painel."""
    await update.callback_query.answer()
    from .onboarding import cmd_reset
    return await cmd_reset(update, context)


async def painel_editar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia a edição a partir do painel."""
    await update.callback_query.answer()
    from .settings import cmd_editar
    return await cmd_editar(update, context)
