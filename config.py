import os

# Diretórios do projeto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PDFS_DIR = os.path.join(DATA_DIR, "pdfs")
VECTOR_STORES_DIR = os.path.join(DATA_DIR, "vector_stores")
DB_PATH = os.path.join(DATA_DIR, "bot.db")

# Garante que os diretórios existem
for d in [DATA_DIR, PDFS_DIR, VECTOR_STORES_DIR]:
    os.makedirs(d, exist_ok=True)
