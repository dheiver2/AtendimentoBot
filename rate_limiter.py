"""Rate limiter simples em memória para proteger contra abuso."""
import time
from collections import defaultdict


class RateLimiter:
    """Rate limiter por usuário com janela deslizante.

    Armazena timestamps das ações em memória. Limpa automaticamente
    entradas expiradas a cada chamada de verificação.
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
        *,
        label: str = "requisições",
        guidance: str = "",
    ):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._label = label
        self._guidance = guidance
        self._requests: dict[int, list[float]] = defaultdict(list)

    def permitir(self, user_id: int) -> bool:
        """Retorna True se o usuário pode fazer a ação, False se excedeu o limite."""
        agora = time.monotonic()
        limite = agora - self._window_seconds

        # Limpa timestamps expirados
        timestamps = self._requests[user_id]
        self._requests[user_id] = [t for t in timestamps if t > limite]

        if len(self._requests[user_id]) >= self._max_requests:
            return False

        self._requests[user_id].append(agora)
        return True

    def tempo_restante(self, user_id: int) -> int:
        """Retorna os segundos restantes até o usuário poder agir novamente."""
        if not self._requests[user_id]:
            return 0

        agora = time.monotonic()
        mais_antigo = min(self._requests[user_id])
        restante = self._window_seconds - (agora - mais_antigo)
        return max(0, int(restante) + 1)


# ── Limitadores globais ──
# Mensagens para o agente: 20 por minuto por usuário
limiter_mensagens = RateLimiter(
    max_requests=20,
    window_seconds=60,
    label="mensagens",
    guidance="Dica: reúna sua dúvida em uma única mensagem para acelerar o atendimento.",
)

# Upload de documentos: 10 por minuto por usuário
limiter_upload = RateLimiter(
    max_requests=10,
    window_seconds=60,
    label="envios de arquivos",
    guidance="Espere a confirmação de cada arquivo antes de enviar o próximo.",
)

# Criação de FAQ: 20 por minuto por usuário
limiter_faq = RateLimiter(
    max_requests=20,
    window_seconds=60,
    label="alterações de FAQ",
    guidance="Aguarde um pouco antes de cadastrar, excluir ou limpar FAQs novamente.",
)

# Comandos gerais: 30 por minuto por usuário
limiter_comandos = RateLimiter(
    max_requests=30,
    window_seconds=60,
    label="comandos",
    guidance="Evite repetir o mesmo comando várias vezes em sequência.",
)


def verificar_rate_limit(limiter: RateLimiter, user_id: int) -> str | None:
    """Verifica o rate limit e retorna a mensagem de erro ou None se permitido."""
    if limiter.permitir(user_id):
        return None

    segundos = limiter.tempo_restante(user_id)
    mensagem = (
        f"⏳ Você atingiu o limite temporário de {limiter._label}. "
        f"Aguarde {segundos} segundo(s) antes de tentar novamente."
    )
    if limiter._guidance:
        mensagem += f" {limiter._guidance}"
    return mensagem
