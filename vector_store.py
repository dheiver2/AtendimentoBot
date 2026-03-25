import os
import shutil
from collections.abc import Mapping, Sequence
from functools import lru_cache

from langchain_community.vectorstores import FAISS

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:  # Compatibilidade temporária com ambientes ainda não atualizados.
    from langchain_community.embeddings import HuggingFaceEmbeddings

from config import VECTOR_STORES_DIR


class VectorStoreIncompatibilityError(RuntimeError):
    """Erro levantado quando o índice FAISS é incompatível com o embedding atual."""


@lru_cache(maxsize=1)
def _get_embeddings():
    modelo = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    return HuggingFaceEmbeddings(model_name=modelo)


def _caminho_store(empresa_id: int) -> str:
    return os.path.join(VECTOR_STORES_DIR, str(empresa_id))


def _assinatura_store(caminho: str) -> tuple[str, float, float]:
    """Cria uma assinatura simples para invalidar cache quando o índice muda em disco."""
    faiss_path = os.path.join(caminho, "index.faiss")
    pkl_path = os.path.join(caminho, "index.pkl")

    try:
        faiss_mtime = os.path.getmtime(faiss_path) if os.path.exists(faiss_path) else 0.0
    except OSError:
        faiss_mtime = 0.0

    try:
        pkl_mtime = os.path.getmtime(pkl_path) if os.path.exists(pkl_path) else 0.0
    except OSError:
        pkl_mtime = 0.0

    return (caminho, faiss_mtime, pkl_mtime)


@lru_cache(maxsize=32)
def _carregar_store_cache(assinatura: tuple[str, float, float]) -> FAISS:
    caminho = assinatura[0]
    embeddings = _get_embeddings()
    return FAISS.load_local(caminho, embeddings, allow_dangerous_deserialization=True)


def adicionar_documentos(
    empresa_id: int,
    chunks: list[str],
    metadados: Mapping[str, object] | None = None,
):
    """Adiciona chunks ao vector store da empresa. Cria se não existir."""
    embeddings = _get_embeddings()
    caminho = _caminho_store(empresa_id)

    meta_list = [dict(metadados or {}) for _ in chunks]

    if os.path.exists(caminho):
        store = _carregar_store_cache(_assinatura_store(caminho))
        store.add_texts(chunks, metadatas=meta_list)
    else:
        store = FAISS.from_texts(chunks, embeddings, metadatas=meta_list)

    store.save_local(caminho)
    _carregar_store_cache.cache_clear()


def substituir_documentos(
    empresa_id: int,
    documentos: Sequence[tuple[list[str], Mapping[str, object] | None]],
):
    """Reconstrói o vector store da empresa a partir de uma nova lista de documentos."""
    caminho = _caminho_store(empresa_id)
    if os.path.exists(caminho):
        shutil.rmtree(caminho, ignore_errors=True)
        _carregar_store_cache.cache_clear()

    if not documentos:
        return

    embeddings = _get_embeddings()
    textos: list[str] = []
    metadados: list[dict[str, object]] = []

    for chunks, meta in documentos:
        if not chunks:
            continue
        textos.extend(chunks)
        metadados.extend([dict(meta or {}) for _ in chunks])

    if not textos:
        return

    store = FAISS.from_texts(textos, embeddings, metadatas=metadados)
    store.save_local(caminho)
    _carregar_store_cache.cache_clear()


def buscar_contexto(empresa_id: int, pergunta: str, k: int = 4) -> list[str]:
    """Busca os chunks mais relevantes para a pergunta."""
    caminho = _caminho_store(empresa_id)

    if not os.path.exists(caminho):
        return []

    store = _carregar_store_cache(_assinatura_store(caminho))

    try:
        docs = store.similarity_search(pergunta, k=k)
    except (AssertionError, ValueError, RuntimeError) as exc:
        raise VectorStoreIncompatibilityError(
            "A base vetorial desta empresa ficou incompatível com o embedding atual. "
            "Reindexe a base em /documentos > Reindexar Base para corrigir."
        ) from exc
    return [doc.page_content for doc in docs]


def empresa_tem_documentos(empresa_id: int) -> bool:
    """Verifica se a empresa já tem um vector store."""
    return os.path.exists(_caminho_store(empresa_id))
