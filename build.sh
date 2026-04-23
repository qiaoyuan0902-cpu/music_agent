#!/bin/bash
# Mac 打包脚本
set -e

echo "==> 激活虚拟环境..."
source .venv/bin/activate

echo "==> 安装/更新 PyInstaller..."
pip install -q pyinstaller

echo "==> 清理旧构建..."
rm -rf build dist

echo "==> 开始打包..."
pyinstaller --noconfirm ClaudioFM.spec

echo ""
echo "✅ 打包完成：dist/ClaudioFM.app"
echo "   将 dist/ClaudioFM.app 拖入 /Applications 即可使用"
