# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

ROOT = Path.cwd().parent.parent
WEB_DIST = ROOT / 'apps' / 'web' / 'dist'

LIGHTWEIGHT_DESKTOP_EXCLUDES = [
    'IPython',
    'PyQt5',
    'PyQt6',
    'PySide2',
    'PySide6',
    '_pytest',
    'agents',
    'black',
    'cv2',
    'docutils',
    'fitz',
    'hdbscan',
    'ipywidgets',
    'jedi',
    'jupyter',
    'jupyter_client',
    'jupyter_core',
    'matplotlib',
    'matplotlib_inline',
    'networkx',
    'notebook',
    'nltk',
    'numpy.distutils',
    'numpydoc',
    'openai',
    'pandas',
    'pdfplumber',
    'PIL',
    'pypdf',
    'pytest',
    'qtpy',
    'scipy',
    'sentence_transformers',
    'sklearn',
    'sphinx',
    'sphinxcontrib',
    'torch',
    'torchaudio',
    'torchvision',
    'transformers',
    'umap',
]

a = Analysis(
    ['src/desktop_launcher.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(WEB_DIST), 'apps/web/dist'),
    ],
    hiddenimports=[
        'uvicorn',
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        'fastapi',
        'starlette',
        'webview',
        'webview.platforms.edgechromium',
        'webview.platforms.mshtml',
        'webview.platforms.winforms',
        'litsurveygrp.webapi.app',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=LIGHTWEIGHT_DESKTOP_EXCLUDES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name='LitSurveyGrp',
    debug=False,
    exclude_binaries=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LitSurveyGrp',
)
