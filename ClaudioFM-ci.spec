# -*- mode: python ; coding: utf-8 -*-
"""
ClaudioFM CI spec — 用于 GitHub Actions
不依赖本地 .venv 路径，由 PyInstaller 自动收集依赖
"""

import sys
import os
from pathlib import Path

ROOT = Path(SPECPATH)
block_cipher = None

# 找 certifi 证书（CI 环境路径不固定，用 importlib 查）
import certifi
CERT_PEM = certifi.where()

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / '加载图.png'), '.'),
        (CERT_PEM, 'certifi'),
    ],
    hiddenimports=[
        'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
        'PyQt6.QtMultimedia', 'PyQt6.sip',
        'anthropic', 'anthropic.lib.streaming', 'anthropic.lib.streaming._messages',
        'openai', 'openai.resources', 'openai._streaming',
        'httpx', 'httpx._transports.default',
        'httpcore', 'httpcore._async.http11', 'httpcore._sync.http11',
        'certifi',
        'anyio', 'anyio._backends._asyncio', 'anyio._backends._trio',
        'sniffio',
        'asyncio',
        'edge_tts', 'edge_tts.communicate',
        'speech_recognition', 'pyaudio',
        'pyncm', 'pyncm.apis', 'pyncm.apis.login',
        'pyncm.apis.track', 'pyncm.apis.playlist',
        'qrcode', 'qrcode.image.pil',
        'PIL', 'PIL.Image',
        'dotenv', 'requests', 'json', 'sqlite3',
    ],
    hookspath=[],
    runtime_hooks=['runtime_hook.py'],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'IPython', 'jupyter'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if sys.platform == 'darwin':
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name='ClaudioFM', debug=False, strip=False, upx=True,
        console=False, target_arch=None,
    )
    coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas,
                   strip=False, upx=True, name='ClaudioFM')
    app = BUNDLE(
        coll,
        name='ClaudioFM.app',
        icon=None,
        bundle_identifier='com.claudiofm.app',
        info_plist={
            'NSMicrophoneUsageDescription': 'Claudio FM 需要麦克风权限用于语音输入',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
        },
    )
else:
    # Windows: 单文件 exe
    exe = EXE(
        pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
        name='ClaudioFM',
        debug=False, strip=False, upx=True,
        console=False, icon=None,
    )
