import logging
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha1
from time import perf_counter

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from metrics import registrar_metrica_rag
from vector_store import buscar_contexto, obter_assinatura_contexto

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
logger = logging.getLogger(__name__)
_DEFAULT_TIMEOUT_SECONDS = 18.0
_RESPONSE_CACHE_TTL_SECONDS = 180.0
_RESPONSE_CACHE_MAX_ITEMS = 256
_MAX_HISTORY_TURNS = 4
_MAX_HISTORY_ITEM_CHARS = 280
_MAX_HISTORY_CACHE_CHARS = 1600

# Modelos open-source gratuitos com fallback automático no OpenRouter
_FALLBACK_MODELS = [
    "meta-llama/llama-3.1-8b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "google/gemma-3-12b-it:free",
    "qwen/qwen-2.5-7b-instruct:free",
]


TEMPLATE = """Você é "{nome_bot}", o assistente virtual de atendimento ao cliente da empresa "{nome_empresa}".

INSTRUÇÕES DA EMPRESA E REGRAS OPERACIONAIS:
{instrucoes}

HISTÓRICO RECENTE DA CONVERSA (use para resolver referências como "isso", "esse plano" e "e o premium"):
{historico}

CONTEXTO DOS DOCUMENTOS DA EMPRESA (use para responder):
{contexto}

REGRAS:
- Siga as instruções da empresa e as regras operacionais informadas acima.
- Use o contexto dos documentos como fonte principal para responder sobre produtos, serviços, políticas, preços, prazos e demais fatos do negócio.
- Use o histórico recente apenas para entender o contexto da pergunta atual. Se histórico e documentos divergirem, priorize os documentos e as regras operacionais.
- Se a pergunta atual depender de algo dito antes, resolva essa referência usando o histórico recente antes de responder.
- Se os trechos recuperados não forem suficientes para responder com segurança, diga claramente que não tem essa informação confirmada na base ou faça uma única pergunta objetiva para esclarecer o item específico.
- Se a informação não estiver no contexto dos documentos nem nas regras operacionais acima, diga educadamente que não tem essa informação e sugira entrar em contato com a empresa.
- Seja sempre educado, profissional e objetivo.
- Responda em português do Brasil.
- Não invente informações.
- Ajuste o tamanho da resposta ao tipo de pergunta do cliente.
- Não entregue respostas longas para perguntas simples.
- Não entregue respostas curtas demais para perguntas que pedem explicação, comparação, condições ou passo a passo.
- Ao responder sobre regras, condições, preços, prazos ou requisitos, preserve exceções e detalhes relevantes presentes no contexto.

DOSAGEM DA RESPOSTA:
{instrucoes_resposta}

PERGUNTA DO CLIENTE:
{pergunta}

RESPOSTA:"""


@dataclass
class _ResponseCacheEntry:
    expires_at: float
    content: str


_response_cache: dict[tuple[int, str, str, str, str], _ResponseCacheEntry] = {}


def _classificar_dosagem_resposta(pergunta: str) -> tuple[str, int, int]:
    """Define o nível de detalhe da resposta e a busca de contexto ideal."""
    pergunta_limpa = " ".join((pergunta or "").strip().lower().split())
    palavras = [palavra for palavra in pergunta_limpa.replace("?", " ").split() if palavra]
    total_palavras = len(palavras)

    gatilhos_detalhados = [
        "como",
        "explique",
        "explica",
        "detalhe",
        "detalhado",
        "passo a passo",
        "quais sao",
        "quais são",
        "qual a diferença",
        "diferenca",
        "compare",
        "comparar",
        "por que",
        "porque",
        "condições",
        "condicoes",
        "regras",
        "processo",
        "funciona",
    ]
    gatilhos_curtos = [
        "qual o horario",
        "tem whatsapp",
        "aceita pix",
        "tem garantia",
        "faz entrega",
        "onde fica",
        "telefone",
        "endereço",
        "endereco",
        "preço",
        "preco",
    ]

    if any(gatilho in pergunta_limpa for gatilho in gatilhos_detalhados) or total_palavras >= 14:
        return (
            "Responda com explicação objetiva, cobrindo os pontos principais da pergunta. "
            "Se ajudar, organize em passos curtos ou tópicos curtos. Evite enrolação e repetição.",
            3,
            420,
        )

    if total_palavras <= 6 or any(gatilho in pergunta_limpa for gatilho in gatilhos_curtos):
        return (
            "Responda de forma curta e direta, preferencialmente em 1 frase ou até 3 linhas. "
            "Só acrescente detalhe extra se for indispensável para não gerar dúvida.",
            1,
            180,
        )

    return (
        "Responda em tamanho médio: um parágrafo curto ou uma lista curta se isso deixar a resposta mais clara. "
        "Seja útil sem ficar prolixo.",
        2,
        260,
    )


def _normalizar_fragmento_cache(texto: str) -> str:
    return " ".join((texto or "").strip().lower().split())


def _hash_fragmento_cache(texto: str) -> str:
    return sha1(_normalizar_fragmento_cache(texto).encode("utf-8")).hexdigest()


def _encurtar_texto(texto: str, limite: int) -> str:
    texto_limpo = " ".join((texto or "").split())
    if len(texto_limpo) <= limite:
        return texto_limpo
    return texto_limpo[: max(limite - 3, 0)].rstrip() + "..."


def _formatar_historico_conversa(historico: Sequence[Mapping[str, object]] | None) -> str:
    if not historico:
        return "Sem histórico recente relevante."

    linhas: list[str] = []
    for turno in historico[-_MAX_HISTORY_TURNS:]:
        mensagem_usuario = turno.get("mensagem_usuario")
        resposta_bot = turno.get("resposta_bot")

        if isinstance(mensagem_usuario, str) and mensagem_usuario.strip():
            linhas.append(f"Cliente: {_encurtar_texto(mensagem_usuario, _MAX_HISTORY_ITEM_CHARS)}")
        if isinstance(resposta_bot, str) and resposta_bot.strip():
            linhas.append(f"Assistente: {_encurtar_texto(resposta_bot, _MAX_HISTORY_ITEM_CHARS)}")

    return "\n".join(linhas) if linhas else "Sem histórico recente relevante."


def _serializar_historico_para_cache(historico: Sequence[Mapping[str, object]] | None) -> str:
    return _formatar_historico_conversa(historico)[:_MAX_HISTORY_CACHE_CHARS]


def _pergunta_depende_de_contexto(pergunta: str) -> bool:
    pergunta_limpa = _normalizar_fragmento_cache(pergunta)
    if not pergunta_limpa:
        return False

    palavras = pergunta_limpa.split()
    if len(palavras) > 8:
        return False

    frases_contextuais = {
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
    marcadores_inicio = {
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
        "sim",
        "nao",
        "não",
        "quero",
        "tambem",
        "também",
        "entao",
        "então",
    }
    marcadores_referencia = {
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

    if pergunta_limpa in frases_contextuais:
        return True
    if palavras[0] in marcadores_inicio:
        return True
    return len(palavras) <= 5 and any(token in palavras for token in marcadores_referencia)


def _montar_consulta_recuperacao(
    pergunta: str,
    historico: Sequence[Mapping[str, object]] | None,
) -> str:
    if not historico or not _pergunta_depende_de_contexto(pergunta):
        return pergunta

    partes: list[str] = []
    for turno in historico[-2:]:
        mensagem_usuario = turno.get("mensagem_usuario")
        resposta_bot = turno.get("resposta_bot")
        if isinstance(mensagem_usuario, str) and mensagem_usuario.strip():
            partes.append(f"Cliente: {_encurtar_texto(mensagem_usuario, 180)}")
        if isinstance(resposta_bot, str) and resposta_bot.strip():
            partes.append(f"Assistente: {_encurtar_texto(resposta_bot, 220)}")

    partes.append(f"Pergunta atual: {pergunta}")
    return "\n".join(partes)


def _cache_key(
    empresa_id: int,
    pergunta: str,
    instrucoes: str,
    historico: Sequence[Mapping[str, object]] | None,
    assinatura_contexto: str,
) -> tuple[int, str, str, str, str]:
    return (
        empresa_id,
        _hash_fragmento_cache(pergunta),
        _hash_fragmento_cache(instrucoes),
        _hash_fragmento_cache(_serializar_historico_para_cache(historico)),
        assinatura_contexto,
    )


def _limpar_cache_expirado(agora: float) -> None:
    expiradas = [chave for chave, valor in _response_cache.items() if valor.expires_at <= agora]
    for chave in expiradas:
        _response_cache.pop(chave, None)


def _obter_resposta_cache(
    empresa_id: int,
    pergunta: str,
    instrucoes: str,
    historico: Sequence[Mapping[str, object]] | None,
    assinatura_contexto: str,
    agora: float,
) -> str | None:
    _limpar_cache_expirado(agora)
    entry = _response_cache.get(
        _cache_key(
            empresa_id,
            pergunta,
            instrucoes,
            historico,
            assinatura_contexto,
        )
    )
    if entry and entry.expires_at > agora:
        return entry.content
    return None


def _salvar_resposta_cache(
    empresa_id: int,
    pergunta: str,
    instrucoes: str,
    historico: Sequence[Mapping[str, object]] | None,
    assinatura_contexto: str,
    resposta: str,
    agora: float,
) -> None:
    if len(_response_cache) >= _RESPONSE_CACHE_MAX_ITEMS:
        chave_mais_antiga = min(_response_cache, key=lambda chave: _response_cache[chave].expires_at)
        _response_cache.pop(chave_mais_antiga, None)
    _response_cache[_cache_key(empresa_id, pergunta, instrucoes, historico, assinatura_contexto)] = _ResponseCacheEntry(
        expires_at=agora + _RESPONSE_CACHE_TTL_SECONDS,
        content=resposta,
    )


def _extrair_texto_resposta(resposta: object) -> str:
    """Converte a saída do LangChain para texto simples, mesmo em formatos estruturados."""
    conteudo = getattr(resposta, "content", resposta)

    if isinstance(conteudo, str):
        return conteudo

    if isinstance(conteudo, list):
        partes: list[str] = []
        for item in conteudo:
            if isinstance(item, str) and item.strip():
                partes.append(item.strip())
                continue

            if isinstance(item, dict):
                texto = item.get("text")
                if isinstance(texto, str) and texto.strip():
                    partes.append(texto.strip())

        texto = "\n".join(partes).strip()
        if texto:
            return texto

    texto = str(conteudo).strip()
    if texto:
        return texto

    raise ValueError("Resposta do modelo veio sem conteúdo textual utilizável.")


async def gerar_resposta(
    empresa_id: int,
    nome_empresa: str,
    nome_bot: str,
    instrucoes: str,
    pergunta: str,
    historico: Sequence[Mapping[str, object]] | None = None,
) -> str:
    """Gera resposta usando RAG com OpenRouter (open-source models com fallback)."""
    inicio = perf_counter()
    assinatura_contexto = obter_assinatura_contexto(empresa_id)
    resposta_cache = _obter_resposta_cache(
        empresa_id,
        pergunta,
        instrucoes,
        historico,
        assinatura_contexto,
        inicio,
    )
    if resposta_cache is not None:
        registrar_metrica_rag(empresa_id, 0.0, cache_hit=True, sucesso=True)
        logger.info("Tempo RAG empresa=%s cache_hit=true total=0.00s", empresa_id)
        return resposta_cache

    instrucoes_resposta, quantidade_chunks, max_tokens = _classificar_dosagem_resposta(pergunta)
    consulta_recuperacao = _montar_consulta_recuperacao(pergunta, historico)
    historico_formatado = _formatar_historico_conversa(historico)
    if consulta_recuperacao != pergunta and quantidade_chunks < 2:
        quantidade_chunks = 2
        max_tokens = max(max_tokens, 220)

    # Busca contexto relevante nos documentos
    inicio_busca = perf_counter()
    chunks = buscar_contexto(empresa_id, consulta_recuperacao, k=quantidade_chunks)
    tempo_busca = perf_counter() - inicio_busca

    if not chunks:
        if assinatura_contexto == "missing":
            return (
                "Desculpe, ainda não tenho documentos carregados para responder sua pergunta. "
                "Por favor, aguarde a configuração ser concluída ou entre em contato diretamente com a empresa."
            )
        return (
            "Desculpe, não tenho essa informação confirmada na base da empresa no momento. "
            "Se puder, reformule a pergunta com mais detalhes ou informe o item específico."
        )

    contexto = "\n\n---\n\n".join(chunks)

    prompt = ChatPromptTemplate.from_template(TEMPLATE)

    # Usa variável de ambiente para sobrescrever modelos se necessário
    modelos_env = os.getenv("OPENROUTER_MODELS")
    modelos = (
        [modelo.strip() for modelo in modelos_env.split(",") if modelo.strip()]
        if modelos_env
        else _FALLBACK_MODELS
    )

    usar_fallback_raw = (os.getenv("OPENROUTER_ENABLE_FALLBACK") or "").strip().lower()
    usar_fallback = (
        usar_fallback_raw in {"1", "true", "yes", "on"}
        if usar_fallback_raw
        else len(modelos) > 1
    )
    timeout = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT_SECONDS)))

    extra_body: dict[str, object] = {}
    if usar_fallback and len(modelos) > 1:
        extra_body = {
            "models": modelos,
            "route": "fallback",
        }

    llm = ChatOpenAI(
        model=modelos[0],
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url=_OPENROUTER_BASE_URL,
        temperature=0.2,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=0,
        extra_body=extra_body,
    )

    chain = prompt | llm

    inicio_llm = perf_counter()
    try:
        resposta = await chain.ainvoke({
            "nome_bot": nome_bot,
            "nome_empresa": nome_empresa,
            "instrucoes": instrucoes,
            "historico": historico_formatado,
            "contexto": contexto,
            "instrucoes_resposta": instrucoes_resposta,
            "pergunta": pergunta,
        })
        texto_resposta = _extrair_texto_resposta(resposta)
    except Exception:
        registrar_metrica_rag(
            empresa_id,
            perf_counter() - inicio,
            cache_hit=False,
            sucesso=False,
        )
        logger.warning(
            "Tempo RAG empresa=%s chunks=%s busca=%.2fs llm_timeout_ou_erro=true total=%.2fs modelo=%s fallback=%s timeout=%.1fs",
            empresa_id,
            len(chunks),
            tempo_busca,
            perf_counter() - inicio,
            modelos[0],
            usar_fallback,
            timeout,
            exc_info=True,
        )
        raise
    tempo_llm = perf_counter() - inicio_llm
    _salvar_resposta_cache(
        empresa_id,
        pergunta,
        instrucoes,
        historico,
        assinatura_contexto,
        texto_resposta,
        perf_counter(),
    )
    registrar_metrica_rag(
        empresa_id,
        perf_counter() - inicio,
        cache_hit=False,
        sucesso=True,
    )

    logger.info(
        "Tempo RAG empresa=%s chunks=%s busca=%.2fs llm=%.2fs total=%.2fs modelo=%s fallback=%s timeout=%.1fs",
        empresa_id,
        len(chunks),
        tempo_busca,
        tempo_llm,
        perf_counter() - inicio,
        modelos[0],
        usar_fallback,
        timeout,
    )

    return texto_resposta
