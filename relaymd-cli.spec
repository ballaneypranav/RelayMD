# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

SOURCE_ROOT = Path(os.environ.get("RELAYMD_CLI_SOURCE_ROOT", "src"))
CORE_ROOT = Path(os.environ.get("RELAYMD_CORE_SOURCE_ROOT", "packages/relaymd-core/src"))

a = Analysis(
    [str(SOURCE_ROOT / 'relaymd' / 'cli' / '__main__.py')],
    pathex=[str(SOURCE_ROOT), str(CORE_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[
        'boto3',
        'botocore',
        'relaymd.runtime_defaults',
        'relaymd.storage',
        'relaymd.storage.client',
    ],
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
)
