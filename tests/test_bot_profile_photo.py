import os
import tempfile
import unittest
from io import BytesIO

from PIL import Image

import bot_profile_photo


class BotProfilePhotoTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_images_dir = bot_profile_photo.IMAGES_DIR
        bot_profile_photo.IMAGES_DIR = self.temp_dir.name

    def tearDown(self):
        bot_profile_photo.IMAGES_DIR = self.original_images_dir
        self.temp_dir.cleanup()

    def _gerar_png_rgba(self) -> bytes:
        imagem = Image.new("RGBA", (16, 16), (255, 0, 0, 128))
        saida = BytesIO()
        imagem.save(saida, format="PNG")
        return saida.getvalue()

    def test_imagem_suportada_por_extensao_ou_mime_type(self):
        self.assertTrue(bot_profile_photo.imagem_suportada("logo.PNG"))
        self.assertTrue(bot_profile_photo.imagem_suportada(mime_type="image/webp"))
        self.assertFalse(bot_profile_photo.imagem_suportada("logo.svg"))

    def test_converter_para_jpg_gera_jpeg_valido(self):
        jpg_bytes = bot_profile_photo.converter_para_jpg(self._gerar_png_rgba())

        self.assertTrue(jpg_bytes.startswith(b"\xff\xd8"))
        self.assertIn(b"JFIF", jpg_bytes[:32])

    def test_converter_para_jpg_rejeita_bytes_invalidos(self):
        with self.assertRaises(ValueError):
            bot_profile_photo.converter_para_jpg(b"nao-e-imagem")

    def test_salvar_e_excluir_imagem_empresa(self):
        caminho = bot_profile_photo.salvar_imagem_empresa(7, self._gerar_png_rgba())

        self.assertTrue(os.path.exists(caminho))
        self.assertTrue(bot_profile_photo.empresa_tem_imagem(7))
        self.assertTrue(bot_profile_photo.excluir_imagem_empresa(7))
        self.assertFalse(bot_profile_photo.empresa_tem_imagem(7))
