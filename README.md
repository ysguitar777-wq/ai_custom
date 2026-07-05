# Sonnet → Fable アライメント設定キット

Claude Sonnet 5 (`claude-sonnet-5`) を、Claude Fable 5 (`claude-fable-5`) の挙動・品質に**できる限り**近づけるための設定とプロンプトのセットです。

## まず正直な前提

Fable 5 は Sonnet より上位のモデルであり、**設定やプロンプトだけで能力を同等にすることはできません**。ただし、Fable の強さの一部は「API パラメータの使い方」と「プロンプトの与え方」に由来するため、その部分は Sonnet でも再現できます。埋められるギャップと埋められないギャップを分けると:

| ギャップ | 埋められるか | 手段 |
|---|---|---|
| 思考の深さ・粘り強さ | ◯ かなり | `effort: "xhigh"` + adaptive thinking + 大きな `max_tokens` |
| 長時間の自律実行 | ◯ 部分的に | タスク仕様を最初に全部渡す + Task Budget + 自己検証ループ |
| 進捗報告の正確さ・出力の読みやすさ | ◯ ほぼ | Fable 向けプロンプトスニペットの移植(`prompts/`) |
| 計画・戦略の質 | △ 部分的に | Advisor ツールで Opus 4.8 に戦略判断だけ委ねる |
| 素の推論能力の上限 | ✕ | モデル固有。ここが最終的な差 |

## 構成

```
config/request_config.json          … 推奨リクエストパラメータ(用途別 3 プロファイル)
prompts/fable_style_system_prompt.md … Fable 流の挙動を引き出すシステムプロンプト
examples/sonnet_fable_client.py     … 上記を組み合わせた Python 実装例
```

## 主要なレバー(効果が大きい順)

### 1. `effort: "xhigh"` + adaptive thinking

Sonnet 5 は Sonnet 系で初めて `xhigh` エフォートに対応しています。Fable がデフォルトで行う「深く考えてから動く」挙動に最も近づく設定です。

```python
client.messages.create(
    model="claude-sonnet-5",
    max_tokens=64000,               # xhigh では思考+ツール呼び出しの余裕を確保
    thinking={"type": "adaptive"},  # Sonnet 5 は省略時も adaptive(明示推奨)
    output_config={"effort": "xhigh"},
    ...
)
```

注意: `budget_tokens` と非デフォルトの `temperature`/`top_p`/`top_k` は Sonnet 5 では 400 エラーになります(Fable と同じ制約)。

### 2. タスク仕様を最初に全部渡す

Fable の長時間自律実行の強さは「最初のターンで完全な仕様を受け取り、high effort で走る」使い方とセットです。Sonnet でも同じ渡し方をすると自律性が大きく向上します。曖昧な指示を小出しにするのが最も性能を落とすパターンです。

### 3. Fable 向けプロンプトスニペットの移植

Fable のプロンプトガイドにある挙動調整(計画しすぎ防止・進捗報告の根拠付け・境界の明示・最終サマリーの読みやすさ)は Sonnet 5 にもそのまま効きます。`prompts/fable_style_system_prompt.md` にまとめてあります。

### 4. Advisor ツール(ベータ)で Opus 4.8 を「参謀」に付ける

実行役は Sonnet 5 のまま、生成途中の戦略判断だけを上位モデルに委ねられます。トークン生成の大半は Sonnet 価格のまま、計画品質を底上げできます。

```python
client.beta.messages.create(
    model="claude-sonnet-5",
    betas=["advisor-tool-2026-03-01"],
    tools=[{"type": "advisor_20260301", "name": "advisor", "model": "claude-opus-4-8"}],
    ...
)
```

(advisor には Fable は指定できません。現状の有効ペアは Opus 4.8 / 4.7 です。)

### 5. Task Budget(ベータ)

エージェントループ全体のトークン予算をモデル自身に見せて、Fable のように「配分を考えながら最後まで走り切る」挙動を促します。ベータヘッダ `task-budgets-2026-03-13`、最小 20,000 トークン。

### 6. 自己検証ループ

Fable は自前の検証を回す傾向が強いモデルです。Sonnet ではプロンプトで明示的に要求します(システムプロンプトに含めてあります)。さらに効果を出すには、別コンテキストの検証用サブエージェント(fresh-context verifier)を立てるのが有効です。

## コスト感

| モデル | 入力 $/1M | 出力 $/1M |
|---|---|---|
| Fable 5 | $10.00 | $50.00 |
| Sonnet 5 | $3.00(〜2026-08-31 は $2.00) | $15.00(同 $10.00) |

Sonnet 5 + xhigh + Advisor(Opus 4.8)でも、多くのワークロードで Fable より安く収まります。まず本キットの設定で評価し、それでも品質が足りないタスクだけ Fable に送る「ルーティング」構成が現実的です。
