#!/bin/bash
cd "$(dirname "$0")"

DIST_NAME="manual-generator"
DIST_DIR="${DIST_NAME}"
ZIP_NAME="${DIST_NAME}.zip"

echo "配布用ZIPファイルを作成します..."
echo ""

# Clean up existing
rm -rf "${DIST_DIR}" "${ZIP_NAME}"

# Create distribution directory
mkdir -p "${DIST_DIR}/.streamlit"
mkdir -p "${DIST_DIR}/projects"

# Copy necessary files
cp app.py "${DIST_DIR}/"
cp requirements.txt "${DIST_DIR}/"
cp start.command "${DIST_DIR}/"
cp start.bat "${DIST_DIR}/"
cp setup.command "${DIST_DIR}/"
cp setup.bat "${DIST_DIR}/"
cp SETUP_GUIDE.txt "${DIST_DIR}/"

# Copy streamlit config (but not secrets)
cp .streamlit/config.toml "${DIST_DIR}/.streamlit/" 2>/dev/null || true
cp .streamlit/secrets.toml.example "${DIST_DIR}/.streamlit/" 2>/dev/null || true

# Create placeholder for projects directory
touch "${DIST_DIR}/projects/.gitkeep"

# Create ZIP
zip -r "${ZIP_NAME}" "${DIST_DIR}"

# Clean up temp directory
rm -rf "${DIST_DIR}"

echo ""
echo "==================================="
echo " 完了: ${ZIP_NAME}"
echo "==================================="
echo ""
echo "このZIPファイルを配布してください。"
echo "受け取った人は以下の手順で使えます："
echo ""
echo "【Mac】"
echo "1. ZIPを展開"
echo "2. setup.command をダブルクリック（初回のみ）"
echo "3. start.command をダブルクリック"
echo ""
echo "【Windows】"
echo "1. ZIPを展開"
echo "2. setup.bat をダブルクリック（初回のみ）"
echo "3. start.bat をダブルクリック"
echo ""
open .
