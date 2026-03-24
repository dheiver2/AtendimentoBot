"""Métricas simples em memória para acompanhamento do atendimento."""
import asyncio
import logging
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from time import time

from database import (
    listar_metricas_empresa,
    registrar_metrica_atendimento_db,
    registrar_metrica_rag_db,
)

_MAX_EVENTOS_POR_EMPRESA = 200
_JANELA_RESUMO_SEGUNDOS = 24 * 60 * 60
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AtendimentoMetric:
    timestamp: float
    decisao: str
    total_segundos: float
    usou_rag: bool
    sucesso: bool


@dataclass(frozen=True)
class RagMetric:
    timestamp: float
    total_segundos: float
    cache_hit: bool
    sucesso: bool


_metricas_atendimento: dict[int, deque[AtendimentoMetric]] = defaultdict(
    lambda: deque(maxlen=_MAX_EVENTOS_POR_EMPRESA)
)
_metricas_rag: dict[int, deque[RagMetric]] = defaultdict(
    lambda: deque(maxlen=_MAX_EVENTOS_POR_EMPRESA)
)


def _filtrar_janela(eventos: deque, agora: float) -> list:
    limite = agora - _JANELA_RESUMO_SEGUNDOS
    return [evento for evento in eventos if evento.timestamp >= limite]


def _media(valores: list[float]) -> float:
    if not valores:
        return 0.0
    return sum(valores) / len(valores)


def _percentil(valores: list[float], percentil: float) -> float:
    if not valores:
        return 0.0

    ordenados = sorted(valores)
    if len(ordenados) == 1:
        return ordenados[0]

    indice = round((len(ordenados) - 1) * percentil)
    return ordenados[indice]


def _log_task_exception(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception as exc:
        logger.warning("Falha ao persistir métrica em background: %s", exc, exc_info=True)


def _agendar_persistencia(coro) -> None:
    try:
        task = asyncio.create_task(coro)
    except RuntimeError:
        return
    task.add_done_callback(_log_task_exception)


def _construir_resumo(atendimentos: list[AtendimentoMetric], rags: list[RagMetric]) -> dict | None:
    if not atendimentos and not rags:
        return None

    totais = [evento.total_segundos for evento in atendimentos]
    decisoes = Counter(evento.decisao for evento in atendimentos)
    total_atendimentos = len(atendimentos)
    total_sucessos = sum(1 for evento in atendimentos if evento.sucesso)
    total_rag = sum(1 for evento in atendimentos if evento.usou_rag)

    tempos_rag = [evento.total_segundos for evento in rags]
    total_rag_exec = len(rags)
    total_rag_cache = sum(1 for evento in rags if evento.cache_hit)
    total_rag_ok = sum(1 for evento in rags if evento.sucesso)

    return {
        "janela_horas": 24,
        "atendimentos": {
            "total": total_atendimentos,
            "media_segundos": _media(totais),
            "p95_segundos": _percentil(totais, 0.95),
            "taxa_rag": (total_rag / total_atendimentos) if total_atendimentos else 0.0,
            "taxa_sucesso": (total_sucessos / total_atendimentos) if total_atendimentos else 0.0,
            "decisoes": dict(decisoes),
        },
        "rag": {
            "total": total_rag_exec,
            "media_segundos": _media(tempos_rag),
            "p95_segundos": _percentil(tempos_rag, 0.95),
            "taxa_cache_hit": (total_rag_cache / total_rag_exec) if total_rag_exec else 0.0,
            "taxa_sucesso": (total_rag_ok / total_rag_exec) if total_rag_exec else 0.0,
        },
    }


def registrar_metrica_atendimento(
    empresa_id: int,
    decisao: str,
    total_segundos: float,
    usou_rag: bool,
    sucesso: bool,
) -> None:
    """Registra uma resposta concluída para resumo operacional."""
    _metricas_atendimento[empresa_id].append(
        AtendimentoMetric(
            timestamp=time(),
            decisao=decisao,
            total_segundos=total_segundos,
            usou_rag=usou_rag,
            sucesso=sucesso,
        )
    )
    _agendar_persistencia(
        registrar_metrica_atendimento_db(
            empresa_id=empresa_id,
            decisao=decisao,
            total_segundos=total_segundos,
            usou_rag=usou_rag,
            sucesso=sucesso,
        )
    )


def registrar_metrica_rag(
    empresa_id: int,
    total_segundos: float,
    cache_hit: bool,
    sucesso: bool,
) -> None:
    """Registra uma execução do RAG para análise de latência."""
    _metricas_rag[empresa_id].append(
        RagMetric(
            timestamp=time(),
            total_segundos=total_segundos,
            cache_hit=cache_hit,
            sucesso=sucesso,
        )
    )
    _agendar_persistencia(
        registrar_metrica_rag_db(
            empresa_id=empresa_id,
            total_segundos=total_segundos,
            cache_hit=cache_hit,
            sucesso=sucesso,
        )
    )


async def obter_resumo_metricas_empresa(empresa_id: int) -> dict | None:
    """Retorna um resumo recente das métricas da empresa."""
    rows = await listar_metricas_empresa(empresa_id, janela_horas=24)
    if rows:
        atendimentos = [
            AtendimentoMetric(
                timestamp=0.0,
                decisao=row["decisao"] or "",
                total_segundos=float(row["total_segundos"]),
                usou_rag=bool(row["usou_rag"]),
                sucesso=bool(row["sucesso"]),
            )
            for row in rows
            if row["tipo"] == "atendimento"
        ]
        rags = [
            RagMetric(
                timestamp=0.0,
                total_segundos=float(row["total_segundos"]),
                cache_hit=bool(row["cache_hit"]),
                sucesso=bool(row["sucesso"]),
            )
            for row in rows
            if row["tipo"] == "rag"
        ]
        return _construir_resumo(atendimentos, rags)

    agora = time()
    atendimentos = _filtrar_janela(_metricas_atendimento[empresa_id], agora)
    rags = _filtrar_janela(_metricas_rag[empresa_id], agora)
    return _construir_resumo(atendimentos, rags)
