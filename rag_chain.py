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

PERGUNTA DO CLIENTE:
{pergunta}

RESPOSTA:"""


async def gerar_resposta(
    empresa_id: int,
    nome_empresa: str,
    nome_bot: str,
    instrucoes: str,
    pergunta: str,
) -> str:
    """Gera resposta usando RAG com Gemini."""
    # Busca contexto relevante nos documentos
    chunks = buscar_contexto(empresa_id, pergunta, k=4)

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
        max_tokens=1024,
    )

    chain = prompt | llm

    resposta = await chain.ainvoke({
        "nome_bot": nome_bot,
        "nome_empresa": nome_empresa,
        "instrucoes": instrucoes,
        "contexto": contexto,
        "pergunta": pergunta,
    })

    return resposta.content
