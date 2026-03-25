"""Testes para metrics.py — resumo, persistência agendada e fallback em memória."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import metrics


class _MetricsStateMixin:
    def setUp(self):
        super().setUp()
        metrics._metricas_atendimento.clear()
        metrics._metricas_rag.clear()


class ConstruirResumoTests(_MetricsStateMixin, unittest.TestCase):
    def test_sem_eventos_retorna_none(self):
        self.assertIsNone(metrics._construir_resumo([], []))

    def test_construi_resumo_com_taxas_e_percentis(self):
        atendimentos = [
            metrics.AtendimentoMetric(timestamp=0.0, decisao="faq", total_segundos=1.0, usou_rag=False, sucesso=True),
            metrics.AtendimentoMetric(timestamp=0.0, decisao="rag", total_segundos=3.0, usou_rag=True, sucesso=False),
        ]
        rags = [
            metrics.RagMetric(timestamp=0.0, total_segundos=2.0, cache_hit=False, sucesso=True),
            metrics.RagMetric(timestamp=0.0, total_segundos=4.0, cache_hit=True, sucesso=False),
        ]

        resumo = metrics._construir_resumo(atendimentos, rags)

        self.assertEqual(resumo["atendimentos"]["total"], 2)
        self.assertEqual(resumo["atendimentos"]["decisoes"]["faq"], 1)
        self.assertEqual(resumo["rag"]["total"], 2)
        self.assertEqual(resumo["rag"]["taxa_cache_hit"], 0.5)


class RegistrarMetricasTests(_MetricsStateMixin, unittest.TestCase):
    @patch("metrics._agendar_persistencia")
    def test_registrar_metrica_atendimento_guarda_em_memoria(self, mock_agendar):
        mock_db = MagicMock(return_value=MagicMock())
        with patch("metrics.registrar_metrica_atendimento_db", new=mock_db):
            metrics.registrar_metrica_atendimento(
                empresa_id=1,
                decisao="faq",
                total_segundos=1.2,
                usou_rag=False,
                sucesso=True,
            )

        self.assertEqual(len(metrics._metricas_atendimento[1]), 1)
        mock_db.assert_called_once()
        mock_agendar.assert_called_once()

    @patch("metrics._agendar_persistencia")
    def test_registrar_metrica_rag_guarda_em_memoria(self, mock_agendar):
        mock_db = MagicMock(return_value=MagicMock())
        with patch("metrics.registrar_metrica_rag_db", new=mock_db):
            metrics.registrar_metrica_rag(
                empresa_id=2,
                total_segundos=2.4,
                cache_hit=True,
                sucesso=True,
            )

        self.assertEqual(len(metrics._metricas_rag[2]), 1)
        mock_db.assert_called_once()
        mock_agendar.assert_called_once()


class ObterResumoMetricasTests(_MetricsStateMixin, unittest.IsolatedAsyncioTestCase):
    @patch("metrics.listar_metricas_empresa", new_callable=AsyncMock)
    async def test_prefere_dados_do_banco(self, mock_listar):
        mock_listar.return_value = [
            {
                "tipo": "atendimento",
                "decisao": "faq",
                "total_segundos": 1.5,
                "usou_rag": 0,
                "cache_hit": 0,
                "sucesso": 1,
            },
            {
                "tipo": "rag",
                "decisao": "",
                "total_segundos": 2.5,
                "usou_rag": 0,
                "cache_hit": 1,
                "sucesso": 1,
            },
        ]

        resumo = await metrics.obter_resumo_metricas_empresa(empresa_id=3)

        self.assertEqual(resumo["atendimentos"]["total"], 1)
        self.assertEqual(resumo["rag"]["total"], 1)
        self.assertEqual(resumo["rag"]["taxa_cache_hit"], 1.0)

    @patch("metrics.listar_metricas_empresa", new_callable=AsyncMock, return_value=[])
    async def test_usa_cache_em_memoria_quando_banco_esta_vazio(self, mock_listar):
        agora = metrics.time()
        metrics._metricas_atendimento[4].append(
            metrics.AtendimentoMetric(
                timestamp=agora,
                decisao="rag",
                total_segundos=1.8,
                usou_rag=True,
                sucesso=True,
            )
        )
        metrics._metricas_rag[4].append(
            metrics.RagMetric(
                timestamp=agora,
                total_segundos=0.9,
                cache_hit=False,
                sucesso=True,
            )
        )

        resumo = await metrics.obter_resumo_metricas_empresa(empresa_id=4)

        mock_listar.assert_awaited_once()
        self.assertEqual(resumo["atendimentos"]["total"], 1)
        self.assertEqual(resumo["rag"]["total"], 1)
        self.assertEqual(resumo["atendimentos"]["taxa_rag"], 1.0)
