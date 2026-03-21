"""Validação e sanitização de entradas do usuário."""
import re
import unicodedata

# ── Limites de texto ──
MAX_NOME_EMPRESA = 100
MAX_NOME_BOT = 60
MAX_SAUDACAO = 500
MAX_INSTRUCOES = 2000
MAX_HORARIO = 300
MAX_FALLBACK = 300
MAX_FAQ_PERGUNTA = 500
MAX_FAQ_RESPOSTA = 2000
MAX_MENSAGEM_USUARIO = 4000

# ── Limites de arquivo ──
MAX_DOCUMENT_SIZE_MB = 20
MAX_DOCUMENT_SIZE_BYTES = MAX_DOCUMENT_SIZE_MB * 1024 * 1024
MAX_IMAGE_SIZE_MB = 10
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024

# ── Limites operacionais ──
MAX_DOCUMENTOS_POR_EMPRESA = 50
MAX_FAQS_POR_EMPRESA = 100


class InputValidationError(Exception):
    """Erro de validação de entrada do usuário."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _limpar_controles(texto: str) -> str:
    """Remove caracteres de controle invisíveis, mantendo espaços e newlines."""
    return "".join(
        char
        for char in texto
        if not unicodedata.category(char).startswith("C") or char in "\n\r\t"
    )


def sanitizar_texto(texto: str, max_len: int, nome_campo: str) -> str:
    """Sanitiza e valida um campo de texto genérico.

    Retorna o texto limpo ou levanta InputValidationError.
    """
    if not texto or not texto.strip():
        raise InputValidationError(f"O campo {nome_campo} não pode ser vazio.")

    texto = _limpar_controles(texto).strip()

    if len(texto) > max_len:
        raise InputValidationError(
            f"O campo {nome_campo} excede o limite de {max_len} caracteres "
            f"(enviado: {len(texto)}). Reduza o texto e tente novamente."
        )

    return texto


def validar_nome_empresa(texto: str) -> str:
    """Valida o nome da empresa."""
    texto = sanitizar_texto(texto, MAX_NOME_EMPRESA, "nome da empresa")
    if len(texto) < 2:
        raise InputValidationError("O nome da empresa deve ter pelo menos 2 caracteres.")
    return texto


def validar_nome_bot(texto: str) -> str:
    """Valida o nome do assistente."""
    texto = sanitizar_texto(texto, MAX_NOME_BOT, "nome do assistente")
    if len(texto) < 2:
        raise InputValidationError("O nome do assistente deve ter pelo menos 2 caracteres.")
    return texto


def validar_saudacao(texto: str) -> str:
    """Valida a mensagem de saudação."""
    return sanitizar_texto(texto, MAX_SAUDACAO, "saudação")


def validar_instrucoes(texto: str) -> str:
    """Valida as instruções do bot."""
    return sanitizar_texto(texto, MAX_INSTRUCOES, "instruções")


def validar_horario(texto: str) -> str:
    """Valida o horário de atendimento."""
    return sanitizar_texto(texto, MAX_HORARIO, "horário de atendimento")


def validar_fallback(texto: str) -> str:
    """Valida o contato de fallback."""
    return sanitizar_texto(texto, MAX_FALLBACK, "contato de fallback")


def validar_faq_pergunta(texto: str) -> str:
    """Valida a pergunta da FAQ."""
    return sanitizar_texto(texto, MAX_FAQ_PERGUNTA, "pergunta da FAQ")


def validar_faq_resposta(texto: str) -> str:
    """Valida a resposta da FAQ."""
    return sanitizar_texto(texto, MAX_FAQ_RESPOSTA, "resposta da FAQ")


def validar_mensagem_usuario(texto: str) -> str:
    """Valida a mensagem do usuário para o agente."""
    return sanitizar_texto(texto, MAX_MENSAGEM_USUARIO, "mensagem")


def validar_tamanho_documento(tamanho_bytes: int, nome_arquivo: str) -> None:
    """Valida o tamanho de um documento enviado."""
    if tamanho_bytes > MAX_DOCUMENT_SIZE_BYTES:
        raise InputValidationError(
            f"O arquivo {nome_arquivo} excede o limite de {MAX_DOCUMENT_SIZE_MB} MB. "
            "Reduza o tamanho do arquivo e tente novamente."
        )

    if tamanho_bytes == 0:
        raise InputValidationError(f"O arquivo {nome_arquivo} está vazio.")


def validar_tamanho_imagem(tamanho_bytes: int) -> None:
    """Valida o tamanho de uma imagem enviada."""
    if tamanho_bytes > MAX_IMAGE_SIZE_BYTES:
        raise InputValidationError(
            f"A imagem excede o limite de {MAX_IMAGE_SIZE_MB} MB. "
            "Reduza o tamanho da imagem e tente novamente."
        )

    if tamanho_bytes == 0:
        raise InputValidationError("A imagem enviada está vazia.")


def sanitizar_nome_arquivo(nome_arquivo: str) -> str:
    """Sanitiza o nome de arquivo para evitar path traversal."""
    if not nome_arquivo:
        raise InputValidationError("Nome de arquivo inválido.")

    # Remove path components
    nome_arquivo = nome_arquivo.replace("\\", "/").split("/")[-1]

    # Remove caracteres perigosos
    nome_arquivo = re.sub(r'[<>:"|?*\x00-\x1f]', "_", nome_arquivo)

    # Impede nomes como .., ., ou vazios
    nome_limpo = nome_arquivo.strip(". ")
    if not nome_limpo:
        raise InputValidationError("Nome de arquivo inválido.")

    return nome_limpo
