"""评估执行器：对 cases.json 中的每个用例自动跑 agent 并打分。

用法（在项目根目录）：
    python -m evals                    # 跑全部用例
    python -m evals --model step-5-preview
    python -m evals --cases evals/cases.json

评分口径：
- 工具选择：期望工具全部被调用即通过；期望为空时要求零调用（防过度触发）
- 内容合格：期望关键词命中率 >= 50%（无关键词的用例不参与内容评分）
- 用例通过 = 工具选择通过 且 内容合格

结果写入 evals/results/run-<时间戳>.json，便于跨运行对比、
支撑“改 prompt → 重跑评测 → 看指标变化”的迭代闭环。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# 允许从任意目录以 `python -m evals` 方式启动
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.core import Agent  # noqa: E402

KEYWORD_PASS_RATE = 0.5


def load_cases(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["cases"]


def score_case(case: dict, tool_calls: list[str], answer: str) -> dict:
    expected = set(case.get("expect_tools", []))
    called = set(tool_calls)

    if not expected:
        tool_ok = len(called) == 0
    else:
        tool_ok = expected.issubset(called)

    keywords = case.get("expect_keywords", [])
    if keywords:
        hits = sum(1 for k in keywords if k.lower() in answer.lower())
        kw_rate = hits / len(keywords)
    else:
        kw_rate = 1.0

    return {
        "tool_ok": tool_ok,
        "extra_tools": sorted(called - expected),
        "kw_rate": round(kw_rate, 2),
        "passed": tool_ok and kw_rate >= KEYWORD_PASS_RATE,
    }


def run_eval(cases: list[dict], model: str | None = None) -> tuple[list[dict], str]:
    agent = Agent(model=model)
    print(f"模型: {agent.model}    用例数: {len(cases)}\n")

    results = []
    for i, case in enumerate(cases, 1):
        agent.reset()  # 每个用例独立上下文，避免相互污染
        started = time.time()
        error = None
        try:
            answer = agent.chat(case["question"])
            tool_calls = list(agent.last_tool_calls)
        except Exception as exc:
            answer, tool_calls, error = "", [], f"{type(exc).__name__}: {exc}"
        elapsed = time.time() - started

        score = score_case(case, tool_calls, answer)
        score.update(
            {
                "id": case["id"],
                "question": case["question"],
                "expect_tools": case.get("expect_tools", []),
                "called_tools": tool_calls,
                "answer": answer,
                "error": error,
                "elapsed_sec": round(elapsed, 1),
            }
        )
        results.append(score)

        mark = "PASS" if score["passed"] else "FAIL"
        print(f"[{i}/{len(cases)}] {mark}  {case['id']}  ({elapsed:.1f}s)")
        if not score["passed"]:
            print(f"        期望工具: {score['expect_tools']}  实际: {tool_calls}")
            if keywords := case.get("expect_keywords"):
                print(f"        关键词命中率: {score['kw_rate']}（期望: {keywords}）")
            if error:
                print(f"        错误: {error}")
    return results, agent.model


def print_report(results: list[dict]) -> None:
    total = len(results)
    tool_ok = sum(1 for r in results if r["tool_ok"])
    passed = sum(1 for r in results if r["passed"])
    kw_rates = [r["kw_rate"] for r in results if r["error"] is None]
    avg_kw = sum(kw_rates) / len(kw_rates) if kw_rates else 0.0

    print("\n" + "=" * 56)
    print("  评估报告")
    print("=" * 56)
    print(f"  工具选择准确率 : {tool_ok}/{total}  ({tool_ok / total:.0%})")
    print(f"  平均关键词命中 : {avg_kw:.0%}")
    print(f"  综合通过率     : {passed}/{total}  ({passed / total:.0%})")
    failed = [r["id"] for r in results if not r["passed"]]
    if failed:
        print(f"  未通过用例     : {', '.join(failed)}")
    print("=" * 56)


def save_results(results: list[dict], model: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"run-{stamp}.json"
    payload = {
        "model": model,
        "timestamp": stamp,
        "summary": {
            "total": len(results),
            "tool_ok": sum(1 for r in results if r["tool_ok"]),
            "passed": sum(1 for r in results if r["passed"]),
        },
        "results": results,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="agent 工具调用评估")
    parser.add_argument("--model", default=None, help="覆盖模型（默认同 agent 本身）")
    parser.add_argument("--cases", default="evals/cases.json", help="测试集路径")
    parser.add_argument("--out-dir", default="evals/results", help="结果输出目录")
    args = parser.parse_args()

    cases = load_cases(Path(args.cases))
    results, model_name = run_eval(cases, model=args.model)
    print_report(results)

    saved = save_results(results, model_name, Path(args.out_dir))
    print(f"\n结果已保存: {saved}")

    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
