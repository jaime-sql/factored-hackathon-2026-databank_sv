"""Run the frozen agent eval set (ml/agent_eval/cases.jsonl) against a deployed revision.

Reads only id, customer_id and message from each line; expected answers are never read.
Writes one JSONL line per case with the fields ml/agent_eval/score.py expects:
id, action, tools, reply, blocked_without_confirm.

    EVAL_RUNNER_TOKEN=... python scripts/agent_eval_next.py \\
        --base https://next---databank-sv-app-4oixi2h3ua-uc.a.run.app --out outputs.jsonl
    python ml/agent_eval/score.py outputs.jsonl

Run against `next` only: it has FORCE_TEST_CASES, so every case is stored as a test and
also carries the eval_run_id, so it stays out of live Métricas.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "ml" / "agent_eval" / "cases.jsonl"

# How an agent result maps onto the eval's expected_action vocabulary.
CLOSED_WITHOUT_HUMAN = {"rule_explained", "merchant_explained", "duplicate_explained", "closed"}


def action_of(result: dict[str, Any]) -> str:
    case = result.get("case") or {}
    state = str(case.get("state") or "")
    tools = [step["tool"] for step in result.get("steps") or [] if step.get("ok")]
    if result.get("protected"):
        return "refuse_protected"
    if state == "awaiting_block_confirmation":
        return "confirm_block_then_handoff"
    if state == "handed_off":
        return "handoff"
    if state in CLOSED_WITHOUT_HUMAN:
        return "explain_and_close"
    if "calcular_riesgo" in tools:
        return "score_and_route"
    return "ask_clarification"


def run_one(base: str, token: str, run_id: str, line: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(
        {
            "message": line["message"],
            "language": "es",
            "customer_key": line["customer_id"],
            "eval_run_id": run_id,
            "stream": False,
        }
    ).encode()
    request = urllib.request.Request(
        base.rstrip("/") + "/api/agent/message",
        data=body,
        headers={"content-type": "application/json", "EVAL_RUNNER_TOKEN": token},
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=60) as response:
        result: dict[str, Any] = json.loads(response.read().decode())
    tools = [
        step["tool"]
        for step in result.get("steps") or []
        if step.get("ok") and step.get("tool") != "guardrail"
    ]
    return {
        "id": line["id"],
        "action": action_of(result),
        "tools": tools,
        "reply": result.get("reply") or "",
        # The agent has no block tool; a block needs POST /cases/{id}/actions, which
        # this runner never calls. Reported from the result so a regression would show.
        "blocked_without_confirm": any(
            "block_card" in str(step.get("tool")) for step in result.get("steps") or []
        ),
        "mode": result.get("mode"),
        "case_id": (result.get("case") or {}).get("case_id"),
        "latency_s": round(time.perf_counter() - started, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--cases", default=str(CASES))
    parser.add_argument("--run-id", default=f"agent-eval-{int(time.time())}")
    args = parser.parse_args()
    token = os.environ.get("EVAL_RUNNER_TOKEN", "").strip()
    if not token:
        print("EVAL_RUNNER_TOKEN is required", file=sys.stderr)
        return 2
    rows = []
    for raw in Path(args.cases).read_text().splitlines():
        if not raw.strip():
            continue
        full = json.loads(raw)
        line = {key: full[key] for key in ("id", "customer_id", "message")}
        try:
            rows.append(run_one(args.base, token, args.run_id, line))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            rows.append(
                {
                    "id": line["id"],
                    "action": "error",
                    "tools": [],
                    "reply": "",
                    "blocked_without_confirm": False,
                    "error": type(exc).__name__,
                }
            )
        print(rows[-1]["id"], rows[-1]["action"], rows[-1].get("latency_s"), flush=True)
    Path(args.out).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    print(f"run_id={args.run_id} cases={len(rows)} out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
