# [PoC] Voice Live API ベースのコールセンター受付エージェント

Azure Voice Live API を使った、コールセンター受付シナリオの音声エージェント PoC です。
ブラウザ上でマイクを通じてリアルタイム音声会話を行い、フェーズベースの状態機械で会話フローを制御します。

## 機能

- **自然な会話**: Azure Semantic VAD による割り込み対応・自然なターン検出
- **Function Calling による業務ツール呼び出し**: 本人確認、注文照会、プラン変更、エスカレーション起票
- **フェーズに応じた動的な処理切替**: triage → identity → business → escalation
- **長時間通話に耐えるコンテキスト管理**: トークン閾値による自動要約、Out-of-Band 推論による引き継ぎサマリ生成、`conversation.item.delete` による古い item 削除と summary system item 再注入

## アーキテクチャ

```
┌──────────────┐       WebSocket        ┌──────────────────┐      WebSocket       ┌─────────────────────┐
│   Browser    │  audio (PCM16) ──────> │   Backend        │  input_audio ──────> │  Azure Voice Live   │
│   (React)    │  <── audio/transcript  │   (FastAPI)      │  <── response.audio  │  API                │
│              │  <── phase_changed     │                  │  ──> session.update  │  (GPT-Realtime)     │
└──────────────┘                        └──────────────────┘                      └─────────────────────┘
```

## 前提条件

- Python 3.11+
- Node.js 18+
- Azure OpenAI リソース（Voice Live API アクセス権限付き）

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
AZURE_OPENAI_ENDPOINT=https://YOUR_RESOURCE.openai.azure.com
AZURE_OPENAI_API_KEY=your_api_key_here
AZURE_OPENAI_DEPLOYMENT=gpt-realtime
```

### フロントエンド

```bash
cd frontend
npm install
npm run dev
```

ブラウザで `http://localhost:5173` を開き、「開始」ボタンを押すとマイク入力が開始されます。

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
