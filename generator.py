"""
generator.py - Gemini 1.5 Pro を使った業務マニュアル自動生成 CLI

使い方:
  # 基本: 書き起こしテキスト + ナレッジフォルダ → マニュアル出力
  python generator.py --transcript transcript.txt --knowledge ./knowledge

  # 音声ファイルから書き起こし → マニュアル生成
  python generator.py --audio recording.mp3 --knowledge ./knowledge

  # 出力先指定
  python generator.py --transcript transcript.txt --knowledge ./knowledge -o manual.md

環境変数:
  GEMINI_API_KEY: Google Gemini API キー（引数でも指定可）
"""

import os
import sys
import json
import argparse
from pathlib import Path

from loader import load_knowledge_folder, load_single_file

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

# モデル設定
GEMINI_MODEL = "gemini-2.5-pro"
CLAUDE_MODEL = "claude-sonnet-4-20250514"

GEMINI_MODELS = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]
CLAUDE_MODELS = [
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-haiku-4-20250514",
]


# ============================================
# System Prompt 設計
# ============================================

SYSTEM_PROMPT = """\
あなたは物流・配車業務のマニュアル作成のプロフェッショナルです。

あなたの役割は、**書き起こしテキストの内容をベースに**、初めてこの業務を担当する人が一人で業務を遂行できるレベルの、極めて詳細な業務マニュアルを作成することです。

## 入力情報と優先度
1. **今回の書き起こしテキスト（メイン）**: 実際の業務操作を録音・録画した音声の文字起こし。**これがマニュアルの主軸であり、この内容に沿って手順を構成すること。**
2. **過去のナレッジ（補助・参照用）**: Excelの列名定義、業務ルール、判断基準、用語集など。**書き起こしの内容を補足・裏付けするために参照する。ナレッジだけに存在し書き起こしに登場しない情報を主題にしないこと。**

## タスク
書き起こしテキストで実際に行われている操作手順をそのまま忠実にマニュアル化してください。
ナレッジは、書き起こし中に登場する用語の正式名称・定義の確認や、判断基準の補足に活用してください。

## 参照元の明示（重要）
**マニュアルの各ステップには、そのステップの根拠となった書き起こしテキストの該当箇所を必ず引用として付記してください。**
形式: 各ステップの末尾に以下を記載する
`📍 参照元: [○○s〜○○s]「書き起こしの該当部分をそのまま引用」`

- タイムスタンプがある場合は `[12.5s〜25.0s]` のように時間範囲を記載する
- タイムスタンプがない場合は、書き起こしテキスト内の該当文章をそのまま引用する
- 1つのステップが複数の発話にまたがる場合は、全ての該当箇所を列挙する
- これにより、マニュアルの各記述がどの発話に基づいているかをトレースできるようにする

## 制約条件（必須）

### 1. 書き起こしファースト
- マニュアルの構成・手順の流れは書き起こしテキストの順序に従う
- 書き起こしに記載されていない手順をナレッジから勝手に追加しない
- ナレッジの情報は、書き起こしの該当箇所に補足として添える形で使う

### 2. 極限の具体性と詳細さ（最重要）
以下のレベルまで細かく記述すること。抽象的な説明は一切不可。

**システム操作の場合:**
- 「どのURLにアクセスし」「どのID/パスワードでログインし」「どのタブをクリックし」「どの画面が開き」「どのフィールドにカーソルを合わせ」「何を入力し」「どのキーを押し」「何が表示されるか」を1操作ずつ記述
- 画面上のフィールド名、ボタン名、タブ名はすべてバッククォートで囲む（例: `受注日`フィールド、`F5`キー、`確定`チェックボックス）
- 入力例がある場合は具体的な値を記載（例: 「`受注日`フィールドに本日の日付を入力」ではなく「`受注日`フィールドに受注した日付（例: 2024/12/05）を入力」）
- ショートカットキーがある場合は明記（例: `F5`キーで検索画面を呼び出す）
- 操作後に画面上で何が起きるか（遷移、表示変更）も記述

**書類・FAX・メール操作の場合:**
- 「誰が」「何を」「どこから取得し」「どこに」「どのように」処理するかを記述
- 物理的な場所（「長尾本部長デスクの左前にある複合機」等）も書き起こしから読み取れる場合は明記
- 書類の仕分けルール、コピーの部数、投函先のボックスの場所など具体的に記述

**判断・分岐がある場合:**
- 条件分岐は全パターンを網羅し、表形式またはリスト形式で整理
- 「◯◯の場合は△△する」「□□の場合は××する」を明確に分ける
- 優先順位がある場合は①②③の番号付きで優先度順に記載
- 判断に必要な基準値・閾値があれば具体的数値を記載

**人が関わる場合:**
- 担当者名・役職・部署が書き起こしから読み取れる場合は明記
- 「誰に確認を取るか」「誰に依頼するか」の担当者を具体的に記述
- 連絡方法（電話、メール、口頭、FAX等）も記述

### 3. ステップの粒度
- 1つのステップには1つの操作のみを記述する（複数操作を1ステップに混ぜない）
- 「AしてBする」は2ステップに分割する
- 入力フォームの各フィールドは個別のステップとして記述する
- サブステップが必要な場合は 1-1, 1-2 のように階層化する

### 4. 補足情報・例外・注意事項
- 書き起こしの中で言及されている例外ケース、特殊ケース、イレギュラーは「【補足】」セクションとして該当ステップの直後に記述
- 「初めて出た商品の場合」「マスタ未登録の場合」等の分岐は省略しない
- 慣習やローカルルール（「慣習として翌日配送」「単位は慣習としてケース」等）は「【慣習ルール】」として明記

### 5. ナレッジによる補足
- 書き起こしに出てくる用語がナレッジのExcel列名やルールと対応する場合、その関連を補足情報として明示する
- ナレッジに定義されている分類・区分・コードが書き起こしの文脈に関連する場合、省略せず全て列挙する
- 「など」「等」で省略しない
- 項目名・チェック項目・送信先など、リスト化できるものは全件列挙する

### 6. 不足情報の明示
- 書き起こしやナレッジから読み取れない情報は **【要確認】** タグを付ける
- 具体的に「何が不明で」「誰に確認すべきか」を記載する
- 例: 「【要確認】この操作を行うタイミング（毎朝？随時？）について、配車担当者に確認が必要です」
- 推測で補完する場合は **【推測】** タグを付け、根拠を添える

### 7. 出力フォーマット
- Markdown形式で出力する
- 最上部に `# マニュアルタイトル` を付ける
- 大見出し `##` で業務フェーズ（大区分）を区切る
- 中見出し `###` でサブフェーズを区切る
- 手順は番号付きリスト（1. 2. 3.）で記述し、サブステップは字下げする
- 重要な注意点は `> **⚠️ 注意:**` で強調する
- 判断分岐は表形式またはリスト形式で整理する
- ナレッジから補足した情報には `> **📎 参考（ナレッジより）:**` を付けて出典を明示する
- 慣習・ローカルルールは `> **📝 慣習ルール:**` を付ける
- 不足情報は `> **❓ 要確認:**` を付ける
"""


def build_prompt(transcript: str, knowledge: str) -> str:
    """Gemini に送信するプロンプトを組み立てる"""
    parts = []

    if knowledge:
        parts.append("=" * 60)
        parts.append("【過去のナレッジ（参照情報）】")
        parts.append("=" * 60)
        parts.append(knowledge)
        parts.append("")

    parts.append("=" * 60)
    parts.append("【今回の書き起こしテキスト（マニュアル化対象）】")
    parts.append("=" * 60)
    parts.append(transcript)
    parts.append("")

    parts.append("=" * 60)
    parts.append("【指示】")
    parts.append("=" * 60)
    parts.append(
        "上記の「書き起こしテキスト」をベースに、初めてこの業務を行う人が一人で遂行できるレベルの"
        "極めて詳細な業務マニュアルをMarkdown形式で作成してください。\n"
        "System Promptに記載された制約条件を全て遵守してください。\n\n"
        "特に以下を徹底してください:\n"
        "- 各ステップの末尾に、書き起こしテキストの該当箇所を `📍 参照元:` として引用する\n"
        "- 1ステップ＝1操作の粒度で分割する（複数操作を1ステップに混ぜない）\n"
        "- システム操作はフィールド名・ボタン名・キー操作を1つずつ記述する\n"
        "- 判断分岐は全パターンを網羅する\n"
        "- 不明点は【要確認】で明示する"
    )

    return "\n".join(parts)


# ============================================
# Gemini API 呼び出し
# ============================================

def generate_manual(
    api_key: str,
    transcript: str,
    knowledge: str = "",
    model: str = GEMINI_MODEL,
) -> str:
    """Gemini 1.5 Pro を呼び出してマニュアルを生成する

    Args:
        api_key: Gemini API キー
        transcript: 書き起こしテキスト
        knowledge: ナレッジテキスト（省略可）
        model: 使用するモデル名

    Returns:
        生成されたマニュアル（Markdown形式）
    """
    if not GENAI_AVAILABLE:
        print("エラー: google-genai SDK がインストールされていません。")
        print("  pip install google-genai")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    user_prompt = build_prompt(transcript, knowledge)

    # トークン数の概算表示
    total_chars = len(SYSTEM_PROMPT) + len(user_prompt)
    print(f"  プロンプト総文字数: {total_chars:,} 文字 (概算 {total_chars // 3:,} トークン)")

    print(f"  モデル: {model}")
    print(f"  Gemini API を呼び出し中...")

    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.3,
            max_output_tokens=65536,
        ),
    )

    result = response.text.strip()
    print(f"  生成完了: {len(result):,} 文字")
    return result


# ============================================
# Claude API 呼び出し
# ============================================

# Claude のトークン上限 (入力)
# 200K tokens。出力に16K確保し、余裕を持たせて入力は170Kトークンまで。
# 日本語混在テキストは 1トークン ≈ 2.5文字 で概算。
CLAUDE_MAX_INPUT_CHARS = 170_000 * 2.5  # 425,000 文字


def truncate_knowledge_for_claude(
    transcript: str,
    knowledge: str,
) -> tuple[str, bool]:
    """Claude のコンテキスト上限に収まるようにナレッジをトリミングする

    書き起こしテキストは絶対に削らない（メイン情報）。
    ナレッジのみを末尾から切り詰める。

    Returns:
        (トリミング後のナレッジ, トリミングしたかどうか)
    """
    system_chars = len(SYSTEM_PROMPT)
    prompt_overhead = 500  # build_prompt のヘッダー・指示文等
    transcript_chars = len(transcript)

    budget_for_knowledge = CLAUDE_MAX_INPUT_CHARS - system_chars - prompt_overhead - transcript_chars

    if budget_for_knowledge <= 0:
        # 書き起こし自体が大きすぎる場合はナレッジなしで試行
        return "", True

    if len(knowledge) <= budget_for_knowledge:
        return knowledge, False

    # ファイル単位で切り詰める（途中で切れないように）
    separator = "========== ファイル:"
    files = knowledge.split(separator)
    trimmed_parts = []
    current_len = 0

    for i, part in enumerate(files):
        chunk = (separator + part) if i > 0 else part
        if current_len + len(chunk) > budget_for_knowledge:
            break
        trimmed_parts.append(chunk)
        current_len += len(chunk)

    trimmed = "".join(trimmed_parts)
    return trimmed, True


def generate_manual_claude(
    api_key: str,
    transcript: str,
    knowledge: str = "",
    model: str = CLAUDE_MODEL,
    temperature: float = 0.3,
) -> str:
    """Claude を呼び出してマニュアルを生成する

    Args:
        api_key: Anthropic API キー
        transcript: 書き起こしテキスト
        knowledge: ナレッジテキスト（省略可）
        model: 使用するモデル名
        temperature: 生成温度

    Returns:
        生成されたマニュアル（Markdown形式）
    """
    if not ANTHROPIC_AVAILABLE:
        raise ImportError("anthropic SDK がインストールされていません: pip install anthropic")

    # コンテキスト上限チェック & トリミング
    knowledge, was_truncated = truncate_knowledge_for_claude(transcript, knowledge)
    if was_truncated:
        print(f"  ⚠️ Claude の入力上限に合わせてナレッジをトリミングしました")
        print(f"     トリミング後ナレッジ: {len(knowledge):,} 文字")

    client = anthropic.Anthropic(api_key=api_key)
    user_prompt = build_prompt(transcript, knowledge)

    total_chars = len(SYSTEM_PROMPT) + len(user_prompt)
    print(f"  プロンプト総文字数: {total_chars:,} 文字 (概算 {total_chars // 3:,} トークン)")
    print(f"  モデル: {model}")
    print(f"  Claude API を呼び出し中...")

    response = client.messages.create(
        model=model,
        max_tokens=16384,
        temperature=temperature,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_prompt},
        ],
    )

    result = response.content[0].text.strip()
    print(f"  生成完了: {len(result):,} 文字")
    return result, was_truncated


# ============================================
# 書き起こし（モック / Whisper連携）
# ============================================

def transcribe_audio(audio_path: str, groq_api_key: str = None) -> str:
    """音声ファイルを書き起こす

    Groq Whisper API が利用可能ならそちらを使い、
    なければ OpenAI Whisper ローカルモデルを使用する。
    """
    print(f"  音声ファイル: {audio_path}")

    # Groq Whisper API を優先
    if groq_api_key:
        try:
            from groq import Groq
            print("  Groq Whisper API で書き起こし中...")
            client = Groq(api_key=groq_api_key)
            with open(audio_path, "rb") as f:
                transcription = client.audio.transcriptions.create(
                    file=(os.path.basename(audio_path), f),
                    model="whisper-large-v3",
                    response_format="verbose_json",
                    language="ja",
                )
            # セグメント結合
            if hasattr(transcription, "segments") and transcription.segments:
                lines = []
                for seg in transcription.segments:
                    start = seg.get("start", seg.start) if hasattr(seg, "start") else seg["start"]
                    text = seg.get("text", seg.text) if hasattr(seg, "text") else seg["text"]
                    lines.append(f"[{start:.1f}s] {text}")
                return "\n".join(lines)
            return transcription.text
        except Exception as e:
            print(f"  Groq API エラー: {e}")
            print("  ローカル Whisper にフォールバックします...")

    # ローカル Whisper
    try:
        import whisper
        print("  ローカル Whisper (base) で書き起こし中...")
        model = whisper.load_model("base")
        result = model.transcribe(audio_path, language="ja")
        lines = []
        for seg in result.get("segments", []):
            lines.append(f"[{seg['start']:.1f}s] {seg['text']}")
        return "\n".join(lines) if lines else result.get("text", "")
    except ImportError:
        print("エラー: 音声書き起こしには groq または openai-whisper が必要です。")
        print("  pip install groq  (Groq Whisper API)")
        print("  pip install openai-whisper  (ローカル Whisper)")
        sys.exit(1)


# ============================================
# メイン CLI
# ============================================

def main():
    parser = argparse.ArgumentParser(
        description="Gemini 1.5 Pro で業務マニュアルを自動生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 書き起こし済みテキスト + ナレッジ → マニュアル
  python generator.py --transcript transcript.txt --knowledge ./knowledge

  # 音声ファイルから直接マニュアル生成
  python generator.py --audio recording.mp3 --knowledge ./knowledge

  # API キーを引数で指定
  python generator.py --transcript transcript.txt --knowledge ./knowledge --api-key YOUR_KEY
        """,
    )

    # 入力ソース（どちらか必須）
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--transcript", "-t",
        help="書き起こし済みテキストファイルのパス",
    )
    input_group.add_argument(
        "--audio", "-a",
        help="音声ファイルのパス（Whisper で書き起こしてからマニュアル生成）",
    )

    # ナレッジ
    parser.add_argument(
        "--knowledge", "-k",
        help="ナレッジファイルが格納されたフォルダパス（CSV, Excel, PDF, Word）",
    )

    # 出力
    parser.add_argument(
        "--output", "-o",
        default="manual_output.md",
        help="出力マニュアルファイルパス (デフォルト: manual_output.md)",
    )

    # API キー
    parser.add_argument(
        "--api-key",
        default=os.environ.get("GEMINI_API_KEY", ""),
        help="Gemini API Key（環境変数 GEMINI_API_KEY でも指定可）",
    )
    parser.add_argument(
        "--groq-api-key",
        default=os.environ.get("GROQ_API_KEY", ""),
        help="Groq API Key（音声書き起こし用、環境変数 GROQ_API_KEY でも指定可）",
    )

    # モデル
    parser.add_argument(
        "--model", "-m",
        default=GEMINI_MODEL,
        help=f"Gemini モデル名 (デフォルト: {GEMINI_MODEL})",
    )

    args = parser.parse_args()

    # API キー検証
    if not args.api_key:
        print("エラー: Gemini API Key が指定されていません。")
        print("  --api-key で指定するか、環境変数 GEMINI_API_KEY を設定してください。")
        sys.exit(1)

    print("=" * 60)
    print("業務マニュアル自動生成ツール")
    print("=" * 60)

    # ---- Step 1: 書き起こしテキスト取得 ----
    print("\n[Step 1] 書き起こしテキスト取得")
    if args.transcript:
        transcript_path = args.transcript
        print(f"  テキストファイル読み込み: {transcript_path}")
        transcript = load_single_file(transcript_path)
        if not transcript:
            # テキストファイルとして直接読み込み
            with open(transcript_path, "r", encoding="utf-8") as f:
                transcript = f.read().strip()
    else:
        transcript = transcribe_audio(args.audio, args.groq_api_key or None)

    if not transcript:
        print("エラー: 書き起こしテキストが空です。")
        sys.exit(1)
    print(f"  書き起こし文字数: {len(transcript):,} 文字")

    # ---- Step 2: ナレッジ読み込み ----
    knowledge = ""
    if args.knowledge:
        print(f"\n[Step 2] ナレッジ読み込み: {args.knowledge}")
        knowledge = load_knowledge_folder(args.knowledge)
    else:
        print("\n[Step 2] ナレッジフォルダ未指定（書き起こしのみでマニュアル生成）")

    # ---- Step 3: マニュアル生成 ----
    print(f"\n[Step 3] マニュアル生成 (Gemini {args.model})")
    manual = generate_manual(
        api_key=args.api_key,
        transcript=transcript,
        knowledge=knowledge,
        model=args.model,
    )

    # ---- Step 4: 出力 ----
    print(f"\n[Step 4] 出力")
    output_path = args.output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(manual)
    print(f"  マニュアルを保存しました: {output_path}")
    print(f"  文字数: {len(manual):,} 文字")

    print("\n" + "=" * 60)
    print("完了!")
    print("=" * 60)


if __name__ == "__main__":
    main()
