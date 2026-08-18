# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_submodules

project_root = os.path.abspath(os.path.join(SPECPATH, ".."))
src_root = os.path.join(project_root, "src")
entrypoint = os.path.join(project_root, "main.py")

block_cipher = None

hidden_imports = (
    ["anthropic", "_zcoder_compat"]
    + collect_submodules("zcoder")
)

datas = [
    (os.path.join(src_root, "zcoder", "api", "anthropic-conformance.yaml"), "zcoder/api")
] + [(os.path.join(src_root, f), ".") for f in os.listdir(src_root) if f.endswith(".py")]

a = Analysis(
    [entrypoint],
    pathex=[project_root, src_root],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludedimports=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="zcoder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)
