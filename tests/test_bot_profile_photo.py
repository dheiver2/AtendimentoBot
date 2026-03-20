import unittest
from io import BytesIO

from PIL import Image

import bot_profile_photo


class BotProfilePhotoTests(unittest.TestCase):
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
