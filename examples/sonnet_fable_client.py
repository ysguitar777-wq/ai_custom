"""Sonnet 5 を Fable に近づけた設定で呼び出すクライアント例。

3 つの呼び出しパターン:
  1. run_fable_max      — xhigh effort + adaptive thinking + ストリーミング(基本形)
  2. run_with_advisor   — Opus 4.8 を Advisor(参謀)に付けて戦略判断を底上げ
  3. run_agent_loop     — Task Budget 付きのエージェントループ

前提: pip install anthropic / ANTHROPIC_API_KEY が設定済み。
"""

from pathlib import Path

import anthropic

MODEL = "claude-sonnet-5"
ADVISOR_MODEL = "claude-opus-4-8"

# Fable スタイルのシステムプロンプト(prompts/ から読み込み)
SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "fable_style_system_prompt.md"

client = anthropic.Anthropic()


def load_system_prompt(base_prompt: str) -> str:
    """アプリ固有のシステムプロンプトに Fable スタイルの挙動指示を連結する。

    キャッシュ効率のため、この結合結果は固定文字列として使うこと
    (タイムスタンプ等の動的要素を混ぜるとプロンプトキャッシュが無効化される)。
    """
    snippets = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return f"{base_prompt}\n\n{snippets}"


def run_fable_max(task: str, system: str) -> anthropic.types.Message:
    """基本形: 最難関タスク向け。Fable のデフォルト挙動に最も近い設定。"""
    with client.messages.stream(
        model=MODEL,
        max_tokens=128000,
        system=[{
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }],
        thinking={"type": "adaptive"},
        output_config={"effort": "xhigh"},
        messages=[{"role": "user", "content": task}],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
        return stream.get_final_message()


def run_with_advisor(task: str, system: str) -> anthropic.types.Message:
    """Opus 4.8 を Advisor に付ける: 実行は Sonnet、戦略判断だけ上位モデル。

    Advisor はサーバーサイドで動くため tool_result の往復は不要。
    """
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=64000,
        betas=["advisor-tool-2026-03-01"],
        system=system,
        thinking={"type": "adaptive"},
        output_config={"effort": "xhigh"},
        tools=[{
            "type": "advisor_20260301",
            "name": "advisor",
            "model": ADVISOR_MODEL,
        }],
        messages=[{"role": "user", "content": task}],
    )
    # 複数ターンで続ける場合は advisor_tool_result ブロックを含む
    # response.content 全体を次の messages に戻すこと。
    return response


def run_agent_loop(task: str, system: str, tools: list, total_budget: int = 200000):
    """Task Budget 付きエージェントループ。

    モデルにループ全体のトークン予算を見せることで、Fable のように
    「残り予算を意識して最後まで走り切る」挙動を促す(最小 20,000)。
    """
    messages = [{"role": "user", "content": task}]

    while True:
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=128000,
            betas=["task-budgets-2026-03-13"],
            system=system,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "xhigh",
                "task_budget": {"type": "tokens", "total": total_budget},
            },
            tools=tools,
            messages=messages,
        ) as stream:
            response = stream.get_final_message()

        if response.stop_reason == "end_turn":
            return response

        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)  # 実装は利用側で
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        # max_tokens 到達など — Sonnet 5 の新トークナイザは同一テキストで
        # 約 30% 多くトークンを消費するため、旧モデル基準の上限だと途中で切れやすい
        return response


def execute_tool(name: str, tool_input: dict) -> str:
    raise NotImplementedError("利用側でツール実装を差し込んでください")


if __name__ == "__main__":
    system = load_system_prompt("You are a senior software engineer.")
    # タスク仕様は最初のターンで完全に渡す — これが Fable 的挙動を引き出す最重要ポイント
    task = (
        "目的: [何を達成したいか]\n"
        "背景: [誰のため・なぜ必要か]\n"
        "制約: [守るべき条件]\n"
        "完了条件: [検証可能な形で]\n"
    )
    msg = run_fable_max(task, system)
    print(f"\n\n[stop_reason={msg.stop_reason}, output_tokens={msg.usage.output_tokens}]")
