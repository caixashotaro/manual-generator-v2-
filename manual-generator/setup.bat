@echo off
cd /d "%~dp0"
echo ===================================
echo  業務マニュアル自動生成アプリ セットアップ
echo ===================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python がインストールされていません。
    echo https://www.python.org/downloads/ からインストールしてください。
    echo インストール時に「Add Python to PATH」にチェックを入れてください。
    pause
    exit /b 1
)

echo Python を検出しました
echo.
echo 必要なパッケージをインストールしています...
echo.

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo ===================================
echo  セットアップ完了!
echo ===================================
echo.
echo 次のステップ:
echo 1. start.bat をダブルクリックしてアプリを起動
echo 2. サイドバーでAPIキーを入力
echo    - Groq API Key: https://console.groq.com/
echo    - Gemini API Key: https://aistudio.google.com/apikey
echo.
pause
