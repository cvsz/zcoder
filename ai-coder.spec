# Compatibility PyInstaller spec for callers that still run `pyinstaller ai-coder.spec`.
# Canonical spec: spec/ai-coder.spec
# -*- mode: python ; coding: utf-8 -*-
import os

project_root = os.path.abspath(SPECPATH)
src_root = os.path.join(project_root, "src")
entrypoint = os.path.join(project_root, "main.py")
block_cipher = None

a = Analysis(
    [entrypoint],
    pathex=[project_root, src_root],
    binaries=[],
    datas=[(os.path.join(src_root, "zcoder", "api", "anthropic-conformance.yaml"), "zcoder/api")],
    hiddenimports=["anthropic", "zcoder.main"],
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
    name="ai-coder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)
