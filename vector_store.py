import os
import shutil

from langchain_community.vectorstores import FAISS

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:  # Compatibilidade temporária com ambientes ainda não atualizados.
    from langchain_community.embeddings import HuggingFaceEmbeddings

from config import VECTOR_STORES_DIR


class VectorStoreIncompatibilityError(RuntimeError):
    """Erro levantado quando o índice FAISS é incompatível com o embedding atual."""


def _get_embeddings():
    modelo = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    return HuggingFaceEmbeddings(model_name=modelo)


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
    dimensao_consulta = len(embeddings.embed_query(pergunta))
    dimensao_indice = store.index.d
    if dimensao_consulta != dimensao_indice:
        raise VectorStoreIncompatibilityError(
            "A base vetorial desta empresa foi criada com outro modelo de embeddings. "
            "Reindexe a base em /documentos > Reindexar Base para voltar a responder."
        )

    try:
        docs = store.similarity_search(pergunta, k=k)
    except AssertionError as exc:
        raise VectorStoreIncompatibilityError(
            "A base vetorial desta empresa ficou incompatível com o embedding atual. "
            "Reindexe a base em /documentos > Reindexar Base para corrigir."
        ) from exc
    return [doc.page_content for doc in docs]


def empresa_tem_documentos(empresa_id: int) -> bool:
    """Verifica se a empresa já tem um vector store."""
    return os.path.exists(_caminho_store(empresa_id))
