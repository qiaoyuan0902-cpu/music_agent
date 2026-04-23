@echo off
REM Windows 打包脚本
echo ==> 激活虚拟环境...
call .venv\Scripts\activate.bat

echo ==> 安装/更新 PyInstaller...
pip install -q pyinstaller

echo ==> 清理旧构建...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo ==> 开始打包...
pyinstaller ClaudioFM.spec

echo.
echo 打包完成：dist\ClaudioFM.exe
pause
