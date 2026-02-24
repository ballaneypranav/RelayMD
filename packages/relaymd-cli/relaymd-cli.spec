# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ['src/relaymd/cli/__main__.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=['relaymd.models', 'relaymd.storage'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pex = PYZ(a.pure)
exe = EXE(
    pex,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='relaymd',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    console=True,
    onefile=True,
)
