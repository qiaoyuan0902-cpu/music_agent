"""
PyInstaller runtime hook
在打包后的 app 启动时修正 SSL 证书路径，
确保 httpx / requests 能找到 certifi 的 cacert.pem
"""
import os
import sys

if getattr(sys, 'frozen', False):
    # sys._MEIPASS 是 PyInstaller 解压临时目录
    bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    cert_path = os.path.join(bundle_dir, 'certifi', 'cacert.pem')
    if os.path.exists(cert_path):
        os.environ['SSL_CERT_FILE'] = cert_path
        os.environ['REQUESTS_CA_BUNDLE'] = cert_path
