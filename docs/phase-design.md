# フェーズ設計ドキュメント

## フェーズ概要

本システムは、コールセンター受付シナリオを **4 つのフェーズ** に分割し、フェーズごとに異なる instructions（システムプロンプト）とツールセットを Voice Live API に適用することで、会話の流れを制御します。

| フェーズ | 役割 | 利用可能ツール |
|----------|------|----------------|
| **triage** | 受付・用件聞き取り | `start_identity_verification`, `end_call`, `escalate_to_human` |
| **identity** | 本人確認 | `verify_customer`, `back_to_triage`, `escalate_to_human` |
| **business** | 業務受付・処理 | `lookup_order`, `update_plan`, `end_call`, `escalate_to_human` |
| **escalation** | エスカレーション準備 | `create_escalation` |

---

## フェーズ定義

### triage（トリアージ）

**目的**: お客様の用件を聞き取り、適切なフェーズに振り分ける。

**instructions**:
```
あなたはコンタクトセンター受付AIです。
明るく丁寧な応対で、お客様のご用件を聞き取ってください。

- ご用件が『本人確認が必要な業務(解約・プラン変更・残高照会)』の場合は
  start_identity_verification ツールを呼んでください。
- ご用件が『単純な問合せ(営業時間、場所など)』の場合は直接お答えし、
  最後に end_call ツールを呼んでください。
- ご用件が不明、またはお客様が強く感情的な場合は
  escalate_to_human ツールを呼んでください。

必ず1-2文以内で短く応答してください。
```

**利用可能ツール**: `start_identity_verification`, `end_call`, `escalate_to_human`

**想定されるインタラクション**:
- 単純な問合せ（営業時間など）→ 直接回答 → `end_call`
- 本人確認が必要な用件 → `start_identity_verification` → identity フェーズへ
- 強い感情的表現・不明瞭な用件 → `escalate_to_human` → escalation フェーズへ

---

### identity（本人確認）

**目的**: お客様番号（8 桁）による本人確認を実施する。

**instructions**:
```
本人確認フェーズです。
お客様に『本人確認のため、8桁のお客様番号をお願いします』と伝えてください。
8桁の数字を聞き取ったら verify_customer ツールを呼んでください。
3回聞き取り失敗したら escalate_to_human を呼んでください。
お客様が本人確認を拒否した場合は back_to_triage を呼んでください。
```

**利用可能ツール**: `verify_customer`, `back_to_triage`, `escalate_to_human`

**想定されるインタラクション**:
- お客様番号提示 → `verify_customer` → 検証成功なら business フェーズへ
- 検証失敗 → 再試行を促す（identity フェーズに留まる）
- 本人確認拒否 → `back_to_triage` → triage フェーズへ
- 3 回失敗 → `escalate_to_human` → escalation フェーズへ

---

### business（業務受付）

**目的**: 本人確認済みのお客様に対し、具体的な業務処理を行う。

**instructions**:
```
業務受付フェーズです。
本人確認済みのお客様: {customer_name}様 (プラン: {customer_plan})
引き継ぎ事項: {triage_summary}

お客様のご用件について具体的な情報を聞き取り、
適切なツール (lookup_order, update_plan 等) を呼んでください。
完了したらお礼を述べて end_call を呼んでください。
```

> `{customer_name}`, `{customer_plan}`, `{triage_summary}` は `ContextManager.prepare_handoff()` で生成されたコンテキスト変数で置換される。

**利用可能ツール**: `lookup_order`, `update_plan`, `end_call`, `escalate_to_human`

**想定されるインタラクション**:
- 注文確認 → `lookup_order` → 結果を伝達
- プラン変更 → `update_plan` → 完了報告 → `end_call`
- 対応困難な案件 → `escalate_to_human` → escalation フェーズへ

---

### escalation（エスカレーション）

**目的**: オペレータへの引き継ぎ準備を行う。

**instructions**:
```
エスカレーション準備フェーズです。
引き継ぎサマリ: {escalation_summary}

オペレータに引き継ぐため、以下を順に実施してください:
1. お客様に『担当者にお繋ぎしますので、そのままお待ちください』と伝える
2. create_escalation ツールを呼ぶ
3. 『少々お待ちください』と伝えて終了
```

> `{escalation_summary}` は OOB Subagent で生成されたサマリで置換される。

**利用可能ツール**: `create_escalation`

**想定されるインタラクション**:
- お客様に待機を依頼 → `create_escalation` → チケット作成 → 通話終了

---

## 遷移ルール

### 遷移マップ

```python
# (current_phase, tool_name) → next_phase
TRANSITIONS = {
    ("triage",    "start_identity_verification"): "identity",
    ("triage",    "escalate_to_human"):           "escalation",
    ("identity",  "verify_customer"):             "business",     # verified=True の場合のみ
    ("identity",  "back_to_triage"):              "triage",
    ("identity",  "escalate_to_human"):           "escalation",
    ("business",  "escalate_to_human"):           "escalation",
}
```

### 終端ツール

以下のツールが実行されるとセッションを終了する。

```python
TERMINAL_TOOLS = {"end_call", "create_escalation"}
```

### 条件付き遷移

| ツール | 条件 | 遷移 |
|--------|------|------|
| `verify_customer` | `result["verified"] == True` | identity → business |
| `verify_customer` | `result["verified"] == False` | 遷移なし（identity に留まる） |

### フェーズ遷移フローチャート

```
                    ┌──────────────────┐
                    │    SESSION START  │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
            ┌──────│     triage        │──────┐
            │      └───────┬──────────┘      │
            │              │                  │
            │  start_      │ end_call         │ escalate_
            │  identity_   │ (終端)            │ to_human
            │  verification│                  │
            ▼              ▼                  │
   ┌──────────────────┐  ┌─────┐             │
   │    identity       │  │ END │             │
   └──┬────┬───────┬──┘  └─────┘             │
      │    │       │                          │
      │    │  back_│                          │
      │    │  to_  │                          │
      │    │  triage                          │
      │    │   │                              │
      │    │   └──► triage へ戻る              │
      │    │                                  │
      │    │ escalate_to_human                │
      │    │                                  │
      │    └──────────────────────────────────┤
      │                                       │
      │ verify_customer                       │
      │ (verified=True)                       │
      ▼                                       ▼
   ┌──────────────────┐             ┌──────────────────┐
   │    business       │────────────│   escalation      │
   └──────┬───────────┘ escalate_   └────────┬─────────┘
          │             to_human              │
          │ end_call                          │ create_escalation
          │ (終端)                             │ (終端)
          ▼                                   ▼
        ┌─────┐                             ┌─────┐
        │ END │                             │ END │
        └─────┘                             └─────┘
```

---

## フェーズ遷移フロー（詳細）

フェーズ遷移は以下の 7 ステップで実行される。

### 1. Function Call 受信

Voice Live API から `conversation.item.created` イベント（`type: "function_call"`）を受信。PhaseRouter が `call_id` と `name` を保持する。

### 2. Tool Executor 実行

`response.function_call_arguments.done` イベントで引数の JSON が確定。`execute_tool(name, args)` でツール関数を実行し、結果を取得。実行時間を計測する。

### 3. 遷移判定

`(current_phase, tool_name)` のペアで `TRANSITIONS` テーブルを参照。

- **終端ツール**（`end_call`, `create_escalation`）: セッション終了フローへ
- **条件付き遷移**（`verify_customer`）: `result["verified"]` が `True` の場合のみ遷移
- **通常遷移**: 遷移先フェーズが決定
- **遷移なし**: ツール結果を返すだけでフェーズは変わらない

### 4. ContextManager prepare_handoff

遷移が発生する場合、`ContextManager.prepare_handoff()` を呼び出す。

- ツール結果から顧客情報（`customer_name`, `customer_plan` など）を抽出
- OOB Subagent で引き継ぎサマリを生成
- 遷移先フェーズの instructions に注入するコンテキスト変数を返す

### 5. session.update

新フェーズの instructions（コンテキスト変数を展開済み）とツールスキーマで `session.update` を Voice Live API に送信。

```json
{
  "type": "session.update",
  "session": {
    "instructions": "業務受付フェーズです。\n本人確認済みのお客様: 山田 太郎様 ...",
    "tools": [
      { "type": "function", "name": "lookup_order", ... },
      { "type": "function", "name": "update_plan", ... },
      ...
    ]
  }
}
```

### 6. response.create

ツール結果を `conversation.item.create`（`function_call_output`）で送信し、続けて `response.create` で応答生成を要求。

### 7. phase_changed 通知

フロントエンドに `phase_changed` イベントを送信し、UI 上のフェーズ表示を更新。

```json
{
  "type": "phase_changed",
  "from": "identity",
  "to": "business",
  "vars": { "customer_name": "山田 太郎", "customer_plan": "プレミアム" }
}
```

---

## コンテキスト管理戦略

> 現在の実装では、OOB による引き継ぎサマリ生成と `conversation_summary` / `*_summary` のアプリ層保持までは行われます。
> 一方で、Issue に記載されている `conversation.item.delete` による古い item の削除、および summary system item の再注入はまだ実装されていません。

### 要約トリガー

- **閾値**: `SUMMARY_TOKEN_THRESHOLD`（デフォルト: 8000 トークン）
- **判定タイミング**: `response.done` イベント受信時
- **実行**: `ContextManager.maybe_summarize()` で OOB Subagent を使用

### 要約で削除されるもの vs 保持されるもの

| 対象 | 処理 |
|------|------|
| 古い発話テキスト | OOB で要約に圧縮 → `conversation_summary` 変数に格納 |
| ツール呼出ログ | ContextManager のフル履歴に保持（Voice Live からは削除） |
| フェーズ遷移履歴 | ContextManager のフル履歴に保持 |
| コンテキスト変数 | 常に保持（`customer_name`, `customer_plan` 等） |
| 累積トークン数 | 要約後にリセット |

### 引き継ぎサマリ生成

フェーズ遷移時に OOB Subagent で生成。

- **入力**: これまでの会話内容（utterances）
- **出力**: 簡潔な引き継ぎサマリ（300 トークン程度）
- **用途**: 次フェーズの instructions に `{triage_summary}` や `{escalation_summary}` として注入

---

## ツール一覧

### verify_customer

**概要**: お客様番号（8 桁）で本人確認を行う。

```json
{
  "type": "function",
  "name": "verify_customer",
  "description": "お客様番号で本人確認を行う",
  "parameters": {
    "type": "object",
    "properties": {
      "customer_id": { "type": "string", "description": "8桁のお客様番号" }
    },
    "required": ["customer_id"]
  }
}
```

**戻り値（成功時）**:
```json
{
  "verified": true,
  "customer_id": "12345678",
  "name": "山田 太郎",
  "plan": "プレミアム",
  "since": "2019-04-01"
}
```

**戻り値（失敗時）**:
```json
{
  "verified": false,
  "reason": "該当する顧客が見つかりません"
}
```

**モック DB**:
| customer_id | name | plan | since |
|-------------|------|------|-------|
| 12345678 | 山田 太郎 | プレミアム | 2019-04-01 |
| 87654321 | 佐藤 花子 | ベーシック | 2023-10-15 |

---

### lookup_order

**概要**: 顧客の注文情報を照会する。`order_id` 省略時は直近の注文を返す。

```json
{
  "type": "function",
  "name": "lookup_order",
  "description": "注文情報を照会する",
  "parameters": {
    "type": "object",
    "properties": {
      "customer_id": { "type": "string", "description": "お客様番号" },
      "order_id": { "type": "string", "description": "注文ID（省略可）" }
    },
    "required": ["customer_id"]
  }
}
```

**戻り値**:
```json
{
  "order_id": "ORD-2026-0042",
  "status": "出荷済",
  "items": ["商品A x1"],
  "total_jpy": 4980
}
```

---

### update_plan

**概要**: 顧客のプランを変更する。

```json
{
  "type": "function",
  "name": "update_plan",
  "description": "プランを変更する",
  "parameters": {
    "type": "object",
    "properties": {
      "customer_id": { "type": "string", "description": "お客様番号" },
      "new_plan": { "type": "string", "description": "新しいプラン名" }
    },
    "required": ["customer_id", "new_plan"]
  }
}
```

**戻り値**:
```json
{
  "success": true,
  "old_plan": "プレミアム",
  "new_plan": "ベーシック"
}
```

---

### create_escalation

**概要**: エスカレーションチケットを作成する。**終端ツール**。

```json
{
  "type": "function",
  "name": "create_escalation",
  "description": "エスカレーションチケットを作成する",
  "parameters": {
    "type": "object",
    "properties": {
      "summary": { "type": "string", "description": "問題のサマリ" },
      "urgency": { "type": "string", "description": "緊急度（low/medium/high）" },
      "customer_id": { "type": "string", "description": "お客様番号（省略可）" }
    },
    "required": ["summary", "urgency"]
  }
}
```

**戻り値**:
```json
{
  "ticket_id": "ESC-a1b2c3d4",
  "created": true
}
```

---

### start_identity_verification

**概要**: 本人確認フェーズを開始する。triage → identity への遷移トリガー。

```json
{
  "type": "function",
  "name": "start_identity_verification",
  "description": "本人確認フェーズを開始する",
  "parameters": { "type": "object", "properties": {}, "required": [] }
}
```

**戻り値**:
```json
{
  "action": "start_identity",
  "next_phase": "identity"
}
```

---

### back_to_triage

**概要**: トリアージフェーズに戻る。identity → triage への遷移トリガー。

```json
{
  "type": "function",
  "name": "back_to_triage",
  "description": "トリアージフェーズに戻る",
  "parameters": { "type": "object", "properties": {}, "required": [] }
}
```

**戻り値**:
```json
{
  "action": "back_to_triage",
  "next_phase": "triage"
}
```

---

### escalate_to_human

**概要**: オペレータにエスカレーションする。複数フェーズからの遷移トリガー。

```json
{
  "type": "function",
  "name": "escalate_to_human",
  "description": "オペレータにエスカレーションする",
  "parameters": {
    "type": "object",
    "properties": {
      "reason": { "type": "string", "description": "エスカレーション理由" }
    },
    "required": ["reason"]
  }
}
```

**戻り値**:
```json
{
  "action": "escalate",
  "reason": "お客様が強い不満を表明",
  "next_phase": "escalation"
}
```

---

### end_call

**概要**: 通話を終了する。**終端ツール**。

```json
{
  "type": "function",
  "name": "end_call",
  "description": "通話を終了する",
  "parameters": {
    "type": "object",
    "properties": {
      "summary": { "type": "string", "description": "対応サマリ" }
    },
    "required": ["summary"]
  }
}
```

**戻り値**:
```json
{
  "action": "end_call",
  "summary": "営業時間のご案内。平日9時〜17時。"
}
```
