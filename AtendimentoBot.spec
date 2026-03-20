# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules


datas = []
for pacote in ("docx", "pptx", "PIL"):
    datas += collect_data_files(pacote)

binaries = collect_dynamic_libs("faiss")

hiddenimports = []
for pacote in (
    "langchain_google_genai",
    "langchain_community",
    "google.ai.generativelanguage",
):
    hiddenimports += collect_submodules(pacote)


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AtendimentoBot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
