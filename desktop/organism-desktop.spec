# -*- mode: python ; coding: utf-8 -*-
# Organism Desktop — optional one-folder freeze (v1.9).
# Build: pip install pyinstaller && pyinstaller desktop/organism-desktop.spec
# CPU / offscreen smoke remains: python -m organism_desktop --smoke

block_cipher = None

a = Analysis(
    ['organism_desktop/__main__.py'],
    pathex=['desktop', 'sdk/python', 'modules'],
    binaries=[],
    datas=[],
    hiddenimports=['organism_sdk', 'organism_desktop', 'PySide6'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='organism-desktop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='organism-desktop',
)
