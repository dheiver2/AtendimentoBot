import os
import sys


def _obter_base_dir() -> str:
    """Resolve o diretório-base do app em source e em executável onefile."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))

    return os.path.dirname(os.path.abspath(__file__))


def _obter_bundle_dir() -> str:
    """Resolve o diretório extraído pelo PyInstaller quando disponível."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


# Diretórios do projeto
BASE_DIR = _obter_base_dir()
BUNDLE_DIR = _obter_bundle_dir()
ENV_PATH = os.path.join(BASE_DIR, ".env")
BUNDLED_ENV_PATH = os.path.join(BUNDLE_DIR, ".env")
DATA_DIR = os.path.join(BASE_DIR, "data")
PDFS_DIR = os.path.join(DATA_DIR, "pdfs")
VECTOR_STORES_DIR = os.path.join(DATA_DIR, "vector_stores")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
DB_PATH = os.path.join(DATA_DIR, "bot.db")

# Garante que os diretórios existem
for d in [DATA_DIR, PDFS_DIR, VECTOR_STORES_DIR, IMAGES_DIR]:
    os.makedirs(d, exist_ok=True)
