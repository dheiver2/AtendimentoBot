"""Fluxo conversacional do WhatsApp Web com paridade funcional ao Telegram."""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import shutil
from dataclasses import dataclass, field
from time import time
from typing import Any, Awaitable, Callable

from agent_service import invalidar_cache_faq, processar_pergunta
from bot_profile_photo import (
    empresa_tem_imagem,
    excluir_imagem_empresa,
    obter_caminho_imagem_empresa,
    salvar_imagem_empresa,
)
from config import IMAGES_DIR, PDFS_DIR, VECTOR_STORES_DIR
from database import (
    adicionar_admin_empresa,
    atualizar_empresa,
    contar_clientes_empresa,
    criar_empresa,
    criar_feedback_resposta,
    criar_faq,
    desvincular_cliente,
    excluir_documento,
    excluir_empresa_com_dados,
    excluir_faq,
    limpar_sessoes_whatsapp_expiradas,
    limpar_faqs,
    listar_documentos,
    listar_empresas,
    listar_faqs,
    obter_documento_por_id,
    obter_empresa_do_cliente,
    obter_empresa_do_usuario,
    obter_empresa_por_admin,
    obter_empresa_por_admin_link_token,
    obter_empresa_por_id,
    obter_empresa_por_link_token,
    obter_sessao_whatsapp,
    registrar_conversa,
    registrar_documento,
    registrar_feedback_resposta,
    remover_sessao_whatsapp,
    salvar_sessao_whatsapp,
    vincular_cliente_empresa,
)
from document_processor import (
    SUPPORTED_EXTENSIONS,
    arquivo_suportado,
    listar_formatos_suportados,
    processar_documento,
    processar_documento_salvo,
)
from handlers.common import (
    _extrair_token_link_admin,
    _gerar_capa_empresa,
    _montar_texto_boas_vindas_cliente,
)
from instruction_templates import listar_templates_instrucao, obter_template_instrucao
from metrics import obter_resumo_metricas_empresa
from rag_chain import gerar_resposta
from rate_limiter import (
    limiter_comandos,
    limiter_faq,
    limiter_mensagens,
    limiter_upload,
    verificar_rate_limit,
)
from validators import (
    MAX_DOCUMENTOS_POR_EMPRESA,
    MAX_FAQS_POR_EMPRESA,
    InputValidationError,
    validar_fallback,
    validar_faq_pergunta,
    validar_faq_resposta,
    validar_horario,
    validar_instrucoes,
    validar_mensagem_usuario,
    validar_nome_bot,
    validar_nome_empresa,
    validar_saudacao,
)
from vector_store import adicionar_documentos, empresa_tem_documentos, substituir_documentos

logger = logging.getLogger(__name__)

_DEFAULT_INSTRUCOES = (
    "Você é um assistente de atendimento ao cliente. "
    "Responda de forma educada e profissional."
)
_SESSION_TTL_SECONDS = 24 * 60 * 60
_FEEDBACK_PROMPT = "👍👎 Essa resposta ajudou? Responda com um desses emojis."

_STATE_ONBOARDING_NOME_EMPRESA = "onboarding_nome_empresa"
_STATE_ONBOARDING_NOME_BOT = "onboarding_nome_bot"
_STATE_ONBOARDING_SAUDACAO = "onboarding_saudacao"
_STATE_ONBOARDING_INSTRUCOES = "onboarding_instrucoes"
_STATE_ONBOARDING_CONFIRMACAO = "onboarding_confirmacao"
_STATE_UPLOAD_DOCUMENTO = "upload_documento"
_STATE_IMAGEM = "imagem"
_STATE_HORARIO = "horario"
_STATE_FALLBACK = "fallback"
_STATE_FAQ_PERGUNTA = "faq_pergunta"
_STATE_FAQ_RESPOSTA = "faq_resposta"
_STATE_RESET_CONFIRMACAO = "reset_confirmacao"
_STATE_EDITAR_CAMPO = "editar_campo"
_STATE_EDITAR_VALOR = "editar_valor"
_STATE_SELECAO_EMPRESA = "selecao_empresa"

_FIELD_LABELS = {
    "nome": "nome da empresa",
    "nome_bot": "nome do assistente",
    "saudacao": "saudacao",
    "instrucoes": "instrucoes",
}
_FIELD_ALIASES = {
    "nome": "nome",
    "empresa": "nome",
    "nome_bot": "nome_bot",
    "bot": "nome_bot",
    "assistente": "nome_bot",
    "saudacao": "saudacao",
    "instrucoes": "instrucoes",
    "instrucao": "instrucoes",
}

DefaultCompanyResolver = Callable[[], Awaitable[dict | None]]
ShareLinkBuilder = Callable[[str], str | None]


@dataclass
class WhatsAppSession:
    state: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    identidade_visual_enviada: bool = False
    updated_at: float = field(default_factory=time)


_sessions: dict[str, WhatsAppSession] = {}


def _coerce_whatsapp_digits(raw_value: str) -> str:
    return "".join(char for char in (raw_value or "") if char.isdigit())


def _coerce_whatsapp_user_id(raw_value: str) -> int:
    digits = _coerce_whatsapp_digits(raw_value)
    if digits:
        value = int(digits)
        return -(value or 1)

    digest = hashlib.sha256((raw_value or "").encode("utf-8")).hexdigest()
    return -int(digest[:15], 16)


def _whatsapp_admin_numbers() -> set[str]:
    raw_value = (os.getenv("WHATSAPP_ADMIN_NUMBERS") or "").strip()
    if not raw_value:
        return set()

    normalized = raw_value.replace("\n", ",").replace(";", ",")
    numbers: set[str] = set()
    for chunk in normalized.split(","):
        digits = _coerce_whatsapp_digits(chunk)
        if digits:
            numbers.add(digits)
    return numbers


def _pode_iniciar_admin_sem_link(sender: str, *, is_owner_chat: bool) -> bool:
    numeros_admin = _whatsapp_admin_numbers()
    if numeros_admin:
        return _coerce_whatsapp_digits(sender) in numeros_admin
    return is_owner_chat


def _usa_bootstrap_owner_chat_padrao(*, is_owner_chat: bool) -> bool:
    return is_owner_chat and not _whatsapp_admin_numbers()


def _touch_session(sender: str) -> WhatsAppSession:
    now = time()
    expirados = [
        chave
        for chave, sessao in _sessions.items()
        if now - sessao.updated_at > _SESSION_TTL_SECONDS
    ]
    for chave in expirados:
        _sessions.pop(chave, None)

    session = _sessions.setdefault(sender, WhatsAppSession())
    session.updated_at = now
    return session


def _clear_session(session: WhatsAppSession, *, keep_identity: bool = True) -> None:
    identidade = session.identidade_visual_enviada if keep_identity else False
    session.state = None
    session.data.clear()
    session.identidade_visual_enviada = identidade
    session.updated_at = time()


def _extrair_resposta_e_conversa_id(resultado: object) -> tuple[str, int | None]:
    if isinstance(resultado, str):
        return resultado, None

    texto = getattr(resultado, "text", None)
    conversa_id = getattr(resultado, "conversation_id", None)
    if isinstance(texto, str):
        return texto, conversa_id if isinstance(conversa_id, int) else None
    return str(resultado), None


def _feedback_pendente(session: WhatsAppSession) -> int | None:
    valor = session.data.get("pending_feedback_id")
    return valor if isinstance(valor, int) else None


def _definir_feedback_pendente(session: WhatsAppSession, feedback_id: int | None) -> None:
    if feedback_id is None:
        session.data.pop("pending_feedback_id", None)
        return
    session.data["pending_feedback_id"] = feedback_id


def _extrair_avaliacao_feedback(text: str) -> int | None:
    texto = (text or "").strip().replace("\ufe0f", "")
    if texto == "👍":
        return 1
    if texto == "👎":
        return -1
    return None


def _sessao_precisa_persistir(session: WhatsAppSession) -> bool:
    return bool(session.state or session.data or session.identidade_visual_enviada)


async def _restaurar_sessao(sender: str) -> WhatsAppSession:
    now = time()
    cutoff = now - _SESSION_TTL_SECONDS
    await limpar_sessoes_whatsapp_expiradas(cutoff)

    expirados = [
        chave
        for chave, sessao in _sessions.items()
        if now - sessao.updated_at > _SESSION_TTL_SECONDS
    ]
    for chave in expirados:
        _sessions.pop(chave, None)

    session = _sessions.get(sender)
    if session:
        session.updated_at = now
        return session

    persisted = await obter_sessao_whatsapp(sender)
    if persisted:
        updated_at = float(persisted.get("updated_at") or 0.0)
        if now - updated_at <= _SESSION_TTL_SECONDS:
            session = WhatsAppSession(
                state=persisted.get("state"),
                data=(
                    persisted.get("data")
                    if isinstance(persisted.get("data"), dict)
                    else {}
                ),
                identidade_visual_enviada=bool(persisted.get("identidade_visual_enviada")),
                updated_at=now,
            )
            _sessions[sender] = session
            return session
        await remover_sessao_whatsapp(sender)

    return _touch_session(sender)


async def _persistir_sessao(sender: str, session: WhatsAppSession) -> None:
    session.updated_at = time()
    if _sessao_precisa_persistir(session):
        await salvar_sessao_whatsapp(
            sender,
            state=session.state,
            data=session.data,
            identidade_visual_enviada=session.identidade_visual_enviada,
            updated_at=session.updated_at,
        )
        _sessions[sender] = session
        return

    _sessions.pop(sender, None)
    await remover_sessao_whatsapp(sender)


def _formatar_templates_instrucao(template_key_atual: str | None) -> str:
    template_atual = obter_template_instrucao(template_key_atual)
    linhas = [
        "🧩 Templates de instrucoes disponiveis:",
        "",
        (
            f"Atual: {template_atual.nome} ({template_atual.key})"
            if template_atual
            else "Atual: Personalizado"
        ),
        "",
    ]
    for template in listar_templates_instrucao():
        linhas.append(f"- {template.key}: {template.nome} - {template.descricao}")
    linhas.extend(
        [
            "",
            "Use /template <slug> para aplicar um template.",
            "Exemplo: /template clinica",
            "Use /template limpar para manter as instrucoes atuais como personalizadas.",
        ]
    )
    return "\n".join(linhas)


def _make_text_action(text: str) -> dict[str, str]:
    return {"type": "text", "text": text}


def _make_image_action(
    image_bytes: bytes,
    *,
    caption: str = "",
    filename: str = "imagem.jpg",
    mime_type: str = "image/jpeg",
) -> dict[str, str]:
    return {
        "type": "image",
        "caption": caption,
        "filename": filename,
        "mime_type": mime_type,
        "media_base64": base64.b64encode(image_bytes).decode("ascii"),
    }


def _image_action_from_path(path: str, caption: str) -> dict[str, str] | None:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as file:
        return _make_image_action(file.read(), caption=caption, filename=os.path.basename(path))


def _make_welcome_actions(empresa: dict, session: WhatsAppSession) -> list[dict[str, str]]:
    texto = _montar_texto_boas_vindas_cliente(empresa, empresa_tem_documentos(empresa["id"]))
    if session.identidade_visual_enviada:
        return [_make_text_action(texto)]

    try:
        capa = _gerar_capa_empresa(empresa)
        session.identidade_visual_enviada = True
        return [_make_image_action(capa.getvalue(), caption=texto, filename="capa.jpg")]
    except Exception as exc:
        logger.warning(
            "Falha ao gerar a identidade visual da empresa %s para o WhatsApp: %s",
            empresa["id"],
            exc,
        )
        session.identidade_visual_enviada = True
        return [_make_text_action(texto)]


def _iniciar_onboarding_admin(
    session: WhatsAppSession,
    *,
    prefixo: str | None = None,
    mostrar_resumo: bool = True,
) -> list[dict[str, str]]:
    _clear_session(session, keep_identity=False)
    session.state = _STATE_ONBOARDING_NOME_EMPRESA

    linhas: list[str] = []
    if prefixo:
        linhas.extend([prefixo, ""])
    linhas.append("👋 Vamos configurar seu agente de atendimento.")
    linhas.append("")
    if mostrar_resumo:
        linhas.extend(
            [
                "Neste onboarding voce vai definir:",
                "1. Nome da empresa",
                "2. Nome do assistente",
                "3. Saudacao inicial",
                "4. Instrucoes de comportamento",
                "",
            ]
        )
    linhas.extend(
        [
            "Para comecar, qual e o nome da sua empresa?",
            "Se quiser sair, envie /cancelar.",
        ]
    )
    return [_make_text_action("\n".join(linhas))]


def _snapshot_empresas_para_selecao(empresas: list[dict]) -> list[dict[str, Any]]:
    return [{"id": int(empresa["id"]), "nome": str(empresa["nome"])} for empresa in empresas]


def _texto_selecao_empresa(
    empresas: list[dict[str, Any]],
    *,
    manter_pendente: bool = False,
) -> str:
    linhas = [
        "🏢 Escolha a empresa com quem deseja falar:",
        "",
    ]
    for indice, empresa in enumerate(empresas, start=1):
        linhas.append(f"{indice}. {empresa['nome']}")

    linhas.extend(
        [
            "",
            "Responda com o numero da empresa desejada.",
        ]
    )
    if manter_pendente:
        linhas.append("Depois da escolha, eu continuo a partir da sua mensagem anterior.")
    linhas.append("Se quiser cancelar, use /cancelar.")
    return "\n".join(linhas)


def _iniciar_selecao_empresa(
    session: WhatsAppSession,
    empresas: list[dict],
    *,
    pending_text: str = "",
) -> list[dict[str, str]]:
    escolhas = _snapshot_empresas_para_selecao(empresas)
    _clear_session(session)
    session.state = _STATE_SELECAO_EMPRESA
    session.data["empresa_choices"] = escolhas
    texto_pendente = (pending_text or "").strip()
    if texto_pendente:
        session.data["pending_text"] = texto_pendente
    return [
        _make_text_action(
            _texto_selecao_empresa(escolhas, manter_pendente=bool(texto_pendente))
        )
    ]


def _resolver_selecao_empresa(
    text: str,
    escolhas: list[dict[str, Any]],
) -> dict[str, Any] | None:
    texto = (text or "").strip()
    if not texto:
        return None

    if texto.isdigit():
        indice = int(texto)
        if 1 <= indice <= len(escolhas):
            return escolhas[indice - 1]
        for escolha in escolhas:
            if escolha["id"] == indice:
                return escolha

    texto_normalizado = texto.casefold()
    correspondencias = [
        escolha
        for escolha in escolhas
        if str(escolha["nome"]).strip().casefold() == texto_normalizado
    ]
    if len(correspondencias) == 1:
        return correspondencias[0]
    return None


async def _vincular_cliente_e_responder(
    *,
    empresa: dict,
    user_id: int,
    session: WhatsAppSession,
    resolve_default_company: DefaultCompanyResolver,
    pending_text: str = "",
) -> list[dict[str, str]]:
    await vincular_cliente_empresa(empresa["id"], user_id)
    session.identidade_visual_enviada = False
    _clear_session(session)
    actions = _make_welcome_actions(empresa, session)

    texto_pendente = (pending_text or "").strip()
    if not texto_pendente:
        return actions

    resposta_pendente = await _processar_interacao_agente(
        session=session,
        user_id=user_id,
        text=texto_pendente,
        resolve_default_company=resolve_default_company,
        auto_bind_default_company=False,
    )
    actions.extend(resposta_pendente)
    return actions


def _parse_command(text: str) -> tuple[str | None, list[str]]:
    texto = (text or "").strip()
    if not texto.startswith("/"):
        return None, []

    partes = texto.split()
    comando = partes[0][1:].split("@", 1)[0].strip().lower()
    return (comando or None), partes[1:]


def _looks_like_confirmation(text: str, *allowed: str) -> bool:
    normalized = (text or "").strip().lower().lstrip("/")
    return normalized in allowed


def _formatar_bloco_metricas_local(resumo: dict | None) -> str:
    if not resumo:
        return "📈 Métricas recentes: ainda sem dados nesta execução."

    atendimento = resumo["atendimentos"]
    rag = resumo["rag"]
    decisoes = atendimento["decisoes"]
    top_decisoes = sorted(decisoes.items(), key=lambda item: (-item[1], item[0]))[:3]
    decisoes_texto = ", ".join(f"{nome}={total}" for nome, total in top_decisoes) or "sem dados"
    return "\n".join(
        [
            f"📈 Métricas recentes ({resumo['janela_horas']}h, max. 200 eventos)",
            (
                f"Atendimentos: {atendimento['total']} | media {atendimento['media_segundos']:.2f}s | "
                f"p95 {atendimento['p95_segundos']:.2f}s | sucesso {atendimento['taxa_sucesso'] * 100:.0f}% | "
                f"RAG {atendimento['taxa_rag'] * 100:.0f}%"
            ),
            (
                f"RAG: {rag['total']} | media {rag['media_segundos']:.2f}s | "
                f"p95 {rag['p95_segundos']:.2f}s | cache hit {rag['taxa_cache_hit'] * 100:.0f}% | "
                f"sucesso {rag['taxa_sucesso'] * 100:.0f}%"
            ),
            f"Top decisoes: {decisoes_texto}",
        ]
    )


def _caminho_documento(empresa_id: int, nome_arquivo: str) -> str:
    return os.path.join(PDFS_DIR, str(empresa_id), nome_arquivo)


def _remover_arquivos_empresa(empresa_id: int) -> None:
    for diretorio_base in [PDFS_DIR, VECTOR_STORES_DIR, IMAGES_DIR]:
        caminho = os.path.join(diretorio_base, str(empresa_id))
        if os.path.isdir(caminho):
            shutil.rmtree(caminho, ignore_errors=True)


def _resumo_reindexacao(quantidade_processada: int, avisos: list[str]) -> str:
    linhas = [f"📊 Base atualizada com {quantidade_processada} documento(s) valido(s)."]
    if avisos:
        linhas.append("")
        linhas.append("⚠️ Avisos:")
        for aviso in avisos[:3]:
            linhas.append(f"- {aviso}")
        if len(avisos) > 3:
            linhas.append(f"- ... e mais {len(avisos) - 3} aviso(s).")
    return "\n".join(linhas)


async def _reindexar_base_empresa(empresa_id: int) -> tuple[int, list[str]]:
    documentos = await listar_documentos(empresa_id)
    documentos_processados: list[tuple[list[str], dict]] = []
    avisos: list[str] = []

    for documento in documentos:
        caminho = _caminho_documento(empresa_id, documento["nome_arquivo"])
        if not os.path.exists(caminho):
            avisos.append(f"{documento['nome_arquivo']}: arquivo nao encontrado no disco.")
            continue

        try:
            chunks = processar_documento_salvo(caminho)
        except Exception as exc:
            avisos.append(f"{documento['nome_arquivo']}: {exc}")
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


def _guess_filename(message_type: str, file_name: str | None, mime_type: str | None) -> str:
    if file_name:
        return file_name

    if mime_type:
        for ext, label in SUPPORTED_EXTENSIONS.items():
            if label.lower() in mime_type.lower():
                return f"arquivo{ext}"
        if mime_type.lower().startswith("image/"):
            return "imagem.jpg"

    if message_type == "image":
        return "imagem.jpg"
    if message_type == "document":
        return "documento"
    return "arquivo"


def _apply_field_validation(field_name: str, raw_value: str) -> str:
    if field_name == "nome":
        return validar_nome_empresa(raw_value)
    if field_name == "nome_bot":
        return validar_nome_bot(raw_value)
    if field_name == "saudacao":
        return validar_saudacao(raw_value)
    if field_name == "instrucoes":
        return validar_instrucoes(raw_value)
    raise InputValidationError("Campo de edicao invalido.")


def _resolve_edit_field(raw_field: str | None) -> str | None:
    if not raw_field:
        return None
    return _FIELD_ALIASES.get(raw_field.strip().lower())


async def _processar_documento_recebido(
    *,
    user_id: int,
    empresa: dict,
    media_bytes: bytes,
    file_name: str,
    modo_upload: bool,
) -> list[dict[str, str]]:
    if not arquivo_suportado(file_name):
        return [
            _make_text_action(
                f"⚠️ Formato nao suportado. Envie um destes formatos: {listar_formatos_suportados()}."
            )
        ]

    rate_msg = verificar_rate_limit(limiter_upload, user_id)
    if rate_msg:
        return [_make_text_action(rate_msg)]

    docs_existentes = await listar_documentos(empresa["id"])
    if len(docs_existentes) >= MAX_DOCUMENTOS_POR_EMPRESA:
        return [
            _make_text_action(
                f"⚠️ Limite de {MAX_DOCUMENTOS_POR_EMPRESA} documentos por empresa atingido.\n"
                "Exclua documentos antigos com /documentos excluir <id> antes de enviar novos."
            )
        ]

    try:
        arquivo_existia = os.path.exists(_caminho_documento(empresa["id"], file_name))
        chunks = processar_documento(empresa["id"], file_name, media_bytes)
        await registrar_documento(empresa["id"], file_name)

        if arquivo_existia:
            quantidade_processada, avisos = await _reindexar_base_empresa(empresa["id"])
            resumo = _resumo_reindexacao(quantidade_processada, avisos)
            return [
                _make_text_action(
                    f"✅ {file_name} atualizado com sucesso.\n"
                    f"{resumo}\n\n"
                    + (
                        "Envie mais arquivos ou use /pronto para finalizar."
                        if modo_upload
                        else "Voce pode enviar mais documentos ou testar o agente com uma pergunta."
                    )
                )
            ]

        adicionar_documentos(empresa["id"], chunks, {"arquivo": file_name})
        return [
            _make_text_action(
                f"✅ {file_name} processado com sucesso.\n"
                f"📊 {len(chunks)} trechos indexados.\n\n"
                + (
                    "Envie mais arquivos ou use /pronto para finalizar."
                    if modo_upload
                    else "Voce pode enviar mais documentos ou testar o agente com uma pergunta."
                )
            )
        ]
    except (ValueError, InputValidationError) as exc:
        return [_make_text_action(f"⚠️ {exc}")]
    except Exception as exc:
        logger.error("Erro ao processar documento no WhatsApp: %s", exc, exc_info=True)
        return [_make_text_action("❌ Erro ao processar o documento. Tente novamente.")]


def _mensagem_somente_admin() -> str:
    return (
        "🔒 Este comando e exclusivo do admin que configurou o atendimento.\n"
        "Se voce recebeu um token de acesso, use este chat apenas para conversar."
    )


async def _handle_state_message(
    *,
    sender: str,
    user_id: int,
    session: WhatsAppSession,
    text: str,
    message_type: str,
    mime_type: str,
    file_name: str,
    media_bytes: bytes | None,
    resolve_default_company: DefaultCompanyResolver,
) -> list[dict[str, str]] | None:
    state = session.state
    if state == _STATE_SELECAO_EMPRESA:
        escolhas = session.data.get("empresa_choices")
        if not isinstance(escolhas, list) or not escolhas:
            _clear_session(session)
            return [_make_text_action("❌ A lista de empresas expirou. Envie uma nova mensagem para recomeçar.")]

        escolha = _resolver_selecao_empresa(text, escolhas)
        if not escolha:
            return [
                _make_text_action(
                    "⚠️ Opcao invalida.\n\n"
                    + _texto_selecao_empresa(
                        escolhas,
                        manter_pendente=bool(session.data.get("pending_text")),
                    )
                )
            ]

        empresa = await obter_empresa_por_id(int(escolha["id"]))
        if not empresa:
            _clear_session(session)
            return [
                _make_text_action(
                    "❌ Essa empresa nao esta mais disponivel. Envie uma nova mensagem para atualizar a lista."
                )
            ]

        return await _vincular_cliente_e_responder(
            empresa=empresa,
            user_id=user_id,
            session=session,
            resolve_default_company=resolve_default_company,
            pending_text=str(session.data.get("pending_text") or ""),
        )

    if state == _STATE_ONBOARDING_NOME_EMPRESA:
        if not text:
            return [_make_text_action("⚠️ Envie o nome da sua empresa em texto.")]
        try:
            session.data["nome_empresa"] = validar_nome_empresa(text)
        except InputValidationError as exc:
            return [_make_text_action(f"⚠️ {exc.message}")]
        session.state = _STATE_ONBOARDING_NOME_BOT
        return [
            _make_text_action(
                "✅ Otimo.\n\n"
                "Agora envie o nome do seu assistente virtual.\n"
                "Exemplo: Ana, Assistente Virtual, Suporte."
            )
        ]

    if state == _STATE_ONBOARDING_NOME_BOT:
        if not text:
            return [_make_text_action("⚠️ Envie o nome do assistente em texto.")]
        try:
            session.data["nome_bot"] = validar_nome_bot(text)
        except InputValidationError as exc:
            return [_make_text_action(f"⚠️ {exc.message}")]
        session.state = _STATE_ONBOARDING_SAUDACAO
        return [
            _make_text_action(
                "👋 Agora envie a mensagem de saudacao inicial.\n"
                "Exemplo: Ola! Bem-vindo. Como posso ajudar?"
            )
        ]

    if state == _STATE_ONBOARDING_SAUDACAO:
        if not text:
            return [_make_text_action("⚠️ Envie a saudacao em texto.")]
        try:
            session.data["saudacao"] = validar_saudacao(text)
        except InputValidationError as exc:
            return [_make_text_action(f"⚠️ {exc.message}")]
        session.state = _STATE_ONBOARDING_INSTRUCOES
        return [
            _make_text_action(
                "📝 Envie agora as instrucoes especiais do bot.\n"
                "Se quiser usar o padrao, envie /pular."
            )
        ]

    if state == _STATE_ONBOARDING_INSTRUCOES:
        if _looks_like_confirmation(text, "pular"):
            session.data["instrucoes"] = _DEFAULT_INSTRUCOES
        else:
            if not text:
                return [_make_text_action("⚠️ Envie as instrucoes em texto ou use /pular.")]
            try:
                session.data["instrucoes"] = validar_instrucoes(text)
            except InputValidationError as exc:
                return [_make_text_action(f"⚠️ {exc.message}")]

        session.state = _STATE_ONBOARDING_CONFIRMACAO
        instrucoes_resumidas = str(session.data["instrucoes"])
        if len(instrucoes_resumidas) > 100:
            instrucoes_resumidas = instrucoes_resumidas[:100] + "..."
        return [
            _make_text_action(
                "📋 Revise sua configuracao:\n\n"
                f"📌 Empresa: {session.data['nome_empresa']}\n"
                f"🤖 Assistente: {session.data['nome_bot']}\n"
                f"👋 Saudacao: {session.data['saudacao']}\n"
                f"📝 Instrucoes: {instrucoes_resumidas}\n\n"
                "Envie /confirmar para salvar ou /recomecar para reiniciar."
            )
        ]

    if state == _STATE_ONBOARDING_CONFIRMACAO:
        if _looks_like_confirmation(text, "recomecar"):
            session.state = _STATE_ONBOARDING_NOME_EMPRESA
            session.data.clear()
            return [_make_text_action("🔄 Vamos recomeçar. Qual e o nome da sua empresa?")]

        if not _looks_like_confirmation(text, "confirmar", "sim"):
            return [_make_text_action("Envie /confirmar para salvar ou /recomecar para reiniciar.")]

        empresa_id = await criar_empresa(str(session.data["nome_empresa"]), user_id)
        await atualizar_empresa(
            empresa_id,
            nome_bot=str(session.data["nome_bot"]),
            saudacao=str(session.data["saudacao"]),
            instrucoes=str(session.data["instrucoes"]),
        )
        _clear_session(session)
        return [
            _make_text_action(
                "🎉 Empresa cadastrada com sucesso.\n\n"
                "Agora envie seus documentos neste chat ou use /upload para entrar no modo guiado.\n"
                "Use /link quando quiser gerar o acesso dos clientes.\n"
                "Use /template para aplicar instrucoes por setor.\n"
                f"Formatos aceitos: {listar_formatos_suportados()}.\n"
                "Se quiser, use /imagem para definir a imagem do agente."
            )
        ]

    if state == _STATE_UPLOAD_DOCUMENTO:
        empresa = await obter_empresa_por_admin(user_id)
        if not empresa:
            _clear_session(session)
            return [_make_text_action("❌ Seu acesso de admin nao foi encontrado. Use /start novamente.")]

        if message_type == "document" and media_bytes:
            return await _processar_documento_recebido(
                user_id=user_id,
                empresa=empresa,
                media_bytes=media_bytes,
                file_name=_guess_filename(message_type, file_name, mime_type),
                modo_upload=True,
            )

        return [_make_text_action("Envie um documento suportado ou use /pronto para finalizar.")]

    if state == _STATE_IMAGEM:
        empresa = await obter_empresa_por_admin(user_id)
        if not empresa:
            _clear_session(session)
            return [_make_text_action("❌ Seu acesso de admin nao foi encontrado. Use /start novamente.")]

        if message_type != "image" or not media_bytes:
            return [_make_text_action("Envie uma imagem valida agora ou use /cancelar.")]

        try:
            salvar_imagem_empresa(empresa["id"], media_bytes)
            _clear_session(session)
            preview = _image_action_from_path(
                obter_caminho_imagem_empresa(empresa["id"]),
                "Preview da imagem atual do seu agente.",
            )
            actions = [_make_text_action("✅ A imagem do seu agente foi atualizada com sucesso.")]
            if preview:
                actions.append(preview)
            return actions
        except (ValueError, InputValidationError) as exc:
            return [_make_text_action(f"⚠️ {exc}")]
        except Exception as exc:
            logger.error("Erro ao salvar imagem via WhatsApp: %s", exc, exc_info=True)
            return [_make_text_action("❌ Nao foi possivel atualizar a imagem agora. Tente novamente.")]

    if state == _STATE_HORARIO:
        empresa = await obter_empresa_por_admin(user_id)
        if not empresa:
            _clear_session(session)
            return [_make_text_action("❌ Seu acesso de admin nao foi encontrado. Use /start novamente.")]

        if not text:
            return [_make_text_action("Envie o horario em texto ou use /cancelar.")]
        try:
            horario = validar_horario(text)
        except InputValidationError as exc:
            return [_make_text_action(f"⚠️ {exc.message}")]
        await atualizar_empresa(empresa["id"], horario_atendimento=horario)
        _clear_session(session)
        return [_make_text_action(f"✅ Horario atualizado para: {horario}")]

    if state == _STATE_FALLBACK:
        empresa = await obter_empresa_por_admin(user_id)
        if not empresa:
            _clear_session(session)
            return [_make_text_action("❌ Seu acesso de admin nao foi encontrado. Use /start novamente.")]

        if not text:
            return [_make_text_action("Envie o contato em texto ou use /cancelar.")]
        try:
            fallback = validar_fallback(text)
        except InputValidationError as exc:
            return [_make_text_action(f"⚠️ {exc.message}")]
        await atualizar_empresa(empresa["id"], fallback_contato=fallback)
        _clear_session(session)
        return [_make_text_action(f"✅ Fallback atualizado para: {fallback}")]

    if state == _STATE_FAQ_PERGUNTA:
        empresa = await obter_empresa_por_admin(user_id)
        if not empresa:
            _clear_session(session)
            return [_make_text_action("❌ Seu acesso de admin nao foi encontrado. Use /start novamente.")]

        rate_msg = verificar_rate_limit(limiter_faq, user_id)
        if rate_msg:
            _clear_session(session)
            return [_make_text_action(rate_msg)]

        if not text:
            return [_make_text_action("Envie a pergunta da FAQ em texto.")]
        try:
            session.data["faq_pergunta"] = validar_faq_pergunta(text)
        except InputValidationError as exc:
            return [_make_text_action(f"⚠️ {exc.message}")]
        session.data["empresa_faq_id"] = empresa["id"]
        session.state = _STATE_FAQ_RESPOSTA
        return [_make_text_action("📝 Agora envie a resposta dessa FAQ.")]

    if state == _STATE_FAQ_RESPOSTA:
        empresa_id = session.data.get("empresa_faq_id")
        pergunta = session.data.get("faq_pergunta")
        if not empresa_id or not pergunta:
            _clear_session(session)
            return [_make_text_action("❌ Erro interno. Use /faq adicionar novamente.")]

        if not text:
            return [_make_text_action("Envie a resposta da FAQ em texto.")]
        try:
            resposta = validar_faq_resposta(text)
        except InputValidationError as exc:
            return [_make_text_action(f"⚠️ {exc.message}")]

        await criar_faq(int(empresa_id), str(pergunta), resposta)
        invalidar_cache_faq(int(empresa_id))
        _clear_session(session)
        return [_make_text_action("✅ FAQ cadastrada com sucesso.")]

    if state == _STATE_RESET_CONFIRMACAO:
        empresa = await obter_empresa_por_admin(user_id)
        if not empresa:
            _clear_session(session, keep_identity=False)
            return [_make_text_action("❌ Seu acesso de admin nao foi encontrado. Use /start novamente.")]

        if _looks_like_confirmation(text, "cancelar", "nao", "não"):
            _clear_session(session)
            return [_make_text_action("✅ Reset cancelado. Sua configuracao continua ativa.")]

        if not _looks_like_confirmation(text, "sim", "confirmar"):
            return [_make_text_action("Responda SIM para apagar tudo ou /cancelar para desistir.")]

        try:
            await excluir_empresa_com_dados(empresa["id"])
            _remover_arquivos_empresa(empresa["id"])
        except Exception as exc:
            logger.error("Erro ao resetar empresa no WhatsApp: %s", exc, exc_info=True)
            _clear_session(session)
            return [_make_text_action("❌ Nao foi possivel resetar a configuracao agora.")]

        _clear_session(session, keep_identity=False)
        session.state = _STATE_ONBOARDING_NOME_EMPRESA
        return [
            _make_text_action(
                f"♻️ A configuracao de {empresa['nome']} foi apagada.\n"
                "Vamos configurar novamente. Qual e o nome da sua empresa?"
            )
        ]

    if state == _STATE_EDITAR_CAMPO:
        campo = _resolve_edit_field(text)
        if not campo:
            return [
                _make_text_action(
                    "Campo invalido. Envie um destes: nome, bot, saudacao, instrucoes.\n"
                    "Ou use /cancelar."
                )
            ]
        session.data["campo_editando"] = campo
        session.state = _STATE_EDITAR_VALOR
        return [_make_text_action(f"📝 Envie o novo valor para {_FIELD_LABELS[campo]}.")]

    if state == _STATE_EDITAR_VALOR:
        empresa = await obter_empresa_por_admin(user_id)
        campo = str(session.data.get("campo_editando") or "")
        if not empresa or not campo:
            _clear_session(session)
            return [_make_text_action("❌ Erro interno. Use /editar novamente.")]
        if not text:
            return [_make_text_action("Envie o novo valor em texto ou use /cancelar.")]

        try:
            novo_valor = _apply_field_validation(campo, text)
        except InputValidationError as exc:
            return [_make_text_action(f"⚠️ {exc.message}")]

        await atualizar_empresa(empresa["id"], **{campo: novo_valor})
        _clear_session(session)
        return [_make_text_action(f"✅ {_FIELD_LABELS[campo].title()} atualizado para: {novo_valor}")]

    return None


async def _cmd_start(
    *,
    sender: str,
    user_id: int,
    args: list[str],
    session: WhatsAppSession,
    resolve_default_company: DefaultCompanyResolver,
    is_owner_chat: bool,
) -> list[dict[str, str]]:
    payload = args[0].strip() if args else ""
    empresa_admin = await obter_empresa_por_admin(user_id)
    empresa_cliente = await obter_empresa_do_cliente(user_id)
    formatos = listar_formatos_suportados()
    pode_iniciar_admin_sem_link = _pode_iniciar_admin_sem_link(
        sender, is_owner_chat=is_owner_chat
    )
    usa_bootstrap_owner_chat_padrao = _usa_bootstrap_owner_chat_padrao(
        is_owner_chat=is_owner_chat
    )

    admin_link_token = _extrair_token_link_admin(payload)
    if admin_link_token:
        empresa_link_admin = await obter_empresa_por_admin_link_token(admin_link_token)
        if not empresa_link_admin:
            return [_make_text_action("❌ Este link de admin e invalido ou expirou.")]

        if empresa_admin:
            if empresa_admin["id"] == empresa_link_admin["id"]:
                return [
                    _make_text_action(
                        f"Voce ja e admin de {empresa_admin['nome']}.\n"
                        "Use /painel para gerenciar o agente e /link para compartilhar os acessos."
                    )
                ]
            return [_make_text_action("🔒 Este link de admin pertence a outra empresa.")]

        await adicionar_admin_empresa(empresa_link_admin["id"], user_id)
        _clear_session(session)
        return [
            _make_text_action(
                f"🔐 Seu acesso de admin para {empresa_link_admin['nome']} foi ativado.\n\n"
                "Use /painel para gerenciar o agente, /link para compartilhar os acessos "
                "e envie uma pergunta neste chat para testar."
            )
        ]

    if payload and usa_bootstrap_owner_chat_padrao and not empresa_admin:
        return _iniciar_onboarding_admin(
            session,
            prefixo="🔒 Este numero conectado como admin nao entra pelo link do cliente.",
        )

    if not payload and pode_iniciar_admin_sem_link and not empresa_admin:
        return _iniciar_onboarding_admin(session)

    if payload:
        empresa_link = await obter_empresa_por_link_token(payload)
        if not empresa_link:
            return [_make_text_action("❌ Este token de atendimento e invalido ou expirou.")]

        if empresa_admin:
            if empresa_admin["id"] == empresa_link["id"]:
                return [
                    _make_text_action(
                        f"Voce ja e o admin de {empresa_admin['nome']}.\n"
                        "Use /painel para gerenciar o agente e /link para compartilhar com clientes."
                    )
                ]
            return [_make_text_action("🔒 Este token e destinado a clientes.")]

        return await _vincular_cliente_e_responder(
            empresa=empresa_link,
            user_id=user_id,
            session=session,
            resolve_default_company=resolve_default_company,
        )

    if empresa_admin:
        _clear_session(session)
        tem_docs = empresa_tem_documentos(empresa_admin["id"])
        dica_teste = (
            "Envie uma pergunta neste chat para testar o agente."
            if tem_docs
            else f"Envie documentos com /upload para o agente comecar a funcionar. Formatos aceitos: {formatos}."
        )
        return [
            _make_text_action(
                f"👋 Sua configuracao para {empresa_admin['nome']} ja esta ativa.\n\n"
                "Use /painel para gerenciar o agente.\n"
                "Use /link para gerar os acessos de admin e cliente.\n"
                "Use /template para aplicar instrucoes por setor.\n"
                "Use /ajuda para ver os comandos.\n"
                f"{dica_teste}"
            )
        ]

    if empresa_cliente:
        session.identidade_visual_enviada = False
        _clear_session(session)
        return _make_welcome_actions(empresa_cliente, session)

    if not pode_iniciar_admin_sem_link:
        empresa_padrao = await resolve_default_company()
        if empresa_padrao:
            return await _vincular_cliente_e_responder(
                empresa=empresa_padrao,
                user_id=user_id,
                session=session,
                resolve_default_company=resolve_default_company,
            )

        empresas = await listar_empresas()
        if len(empresas) > 1:
            return _iniciar_selecao_empresa(session, empresas)
        if len(empresas) == 1:
            return await _vincular_cliente_e_responder(
                empresa=empresas[0],
                user_id=user_id,
                session=session,
                resolve_default_company=resolve_default_company,
            )

        return [
            _make_text_action(
                "👋 Este numero ainda nao foi vinculado a um atendimento.\n"
                "Aguarde o admin concluir a configuracao do WhatsApp ou compartilhar o acesso correto."
            )
        ]

    return _iniciar_onboarding_admin(session)


async def _cmd_registrar(
    *,
    sender: str,
    user_id: int,
    session: WhatsAppSession,
    is_owner_chat: bool,
) -> list[dict[str, str]]:
    empresa_admin = await obter_empresa_por_admin(user_id)
    empresa_cliente = await obter_empresa_do_cliente(user_id)
    if empresa_admin:
        return [
            _make_text_action(
                f"Voce ja tem a empresa {empresa_admin['nome']} registrada.\n"
                "Use /painel para gerenciar, /editar para ajustar a configuracao ou /reset para recomecar."
            )
        ]
    if empresa_cliente:
        return [_make_text_action(_mensagem_somente_admin())]
    if not _pode_iniciar_admin_sem_link(sender, is_owner_chat=is_owner_chat):
        return [
            _make_text_action(
                "🔒 O cadastro e a configuracao da empresa so podem ser feitos por um numero autorizado como admin.\n"
                "Se voce chegou pelo link de atendimento, use este chat apenas para conversar."
            )
        ]

    return _iniciar_onboarding_admin(session, mostrar_resumo=False)


async def _cmd_sair(*, user_id: int, session: WhatsAppSession) -> list[dict[str, str]]:
    empresa_admin = await obter_empresa_por_admin(user_id)
    if empresa_admin:
        return [_make_text_action("🔒 Admins nao podem usar /sair. Use /reset para reconfigurar do zero.")]

    empresa = await obter_empresa_do_cliente(user_id)
    if not empresa:
        return [_make_text_action("Voce nao esta vinculado a nenhum atendimento no momento.")]

    desvinculado = await desvincular_cliente(user_id)
    if not desvinculado:
        return [_make_text_action("❌ Nao foi possivel sair do atendimento agora. Tente novamente.")]

    _clear_session(session, keep_identity=False)
    return [
        _make_text_action(
            f"✅ Voce saiu do atendimento de {empresa['nome']}.\n\n"
            "Se quiser entrar novamente, envie /empresas para escolher outro atendimento "
            "ou use /start TOKEN se recebeu um acesso direto."
        )
    ]


async def _cmd_ajuda(
    *,
    sender: str,
    user_id: int,
    is_owner_chat: bool,
) -> list[dict[str, str]]:
    empresa_admin = await obter_empresa_por_admin(user_id)
    empresa_cliente = await obter_empresa_do_cliente(user_id)
    formatos = listar_formatos_suportados()
    if empresa_admin:
        texto = (
            "📋 Comandos do admin no WhatsApp:\n\n"
            "/start - Abrir a configuracao inicial\n"
            "/registrar - Iniciar o cadastro\n"
            "/meuid - Mostrar seu identificador\n"
            "/link - Gerar os acessos de admin e cliente\n"
            "/painel - Ver resumo geral\n"
            "/upload - Entrar no modo de envio de documentos\n"
            "/documentos - Listar, reprocessar, reindexar e excluir documentos\n"
            "/imagem - Atualizar a imagem do agente\n"
            "/pausar - Pausar o agente\n"
            "/ativar - Reativar o agente\n"
            "/template - Aplicar template de instrucoes por setor\n"
            "/horario - Configurar horario de atendimento\n"
            "/fallback - Configurar contato humano\n"
            "/faq - Gerenciar perguntas frequentes\n"
            "/editar - Editar configuracoes do bot\n"
            "/status - Ver status do agente\n"
            "/reset - Apagar tudo e recomecar\n"
            "/cancelar - Cancelar o fluxo atual\n\n"
            f"Voce pode enviar documentos diretamente neste chat. Formatos aceitos: {formatos}.\n"
            "Clientes podem entrar com /start TOKEN ou escolher a empresa pelo proprio WhatsApp."
        )
    elif empresa_cliente:
        texto = (
            f"💬 Este chat esta vinculado ao atendimento de {empresa_cliente['nome']}.\n\n"
            "Basta enviar sua mensagem normalmente para conversar com o agente.\n"
            "Comandos de configuracao e gestao ficam bloqueados para clientes.\n"
            "Se precisar informar seu identificador ao atendimento, use /meuid.\n"
            "Se quiser trocar de empresa, use /empresas. Se quiser sair, use /sair."
        )
    else:
        pode_iniciar_admin_sem_link = _pode_iniciar_admin_sem_link(
            sender, is_owner_chat=is_owner_chat
        )
        texto = (
            "👋 Este atendimento possui dois perfis:\n\n"
            "- admin: configura empresa, documentos, FAQ e horario\n"
            "- cliente: escolhe a empresa e conversa normalmente\n\n"
            + (
                "Seu numero esta autorizado como admin. Use /start para configurar uma empresa."
                if pode_iniciar_admin_sem_link
                else "Se voce recebeu um link de admin, abra-o para liberar a gestao. Se voce e cliente, envie /empresas para escolher a empresa ou /start TOKEN se recebeu um acesso direto."
            )
        )
    return [_make_text_action(texto)]


async def _cmd_meuid(*, sender: str, user_id: int) -> list[dict[str, str]]:
    return [
        _make_text_action(
            "🆔 Seus identificadores neste atendimento:\n\n"
            f"WhatsApp: {sender}\n"
            f"Interno: {user_id}\n\n"
            "Envie esse numero ao administrador se ele precisar conferir seu acesso."
        )
    ]


async def _cmd_link(
    *,
    user_id: int,
    share_link_builder: ShareLinkBuilder | None,
) -> list[dict[str, str]]:
    empresa = await obter_empresa_por_admin(user_id)
    if not empresa:
        empresa_cliente = await obter_empresa_do_cliente(user_id)
        if empresa_cliente:
            return [_make_text_action(_mensagem_somente_admin())]
        return [_make_text_action("❌ Seu agente ainda nao foi configurado. Use /start primeiro.")]

    token_cliente = empresa["link_token"]
    token_admin = empresa["admin_link_token"]
    share_link_cliente = (
        share_link_builder(f"/start {token_cliente}") if share_link_builder else None
    )
    share_link_admin = (
        share_link_builder(f"/start admin_{token_admin}") if share_link_builder else None
    )
    mensagem_cliente_linhas = [
        f"Olá! Para falar com o atendimento de {empresa['nome']}, use este acesso:",
        "",
    ]
    if share_link_cliente:
        mensagem_cliente_linhas.append(share_link_cliente)
    else:
        mensagem_cliente_linhas.append(f"/start {token_cliente}")
    mensagem_cliente_linhas.extend(
        [
            "",
            "Se preferir, voce tambem pode entrar enviando:",
            f"/start {token_cliente}",
        ]
    )
    mensagem_cliente = "\n".join(mensagem_cliente_linhas)
    mensagem_admin_linhas = [
        f"Olá! Para administrar o atendimento de {empresa['nome']}, use este acesso:",
        "",
    ]
    if share_link_admin:
        mensagem_admin_linhas.append(share_link_admin)
    else:
        mensagem_admin_linhas.append(f"/start admin_{token_admin}")
    mensagem_admin_linhas.extend(
        [
            "",
            "Se preferir, voce tambem pode entrar enviando:",
            f"/start admin_{token_admin}",
        ]
    )
    mensagem_admin = "\n".join(mensagem_admin_linhas)
    linhas = [
        f"🔗 Acesso de atendimento de {empresa['nome']}",
        "",
        f"Token do cliente: {token_cliente}",
        f"Token do admin: {token_admin}",
        "",
        "Cliente pode entrar enviando:",
        f"/start {token_cliente}",
        "",
        "Admin pode entrar enviando:",
        f"/start admin_{token_admin}",
    ]
    if share_link_cliente:
        linhas.extend(["", f"Link do cliente:\n{share_link_cliente}"])
    if share_link_admin:
        linhas.extend(["", f"Link do admin:\n{share_link_admin}"])
    linhas.extend(
        [
            "",
            "O cliente entra apenas para conversar. O link de admin concede acesso de gestao.",
            "",
            f"Mensagem pronta para encaminhar ao cliente:\n\n{mensagem_cliente}",
            "",
            f"Mensagem pronta para encaminhar ao admin:\n\n{mensagem_admin}",
        ]
    )
    return [_make_text_action("\n".join(linhas))]


async def _cmd_empresas(
    *,
    sender: str,
    user_id: int,
    session: WhatsAppSession,
    resolve_default_company: DefaultCompanyResolver,
    is_owner_chat: bool,
) -> list[dict[str, str]]:
    empresa_admin = await obter_empresa_por_admin(user_id)
    if empresa_admin:
        return [
            _make_text_action(
                "🔒 Este chat ja esta operando como admin.\n"
                "Use /painel para gerenciar a empresa ou um outro numero para simular clientes."
            )
        ]

    empresas = await listar_empresas()
    if not empresas:
        pode_iniciar_admin_sem_link = _pode_iniciar_admin_sem_link(
            sender, is_owner_chat=is_owner_chat
        )
        return [
            _make_text_action(
                "👋 Ainda nao existem empresas disponiveis neste WhatsApp.\n"
                + (
                    "Use /start para configurar a primeira empresa."
                    if pode_iniciar_admin_sem_link
                    else "Aguarde o admin concluir a configuracao."
                )
            )
        ]

    empresa_padrao = await resolve_default_company()
    if empresa_padrao and len(empresas) == 1:
        return await _vincular_cliente_e_responder(
            empresa=empresa_padrao,
            user_id=user_id,
            session=session,
            resolve_default_company=resolve_default_company,
        )

    if len(empresas) == 1:
        return await _vincular_cliente_e_responder(
            empresa=empresas[0],
            user_id=user_id,
            session=session,
            resolve_default_company=resolve_default_company,
        )

    return _iniciar_selecao_empresa(session, empresas)


async def _cmd_painel(*, user_id: int) -> list[dict[str, str]]:
    empresa = await obter_empresa_por_admin(user_id)
    if not empresa:
        empresa_cliente = await obter_empresa_do_cliente(user_id)
        if empresa_cliente:
            return [_make_text_action(_mensagem_somente_admin())]
        return [_make_text_action("❌ Seu agente ainda nao foi configurado. Use /start primeiro.")]

    docs = await listar_documentos(empresa["id"])
    faqs = await listar_faqs(empresa["id"])
    total_clientes = await contar_clientes_empresa(empresa["id"])
    tem_docs = empresa_tem_documentos(empresa["id"])
    tem_imagem = empresa_tem_imagem(empresa["id"])
    agente_ativo = bool(empresa.get("ativo", 1))
    template = obter_template_instrucao(empresa.get("instruction_template_key"))
    template_texto = template.nome if template else "Personalizado"

    if not agente_ativo:
        status_emoji = "⏸️"
        status_texto = "Pausado"
    elif tem_docs:
        status_emoji = "🟢"
        status_texto = "Pronto para teste"
    else:
        status_emoji = "🟡"
        status_texto = "Sem documentos"

    return [
        _make_text_action(
            f"📊 Painel - {empresa['nome']}\n\n"
            f"🤖 Assistente: {empresa['nome_bot']}\n"
            f"👋 Saudacao: {empresa['saudacao']}\n"
            f"🧩 Template: {template_texto}\n"
            f"⏱️ Atendimento: {'Ativo' if agente_ativo else 'Pausado'}\n"
            f"🖼️ Imagem: {'Configurada' if tem_imagem else 'Nao configurada'}\n"
            f"🕒 Horario: {'Configurado' if empresa.get('horario_atendimento') else 'Nao configurado'}\n"
            f"🆘 Fallback: {'Configurado' if empresa.get('fallback_contato') else 'Nao configurado'}\n"
            f"👥 Clientes: {total_clientes}\n"
            f"❔ FAQs: {len(faqs)}\n"
            f"📄 Documentos: {len(docs)}\n"
            f"{status_emoji} Status: {status_texto}\n\n"
            "Comandos uteis:\n"
            "/upload, /documentos, /imagem, /faq, /template, /horario, /fallback, /editar, /status, /link"
        )
    ]


async def _cmd_status(*, user_id: int) -> list[dict[str, str]]:
    empresa = await obter_empresa_por_admin(user_id)
    if not empresa:
        empresa_cliente = await obter_empresa_do_cliente(user_id)
        if empresa_cliente:
            return [_make_text_action(_mensagem_somente_admin())]
        return [_make_text_action("❌ Seu agente ainda nao foi configurado. Use /start primeiro.")]

    tem_docs = empresa_tem_documentos(empresa["id"])
    docs = await listar_documentos(empresa["id"])
    faqs = await listar_faqs(empresa["id"])
    total_clientes = await contar_clientes_empresa(empresa["id"])
    tem_imagem = empresa_tem_imagem(empresa["id"])
    resumo_metricas = await obter_resumo_metricas_empresa(empresa["id"])

    if tem_docs:
        texto = (
            f"🟢 Agente CONFIGURADO\n\n"
            f"Empresa: {empresa['nome']}\n"
            f"Assistente: {empresa['nome_bot']}\n"
            f"Atendimento: {'Ativo' if bool(empresa.get('ativo', 1)) else 'Pausado'}\n"
            f"Imagem: {'Configurada' if tem_imagem else 'Nao configurada'}\n"
            f"Horario: {empresa.get('horario_atendimento') or 'Nao configurado'}\n"
            f"Fallback: {empresa.get('fallback_contato') or 'Nao configurado'}\n"
            f"Clientes vinculados: {total_clientes}\n"
            f"FAQs: {len(faqs)}\n"
            f"Documentos indexados: {len(docs)}\n\n"
            f"{_formatar_bloco_metricas_local(resumo_metricas)}\n\n"
            "Seu agente ja pode ser testado neste chat e compartilhado com /link."
        )
    else:
        texto = (
            f"🟡 Agente INCOMPLETO\n\n"
            f"Empresa: {empresa['nome']}\n"
            f"Atendimento: {'Ativo' if bool(empresa.get('ativo', 1)) else 'Pausado'}\n"
            f"Imagem: {'Configurada' if tem_imagem else 'Nao configurada'}\n"
            f"Horario: {empresa.get('horario_atendimento') or 'Nao configurado'}\n"
            f"Fallback: {empresa.get('fallback_contato') or 'Nao configurado'}\n"
            f"Clientes vinculados: {total_clientes}\n"
            f"FAQs: {len(faqs)}\n"
            "Nenhum documento carregado.\n\n"
            f"{_formatar_bloco_metricas_local(resumo_metricas)}\n\n"
            "Envie documentos neste chat ou use /upload para concluir a configuracao."
        )

    actions: list[dict[str, str]] = [_make_text_action(texto)]
    if tem_imagem:
        preview = _image_action_from_path(
            obter_caminho_imagem_empresa(empresa["id"]),
            "Imagem atual do seu agente.",
        )
        if preview:
            actions.append(preview)
    return actions


async def _cmd_pausar_ativar(*, user_id: int, ativo: bool) -> list[dict[str, str]]:
    empresa = await obter_empresa_por_admin(user_id)
    if not empresa:
        empresa_cliente = await obter_empresa_do_cliente(user_id)
        if empresa_cliente:
            return [_make_text_action(_mensagem_somente_admin())]
        return [_make_text_action("❌ Seu agente ainda nao foi configurado. Use /start primeiro.")]

    ativo_atual = bool(empresa.get("ativo", 1))
    if ativo_atual == ativo:
        return [
            _make_text_action("ℹ️ Seu agente ja esta ativo." if ativo else "ℹ️ Seu agente ja esta pausado.")
        ]

    await atualizar_empresa(empresa["id"], ativo=1 if ativo else 0)
    return [
        _make_text_action(
            "▶️ Seu agente foi ativado e ja pode voltar a responder neste chat."
            if ativo
            else "⏸️ Seu agente foi pausado. Enquanto estiver pausado, as pessoas verao apenas sua orientacao operacional."
        )
    ]


async def _cmd_horario(*, user_id: int, args: list[str], session: WhatsAppSession) -> list[dict[str, str]]:
    empresa = await obter_empresa_por_admin(user_id)
    if not empresa:
        empresa_cliente = await obter_empresa_do_cliente(user_id)
        if empresa_cliente:
            return [_make_text_action(_mensagem_somente_admin())]
        return [_make_text_action("❌ Seu agente ainda nao foi configurado. Use /start primeiro.")]

    if args:
        acao = args[0].lower()
        if acao in {"limpar", "remover", "apagar"}:
            await atualizar_empresa(empresa["id"], horario_atendimento="")
            return [_make_text_action("✅ O horario de atendimento foi removido.")]
        try:
            horario = validar_horario(" ".join(args))
        except InputValidationError as exc:
            return [_make_text_action(f"⚠️ {exc.message}")]
        await atualizar_empresa(empresa["id"], horario_atendimento=horario)
        return [_make_text_action(f"✅ Horario atualizado para: {horario}")]

    _clear_session(session)
    session.state = _STATE_HORARIO
    horario_atual = empresa.get("horario_atendimento") or "Nao configurado"
    return [
        _make_text_action(
            "🕒 Horario de atendimento\n\n"
            f"Atual: {horario_atual}\n\n"
            "Envie o texto completo do horario.\n"
            "Exemplo: Seg a Sex, 08h as 18h.\n"
            "Se quiser remover, use /horario limpar."
        )
    ]


async def _cmd_fallback(*, user_id: int, args: list[str], session: WhatsAppSession) -> list[dict[str, str]]:
    empresa = await obter_empresa_por_admin(user_id)
    if not empresa:
        empresa_cliente = await obter_empresa_do_cliente(user_id)
        if empresa_cliente:
            return [_make_text_action(_mensagem_somente_admin())]
        return [_make_text_action("❌ Seu agente ainda nao foi configurado. Use /start primeiro.")]

    if args:
        acao = args[0].lower()
        if acao in {"limpar", "remover", "apagar"}:
            await atualizar_empresa(empresa["id"], fallback_contato="")
            return [_make_text_action("✅ O fallback para atendimento humano foi removido.")]
        try:
            fallback = validar_fallback(" ".join(args))
        except InputValidationError as exc:
            return [_make_text_action(f"⚠️ {exc.message}")]
        await atualizar_empresa(empresa["id"], fallback_contato=fallback)
        return [_make_text_action(f"✅ Fallback atualizado para: {fallback}")]

    _clear_session(session)
    session.state = _STATE_FALLBACK
    fallback_atual = empresa.get("fallback_contato") or "Nao configurado"
    return [
        _make_text_action(
            "🆘 Fallback para humano\n\n"
            f"Atual: {fallback_atual}\n\n"
            "Envie o contato de fallback.\n"
            "Exemplo: WhatsApp (11) 99999-9999 ou suporte@empresa.com.\n"
            "Se quiser remover, use /fallback limpar."
        )
    ]


async def _cmd_template(*, user_id: int, args: list[str]) -> list[dict[str, str]]:
    empresa = await obter_empresa_por_admin(user_id)
    if not empresa:
        empresa_cliente = await obter_empresa_do_cliente(user_id)
        if empresa_cliente:
            return [_make_text_action(_mensagem_somente_admin())]
        return [_make_text_action("❌ Seu agente ainda nao foi configurado. Use /start primeiro.")]

    if not args or args[0].lower() in {"listar", "lista"}:
        return [_make_text_action(_formatar_templates_instrucao(empresa.get("instruction_template_key")))]

    acao = args[0].lower()
    if acao in {"limpar", "personalizado"}:
        await atualizar_empresa(empresa["id"], instruction_template_key=None)
        return [
            _make_text_action(
                "✅ O vinculo com o template foi removido.\n"
                "Suas instrucoes atuais continuam salvas como personalizadas."
            )
        ]

    template_key = args[1] if acao in {"aplicar", "usar"} and len(args) > 1 else args[0]
    template = obter_template_instrucao(template_key)
    if not template:
        return [
            _make_text_action(
                "⚠️ Template nao encontrado.\n\n"
                + _formatar_templates_instrucao(empresa.get("instruction_template_key"))
            )
        ]

    await atualizar_empresa(
        empresa["id"],
        instrucoes=template.texto,
        instruction_template_key=template.key,
    )
    return [
        _make_text_action(
            f"✅ Template aplicado: {template.nome}\n\n"
            f"{template.descricao}\n\n"
            "Se quiser ajustar o texto depois, use /editar e altere as instrucoes."
        )
    ]


async def _cmd_faq(*, user_id: int, args: list[str], session: WhatsAppSession) -> list[dict[str, str]]:
    empresa = await obter_empresa_por_admin(user_id)
    if not empresa:
        empresa_cliente = await obter_empresa_do_cliente(user_id)
        if empresa_cliente:
            return [_make_text_action(_mensagem_somente_admin())]
        return [_make_text_action("❌ Seu agente ainda nao foi configurado. Use /start primeiro.")]

    if args:
        acao = args[0].lower()
        if acao in {"adicionar", "nova", "novo"}:
            faqs = await listar_faqs(empresa["id"])
            if len(faqs) >= MAX_FAQS_POR_EMPRESA:
                return [
                    _make_text_action(
                        f"⚠️ Limite de {MAX_FAQS_POR_EMPRESA} FAQs por empresa atingido.\n"
                        "Exclua FAQs antigas com /faq excluir <id> antes de cadastrar novas."
                    )
                ]
            _clear_session(session)
            session.state = _STATE_FAQ_PERGUNTA
            return [_make_text_action("➕ Nova FAQ\n\nEnvie agora a pergunta da FAQ.")]

        if acao in {"limpar", "apagar"}:
            removidas = await limpar_faqs(empresa["id"])
            invalidar_cache_faq(empresa["id"])
            return [_make_text_action(f"🧹 {removidas} FAQ(s) removida(s).")]

        if acao in {"remover", "excluir"}:
            if len(args) < 2 or not args[1].isdigit():
                return [_make_text_action("⚠️ Use /faq excluir <id> para remover uma FAQ.")]
            removida = await excluir_faq(empresa["id"], int(args[1]))
            if removida:
                invalidar_cache_faq(empresa["id"])
                return [_make_text_action("🗑 FAQ removida com sucesso.")]
            return [_make_text_action("⚠️ FAQ nao encontrada.")]

    faqs = await listar_faqs(empresa["id"])
    if not faqs:
        return [
            _make_text_action(
                f"❔ FAQs - {empresa['nome']}\n\n"
                "Nenhuma FAQ cadastrada ainda.\n"
                "Use /faq adicionar para criar uma."
            )
        ]

    linhas = [
        f"❔ FAQs - {empresa['nome']}",
        "",
        "Use /faq adicionar, /faq excluir <id> ou /faq limpar.",
        "",
    ]
    for faq in faqs:
        linhas.append(f"{faq['id']}. {faq['pergunta']}")
    return [_make_text_action("\n".join(linhas))]


async def _cmd_documentos(*, user_id: int, args: list[str]) -> list[dict[str, str]]:
    empresa = await obter_empresa_por_admin(user_id)
    if not empresa:
        empresa_cliente = await obter_empresa_do_cliente(user_id)
        if empresa_cliente:
            return [_make_text_action(_mensagem_somente_admin())]
        return [_make_text_action("❌ Seu agente ainda nao foi configurado. Use /start primeiro.")]

    if args:
        acao = args[0].lower()
        if acao == "reindexar":
            try:
                quantidade_processada, avisos = await _reindexar_base_empresa(empresa["id"])
            except Exception as exc:
                logger.error("Erro ao reindexar base no WhatsApp: %s", exc, exc_info=True)
                return [_make_text_action("❌ Nao foi possivel reindexar a base agora.")]
            return [_make_text_action(f"✅ Base reindexada com sucesso.\n{_resumo_reindexacao(quantidade_processada, avisos)}")]

        if acao == "reprocessar":
            if len(args) < 2 or not args[1].isdigit():
                return [_make_text_action("⚠️ Use /documentos reprocessar <id>.")]
            documento = await obter_documento_por_id(empresa["id"], int(args[1]))
            if not documento:
                return [_make_text_action("⚠️ Documento nao encontrado.")]
            caminho = _caminho_documento(empresa["id"], documento["nome_arquivo"])
            if not os.path.exists(caminho):
                return [_make_text_action("⚠️ O arquivo nao foi encontrado no disco.")]
            try:
                quantidade_processada, avisos = await _reindexar_base_empresa(empresa["id"])
            except Exception as exc:
                logger.error("Erro ao reprocessar documento no WhatsApp: %s", exc, exc_info=True)
                return [_make_text_action("❌ Nao foi possivel reprocessar esse documento agora.")]
            return [
                _make_text_action(
                    f"✅ Documento reprocessado: {documento['nome_arquivo']}\n"
                    f"{_resumo_reindexacao(quantidade_processada, avisos)}"
                )
            ]

        if acao == "excluir":
            if len(args) < 2 or not args[1].isdigit():
                return [_make_text_action("⚠️ Use /documentos excluir <id>.")]
            documento_id = int(args[1])
            documento = await obter_documento_por_id(empresa["id"], documento_id)
            if not documento:
                return [_make_text_action("⚠️ Documento nao encontrado.")]
            caminho = _caminho_documento(empresa["id"], documento["nome_arquivo"])
            try:
                if os.path.exists(caminho):
                    os.remove(caminho)
                removido = await excluir_documento(empresa["id"], documento_id)
                if not removido:
                    return [_make_text_action("⚠️ Documento nao encontrado.")]
                quantidade_processada, avisos = await _reindexar_base_empresa(empresa["id"])
            except Exception as exc:
                logger.error("Erro ao excluir documento no WhatsApp: %s", exc, exc_info=True)
                return [_make_text_action("❌ Nao foi possivel excluir esse documento agora.")]
            return [
                _make_text_action(
                    f"🗑 Documento excluido: {documento['nome_arquivo']}\n"
                    f"{_resumo_reindexacao(quantidade_processada, avisos)}"
                )
            ]

    docs = await listar_documentos(empresa["id"])
    if not docs:
        return [
            _make_text_action(
                f"📭 Base de conhecimento - {empresa['nome']}\n\n"
                "Nenhum documento enviado ainda.\n"
                "Use /upload ou envie arquivos diretamente neste chat para comecar."
            )
        ]

    linhas = [
        f"📚 Base de conhecimento - {empresa['nome']}",
        "",
        "Comandos:",
        "/documentos reindexar",
        "/documentos reprocessar <id>",
        "/documentos excluir <id>",
        "",
    ]
    for documento in docs:
        linhas.append(f"{documento['id']}. {documento['nome_arquivo']} - {documento['carregado_em']}")
    return [_make_text_action("\n".join(linhas))]


async def _cmd_upload(*, user_id: int, session: WhatsAppSession) -> list[dict[str, str]]:
    empresa = await obter_empresa_por_admin(user_id)
    if not empresa:
        empresa_cliente = await obter_empresa_do_cliente(user_id)
        if empresa_cliente:
            return [_make_text_action(_mensagem_somente_admin())]
        return [_make_text_action("❌ Seu agente ainda nao foi configurado. Use /start primeiro.")]

    _clear_session(session)
    session.state = _STATE_UPLOAD_DOCUMENTO
    return [
        _make_text_action(
            "📄 Envio de documentos\n\n"
            "Envie seus arquivos agora, um de cada vez.\n"
            f"Formatos aceitos: {listar_formatos_suportados()}.\n"
            "Quando terminar, envie /pronto.\n"
            "Voce tambem pode enviar documentos diretamente fora deste modo."
        )
    ]


async def _cmd_imagem(
    *,
    user_id: int,
    args: list[str],
    session: WhatsAppSession,
    message_type: str,
    media_bytes: bytes | None,
) -> list[dict[str, str]]:
    empresa = await obter_empresa_por_admin(user_id)
    if not empresa:
        empresa_cliente = await obter_empresa_do_cliente(user_id)
        if empresa_cliente:
            return [_make_text_action(_mensagem_somente_admin())]
        return [_make_text_action("❌ Seu agente ainda nao foi configurado. Use /start primeiro.")]

    if args and args[0].lower() in {"remover", "apagar"}:
        removida = excluir_imagem_empresa(empresa["id"])
        if removida:
            return [_make_text_action("✅ A imagem do seu agente foi removida.")]
        return [_make_text_action("ℹ️ Seu agente nao tinha uma imagem configurada.")]

    if message_type == "image" and media_bytes:
        try:
            salvar_imagem_empresa(empresa["id"], media_bytes)
        except (ValueError, InputValidationError) as exc:
            return [_make_text_action(f"⚠️ {exc}")]
        preview = _image_action_from_path(
            obter_caminho_imagem_empresa(empresa["id"]),
            "Preview da imagem atual do seu agente.",
        )
        actions = [_make_text_action("✅ A imagem do seu agente foi atualizada com sucesso.")]
        if preview:
            actions.append(preview)
        return actions

    _clear_session(session)
    session.state = _STATE_IMAGEM
    return [
        _make_text_action(
            "🖼️ Imagem do agente\n\n"
            "Envie uma imagem agora.\n"
            "Se quiser remover a atual, use /imagem remover.\n"
            "Se quiser sair, use /cancelar."
        )
    ]


async def _cmd_editar(*, user_id: int, args: list[str], session: WhatsAppSession) -> list[dict[str, str]]:
    empresa = await obter_empresa_por_admin(user_id)
    if not empresa:
        empresa_cliente = await obter_empresa_do_cliente(user_id)
        if empresa_cliente:
            return [_make_text_action(_mensagem_somente_admin())]
        return [_make_text_action("❌ Seu agente ainda nao foi configurado. Use /start primeiro.")]

    if args:
        campo = _resolve_edit_field(args[0])
        if not campo:
            return [_make_text_action("⚠️ Campo invalido. Use nome, bot, saudacao ou instrucoes.")]
        if len(args) > 1:
            try:
                novo_valor = _apply_field_validation(campo, " ".join(args[1:]))
            except InputValidationError as exc:
                return [_make_text_action(f"⚠️ {exc.message}")]
            await atualizar_empresa(empresa["id"], **{campo: novo_valor})
            return [_make_text_action(f"✅ {_FIELD_LABELS[campo].title()} atualizado para: {novo_valor}")]

        _clear_session(session)
        session.state = _STATE_EDITAR_VALOR
        session.data["campo_editando"] = campo
        return [_make_text_action(f"📝 Envie o novo valor para {_FIELD_LABELS[campo]}.")]

    _clear_session(session)
    session.state = _STATE_EDITAR_CAMPO
    return [
        _make_text_action(
            "⚙️ O que deseja editar?\n\n"
            "Envie um destes campos: nome, bot, saudacao, instrucoes.\n"
            "Ou use o formato direto: /editar nome Novo Nome"
        )
    ]


async def _cmd_reset(*, user_id: int, session: WhatsAppSession) -> list[dict[str, str]]:
    empresa = await obter_empresa_por_admin(user_id)
    if not empresa:
        empresa_cliente = await obter_empresa_do_cliente(user_id)
        if empresa_cliente:
            return [_make_text_action(_mensagem_somente_admin())]
        return [_make_text_action("❌ Seu agente ainda nao foi configurado. Use /start primeiro.")]

    _clear_session(session)
    session.state = _STATE_RESET_CONFIRMACAO
    return [
        _make_text_action(
            f"⚠️ Tem certeza que deseja apagar toda a configuracao de {empresa['nome']}?\n\n"
            "Isso vai remover documentos, FAQs, historico e todos os dados associados.\n"
            "Responda SIM para confirmar ou /cancelar para desistir."
        )
    ]


async def _processar_interacao_agente(
    *,
    session: WhatsAppSession,
    user_id: int,
    text: str,
    resolve_default_company: DefaultCompanyResolver,
    auto_bind_default_company: bool,
) -> list[dict[str, str]]:
    empresa = await obter_empresa_do_usuario(user_id)
    usuario_admin = False
    if empresa:
        usuario_admin = bool(empresa.get("_usuario_admin"))
    else:
        empresa = await resolve_default_company()
        if empresa and auto_bind_default_company:
            await vincular_cliente_empresa(empresa["id"], user_id)
        else:
            empresas = await listar_empresas()
            if len(empresas) > 1 and auto_bind_default_company:
                return _iniciar_selecao_empresa(session, empresas, pending_text=text)
            if len(empresas) == 1 and auto_bind_default_company:
                empresa = empresas[0]
                await vincular_cliente_empresa(empresa["id"], user_id)

        if not empresa:
            return [
                _make_text_action(
                    "👋 Este numero ainda nao foi vinculado a um atendimento.\n"
                    "Aguarde o admin concluir a configuracao do WhatsApp ou compartilhar o acesso correto."
                )
            ]

    if not text:
        return [_make_text_action("No momento eu consigo responder apenas mensagens de texto.")]

    rate_msg = verificar_rate_limit(limiter_mensagens, user_id)
    if rate_msg:
        return [_make_text_action(rate_msg)]

    try:
        pergunta = validar_mensagem_usuario(text)
    except InputValidationError as exc:
        return [_make_text_action(f"⚠️ {exc.message}")]

    resultado = await processar_pergunta(
        empresa=empresa,
        pergunta_bruta=pergunta,
        usuario_id=user_id,
        usuario_admin=usuario_admin,
        faq_loader=listar_faqs,
        registrar_conversa_fn=registrar_conversa,
        rate_limit_checker=verificar_rate_limit,
        message_validator=validar_mensagem_usuario,
        document_checker=empresa_tem_documentos,
        rag_responder=gerar_resposta,
        skip_rate_limit=True,
        skip_validation=True,
        return_context=True,
    )
    resposta, conversa_id = _extrair_resposta_e_conversa_id(resultado)
    if conversa_id is None:
        _definir_feedback_pendente(session, None)
        return [_make_text_action(resposta)]

    feedback_id = await criar_feedback_resposta(
        conversa_id,
        empresa["id"],
        user_id,
        canal="whatsapp",
        resposta_bot=resposta,
    )
    _definir_feedback_pendente(session, feedback_id)
    return [_make_text_action(f"{resposta}\n\n{_FEEDBACK_PROMPT}")]


async def _processar_mensagem_whatsapp_inner(
    *,
    sender: str,
    session: WhatsAppSession,
    text: str,
    message_type: str,
    is_owner_chat: bool = False,
    mime_type: str = "",
    file_name: str = "",
    media_bytes: bytes | None = None,
    resolve_default_company: DefaultCompanyResolver,
    share_link_builder: ShareLinkBuilder | None = None,
) -> list[dict[str, str]]:
    user_id = _coerce_whatsapp_user_id(sender)
    texto = (text or "").strip()
    comando, args = _parse_command(texto)

    if comando == "cancelar":
        _clear_session(session)
        return [_make_text_action("❌ Operacao cancelada.")]

    if comando == "pronto" and session.state == _STATE_UPLOAD_DOCUMENTO:
        _clear_session(session)
        return [
            _make_text_action(
                "✅ Upload concluido.\n\n"
                "Seus documentos ja foram indexados.\n"
                "Use /status para ver o estado atual ou envie uma pergunta para testar."
            )
        ]

    if comando == "pular" and session.state == _STATE_ONBOARDING_INSTRUCOES:
        return await _handle_state_message(
            sender=sender,
            user_id=user_id,
            session=session,
            text="/pular",
            message_type=message_type,
            mime_type=mime_type,
            file_name=file_name,
            media_bytes=media_bytes,
            resolve_default_company=resolve_default_company,
        ) or []

    if session.state == _STATE_ONBOARDING_CONFIRMACAO and comando in {"confirmar", "recomecar"}:
        return await _handle_state_message(
            sender=sender,
            user_id=user_id,
            session=session,
            text=f"/{comando}",
            message_type=message_type,
            mime_type=mime_type,
            file_name=file_name,
            media_bytes=media_bytes,
            resolve_default_company=resolve_default_company,
        ) or []

    if session.state == _STATE_RESET_CONFIRMACAO and comando in {"sim", "confirmar"}:
        return await _handle_state_message(
            sender=sender,
            user_id=user_id,
            session=session,
            text="/sim",
            message_type=message_type,
            mime_type=mime_type,
            file_name=file_name,
            media_bytes=media_bytes,
            resolve_default_company=resolve_default_company,
        ) or []

    if comando:
        rate_msg = verificar_rate_limit(limiter_comandos, user_id)
        if rate_msg:
            return [_make_text_action(rate_msg)]

        if comando == "start":
            return await _cmd_start(
                sender=sender,
                user_id=user_id,
                args=args,
                session=session,
                resolve_default_company=resolve_default_company,
                is_owner_chat=is_owner_chat,
            )
        if comando == "registrar":
            return await _cmd_registrar(
                sender=sender,
                user_id=user_id,
                session=session,
                is_owner_chat=is_owner_chat,
            )
        if comando == "sair":
            return await _cmd_sair(user_id=user_id, session=session)
        if comando == "ajuda":
            return await _cmd_ajuda(
                sender=sender,
                user_id=user_id,
                is_owner_chat=is_owner_chat,
            )
        if comando in {"empresas", "trocar", "trocar_empresa"}:
            return await _cmd_empresas(
                sender=sender,
                user_id=user_id,
                session=session,
                resolve_default_company=resolve_default_company,
                is_owner_chat=is_owner_chat,
            )
        if comando == "meuid":
            return await _cmd_meuid(sender=sender, user_id=user_id)
        if comando == "link":
            return await _cmd_link(user_id=user_id, share_link_builder=share_link_builder)
        if comando == "painel":
            return await _cmd_painel(user_id=user_id)
        if comando == "status":
            return await _cmd_status(user_id=user_id)
        if comando == "pausar":
            return await _cmd_pausar_ativar(user_id=user_id, ativo=False)
        if comando == "ativar":
            return await _cmd_pausar_ativar(user_id=user_id, ativo=True)
        if comando == "template":
            return await _cmd_template(user_id=user_id, args=args)
        if comando == "horario":
            return await _cmd_horario(user_id=user_id, args=args, session=session)
        if comando == "fallback":
            return await _cmd_fallback(user_id=user_id, args=args, session=session)
        if comando == "faq":
            return await _cmd_faq(user_id=user_id, args=args, session=session)
        if comando == "documentos":
            return await _cmd_documentos(user_id=user_id, args=args)
        if comando == "upload":
            return await _cmd_upload(user_id=user_id, session=session)
        if comando == "imagem":
            return await _cmd_imagem(
                user_id=user_id,
                args=args,
                session=session,
                message_type=message_type,
                media_bytes=media_bytes,
            )
        if comando == "editar":
            return await _cmd_editar(user_id=user_id, args=args, session=session)
        if comando == "reset":
            return await _cmd_reset(user_id=user_id, session=session)

        return [_make_text_action("⚠️ Comando nao reconhecido. Use /ajuda para ver as opcoes.")]

    state_result = await _handle_state_message(
        sender=sender,
        user_id=user_id,
        session=session,
        text=texto,
        message_type=message_type,
        mime_type=mime_type,
        file_name=file_name,
        media_bytes=media_bytes,
        resolve_default_company=resolve_default_company,
    )
    if state_result is not None:
        return state_result

    feedback = _extrair_avaliacao_feedback(texto)
    if session.state is None and feedback is not None:
        feedback_id = _feedback_pendente(session)
        if feedback_id is not None:
            _definir_feedback_pendente(session, None)
            salvo = await registrar_feedback_resposta(feedback_id, feedback)
            return [
                _make_text_action(
                    "✅ Obrigado pelo feedback. Vou usar isso para melhorar as proximas respostas."
                    if salvo
                    else "ℹ️ Esse feedback ja tinha sido registrado."
                )
            ]

    empresa_admin = await obter_empresa_por_admin(user_id)
    empresa_cliente = None if empresa_admin else await obter_empresa_do_cliente(user_id)
    pode_iniciar_admin_sem_link = _pode_iniciar_admin_sem_link(
        sender, is_owner_chat=is_owner_chat
    )
    if pode_iniciar_admin_sem_link and not empresa_admin and not empresa_cliente:
        return await _cmd_start(
            sender=sender,
            user_id=user_id,
            args=[],
            session=session,
            resolve_default_company=resolve_default_company,
            is_owner_chat=is_owner_chat,
        )

    if message_type == "document" and media_bytes and empresa_admin:
        return await _processar_documento_recebido(
            user_id=user_id,
            empresa=empresa_admin,
            media_bytes=media_bytes,
            file_name=_guess_filename(message_type, file_name, mime_type),
            modo_upload=False,
        )

    if message_type == "image":
        return [_make_text_action("No momento eu so trato imagens para /imagem. Para conversar, envie texto.")]

    if message_type != "chat":
        return [_make_text_action("No momento eu consigo responder apenas mensagens de texto.")]

    return await _processar_interacao_agente(
        session=session,
        user_id=user_id,
        text=texto,
        resolve_default_company=resolve_default_company,
        auto_bind_default_company=not pode_iniciar_admin_sem_link,
    )


async def processar_mensagem_whatsapp(
    *,
    sender: str,
    text: str,
    message_type: str,
    is_owner_chat: bool = False,
    mime_type: str = "",
    file_name: str = "",
    media_bytes: bytes | None = None,
    resolve_default_company: DefaultCompanyResolver,
    share_link_builder: ShareLinkBuilder | None = None,
) -> list[dict[str, str]]:
    session = await _restaurar_sessao(sender)
    try:
        return await _processar_mensagem_whatsapp_inner(
            sender=sender,
            session=session,
            text=text,
            message_type=message_type,
            is_owner_chat=is_owner_chat,
            mime_type=mime_type,
            file_name=file_name,
            media_bytes=media_bytes,
            resolve_default_company=resolve_default_company,
            share_link_builder=share_link_builder,
        )
    finally:
        await _persistir_sessao(sender, session)
