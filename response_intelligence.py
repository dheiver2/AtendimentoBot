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

_FAQ_STOPWORDS = {
    "a",
    "as",
    "com",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "o",
    "os",
    "para",
    "por",
    "qual",
    "quais",
    "que",
    "um",
    "uma",
}

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
    "preco",
    "preço",
    "valor",
    "prazo",
    "documento",
    "documentos",
}

_PERGUNTAS_BAIXA_INFORMACAO_PATTERNS = (
    re.compile(
        r"^(?:quero|queria|gostaria(?:\s+de)?|preciso(?:\s+de)?)\s+"
        r"(?:tirar|esclarecer|sanar)\s+(?:uma?s?\s+)?duvidas?[?!.,:;]*$"
    ),
    re.compile(
        r"^(?:tenho|estou\s+com|to\s+com)\s+(?:uma?s?\s+)?duvidas?[?!.,:;]*$"
    ),
    re.compile(
        r"^(?:quero|queria|gostaria(?:\s+de)?|preciso(?:\s+de)?)\s+"
        r"(?:ajuda|informacao|informacoes|info)[?!.,:;]*$"
    ),
    re.compile(r"^(?:pode\s+)?me\s+ajudar[?!.,:;]*$"),
    re.compile(
        r"^(?:quero|queria|gostaria(?:\s+de)?|preciso(?:\s+de)?)\s+saber\s+mais[?!.,:;]*$"
    ),
    re.compile(r"^(?:qual(?:\s+e)?\s+o\s+)?(?:preco|valor)[?!.,:;]*$"),
    re.compile(r"^quanto\s+custa[?!.,:;]*$"),
    re.compile(r"^(?:qual(?:\s+e)?\s+o\s+)?prazo[?!.,:;]*$"),
    re.compile(r"^(?:quais?\s+(?:sao\s+os\s+)?)?documentos[?!.,:;]*$"),
    re.compile(r"^como\s+funciona(?:\s+isso)?[?!.,:;]*$"),
)

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


@dataclass(frozen=True)
class FaqResolution:
    answer: str | None = None
    ambiguous: bool = False


def normalizar_texto(texto: str) -> str:
    """Normaliza texto para comparações simples."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(char for char in texto if not unicodedata.combining(char))
    return " ".join(texto.lower().strip().split())


def _obter_campo_textual(item: Mapping[str, object], campo: str) -> str:
    """Extrai um campo textual com fallback seguro para string vazia."""
    valor = item.get(campo)
    return valor if isinstance(valor, str) else ""


def _tokens_relevantes(texto: str) -> set[str]:
    return {
        token
        for token in normalizar_texto(texto).split()
        if token and len(token) > 2 and token not in _FAQ_STOPWORDS
    }


def _resolver_resposta_faq(
    pergunta: str,
    faqs: Sequence[Mapping[str, object]],
) -> FaqResolution:
    """Resolve FAQ com guarda contra matches ambíguos ou fracos."""
    pergunta_normalizada = normalizar_texto(pergunta)
    tokens_pergunta = _tokens_relevantes(pergunta_normalizada)
    candidatos: list[tuple[float, float, str, str]] = []

    for faq in faqs:
        pergunta_faq = normalizar_texto(_obter_campo_textual(faq, "pergunta"))
        if not pergunta_faq:
            continue

        resposta_faq = _obter_campo_textual(faq, "resposta")
        if not resposta_faq:
            continue

        if pergunta_normalizada == pergunta_faq:
            return FaqResolution(answer=resposta_faq)

        tokens_faq = _tokens_relevantes(pergunta_faq)
        intersecao = tokens_pergunta & tokens_faq
        cobertura_pergunta = (
            len(intersecao) / len(tokens_pergunta)
            if tokens_pergunta
            else 0.0
        )
        contains = bool(
            pergunta_normalizada
            and (
                pergunta_normalizada in pergunta_faq
                or pergunta_faq in pergunta_normalizada
            )
        )

        score = SequenceMatcher(None, pergunta_normalizada, pergunta_faq).ratio()
        score_efetivo = score
        if contains and cobertura_pergunta >= 0.5:
            score_efetivo = max(score_efetivo, 0.94)
        if cobertura_pergunta:
            score_efetivo = max(score_efetivo, 0.52 + (cobertura_pergunta * 0.38))

        candidatos.append((score_efetivo, cobertura_pergunta, pergunta_faq, resposta_faq))

    if not candidatos:
        return FaqResolution()

    candidatos.sort(key=lambda item: (-item[0], -item[1], item[2]))
    melhor_score, melhor_cobertura, _melhor_pergunta, melhor_resposta = candidatos[0]
    if melhor_score < 0.84 or (tokens_pergunta and melhor_cobertura < 0.5):
        return FaqResolution()

    if len(candidatos) > 1:
        segundo_score, segundo_cobertura, _segundo_pergunta, segunda_resposta = candidatos[1]
        if (
            segunda_resposta != melhor_resposta
            and segundo_score >= 0.82
            and segundo_cobertura >= 0.5
            and (melhor_score - segundo_score) < 0.05
        ):
            return FaqResolution(ambiguous=True)

    return FaqResolution(answer=melhor_resposta)


def buscar_resposta_faq(pergunta: str, faqs: Sequence[Mapping[str, object]]) -> str | None:
    """Busca a resposta mais provável entre FAQs cadastradas."""
    return _resolver_resposta_faq(pergunta, faqs).answer


def detectar_mensagem_trivial(pergunta: str) -> bool:
    """Identifica mensagens sociais/curtas que não precisam de RAG."""
    pergunta_normalizada = normalizar_texto(pergunta)
    if pergunta_normalizada in _MENSAGENS_TRIVIAIS:
        return True

    palavras = pergunta_normalizada.split()
    if len(palavras) <= 2 and all(palavra in _MENSAGENS_TRIVIAIS for palavra in palavras):
        return True

    return False


def detectar_pergunta_baixa_informacao(pergunta: str) -> bool:
    """Identifica pedidos abertos que ainda não trazem assunto suficiente."""
    pergunta_normalizada = normalizar_texto(pergunta)
    if pergunta_normalizada in _PERGUNTAS_BAIXA_INFORMACAO:
        return True

    return any(
        pattern.fullmatch(pergunta_normalizada)
        for pattern in _PERGUNTAS_BAIXA_INFORMACAO_PATTERNS
    )


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

    if "boa tarde" in pergunta_normalizada:
        return "Boa tarde. Como posso ajudar?"
    if "boa noite" in pergunta_normalizada:
        return "Boa noite. Como posso ajudar?"
    if "bom dia" in pergunta_normalizada:
        return "Bom dia. Como posso ajudar?"

    return "Olá. Como posso ajudar?"


def _pergunta_baixa_informacao_exige_base(pergunta: str) -> bool:
    pergunta_normalizada = normalizar_texto(pergunta)
    return any(
        termo in pergunta_normalizada
        for termo in (
            "preco",
            "preço",
            "valor",
            "custa",
            "prazo",
            "entrega",
            "documento",
            "documentos",
            "plano",
            "produto",
            "servico",
            "serviço",
            "funciona",
        )
    )


def resposta_clarificacao(empresa: dict, pergunta: str) -> str:
    """Monta respostas de esclarecimento para mensagens vagas."""
    pergunta_normalizada = normalizar_texto(pergunta)
    resposta: str | None = None

    if any(token in pergunta_normalizada for token in ("preco", "preço", "valor", "custa")):
        resposta = "Claro. De qual produto, plano ou serviço você quer saber o preço?"
    elif any(token in pergunta_normalizada for token in ("prazo", "entrega")):
        resposta = "Claro. Prazo de qual entrega, serviço ou processo você quer confirmar?"
    elif "documento" in pergunta_normalizada:
        resposta = "Claro. Você precisa saber quais documentos para qual serviço, cadastro ou processo?"
    elif any(token in pergunta_normalizada for token in ("plano", "produto", "servico", "serviço", "funciona")):
        resposta = "Claro. Qual plano, produto ou serviço você quer que eu detalhe?"
    elif "duvida" in pergunta_normalizada or "ajuda" in pergunta_normalizada:
        resposta = (
            "Claro. Quais dúvidas você tem sobre a empresa? "
            "Posso ajudar com serviços, preços, prazos, documentos, horários e atendimento."
        )
    elif (
        "informacao" in pergunta_normalizada
        or "informacoes" in pergunta_normalizada
        or "info" in pergunta_normalizada
        or "saber mais" in pergunta_normalizada
    ):
        resposta = (
            "Claro. Sobre o que você quer saber mais? "
            "Se puder, diga o serviço, produto, prazo, documento ou regra que você quer consultar."
        )
    if resposta is None:
        resposta = "Posso ajudar melhor se você mandar uma pergunta mais específica."

    if empresa.get("fallback_contato"):
        resposta += f"\n\nSe preferir atendimento humano: {empresa['fallback_contato']}"

    return resposta


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

    if detectar_pergunta_baixa_informacao(pergunta_normalizada):
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

    pediu_humano = detectar_pedido_humano(pergunta)
    pediu_horario = detectar_pergunta_horario(pergunta)
    tem_fallback = bool(empresa.get("fallback_contato"))
    tem_horario = bool(empresa.get("horario_atendimento"))

    if pediu_humano and pediu_horario:
        linhas: list[str] = []
        if tem_horario:
            linhas.append(f"🕒 Horário de atendimento: {empresa['horario_atendimento']}")
        elif usuario_admin:
            linhas.append("🕒 Você ainda não configurou o horário de atendimento. Use /horario para definir.")
        else:
            linhas.append("🕒 Este atendimento ainda não informou o horário de atendimento.")

        if tem_fallback:
            linhas.append(f"🆘 Para atendimento humano, use este contato: {empresa['fallback_contato']}")
        elif usuario_admin:
            linhas.append("🆘 Você ainda não configurou um contato humano. Use /fallback para definir.")
        else:
            linhas.append("🆘 Este atendimento ainda não informou um contato humano para este canal.")

        return ResponseDecision(
            "human",
            answer="\n".join(linhas),
            reason="hours_and_human_request",
        )

    if pediu_humano:
        return ResponseDecision(
            "human",
            answer=(
                f"🆘 Para atendimento humano, use este contato: {empresa['fallback_contato']}"
                if tem_fallback
                else (
                    "🆘 Você ainda não configurou um contato humano. Use /fallback para definir."
                    if usuario_admin
                    else "🆘 Este atendimento ainda não informou um contato humano para este canal."
                )
            ),
            reason="explicit_human_request" if tem_fallback else "human_request_missing_config",
        )

    if pediu_horario:
        return ResponseDecision(
            "hours",
            answer=(
                f"🕒 Horário de atendimento: {empresa['horario_atendimento']}"
                if tem_horario
                else (
                    "🕒 Você ainda não configurou o horário de atendimento. Use /horario para definir."
                    if usuario_admin
                    else "🕒 Este atendimento ainda não informou o horário de atendimento."
                )
            ),
            reason="hours_request" if tem_horario else "hours_missing_config",
        )

    resolucao_faq = _resolver_resposta_faq(pergunta, faqs)
    if resolucao_faq.answer:
        return ResponseDecision("faq", answer=resolucao_faq.answer, reason="faq_match")
    if resolucao_faq.ambiguous:
        return ResponseDecision(
            "clarify",
            answer=resposta_clarificacao(empresa, pergunta),
            reason="faq_ambiguous",
        )

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

        if detectar_pergunta_baixa_informacao(pergunta):
            if not tem_documentos and _pergunta_baixa_informacao_exige_base(pergunta):
                return ResponseDecision(
                    "no_documents",
                    answer=resposta_sem_base,
                    reason="knowledge_base_missing_admin" if usuario_admin else "knowledge_base_missing_client",
                )
            resposta = resposta_clarificacao(empresa, pergunta)
        else:
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
