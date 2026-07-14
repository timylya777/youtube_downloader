@echo off
echo ==============================================
echo Сборка Standalone EXE для YouTube Downloader
echo ==============================================
echo.
echo 1. Установка PyInstaller...
pip install pyinstaller

echo.
echo 2. Создание папки bin если она отсутствует...
if not exist "bin" mkdir "bin"

echo.
echo 3. Сборка проекта с помощью PyInstaller...
pyinstaller --noconfirm --onefile --windowed --add-data "bin;bin" --add-data "static;static" main.py

echo.
echo ==============================================
echo Сборка завершена!
echo Исполняемый файл находится в папке: dist/main.exe
echo ==============================================
pause
