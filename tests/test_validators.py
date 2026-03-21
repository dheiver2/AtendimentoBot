import unittest

from validators import (
    InputValidationError,
    sanitizar_nome_arquivo,
    sanitizar_texto,
    validar_faq_pergunta,
    validar_faq_resposta,
    validar_fallback,
    validar_horario,
    validar_instrucoes,
    validar_mensagem_usuario,
    validar_nome_bot,
    validar_nome_empresa,
    validar_saudacao,
    validar_tamanho_documento,
    validar_tamanho_imagem,
    MAX_NOME_EMPRESA,
    MAX_DOCUMENT_SIZE_BYTES,
    MAX_IMAGE_SIZE_BYTES,
)


class SanitizarTextoTests(unittest.TestCase):
    def test_texto_valido_retorna_limpo(self):
        resultado = sanitizar_texto("  Olá Mundo  ", 100, "campo")
        self.assertEqual(resultado, "Olá Mundo")

    def test_texto_vazio_gera_erro(self):
        with self.assertRaises(InputValidationError) as ctx:
            sanitizar_texto("", 100, "campo")
        self.assertIn("não pode ser vazio", ctx.exception.message)

    def test_texto_somente_espacos_gera_erro(self):
        with self.assertRaises(InputValidationError):
            sanitizar_texto("   ", 100, "campo")

    def test_texto_excede_limite_gera_erro(self):
        with self.assertRaises(InputValidationError) as ctx:
            sanitizar_texto("a" * 101, 100, "campo")
        self.assertIn("excede o limite", ctx.exception.message)

    def test_remove_caracteres_de_controle(self):
        texto = "Olá\x00Mundo\x01teste"
        resultado = sanitizar_texto(texto, 100, "campo")
        self.assertEqual(resultado, "OláMundoteste")

    def test_preserva_newlines_e_tabs(self):
        resultado = sanitizar_texto("Linha1\nLinha2\tTab", 100, "campo")
        self.assertIn("\n", resultado)
        self.assertIn("\t", resultado)


class ValidarNomeEmpresaTests(unittest.TestCase):
    def test_nome_valido(self):
        self.assertEqual(validar_nome_empresa("TechCorp"), "TechCorp")

    def test_nome_curto_gera_erro(self):
        with self.assertRaises(InputValidationError):
            validar_nome_empresa("A")

    def test_nome_excede_limite(self):
        with self.assertRaises(InputValidationError):
            validar_nome_empresa("A" * (MAX_NOME_EMPRESA + 1))


class ValidarNomeBotTests(unittest.TestCase):
    def test_nome_valido(self):
        self.assertEqual(validar_nome_bot("Ana"), "Ana")

    def test_nome_curto_gera_erro(self):
        with self.assertRaises(InputValidationError):
            validar_nome_bot("A")


class ValidarSaudacaoTests(unittest.TestCase):
    def test_saudacao_valida(self):
        self.assertEqual(validar_saudacao("Olá! Bem-vindo!"), "Olá! Bem-vindo!")


class ValidarInstrucoesTests(unittest.TestCase):
    def test_instrucoes_validas(self):
        self.assertEqual(validar_instrucoes("Seja educado"), "Seja educado")


class ValidarHorarioTests(unittest.TestCase):
    def test_horario_valido(self):
        self.assertEqual(validar_horario("Seg a Sex, 08h às 18h"), "Seg a Sex, 08h às 18h")


class ValidarFallbackTests(unittest.TestCase):
    def test_fallback_valido(self):
        self.assertEqual(validar_fallback("WhatsApp (11) 99999-9999"), "WhatsApp (11) 99999-9999")


class ValidarFaqTests(unittest.TestCase):
    def test_faq_pergunta_valida(self):
        self.assertEqual(validar_faq_pergunta("Qual o horário?"), "Qual o horário?")

    def test_faq_resposta_valida(self):
        self.assertEqual(validar_faq_resposta("Seg a Sex"), "Seg a Sex")


class ValidarMensagemUsuarioTests(unittest.TestCase):
    def test_mensagem_valida(self):
        self.assertEqual(validar_mensagem_usuario("Olá, bom dia!"), "Olá, bom dia!")

    def test_mensagem_vazia_gera_erro(self):
        with self.assertRaises(InputValidationError):
            validar_mensagem_usuario("")


class ValidarTamanhoDocumentoTests(unittest.TestCase):
    def test_tamanho_valido(self):
        validar_tamanho_documento(1024, "teste.pdf")

    def test_excede_limite(self):
        with self.assertRaises(InputValidationError):
            validar_tamanho_documento(MAX_DOCUMENT_SIZE_BYTES + 1, "teste.pdf")

    def test_arquivo_vazio_gera_erro(self):
        with self.assertRaises(InputValidationError):
            validar_tamanho_documento(0, "teste.pdf")


class ValidarTamanhoImagemTests(unittest.TestCase):
    def test_tamanho_valido(self):
        validar_tamanho_imagem(1024)

    def test_excede_limite(self):
        with self.assertRaises(InputValidationError):
            validar_tamanho_imagem(MAX_IMAGE_SIZE_BYTES + 1)

    def test_imagem_vazia_gera_erro(self):
        with self.assertRaises(InputValidationError):
            validar_tamanho_imagem(0)


class SanitizarNomeArquivoTests(unittest.TestCase):
    def test_nome_valido(self):
        self.assertEqual(sanitizar_nome_arquivo("documento.pdf"), "documento.pdf")

    def test_remove_path_traversal(self):
        self.assertEqual(sanitizar_nome_arquivo("../../etc/passwd"), "passwd")
        self.assertEqual(sanitizar_nome_arquivo("..\\..\\Windows\\System32\\cmd.exe"), "cmd.exe")

    def test_remove_caracteres_perigosos(self):
        resultado = sanitizar_nome_arquivo('doc<teste>.pdf')
        self.assertNotIn("<", resultado)
        self.assertNotIn(">", resultado)

    def test_nome_vazio_gera_erro(self):
        with self.assertRaises(InputValidationError):
            sanitizar_nome_arquivo("")

    def test_nome_somente_pontos_gera_erro(self):
        with self.assertRaises(InputValidationError):
            sanitizar_nome_arquivo("..")

    def test_path_com_barras(self):
        self.assertEqual(sanitizar_nome_arquivo("/caminho/para/arquivo.txt"), "arquivo.txt")
