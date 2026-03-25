import logging
import os
from dataclasses import dataclass
from time import perf_counter

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from metrics import registrar_metrica_rag
from vector_store import buscar_contexto

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
logger = logging.getLogger(__name__)
_DEFAULT_TIMEOUT_SECONDS = 18.0
_RESPONSE_CACHE_TTL_SECONDS = 180.0
_RESPONSE_CACHE_MAX_ITEMS = 256

# Modelos open-source gratuitos com fallback automático no OpenRouter
_FALLBACK_MODELS = [
    "meta-llama/llama-3.1-8b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "google/gemma-3-12b-it:free",
    "qwen/qwen-2.5-7b-instruct:free",
]


TEMPLATE = """Você é "{nome_bot}", o assistente virtual de atendimento ao cliente da empresa "{nome_empresa}".

INSTRUÇÕES DA EMPRESA:
{instrucoes}

CONTEXTO DOS DOCUMENTOS DA EMPRESA (use para responder):
{contexto}

REGRAS:
- Responda APENAS com base no contexto dos documentos fornecidos acima.
- Se a informação não estiver no contexto, diga educadamente que não tem essa informação e sugira entrar em contato com a empresa.
- Seja sempre educado, profissional e objetivo.
- Responda em português do Brasil.
- Não invente informações.
- Ajuste o tamanho da resposta ao tipo de pergunta do cliente.
- Não entregue respostas longas para perguntas simples.
- Não entregue respostas curtas demais para perguntas que pedem explicação, comparação, condições ou passo a passo.

DOSAGEM DA RESPOSTA:
{instrucoes_resposta}

PERGUNTA DO CLIENTE:
{pergunta}

RESPOSTA:"""


@dataclass
class _ResponseCacheEntry:
    expires_at: float
    content: str


_response_cache: dict[tuple[int, str], _ResponseCacheEntry] = {}


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


def _cache_key(empresa_id: int, pergunta: str) -> tuple[int, str]:
    pergunta_normalizada = " ".join((pergunta or "").strip().lower().split())
    return empresa_id, pergunta_normalizada


def _limpar_cache_expirado(agora: float) -> None:
    expiradas = [chave for chave, valor in _response_cache.items() if valor.expires_at <= agora]
    for chave in expiradas:
        _response_cache.pop(chave, None)


def _obter_resposta_cache(empresa_id: int, pergunta: str, agora: float) -> str | None:
    _limpar_cache_expirado(agora)
    entry = _response_cache.get(_cache_key(empresa_id, pergunta))
    if entry and entry.expires_at > agora:
        return entry.content
    return None


def _salvar_resposta_cache(empresa_id: int, pergunta: str, resposta: str, agora: float) -> None:
    if len(_response_cache) >= _RESPONSE_CACHE_MAX_ITEMS:
        chave_mais_antiga = min(_response_cache, key=lambda chave: _response_cache[chave].expires_at)
        _response_cache.pop(chave_mais_antiga, None)
    _response_cache[_cache_key(empresa_id, pergunta)] = _ResponseCacheEntry(
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
) -> str:
    """Gera resposta usando RAG com OpenRouter (open-source models com fallback)."""
    inicio = perf_counter()
    resposta_cache = _obter_resposta_cache(empresa_id, pergunta, inicio)
    if resposta_cache is not None:
        registrar_metrica_rag(empresa_id, 0.0, cache_hit=True, sucesso=True)
        logger.info("Tempo RAG empresa=%s cache_hit=true total=0.00s", empresa_id)
        return resposta_cache

    instrucoes_resposta, quantidade_chunks, max_tokens = _classificar_dosagem_resposta(pergunta)

    # Busca contexto relevante nos documentos
    inicio_busca = perf_counter()
    chunks = buscar_contexto(empresa_id, pergunta, k=quantidade_chunks)
    tempo_busca = perf_counter() - inicio_busca

    if not chunks:
        return (
            "Desculpe, ainda não tenho documentos carregados para responder sua pergunta. "
            "Por favor, aguarde a configuração ser concluída ou entre em contato diretamente com a empresa."
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

    usar_fallback = os.getenv("OPENROUTER_ENABLE_FALLBACK", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
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
        temperature=0.3,
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
    _salvar_resposta_cache(empresa_id, pergunta, texto_resposta, perf_counter())
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
