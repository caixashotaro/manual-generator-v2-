#!/bin/bash
cd "$(dirname "$0")"
echo "==================================="
echo " 業務マニュアル自動生成アプリ セットアップ"
echo "==================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Python3 がインストールされていません。"
    echo "https://www.python.org/downloads/ からインストールしてください。"
    read -p "Press Enter to exit..."
    exit 1
fi

echo "Python3 を検出しました: $(python3 --version)"
echo ""
echo "必要なパッケージをインストールしています..."
echo ""

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

echo ""
echo "==================================="
echo " セットアップ完了!"
echo "==================================="
echo ""
echo "次のステップ:"
echo "1. start.command をダブルクリックしてアプリを起動"
echo "2. サイドバーでAPIキーを入力"
echo "   - Groq API Key: https://console.groq.com/"
echo "   - Gemini API Key: https://aistudio.google.com/apikey"
echo ""
read -p "Press Enter to exit..."
