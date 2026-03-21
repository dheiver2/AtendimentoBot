import os

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from vector_store import buscar_contexto


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
            "Responda com explicação mais completa, cobrindo os pontos principais da pergunta. "
            "Se ajudar, organize em passos curtos ou tópicos curtos. Evite enrolação e repetição.",
            6,
            896,
        )

    if total_palavras <= 6 or any(gatilho in pergunta_limpa for gatilho in gatilhos_curtos):
        return (
            "Responda de forma curta e direta, preferencialmente em 1 frase ou até 3 linhas. "
            "Só acrescente detalhe extra se for indispensável para não gerar dúvida.",
            3,
            320,
        )

    return (
        "Responda em tamanho médio: um parágrafo curto ou uma lista curta se isso deixar a resposta mais clara. "
        "Seja útil sem ficar prolixo.",
        4,
        512,
    )


async def gerar_resposta(
    empresa_id: int,
    nome_empresa: str,
    nome_bot: str,
    instrucoes: str,
    pergunta: str,
) -> str:
    """Gera resposta usando RAG com Gemini."""
    instrucoes_resposta, quantidade_chunks, max_tokens = _classificar_dosagem_resposta(pergunta)

    # Busca contexto relevante nos documentos
    chunks = buscar_contexto(empresa_id, pergunta, k=quantidade_chunks)

    if not chunks:
        return (
            "Desculpe, ainda não tenho documentos carregados para responder sua pergunta. "
            "Por favor, aguarde a configuração ser concluída ou entre em contato diretamente com a empresa."
        )

    contexto = "\n\n---\n\n".join(chunks)

    prompt = ChatPromptTemplate.from_template(TEMPLATE)
    modelo = os.getenv("GOOGLE_GENERATION_MODEL", "gemini-2.5-flash")

    llm = ChatGoogleGenerativeAI(
        model=modelo,
        temperature=0.3,
        max_tokens=max_tokens,
    )

    chain = prompt | llm

    resposta = await chain.ainvoke({
        "nome_bot": nome_bot,
        "nome_empresa": nome_empresa,
        "instrucoes": instrucoes,
        "contexto": contexto,
        "instrucoes_resposta": instrucoes_resposta,
        "pergunta": pergunta,
    })

    return resposta.content
