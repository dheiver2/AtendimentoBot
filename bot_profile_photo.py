import os
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from config import IMAGES_DIR

SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".gif",
}

SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/bmp",
    "image/gif",
}


def listar_formatos_imagem_suportados() -> str:
    """Retorna a lista curta dos formatos de imagem suportados na entrada."""
    return ", ".join(sorted(SUPPORTED_IMAGE_EXTENSIONS))


def imagem_suportada(nome_arquivo: str | None = None, mime_type: str | None = None) -> bool:
    """Valida se o arquivo recebido é uma imagem suportada."""
    if mime_type and mime_type.lower() in SUPPORTED_IMAGE_MIME_TYPES:
        return True

    if nome_arquivo:
        return Path(nome_arquivo).suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS

    return False


def converter_para_jpg(conteudo_bytes: bytes) -> bytes:
    """Converte uma imagem suportada para JPG."""
    try:
        with Image.open(BytesIO(conteudo_bytes)) as imagem:
            imagem = ImageOps.exif_transpose(imagem)

            if getattr(imagem, "is_animated", False):
                imagem.seek(0)

            if imagem.mode in {"RGBA", "LA"} or (
                imagem.mode == "P" and "transparency" in imagem.info
            ):
                imagem_rgba = imagem.convert("RGBA")
                fundo = Image.new("RGB", imagem_rgba.size, (255, 255, 255))
                fundo.paste(imagem_rgba, mask=imagem_rgba.getchannel("A"))
                imagem_final = fundo
            else:
                imagem_final = imagem.convert("RGB")

            saida = BytesIO()
            imagem_final.save(saida, format="JPEG", quality=92, optimize=True)
            return saida.getvalue()
    except UnidentifiedImageError as exc:
        raise ValueError("Não foi possível reconhecer o arquivo como uma imagem válida.") from exc


def obter_caminho_imagem_empresa(empresa_id: int) -> str:
    """Retorna o caminho da imagem configurada pela empresa."""
    return os.path.join(IMAGES_DIR, str(empresa_id), "perfil.jpg")


def empresa_tem_imagem(empresa_id: int) -> bool:
    """Indica se a empresa já configurou uma imagem própria."""
    return os.path.exists(obter_caminho_imagem_empresa(empresa_id))


def salvar_imagem_empresa(empresa_id: int, conteudo_bytes: bytes) -> str:
    """Salva a imagem da empresa em JPG no disco."""
    conteudo_jpg = converter_para_jpg(conteudo_bytes)
    pasta_empresa = os.path.join(IMAGES_DIR, str(empresa_id))
    os.makedirs(pasta_empresa, exist_ok=True)
    caminho = obter_caminho_imagem_empresa(empresa_id)
    with open(caminho, "wb") as arquivo:
        arquivo.write(conteudo_jpg)
    return caminho


def excluir_imagem_empresa(empresa_id: int) -> bool:
    """Remove a imagem configurada pela empresa."""
    caminho = obter_caminho_imagem_empresa(empresa_id)
    if not os.path.exists(caminho):
        return False

    os.remove(caminho)
    pasta_empresa = os.path.dirname(caminho)
    if os.path.isdir(pasta_empresa) and not os.listdir(pasta_empresa):
        os.rmdir(pasta_empresa)

    return True
