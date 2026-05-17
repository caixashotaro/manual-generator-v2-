"""
manual_app.py - ナレッジ統合マニュアル生成 Web UI (Streamlit)

起動:
  streamlit run manual_app.py
"""

import streamlit as st
import tempfile
import os
import json
import time
import shutil
from datetime import datetime
from pathlib import Path

from loader import load_single_file, load_knowledge_folder, LOADERS

# Google GenAI SDK
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# Anthropic SDK
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from generator import (
    SYSTEM_PROMPT, build_prompt,
    GEMINI_MODELS, CLAUDE_MODELS,
    generate_manual_claude,
)

# ============================================
# 永続化ディレクトリ
# ============================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge_store")
MANUALS_DIR = os.path.join(BASE_DIR, "manuals_store")
CONFIG_PATH = os.path.join(BASE_DIR, ".manual_app_config.json")

os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
os.makedirs(MANUALS_DIR, exist_ok=True)


# ============================================
# 設定の保存 / 読み込み
# ============================================

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ============================================
# ナレッジファイルの永続化
# ============================================

def get_stored_knowledge_files() -> list[dict]:
    """保存済みナレッジファイル一覧を返す"""
    files = []
    for name in sorted(os.listdir(KNOWLEDGE_DIR)):
        if name.startswith("."):
            continue
        path = os.path.join(KNOWLEDGE_DIR, name)
        if os.path.isfile(path):
            size_kb = os.path.getsize(path) / 1024
            files.append({"name": name, "path": path, "size_kb": size_kb})
    return files


def save_uploaded_knowledge(uploaded_file) -> str:
    """アップロードされたファイルを knowledge_store に保存"""
    dest = os.path.join(KNOWLEDGE_DIR, uploaded_file.name)
    with open(dest, "wb") as f:
        f.write(uploaded_file.getvalue())
    return dest


def delete_knowledge_file(name: str):
    """ナレッジファイルを削除"""
    path = os.path.join(KNOWLEDGE_DIR, name)
    if os.path.exists(path):
        os.remove(path)


# ============================================
# マニュアル履歴の保存 / 読み込み
# ============================================

def save_manual(title: str, content: str, model_name: str = "") -> str:
    """生成マニュアルを保存し、ファイルパスを返す"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c if c.isalnum() or c in "_-" else "_" for c in title)[:40]
    filename = f"{ts}_{safe_title}.md"
    path = os.path.join(MANUALS_DIR, filename)

    # メタデータをMarkdownの先頭にコメントとして埋め込む
    meta_header = ""
    if model_name:
        meta_header = f"<!-- model: {model_name} -->\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(meta_header + content)
    return path


def get_saved_manuals() -> list[dict]:
    """保存済みマニュアル一覧を返す（新しい順）"""
    manuals = []
    for name in os.listdir(MANUALS_DIR):
        if not name.endswith(".md"):
            continue
        path = os.path.join(MANUALS_DIR, name)
        size_kb = os.path.getsize(path) / 1024

        # ファイル名から日時を取得
        parts = name.split("_", 2)
        if len(parts) >= 3:
            date_str = parts[0]
            time_str = parts[1]
            try:
                dt = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
                display_date = dt.strftime("%Y/%m/%d %H:%M")
            except ValueError:
                display_date = ""
        else:
            display_date = ""

        # メタデータからモデル名を取得
        model_name = ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                first_line = f.readline()
                if first_line.startswith("<!-- model:"):
                    model_name = first_line.replace("<!-- model:", "").replace("-->", "").strip()
        except Exception:
            pass

        manuals.append({
            "name": name,
            "path": path,
            "size_kb": size_kb,
            "date": display_date,
            "model": model_name,
        })
    manuals.sort(key=lambda m: m["name"], reverse=True)
    return manuals


def delete_manual(name: str):
    path = os.path.join(MANUALS_DIR, name)
    if os.path.exists(path):
        os.remove(path)


# ============================================
# ページ設定
# ============================================
st.set_page_config(
    page_title="マニュアル自動生成",
    page_icon="📋",
    layout="wide",
)

st.title("📋 ナレッジ統合マニュアル自動生成")
st.caption("書き起こしテキスト + ナレッジファイル → AI で詳細マニュアルを生成")

config = load_config()

# ============================================
# サイドバー: API設定 & ナレッジ管理
# ============================================
with st.sidebar:
    st.header("⚙️ 設定")

    # --- プロバイダー選択 ---
    provider = st.radio(
        "使用するモデル",
        ["Gemini", "Claude"],
        horizontal=True,
        index=0,
    )

    st.divider()

    # --- Gemini API キー（常に表示・保存）---
    saved_gemini_key = config.get("gemini_api_key", "")
    gemini_api_key = st.text_input(
        "Gemini API Key",
        value=saved_gemini_key,
        type="password",
        help="Google AI Studio で取得",
    )
    if gemini_api_key != saved_gemini_key:
        config["gemini_api_key"] = gemini_api_key
        save_config(config)
        st.toast("Gemini API Key を保存しました")

    # --- Claude API キー（常に表示・保存）---
    saved_claude_key = config.get("claude_api_key", "")
    claude_api_key = st.text_input(
        "Claude API Key",
        value=saved_claude_key,
        type="password",
        help="Anthropic Console で取得",
    )
    if claude_api_key != saved_claude_key:
        config["claude_api_key"] = claude_api_key
        save_config(config)
        st.toast("Claude API Key を保存しました")

    st.divider()

    # --- モデル選択（プロバイダーに応じて切替）---
    if provider == "Gemini":
        model = st.selectbox("Gemini モデル", GEMINI_MODELS, index=0)
        active_api_key = gemini_api_key
    else:
        model = st.selectbox("Claude モデル", CLAUDE_MODELS, index=0)
        active_api_key = claude_api_key

    temperature = st.slider("Temperature", 0.0, 1.0, 0.3, 0.1)

    # --- 保存済みナレッジ管理 ---
    st.divider()
    st.header("📂 ナレッジファイル")

    stored_files = get_stored_knowledge_files()
    if stored_files:
        st.write(f"**保存済み: {len(stored_files)} ファイル**")
        for f in stored_files:
            col_name, col_del = st.columns([4, 1])
            with col_name:
                st.write(f"📄 {f['name']} ({f['size_kb']:.1f}KB)")
            with col_del:
                if st.button("✕", key=f"del_{f['name']}", help="削除"):
                    delete_knowledge_file(f["name"])
                    st.rerun()
    else:
        st.caption("ナレッジファイルはまだありません")

    new_files = st.file_uploader(
        "ナレッジを追加",
        type=["csv", "xlsx", "xls", "pdf", "docx", "txt", "md"],
        accept_multiple_files=True,
        help="アップロードしたファイルはリロード後も保持されます",
        key="knowledge_uploader",
    )
    if new_files:
        for uf in new_files:
            save_uploaded_knowledge(uf)
        st.toast(f"{len(new_files)} ファイルを保存しました")
        st.rerun()

# ============================================
# メインエリア: タブ構成
# ============================================
tab_generate, tab_history = st.tabs(["🚀 マニュアル生成", "📚 保存済みマニュアル"])

# ---------- 生成タブ ----------
with tab_generate:
    col_left, col_right = st.columns([1, 1])

    # --- 左カラム: 入力 ---
    with col_left:
        st.header("① 入力データ")

        st.subheader("書き起こしテキスト")
        transcript_mode = st.radio(
            "入力方法",
            ["テキストを直接入力", "ファイルをアップロード"],
            horizontal=True,
            label_visibility="collapsed",
        )

        transcript_text = ""
        if transcript_mode == "テキストを直接入力":
            transcript_text = st.text_area(
                "書き起こしテキスト",
                height=300,
                placeholder="Whisper 等で書き起こしたテキストをここに貼り付け...",
            )
        else:
            transcript_file = st.file_uploader(
                "書き起こしファイル",
                type=["txt", "md"],
                help="テキストファイルをアップロード",
            )
            if transcript_file:
                transcript_text = transcript_file.read().decode("utf-8")
                st.text_area("内容プレビュー", transcript_text, height=250, disabled=True)

        # 使用するナレッジの確認
        stored_files = get_stored_knowledge_files()
        if stored_files:
            st.subheader("使用するナレッジ")
            st.caption(f"サイドバーで管理している {len(stored_files)} ファイルが参照されます")
            with st.expander("ファイル一覧を確認"):
                for f in stored_files:
                    st.write(f"- {f['name']} ({f['size_kb']:.1f}KB)")

    # --- 右カラム: 出力 ---
    with col_right:
        st.header("② 生成結果")

        # 選択中モデルの表示
        provider_label = "Gemini" if provider == "Gemini" else "Claude"
        st.caption(f"選択中: **{provider_label}** / `{model}`")

        can_generate = bool(active_api_key and transcript_text)

        if not active_api_key:
            st.info(f"サイドバーで {provider_label} API Key を入力してください。")
        elif not transcript_text:
            st.info("左側で書き起こしテキストを入力してください。")

        generate_btn = st.button(
            f"🚀 {provider_label} でマニュアルを生成",
            type="primary",
            use_container_width=True,
            disabled=not can_generate,
        )

        if generate_btn:
            # --- ナレッジ読み込み（保存済みファイルから）---
            knowledge_text = ""
            stored_files = get_stored_knowledge_files()
            if stored_files:
                with st.spinner("ナレッジファイルを読み込み中..."):
                    knowledge_parts = []
                    for f in stored_files:
                        content = load_single_file(f["path"])
                        if content:
                            knowledge_parts.append(
                                f"========== ファイル: {f['name']} ==========\n{content}"
                            )
                    knowledge_text = "\n\n".join(knowledge_parts)
                    st.toast(f"ナレッジ {len(knowledge_parts)} ファイル読み込み完了")

            # --- プロンプト構築 ---
            user_prompt = build_prompt(transcript_text, knowledge_text)
            total_chars = len(SYSTEM_PROMPT) + len(user_prompt)

            with st.expander(f"📊 プロンプト情報 ({total_chars:,} 文字)"):
                st.write(f"- System Prompt: {len(SYSTEM_PROMPT):,} 文字")
                st.write(f"- 書き起こし: {len(transcript_text):,} 文字")
                st.write(f"- ナレッジ: {len(knowledge_text):,} 文字")
                st.write(f"- 概算トークン数: ~{total_chars // 3:,}")

            # --- API 呼び出し（プロバイダー分岐）---
            with st.spinner(f"{provider_label} ({model}) でマニュアルを生成中... しばらくお待ちください"):
                try:
                    start_time = time.time()

                    if provider == "Gemini":
                        if not GENAI_AVAILABLE:
                            st.error("google-genai SDK がインストールされていません: `pip install google-genai`")
                            st.stop()
                        client = genai.Client(api_key=active_api_key)
                        response = client.models.generate_content(
                            model=model,
                            contents=user_prompt,
                            config=types.GenerateContentConfig(
                                system_instruction=SYSTEM_PROMPT,
                                temperature=temperature,
                                max_output_tokens=65536,
                            ),
                        )
                        manual_text = response.text.strip()
                    else:
                        if not ANTHROPIC_AVAILABLE:
                            st.error("anthropic SDK がインストールされていません: `pip install anthropic`")
                            st.stop()
                        manual_text, was_truncated = generate_manual_claude(
                            api_key=active_api_key,
                            transcript=transcript_text,
                            knowledge=knowledge_text,
                            model=model,
                            temperature=temperature,
                        )
                        if was_truncated:
                            st.warning(
                                "Claude の入力上限（200Kトークン）に合わせて、ナレッジの一部を自動的に省略しました。"
                                "書き起こしテキストは全文送信されています。"
                            )

                    elapsed = time.time() - start_time

                    st.session_state["generated_manual"] = manual_text
                    st.session_state["generation_time"] = elapsed
                    st.session_state["generation_model"] = model
                    st.toast(f"生成完了! ({elapsed:.1f}秒)")

                except Exception as e:
                    st.error(f"{provider_label} API エラー: {e}")

        # --- 結果表示 ---
        if "generated_manual" in st.session_state:
            manual = st.session_state["generated_manual"]
            elapsed = st.session_state.get("generation_time", 0)
            gen_model = st.session_state.get("generation_model", "")

            model_badge = f" | モデル: `{gen_model}`" if gen_model else ""
            st.success(f"生成完了 ({len(manual):,} 文字 / {elapsed:.1f}秒{model_badge})")

            view_mode = st.radio(
                "表示形式",
                ["プレビュー (Markdown)", "ソース (テキスト)"],
                horizontal=True,
                label_visibility="collapsed",
            )

            if view_mode == "プレビュー (Markdown)":
                st.markdown(manual)
            else:
                st.text_area("生成されたマニュアル", manual, height=500)

            # 保存 & ダウンロード
            st.divider()
            save_col, dl_col = st.columns(2)
            with save_col:
                manual_title = st.text_input(
                    "保存名",
                    value="マニュアル",
                    label_visibility="collapsed",
                    placeholder="マニュアルの名前を入力...",
                )
                if st.button("💾 サーバーに保存", use_container_width=True):
                    path = save_manual(manual_title, manual, model_name=gen_model)
                    st.toast(f"保存しました: {os.path.basename(path)}")
                    st.rerun()
            with dl_col:
                st.write("")  # スペーサー
                st.download_button(
                    "📥 Markdown でダウンロード",
                    data=manual,
                    file_name="generated_manual.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

# ---------- 履歴タブ ----------
with tab_history:
    st.header("📚 保存済みマニュアル")

    manuals = get_saved_manuals()
    if not manuals:
        st.info("保存済みのマニュアルはまだありません。生成後に「サーバーに保存」で保存できます。")
    else:
        for m in manuals:
            model_tag = f"  [{m['model']}]" if m["model"] else ""
            with st.expander(f"📄 {m['date']}{model_tag}  —  {m['name']}  ({m['size_kb']:.1f}KB)"):
                with open(m["path"], "r", encoding="utf-8") as f:
                    content = f.read()

                # メタデータコメント行を表示から除外
                display_content = content
                if display_content.startswith("<!-- model:"):
                    display_content = display_content.split("\n", 1)[-1]

                view = st.radio(
                    "表示",
                    ["プレビュー", "ソース"],
                    horizontal=True,
                    key=f"view_{m['name']}",
                    label_visibility="collapsed",
                )
                if view == "プレビュー":
                    st.markdown(display_content)
                else:
                    st.text_area("内容", display_content, height=400, key=f"src_{m['name']}")

                action_col1, action_col2, action_col3 = st.columns(3)
                with action_col1:
                    st.download_button(
                        "📥 ダウンロード",
                        data=display_content,
                        file_name=m["name"],
                        mime="text/markdown",
                        use_container_width=True,
                        key=f"dl_{m['name']}",
                    )
                with action_col2:
                    if st.button("📋 編集画面に読み込む", use_container_width=True, key=f"load_{m['name']}"):
                        st.session_state["generated_manual"] = display_content
                        st.session_state["generation_time"] = 0
                        st.session_state["generation_model"] = m.get("model", "")
                        st.toast("生成タブに読み込みました")
                        st.rerun()
                with action_col3:
                    if st.button("🗑️ 削除", use_container_width=True, key=f"delman_{m['name']}"):
                        delete_manual(m["name"])
                        st.toast(f"削除しました: {m['name']}")
                        st.rerun()
