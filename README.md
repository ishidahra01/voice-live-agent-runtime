# [PoC] Voice Live API ベースのコールセンター受付エージェント

Azure Voice Live API を使った、コールセンター受付シナリオの音声エージェント PoC です。
ブラウザ上でマイクを通じてリアルタイム音声会話を行い、フェーズベースの状態機械で会話フローを制御します。

## 機能

- **自然な会話**: Azure Semantic VAD による割り込み対応・自然なターン検出
- **Function Calling による業務ツール呼び出し**: 本人確認、注文照会、プラン変更、エスカレーション起票
- **フェーズに応じた動的な処理切替**: triage → identity → business → escalation
- **長時間通話に向けたコンテキスト管理の土台**: トークン閾値判定、Out-of-Band 推論による引き継ぎサマリ生成、フル履歴保持

## 現在の実装状況（2026-04-23 時点）

実コード・テスト・ビルド結果を確認したうえで、現時点のステータスを明記します。

### 実装済み

- ブラウザ → FastAPI → Azure Voice Live API の WebSocket 音声経路
- 4 フェーズ（`triage` / `identity` / `business` / `escalation`）の instructions / tools 切替
- Function Calling によるツール実行と `response.create` による応答継続
- Out-of-Band Response（`conversation: "none"`）を使った要約生成
- 会話ログ、現在フェーズ、ツール呼び出しの UI 表示
- バックエンドテスト 26 件成功、フロントエンド本番ビルド成功

### 原 Issue に対して未完了または部分実装の項目

- Voice Live 接続は `azure-ai-voicelive` SDK ではなく、現状は `websockets` による JSON イベント送受信で実装
- `ContextManager` は要約文の生成とアプリ層での履歴保持までは実装済みだが、Issue にある `conversation.item.delete` による古い item 削除と summary system item の再注入までは未実装
- UI は現在フェーズ表示を持つが、フェーズ遷移履歴の専用ログ表示までは未実装

### モック実装について

- `verify_customer` / `lookup_order` / `update_plan` / `create_escalation` の業務バックエンドはモック
- これは original Issue の Out-of-Scope にある「CRM / 基幹系への実接続（モック実装で代替）」に沿ったものです

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
