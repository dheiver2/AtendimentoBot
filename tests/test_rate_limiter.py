import time
import unittest

from rate_limiter import RateLimiter, verificar_rate_limit


class RateLimiterTests(unittest.TestCase):
    def test_permite_dentro_do_limite(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)

        self.assertTrue(limiter.permitir(1))
        self.assertTrue(limiter.permitir(1))
        self.assertTrue(limiter.permitir(1))

    def test_bloqueia_apos_exceder_limite(self):
        limiter = RateLimiter(max_requests=2, window_seconds=60)

        self.assertTrue(limiter.permitir(1))
        self.assertTrue(limiter.permitir(1))
        self.assertFalse(limiter.permitir(1))

    def test_usuarios_diferentes_sao_independentes(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)

        self.assertTrue(limiter.permitir(1))
        self.assertTrue(limiter.permitir(2))
        self.assertFalse(limiter.permitir(1))

    def test_limpa_apos_janela_expirar(self):
        limiter = RateLimiter(max_requests=1, window_seconds=1)

        self.assertTrue(limiter.permitir(1))
        self.assertFalse(limiter.permitir(1))

        # Simula passagem de tempo
        limiter._requests[1] = [time.monotonic() - 2]
        self.assertTrue(limiter.permitir(1))

    def test_tempo_restante_zero_quando_liberado(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        self.assertEqual(limiter.tempo_restante(1), 0)

    def test_tempo_restante_positivo_quando_bloqueado(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)

        limiter.permitir(1)
        limiter.permitir(1)

        restante = limiter.tempo_restante(1)
        self.assertGreater(restante, 0)
        self.assertLessEqual(restante, 61)


class VerificarRateLimitTests(unittest.TestCase):
    def test_retorna_none_quando_permitido(self):
        limiter = RateLimiter(max_requests=10, window_seconds=60)
        resultado = verificar_rate_limit(limiter, 1)
        self.assertIsNone(resultado)

    def test_retorna_mensagem_quando_bloqueado(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        limiter.permitir(1)

        resultado = verificar_rate_limit(limiter, 1)
        self.assertIsNotNone(resultado)
        self.assertIn("muito rápido", resultado)
        self.assertIn("segundo", resultado)
