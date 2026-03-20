import json
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

TELEGRAM_BOT_API_BASE = "https://api.telegram.org"

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
    """Converte uma imagem estática suportada para JPG, exigido pela Bot API."""
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


async def _post_bot_api(token: str, method: str, *, data: dict | None = None, files: dict | None = None):
    """Executa uma chamada direta à Bot API do Telegram."""
    url = f"{TELEGRAM_BOT_API_BASE}/bot{token}/{method}"

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, data=data, files=files)

    try:
        payload = response.json()
    except ValueError:
        response.raise_for_status()
        raise ValueError("Resposta inválida da Bot API do Telegram.") from None

    if response.status_code >= 400 or not payload.get("ok"):
        descricao = payload.get("description") or f"HTTP {response.status_code}"
        raise ValueError(descricao)

    return payload.get("result")


async def definir_foto_perfil_bot(token: str, conteudo_bytes: bytes):
    """Define a foto de perfil do bot usando a Bot API."""
    conteudo_jpg = converter_para_jpg(conteudo_bytes)
    data = {
        "photo": json.dumps(
            {
                "type": "static",
                "photo": "attach://profile_photo",
            }
        )
    }
    files = {
        "profile_photo": ("profile.jpg", conteudo_jpg, "image/jpeg"),
    }
    await _post_bot_api(token, "setMyProfilePhoto", data=data, files=files)


async def remover_foto_perfil_bot(token: str):
    """Remove a foto de perfil atual do bot."""
    await _post_bot_api(token, "removeMyProfilePhoto")
