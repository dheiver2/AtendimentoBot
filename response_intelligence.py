"""Camada de decisão para escolher a estratégia de resposta do atendimento."""
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

DecisionKind = Literal[
    "paused",
    "human",
    "hours",
    "faq",
    "trivial",
    "clarify",
    "no_documents",
    "rag",
]

_MENSAGENS_TRIVIAIS = {
    "oi",
    "ola",
    "olá",
    "opa",
    "e ai",
    "ei",
    "hey",
    "bom dia",
    "boa tarde",
    "boa noite",
    "obrigado",
    "obrigada",
    "valeu",
    "vlw",
    "ok",
    "oks",
    "okay",
    "blz",
    "beleza",
    "certo",
    "perfeito",
    "entendi",
    "show",
    "top",
    "como vai",
    "tudo bem",
    "td bem",
    "como vc esta",
    "como voce esta",
    "como c vai",
}

_PERGUNTAS_BAIXA_INFORMACAO = {
    "ajuda",
    "me ajuda",
    "preciso de ajuda",
    "socorro",
    "duvida",
    "dúvida",
    "tenho uma duvida",
    "tenho uma dúvida",
    "informacao",
    "informação",
    "info",
}

_CONTINUATION_PHRASES = {
    "sim",
    "nao",
    "não",
    "quero",
    "quero sim",
    "pode ser",
    "isso",
    "esse",
    "essa",
    "esses",
    "essas",
    "outro",
    "outra",
    "o premium",
    "no premium",
    "o basico",
    "o básico",
    "no basico",
    "no básico",
}

_CONTINUATION_START_TOKENS = {
    "e",
    "mas",
    "esse",
    "essa",
    "esses",
    "essas",
    "isso",
    "ele",
    "ela",
    "eles",
    "elas",
    "nele",
    "nela",
    "sim",
    "nao",
    "não",
    "quero",
    "tambem",
    "também",
    "entao",
    "então",
}

_CONTINUATION_REFERENCE_TOKENS = {
    "esse",
    "essa",
    "esses",
    "essas",
    "isso",
    "ele",
    "ela",
    "eles",
    "elas",
    "premium",
    "basico",
    "básico",
    "plano",
    "opcao",
    "opção",
}

_HUMAN_REQUEST_FRAGMENTS = (
    "falar com atendente",
    "falar com humano",
    "atendimento humano",
    "quero um atendente",
    "quero falar com alguem",
    "quero falar com uma pessoa",
    "me encaminha para um atendente",
)

_HUMAN_CONTACT_PATTERNS = (
    re.compile(
        r"\b(?:qual\s+e\s+o|qual\s+o|preciso\s+do|preciso\s+de|quero\s+o|quero\s+um)\b"
        r"(?:\s+\w+){0,3}\s+(?:telefone|whatsapp|numero|contato)\b"
    ),
    re.compile(
        r"\bme\s+(?:passa|passe|informa|informe)\b"
        r"(?:\s+\w+){0,3}\s+(?:telefone|whatsapp|numero|contato)\b"
    ),
    re.compile(
        r"\b(?:telefone|whatsapp|numero|contato)\s+"
        r"(?:de\s+contato|da\s+empresa|do\s+suporte|humano)\b"
    ),
)

_SHORT_HUMAN_CONTACT_TOKENS = {"telefone", "whatsapp", "numero", "contato"}

_HOURS_REQUEST_FRAGMENTS = (
    "horario de atendimento",
    "horario de funcionamento",
    "qual o horario",
    "qual e o horario",
    "que horas",
    "aberto agora",
    "esta aberto",
    "estao abertos",
    "estarao abertos",
    "funcionamento",
    "expediente",
)

_HOURS_REQUEST_PATTERNS = (
    re.compile(
        r"\b(?:abre|abrem|fecha|fecham|funciona|funcionam)\b"
        r"(?:\s+\w+){0,3}\s+\b(?:hoje|amanha|agora)\b"
    ),
)


@dataclass(frozen=True)
class ResponseDecision:
    kind: DecisionKind
    answer: str | None = None
    reason: str | None = None


def normalizar_texto(texto: str) -> str:
    """Normaliza texto para comparações simples."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(char for char in texto if not unicodedata.combining(char))
    return " ".join(texto.lower().strip().split())


def _obter_campo_textual(item: Mapping[str, object], campo: str) -> str:
    """Extrai um campo textual com fallback seguro para string vazia."""
    valor = item.get(campo)
    return valor if isinstance(valor, str) else ""


def buscar_resposta_faq(pergunta: str, faqs: Sequence[Mapping[str, object]]) -> str | None:
    """Busca a resposta mais provável entre FAQs cadastradas."""
    pergunta_normalizada = normalizar_texto(pergunta)
    melhor_resposta: str | None = None
    melhor_score = 0.0

    for faq in faqs:
        pergunta_faq = normalizar_texto(_obter_campo_textual(faq, "pergunta"))
        if not pergunta_faq:
            continue

        resposta_faq = _obter_campo_textual(faq, "resposta")
        if not resposta_faq:
            continue

        if (
            pergunta_normalizada == pergunta_faq
            or pergunta_normalizada in pergunta_faq
            or pergunta_faq in pergunta_normalizada
        ):
            return resposta_faq

        score = SequenceMatcher(None, pergunta_normalizada, pergunta_faq).ratio()
        if score > melhor_score:
            melhor_score = score
            melhor_resposta = resposta_faq

    if melhor_score >= 0.82:
        return melhor_resposta

    return None


def detectar_mensagem_trivial(pergunta: str) -> bool:
    """Identifica mensagens sociais/curtas que não precisam de RAG."""
    pergunta_normalizada = normalizar_texto(pergunta)
    if pergunta_normalizada in _MENSAGENS_TRIVIAIS:
        return True

    palavras = pergunta_normalizada.split()
    if len(palavras) <= 2 and all(palavra in _MENSAGENS_TRIVIAIS for palavra in palavras):
        return True

    return False


def resposta_trivial(empresa: dict, pergunta: str) -> str:
    """Monta respostas curtas para mensagens sociais."""
    pergunta_normalizada = normalizar_texto(pergunta)

    if any(token in pergunta_normalizada for token in ("obrigado", "obrigada", "valeu", "vlw")):
        return "Por nada. Se quiser, pode me mandar sua próxima dúvida."

    if any(
        token in pergunta_normalizada
        for token in ("ok", "okay", "certo", "perfeito", "entendi", "beleza", "blz", "show", "top")
    ):
        return "Certo. Quando quiser, envie sua dúvida."

    if any(
        token in pergunta_normalizada
        for token in ("como vai", "tudo bem", "td bem", "como vc esta", "como voce esta", "como c vai")
    ):
        return "Estou bem e pronto para ajudar. Qual é a sua dúvida?"

    return empresa.get("saudacao") or "Olá. Como posso ajudar?"


def detectar_pedido_humano(pergunta: str) -> bool:
    """Detecta pedidos explícitos de encaminhamento para humano/contato."""
    pergunta_normalizada = normalizar_texto(pergunta)
    if any(gatilho in pergunta_normalizada for gatilho in _HUMAN_REQUEST_FRAGMENTS):
        return True

    if any(pattern.search(pergunta_normalizada) for pattern in _HUMAN_CONTACT_PATTERNS):
        return True

    palavras = [palavra.strip("?!.,:;") for palavra in pergunta_normalizada.split()]
    return len(palavras) <= 2 and any(palavra in _SHORT_HUMAN_CONTACT_TOKENS for palavra in palavras)


def detectar_pergunta_horario(pergunta: str) -> bool:
    """Detecta perguntas sobre horário de atendimento."""
    pergunta_normalizada = normalizar_texto(pergunta)
    if any(gatilho in pergunta_normalizada for gatilho in _HOURS_REQUEST_FRAGMENTS):
        return True

    return any(pattern.search(pergunta_normalizada) for pattern in _HOURS_REQUEST_PATTERNS)


def detectar_continuacao_contextual(
    pergunta: str,
    historico_recente: Sequence[Mapping[str, object]] | None,
) -> bool:
    """Detecta perguntas curtas que dependem do turno anterior para fazer sentido."""
    if not historico_recente:
        return False

    pergunta_normalizada = normalizar_texto(pergunta)
    if not pergunta_normalizada:
        return False

    palavras = [palavra.strip("?!.,:;") for palavra in pergunta_normalizada.split() if palavra]
    if not palavras or len(palavras) > 6:
        return False

    if pergunta_normalizada in _CONTINUATION_PHRASES:
        return True

    if palavras[0] in _CONTINUATION_START_TOKENS:
        return True

    if len(palavras) <= 4 and any(token in palavras for token in _CONTINUATION_REFERENCE_TOKENS):
        return True

    return False


def deve_usar_rag(pergunta: str) -> bool:
    """Decide se vale consultar a base vetorial para a pergunta."""
    pergunta_normalizada = normalizar_texto(pergunta)
    if detectar_mensagem_trivial(pergunta_normalizada):
        return False

    if pergunta_normalizada in _PERGUNTAS_BAIXA_INFORMACAO:
        return False

    palavras = pergunta_normalizada.split()
    if len(palavras) == 1 and not any(char.isdigit() for char in pergunta_normalizada):
        return False

    gatilhos_rag = [
        "o que e",
        "oque e",
        "quem e",
        "quem somos",
        "sobre a clinica",
        "sobre a empresa",
        "sobre voces",
        "sobre nos",
        "clinica",
        "clínica",
        "empresa",
        "servicos",
        "serviços",
        "preco",
        "preços",
        "preço",
        "valor",
        "custa",
        "prazo",
        "entrega",
        "troca",
        "devolucao",
        "devolução",
        "garantia",
        "contrato",
        "plano",
        "servico",
        "serviço",
        "produto",
        "produtos",
        "pagamento",
        "pix",
        "cartao",
        "cartão",
        "boleto",
        "documento",
        "documentos",
        "politica",
        "política",
        "regra",
        "regras",
        "como",
        "quais",
        "qual",
        "funciona",
        "passo",
        "processo",
        "o que",
        "quem",
        "onde",
        "diferenca",
        "diferença",
        "compar",
        "cancel",
        "suporte",
    ]
    if any(gatilho in pergunta_normalizada for gatilho in gatilhos_rag):
        return True

    return len(palavras) >= 2


def decidir_resposta(
    pergunta: str,
    empresa: dict,
    faqs: list[dict] | None,
    usuario_admin: bool,
    tem_documentos: bool,
    resposta_pausado: str,
    resposta_sem_base: str,
    historico_recente: Sequence[Mapping[str, object]] | None = None,
) -> ResponseDecision:
    """Classifica a mensagem e escolhe a estratégia de resposta."""
    if not pergunta or not pergunta.strip():
        return ResponseDecision("clarify", answer="Não recebi sua mensagem. Pode repetir?", reason="empty_input")

    faqs = faqs or []

    if not bool(empresa.get("ativo", 1)):
        return ResponseDecision("paused", answer=resposta_pausado, reason="agent_paused")

    solicitou_humano = bool(empresa.get("fallback_contato")) and detectar_pedido_humano(pergunta)
    solicitou_horario = bool(empresa.get("horario_atendimento")) and detectar_pergunta_horario(pergunta)

    if solicitou_humano and solicitou_horario:
        return ResponseDecision(
            "human",
            answer=(
                f"🕒 Horário de atendimento: {empresa['horario_atendimento']}\n"
                f"🆘 Para atendimento humano, use este contato: {empresa['fallback_contato']}"
            ),
            reason="hours_and_human_request",
        )

    if solicitou_humano:
        return ResponseDecision(
            "human",
            answer=f"🆘 Para atendimento humano, use este contato: {empresa['fallback_contato']}",
            reason="explicit_human_request",
        )

    if solicitou_horario:
        return ResponseDecision(
            "hours",
            answer=f"🕒 Horário de atendimento: {empresa['horario_atendimento']}",
            reason="hours_request",
        )

    resposta_faq = buscar_resposta_faq(pergunta, faqs)
    if resposta_faq:
        return ResponseDecision("faq", answer=resposta_faq, reason="faq_match")

    if detectar_mensagem_trivial(pergunta):
        return ResponseDecision("trivial", answer=resposta_trivial(empresa, pergunta), reason="smalltalk")

    if not deve_usar_rag(pergunta):
        if detectar_continuacao_contextual(pergunta, historico_recente):
            if not tem_documentos:
                return ResponseDecision(
                    "no_documents",
                    answer=resposta_sem_base,
                    reason="knowledge_base_missing_admin" if usuario_admin else "knowledge_base_missing_client",
                )
            return ResponseDecision("rag", reason="contextual_followup")

        resposta = "Posso ajudar melhor se você mandar uma pergunta mais específica."
        if empresa.get("fallback_contato"):
            resposta += f"\n\nSe preferir atendimento humano: {empresa['fallback_contato']}"
        return ResponseDecision("clarify", answer=resposta, reason="low_information_question")

    if not tem_documentos:
        return ResponseDecision(
            "no_documents",
            answer=resposta_sem_base,
            reason="knowledge_base_missing_admin" if usuario_admin else "knowledge_base_missing_client",
        )

    return ResponseDecision("rag", reason="document_lookup_needed")
