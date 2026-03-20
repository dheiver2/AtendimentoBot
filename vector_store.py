import os
import shutil
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from config import VECTOR_STORES_DIR


def _get_embeddings():
    modelo = os.getenv("GOOGLE_EMBEDDING_MODEL", "models/gemini-embedding-001")
    return GoogleGenerativeAIEmbeddings(model=modelo)


def _caminho_store(empresa_id: int) -> str:
    return os.path.join(VECTOR_STORES_DIR, str(empresa_id))


def adicionar_documentos(empresa_id: int, chunks: list[str], metadados: dict | None = None):
    """Adiciona chunks ao vector store da empresa. Cria se não existir."""
    embeddings = _get_embeddings()
    caminho = _caminho_store(empresa_id)

    meta_list = [metadados or {} for _ in chunks]

    if os.path.exists(caminho):
        store = FAISS.load_local(caminho, embeddings, allow_dangerous_deserialization=True)
        store.add_texts(chunks, metadatas=meta_list)
    else:
        store = FAISS.from_texts(chunks, embeddings, metadatas=meta_list)

    store.save_local(caminho)


def substituir_documentos(empresa_id: int, documentos: list[tuple[list[str], dict | None]]):
    """Reconstrói o vector store da empresa a partir de uma nova lista de documentos."""
    caminho = _caminho_store(empresa_id)
    if os.path.exists(caminho):
        shutil.rmtree(caminho, ignore_errors=True)

    if not documentos:
        return

    embeddings = _get_embeddings()
    textos: list[str] = []
    metadados: list[dict] = []

    for chunks, meta in documentos:
        if not chunks:
            continue
        textos.extend(chunks)
        metadados.extend([(meta or {}) for _ in chunks])

    if not textos:
        return

    store = FAISS.from_texts(textos, embeddings, metadatas=metadados)
    store.save_local(caminho)


def buscar_contexto(empresa_id: int, pergunta: str, k: int = 4) -> list[str]:
    """Busca os chunks mais relevantes para a pergunta."""
    embeddings = _get_embeddings()
    caminho = _caminho_store(empresa_id)

    if not os.path.exists(caminho):
        return []

    store = FAISS.load_local(caminho, embeddings, allow_dangerous_deserialization=True)
    docs = store.similarity_search(pergunta, k=k)
    return [doc.page_content for doc in docs]


def empresa_tem_documentos(empresa_id: int) -> bool:
    """Verifica se a empresa já tem um vector store."""
    return os.path.exists(_caminho_store(empresa_id))
