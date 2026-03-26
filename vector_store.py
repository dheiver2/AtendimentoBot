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

_DEFAULT_SEARCH_FETCH_MULTIPLIER = 4
_DEFAULT_SEARCH_FETCH_MIN = 8
_DEFAULT_RELEVANCE_SCORE_THRESHOLD = 0.22
_NEAR_THRESHOLD_MARGIN = 0.08


class VectorStoreIncompatibilityError(RuntimeError):
    """Erro levantado quando o índice FAISS é incompatível com o embedding atual."""


@lru_cache(maxsize=1)
def _get_embeddings():
    modelo = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    return HuggingFaceEmbeddings(model_name=modelo)


def _caminho_store(empresa_id: int) -> str:
    return os.path.join(VECTOR_STORES_DIR, str(empresa_id))


def _obter_stat_arquivo(caminho: str) -> tuple[float, int]:
    try:
        if os.path.exists(caminho):
            return os.path.getmtime(caminho), os.path.getsize(caminho)
    except OSError:
        return 0.0, 0
    return 0.0, 0


def _assinatura_store(caminho: str) -> tuple[str, float, int, float, int]:
    """Cria uma assinatura simples para invalidar cache quando o índice muda em disco."""
    faiss_path = os.path.join(caminho, "index.faiss")
    pkl_path = os.path.join(caminho, "index.pkl")
    faiss_mtime, faiss_size = _obter_stat_arquivo(faiss_path)
    pkl_mtime, pkl_size = _obter_stat_arquivo(pkl_path)
    return (caminho, faiss_mtime, faiss_size, pkl_mtime, pkl_size)

@lru_cache(maxsize=32)
def _carregar_store_cache(assinatura: tuple[str, float, int, float, int]) -> FAISS:
    caminho = assinatura[0]
    embeddings = _get_embeddings()
    return FAISS.load_local(caminho, embeddings, allow_dangerous_deserialization=True)


def _obter_relevance_score_threshold() -> float:
    raw_value = (os.getenv("VECTOR_SEARCH_SCORE_THRESHOLD") or "").strip()
    if not raw_value:
        return _DEFAULT_RELEVANCE_SCORE_THRESHOLD

    try:
        threshold = float(raw_value)
    except ValueError:
        return _DEFAULT_RELEVANCE_SCORE_THRESHOLD

    return max(0.0, min(threshold, 1.0))


def obter_assinatura_contexto(empresa_id: int) -> str:
    """Expõe uma assinatura estável da base para cache de respostas."""
    caminho = _caminho_store(empresa_id)
    if not os.path.exists(caminho):
        return "missing"

    _, faiss_mtime, faiss_size, pkl_mtime, pkl_size = _assinatura_store(caminho)
    return (
        f"faiss:{faiss_mtime:.6f}:{faiss_size}"
        f"|pkl:{pkl_mtime:.6f}:{pkl_size}"
    )


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
    fetch_k = max(k * _DEFAULT_SEARCH_FETCH_MULTIPLIER, _DEFAULT_SEARCH_FETCH_MIN)
    score_threshold = _obter_relevance_score_threshold()

    try:
        docs_com_score = store.similarity_search_with_relevance_scores(
            pergunta,
            k=max(k, 1),
            fetch_k=fetch_k,
            score_threshold=score_threshold,
        )
        if not docs_com_score and score_threshold > 0.0:
            candidatos = store.similarity_search_with_relevance_scores(
                pergunta,
                k=max(k, 1),
                fetch_k=fetch_k,
            )
            if candidatos and candidatos[0][1] >= max(score_threshold - _NEAR_THRESHOLD_MARGIN, 0.0):
                docs_com_score = [candidatos[0]]
    except (AssertionError, ValueError, RuntimeError) as exc:
        raise VectorStoreIncompatibilityError(
            "A base vetorial desta empresa ficou incompatível com o embedding atual. "
            "Reindexe a base em /documentos > Reindexar Base para corrigir."
        ) from exc

    resultados: list[str] = []
    vistos: set[str] = set()
    for doc, _score in docs_com_score:
        conteudo = doc.page_content.strip()
        if not conteudo or conteudo in vistos:
            continue
        vistos.add(conteudo)
        resultados.append(conteudo)
        if len(resultados) >= k:
            break

    return resultados


def empresa_tem_documentos(empresa_id: int) -> bool:
    """Verifica se a empresa já tem um vector store."""
    return os.path.exists(_caminho_store(empresa_id))
