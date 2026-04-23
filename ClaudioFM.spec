# -*- mode: python ; coding: utf-8 -*-
"""
ClaudioFM PyInstaller spec
生成 Mac .app 和 Windows .exe
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH)
VENV = ROOT / '.venv' / 'lib' / 'python3.14' / 'site-packages'

block_cipher = None

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # 加载图
        (str(ROOT / '加载图.png'), '.'),
        # SSL 证书（httpx/requests 需要）
        (str(VENV / 'certifi' / 'cacert.pem'), 'certifi'),
        # edge-tts
        (str(VENV / 'edge_tts'), 'edge_tts'),
        # speech_recognition
        (str(VENV / 'speech_recognition'), 'speech_recognition'),
        # qrcode
        (str(VENV / 'qrcode'), 'qrcode'),
        # anyio 后端（动态加载，必须作为数据带入）
        (str(VENV / 'anyio'), 'anyio'),
        # httpcore
        (str(VENV / 'httpcore'), 'httpcore'),
    ],
    hiddenimports=[
        # PyQt6
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.QtMultimedia',
        'PyQt6.sip',
        # anthropic + httpx 依赖链
        'anthropic',
        'anthropic.lib.streaming',
        'anthropic.lib.streaming._messages',
        'httpx',
        'httpx._transports.default',
        'httpcore',
        'httpcore._async.http11',
        'httpcore._sync.http11',
        'certifi',
        # anyio 后端（动态 import，PyInstaller 检测不到）
        'anyio',
        'anyio._backends._asyncio',
        'anyio._backends._trio',
        'sniffio',
        # 异步
        'asyncio',
        # edge-tts
        'edge_tts',
        'edge_tts.communicate',
        # speech recognition
        'speech_recognition',
        'pyaudio',
        # pyncm
        'pyncm',
        'pyncm.apis',
        'pyncm.apis.login',
        'pyncm.apis.track',
        'pyncm.apis.playlist',
        # qrcode
        'qrcode',
        'qrcode.image.pil',
        'PIL',
        'PIL.Image',
        # dotenv
        'dotenv',
        # misc
        'requests',
        'json',
        'sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['runtime_hook.py'],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'pandas',
        'IPython', 'jupyter', 'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Mac .app ──────────────────────────────────────────────
if sys.platform == 'darwin':
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name='ClaudioFM',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe, a.binaries, a.zipfiles, a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='ClaudioFM',
    )
    app = BUNDLE(
        coll,
        name='ClaudioFM.app',
        icon=None,
        bundle_identifier='com.claudiofm.app',
        info_plist={
            'NSMicrophoneUsageDescription': 'Claudio FM 需要麦克风权限用于语音输入',
            'CFBundleShortVersionString': '1.0.0',
            'CFBundleVersion': '1.0.0',
            'NSHighResolutionCapable': True,
        },
    )

# ── Windows .exe ──────────────────────────────────────────
else:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
        name='ClaudioFM',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
    )


pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Mac .app ──────────────────────────────────────────────
if sys.platform == 'darwin':
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name='ClaudioFM',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe, a.binaries, a.zipfiles, a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='ClaudioFM',
    )
    app = BUNDLE(
        coll,
        name='ClaudioFM.app',
        icon=None,
        bundle_identifier='com.claudiofm.app',
        info_plist={
            'NSMicrophoneUsageDescription': 'Claudio FM 需要麦克风权限用于语音输入',
            'CFBundleShortVersionString': '1.0.0',
            'CFBundleVersion': '1.0.0',
            'NSHighResolutionCapable': True,
        },
    )

# ── Windows .exe ──────────────────────────────────────────
else:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
        name='ClaudioFM',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
    )
