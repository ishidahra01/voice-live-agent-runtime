# アーキテクチャドキュメント

## アーキテクチャ概要

本システムは、Azure Voice Live API を活用した音声エージェントの PoC（Proof of Concept）です。
ブラウザから WebSocket を介してバックエンド（FastAPI）に接続し、バックエンドがさらに Azure Voice Live API と双方向音声ストリームを確立する 3 層構成です。

## 現在の実装ステータス

このドキュメントには元 Issue で目指した設計も含まれますが、2026-04-23 時点でコードベース上で確認できる実装状態は以下の通りです。

- 実装済み:
  - ブラウザ / バックエンド / Voice Live API の双方向 WebSocket 接続
  - 4 フェーズの状態管理、Function Calling、OOB 要約要求
  - 会話ログ・現在フェーズ・ツール呼び出しの可視化 UI
- 未完了または部分実装:
  - Voice Live 接続は `azure-ai-voicelive` SDK ではなく `websockets` ベース
  - Context compaction は「要約生成とアプリ層保持」までで、`conversation.item.delete` や summary item の再注入は未実装
  - phase transition の専用 UI ログは未実装

```
┌──────────────┐         WebSocket          ┌──────────────────┐       WebSocket        ┌─────────────────────┐
│              │  audio (PCM16 base64)  ──>  │                  │  input_audio_buffer ──> │                     │
│   Browser    │                             │  Backend         │                         │  Azure Voice Live   │
│   (React)    │  <── audio / transcript     │  (FastAPI)       │  <── response.audio     │  API                │
│              │  <── phase_changed          │                  │  <── function_call      │                     │
│              │  <── tool_call              │                  │  ──> session.update     │                     │
└──────────────┘                             └──────────────────┘                         └─────────────────────┘
     Frontend                                   Phase Router                                GPT-Realtime
     Web Audio API                              Context Manager                             TTS / STT / VAD
     AudioWorklet                               Tool Registry                               Function Calling
                                                OOB Subagent
```

### 設計原則

| # | 原則 | 説明 |
|---|------|------|
| 1 | **音声ストリームは Voice Live を通り続ける** | フェーズ切替でも WebSocket を切断しない。`session.update` で挙動（instructions / tools）を差し替えるだけで、音声パイプラインは維持される。 |
| 2 | **Phase Router は音声を振り分けない** | Phase Router は Function Calling をフックして `session.update` を発行する *外側のコントロールループ* であり、音声データ自体には触れない。 |
| 3 | **メイン会話コンテキストは縮約して維持** | Voice Live のメイン会話コンテキストはトークン閾値を超えると要約して圧縮する。フル履歴はアプリ層（Context Manager）に持つ。 |
| 4 | **副次推論は Out-of-Band Response で実行** | 要約・分類・検証などの副次推論は `conversation: "none"` の Out-of-Band Response で実行し、メイン会話コンテキストを汚染しない。 |

---

## コンポーネント構成

### VoiceLiveSession

Azure Voice Live API との WebSocket 接続を管理するコアコンポーネント。
現状の実装は Azure SDK ではなく `websockets` を用いた低レベル実装です。

- **責務**: 接続確立、初期セッション設定送信、双方向音声中継、イベントディスパッチ
- **主要メソッド**:
  - `connect()` — Azure Voice Live API に WebSocket 接続
  - `send(event)` — Voice Live API へ JSON イベント送信
  - `send_to_frontend(event)` — フロントエンドへイベント転送
  - `send_audio_to_voice_live(audio_base64)` — 音声チャンクを `input_audio_buffer.append` として転送
  - `handle_voice_live_events(...)` — Voice Live API からのイベントループ
  - `_dispatch_event(event, ...)` — イベントタイプに応じたハンドラ振り分け
- **ファイル**: `backend/app/voicelive/session.py`

### PhaseRouter

フェーズ状態機械の管理と、Function Call のフックによるフェーズ遷移を担当。

- **責務**: 現フェーズ管理、tool 名→遷移判定、`session.update` でのフェーズ切替
- **主要メソッド**:
  - `handle_function_call(item)` — `conversation.item.created` で受信した function_call を保持
  - `handle_function_call_arguments_done(event)` — ツール実行 → 遷移判定 → 結果返却
  - `_check_transition(tool_name, tool_result, ...)` — 遷移ルール照合と `session.update` 発行
  - `_apply_phase_config(phase, vars_dict)` — instructions / tools を差し替え
- **ファイル**: `backend/app/phases/router.py`

### ContextManager

会話の完全な履歴とコンテキスト変数を保持し、トークン閾値による自動要約を管理。

- **責務**: 発話記録、ツール呼出記録、フェーズ遷移記録、トークン計数、要約トリガー
- **主要データ構造**:
  - `Utterance` — 発話（role, text, item_id, phase, timestamp）
  - `ToolCallLog` — ツール呼出（name, args, result, duration_ms, ...）
  - `PhaseTransition` — フェーズ遷移（from_phase, to_phase, trigger_tool, context_vars）
  - `FullContext` — 通話全体の状態（call_id, utterances, tool_calls, vars, cumulative_tokens）
- **主要メソッド**:
  - `record_utterance(...)` / `record_tool_call(...)` / `record_phase_transition(...)`
  - `prepare_handoff(session, oob, from_phase, to_phase, tool_result)` — フェーズ遷移時の引き継ぎコンテキスト生成
  - `maybe_summarize(session, oob)` — トークン閾値超過時の自動要約
  - `dump(path)` — 通話ログを JSON 出力
- **ファイル**: `backend/app/context/manager.py`

### OOBSubagent

Out-of-Band Response を利用した副次推論の実行器。メイン会話コンテキストに影響を与えずに要約・分類などを実行する。

- **責務**: 会話要約生成、フェーズ引き継ぎサマリ生成
- **主要メソッド**:
  - `run(purpose, instructions, input_items, ...)` — OOB リクエスト発行（`conversation: "none"`）
  - `handle_response_done(event)` — OOB レスポンスのマッチングと結果取得
- **仕組み**: `response.create` に `conversation: "none"` と一意の `oob_id` をメタデータに付与して送信。`response.done` イベントで `oob_id` を照合して結果を取得。
- **ファイル**: `backend/app/subagent/oob.py`

### Tool Registry

デコレータベースのツール登録と実行ディスパッチ機構。

- **責務**: ツール関数の登録・実行、OpenAI Function Calling 互換スキーマの生成
- **主要関数**:
  - `@register_tool("name")` — ツール関数登録デコレータ
  - `execute_tool(name, args)` — 名前でツール実行（async 対応）
  - `build_tool_schemas(tool_names)` — フェーズに応じたツールスキーマ一覧を構築
- **ファイル**: `backend/app/tools/registry.py`

---

## 技術スタック

| レイヤー | 技術 |
|----------|------|
| **Backend** | Python 3.11+ / FastAPI / uvicorn / websockets / aiohttp |
| **Frontend** | React 18 / Vite / TypeScript / Web Audio API (AudioWorklet) |
| **音声処理** | PCM16 24kHz / Azure Semantic VAD / Deep Noise Suppression / Echo Cancellation |
| **音声認識** | Azure Speech (日本語) — `input_audio_transcription` |
| **音声合成** | Azure Voice Live 内蔵 TTS（`ja-JP-NanamiNeural`） |
| **LLM** | GPT-Realtime（Azure OpenAI） |
| **Storage** | In-memory（通話終了時に JSON ログ出力） |
| **認証** | Azure API Key（`.env` で管理） |

---

## リポジトリ構成

```
voice-live-agent-runtime/
├── README.md
├── LICENSE
├── docs/
│   ├── architecture.md          # 本ドキュメント
│   └── phase-design.md          # フェーズ設計ドキュメント
│
├── backend/
│   ├── pyproject.toml            # Python プロジェクト設定
│   ├── .env.example              # 環境変数テンプレート
│   └── app/
│       ├── __init__.py           # バージョン定義
│       ├── main.py               # FastAPI アプリ & WebSocket ハンドラ
│       ├── config.py             # Pydantic Settings
│       ├── voicelive/
│       │   └── session.py        # VoiceLiveSession（Azure WS 管理）
│       ├── context/
│       │   └── manager.py        # ContextManager（履歴・要約）
│       ├── phases/
│       │   ├── definitions.py    # フェーズ定義（instructions / tools）
│       │   ├── transitions.py    # 遷移ルール・終端ツール
│       │   └── router.py         # PhaseRouter（状態機械）
│       ├── tools/
│       │   ├── registry.py       # ツール登録・スキーマ
│       │   ├── meta.py           # フェーズ制御ツール
│       │   ├── customer.py       # 本人確認（モック DB）
│       │   ├── order.py          # 注文照会・プラン変更
│       │   └── escalation.py     # エスカレーション起票
│       └── subagent/
│           └── oob.py            # OOBSubagent（Out-of-Band 推論）
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   ├── public/
│   │   └── pcm-worklet.js       # AudioWorklet プロセッサ
│   └── src/
│       ├── main.tsx              # エントリポイント
│       ├── App.tsx               # メインコンポーネント
│       ├── components/
│       │   ├── SessionControl.tsx   # セッション制御 UI
│       │   ├── PhaseIndicator.tsx   # フェーズ表示バッジ
│       │   ├── TranscriptLog.tsx    # 会話ログ表示
│       │   └── ToolCallLog.tsx      # ツール呼出ログ表示
│       ├── audio/
│       │   ├── recorder.ts       # MicRecorder（AudioWorklet）
│       │   └── player.ts         # AudioPlayer（Web Audio API）
│       ├── ws/
│       │   └── client.ts         # WsClient（WebSocket クライアント）
│       └── types/
│           └── events.ts         # メッセージ型定義
│
└── tests/                        # （backend/tests/ 配下）
    ├── conftest.py
    ├── test_phase_router.py
    ├── test_context_manager.py
    └── test_oob_subagent.py
```

---

## WebSocket メッセージフォーマット

### Frontend → Backend

#### 音声データ

```json
{
  "type": "audio",
  "data": "<base64 encoded PCM16 24kHz mono>"
}
```

#### セッション制御

```json
{
  "type": "control",
  "action": "start" | "stop"
}
```

### Backend → Frontend

#### 音声再生

```json
{
  "type": "audio",
  "data": "<base64 encoded PCM16 24kHz mono>"
}
```

#### ユーザー発話テキスト

```json
{
  "type": "transcript",
  "role": "user",
  "text": "プランを変更したいのですが",
  "phase": "business",
  "item_id": "item_abc123"
}
```

#### アシスタント発話（ストリーミング差分）

```json
{
  "type": "transcript_delta",
  "role": "assistant",
  "delta": "かしこまりました",
  "item_id": "item_def456"
}
```

#### アシスタント発話（確定）

```json
{
  "type": "transcript",
  "role": "assistant",
  "text": "かしこまりました。プランの変更を承ります。",
  "phase": "business",
  "item_id": "item_def456"
}
```

#### フェーズ変更通知

```json
{
  "type": "phase_changed",
  "from": "identity",
  "to": "business",
  "vars": {
    "customer_name": "山田 太郎",
    "customer_plan": "プレミアム"
  }
}
```

#### ツール呼出結果

```json
{
  "type": "tool_call",
  "name": "verify_customer",
  "args": { "customer_id": "12345678" },
  "result": { "verified": true, "customer_id": "12345678", "name": "山田 太郎", "plan": "プレミアム" },
  "duration_ms": 15
}
```

#### 発話検出

```json
{ "type": "speech_started" }
```

```json
{ "type": "speech_stopped" }
```

#### セッション状態

```json
{ "type": "session_ready" }
```

```json
{ "type": "session_end", "reason": "通話終了" }
```

#### 要約実行通知

```json
{ "type": "summary_executed", "tokens": 12500 }
```

#### エラー

```json
{ "type": "error", "message": "Voice Live error: ..." }
```

---

## イベント処理フロー

Voice Live API から受信するサーバーイベントと、各イベントの処理内容を以下に示す。

### イベントディスパッチ表

| Voice Live イベント | 処理内容 |
|---------------------|----------|
| `session.created` | フロントエンドに `session_ready` を送信 |
| `session.updated` | ログ出力のみ |
| `input_audio_buffer.speech_started` | フロントエンドに `speech_started` を送信 |
| `input_audio_buffer.speech_stopped` | フロントエンドに `speech_stopped` を送信 |
| `conversation.item.input_audio_transcription.completed` | ContextManager に発話記録、フロントエンドに `transcript` 送信 |
| `response.audio_transcript.delta` | フロントエンドに `transcript_delta` 送信（ストリーミング） |
| `response.audio_transcript.done` | ContextManager に発話記録、フロントエンドに `transcript` 送信（確定） |
| `response.audio.delta` | フロントエンドに `audio` 送信（再生用音声データ） |
| `conversation.item.created` | item が `function_call` の場合、PhaseRouter に通知 |
| `response.function_call_arguments.done` | PhaseRouter でツール実行 → 遷移判定 → 結果返却 |
| `response.done` | トークン使用量更新、OOB レスポンスチェック、要約トリガー判定 |
| `error` | エラーログ出力、フロントエンドに `error` 送信 |

### 処理シーケンス図

```
Frontend            Backend                     Voice Live API
  │                    │                              │
  │── audio ─────────> │── input_audio_buffer ──────> │
  │                    │                              │
  │                    │ <── speech_started ───────── │
  │ <── speech_started │                              │
  │                    │                              │
  │                    │ <── transcription.completed ─ │
  │ <── transcript     │  (ContextManager に記録)      │
  │                    │                              │
  │                    │ <── audio_transcript.delta ── │
  │ <── transcript_delta│                              │
  │                    │ <── response.audio.delta ──── │
  │ <── audio (再生)    │                              │
  │                    │                              │
  │                    │ <── item.created (func_call) ─│
  │                    │  → PhaseRouter.handle_function_call
  │                    │                              │
  │                    │ <── func_call_arguments.done ─│
  │                    │  → execute_tool()             │
  │                    │  → _check_transition()        │
  │                    │                              │
  │                    │── conversation.item.create ──>│  (ツール結果)
  │                    │── response.create ──────────> │  (応答生成要求)
  │ <── tool_call      │                              │
  │ <── phase_changed  │── session.update ──────────> │  (フェーズ切替)
  │                    │                              │
  │                    │ <── response.done ─────────── │
  │                    │  → update_usage()             │
  │                    │  → maybe_summarize()          │
  │ <── summary_executed│                              │
  │                    │                              │
```
