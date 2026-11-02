# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ZCoder Enterprise Desktop Full GUI build."""

import os

from PyInstaller.utils.hooks import collect_submodules

project_root = os.path.abspath(os.path.join(SPECPATH, ".."))
src_root = os.path.join(project_root, "src")
entrypoint = os.path.join(project_root, "main.py")

block_cipher = None

hidden_imports = (
    ["anthropic", "tkinter", "tkinter.ttk", "tkinter.messagebox", "tkinter.filedialog"]
    + collect_submodules("zcoder")
)

datas = [
    (os.path.join(src_root, "zcoder", "api", "anthropic-conformance.yaml"), "zcoder/api")
]

# Include brand assets if present
assets_dir = os.path.join(project_root, "assets")
if os.path.isdir(assets_dir):
    datas.append((assets_dir, "assets"))

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
    name="zcoder-desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Windowed GUI application without console window popup
    disable_windowed_traceback=False,
)
