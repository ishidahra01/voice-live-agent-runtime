# [PoC] Voice Live API ベースのコールセンター受付エージェント

Azure Voice Live API を使った、コールセンター受付シナリオの音声エージェント PoC です。
ブラウザ上でマイクを通じてリアルタイム音声会話を行い、フェーズベースの状態機械で会話フローを制御します。
バックエンドは Azure Voice Live SDK を使って Voice Live セッションを確立し、公式 API 仕様に沿って `session.update` / `response.create` / `conversation.item.create` などのイベントを扱います。

## 機能

- **自然な会話**: Azure Semantic VAD による割り込み対応・自然なターン検出
- **Function Calling による業務ツール呼び出し**: 本人確認、注文照会、プラン変更、エスカレーション起票
- **フェーズに応じた動的な処理切替**: triage は `gpt-realtime`、identity / business / escalation は `gpt-5-nano` に `session.update` で切り替え
- **長時間通話に耐えるコンテキスト管理**: トークン閾値による自動要約、Out-of-Band 推論による引き継ぎサマリ生成、`conversation.item.delete` による古い item 削除と summary system item 再注入
- **オペレータ向け可視化**: 現在の model / voice / tool set、抽出済み vars、引き継ぎサマリ、会話要約を画面に常時表示
- **インテリジェント summary**: handoff summary / conversation summary は Voice Live の会話ストリームとは分離した Foundry/Azure OpenAI 呼び出しで生成

## アーキテクチャ

```text
┌──────────────┐       WebSocket        ┌──────────────────┐      WebSocket       ┌─────────────────────┐
│   Browser    │  audio (PCM16) ──────> │   Backend        │  input_audio ──────> │  Azure Voice Live   │
│   (React)    │  <── audio/transcript  │   (FastAPI)      │  <── response.audio  │  API                │
│              │  <── phase_changed     │                  │  ──> session.update  │  (GPT-Realtime)     │
└──────────────┘                        └──────────────────┘                      └─────────────────────┘
```

## 前提条件

- Python 3.11+
- Node.js 18+
- Azure AI Foundry または Azure AI Services の Voice Live 対応リソース
- Voice Live API を利用できる認証情報
  - API Key もしくは
  - Microsoft Entra ID / `DefaultAzureCredential`

## セットアップ

### バックエンド

```bash
cd backend
cp .env.example .env
# .env を編集して Azure 認証情報を設定
pip install -e ".[dev]"
python -m app.main
```

`.env` に設定が必要な項目:

```env
AZURE_VOICELIVE_ENDPOINT=https://YOUR_RESOURCE.services.ai.azure.com
AZURE_VOICELIVE_API_KEY=your_api_key_here
AZURE_VOICELIVE_MODEL=gpt-realtime
AZURE_VOICELIVE_STRUCTURED_MODEL=gpt-5-nano
AZURE_VOICELIVE_API_VERSION=2025-10-01
AZURE_VOICELIVE_VOICE=ja-JP-NanamiNeural
AZURE_VOICELIVE_STRUCTURED_VOICE=ja-JP-KeitaNeural
AZURE_VOICELIVE_TRANSCRIPTION_MODEL=azure-speech
AZURE_VOICELIVE_TRANSCRIPTION_LANGUAGE=ja-JP
AZURE_SUMMARY_ENDPOINT=https://YOUR_RESOURCE.openai.azure.com
AZURE_SUMMARY_API_KEY=your_api_key_here
AZURE_SUMMARY_MODEL=gpt-5.4-nano-1
```

`AZURE_VOICELIVE_API_KEY` を省略した場合、バックエンドは `DefaultAzureCredential` を使って接続します。
`AZURE_SUMMARY_API_KEY` を省略した場合も、summary 用の Foundry/Azure OpenAI 呼び出しは `DefaultAzureCredential` と `https://ai.azure.com/.default` の bearer token provider を使います。

### フロントエンド

```bash
cd frontend
npm install
npm run dev
```

ブラウザで `http://localhost:5173` を開き、「開始」ボタンを押すとマイク入力が開始されます。

triage は既定の realtime 音声、本人確認や定型ヒアリングを含む structured phases は既定で男性音声 `ja-JP-KeitaNeural` に切り替わるので、テスト時に phase 切替を耳でも判別できます。

## テスト

```bash
cd backend
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## ドキュメント

- [アーキテクチャドキュメント](docs/architecture.md) — システム構成、コンポーネント設計、メッセージフォーマット
- [フェーズ設計ドキュメント](docs/phase-design.md) — フェーズ定義、遷移ルール、ツール一覧

## ライセンス

MIT
