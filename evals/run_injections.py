# evals/run_injections.py
import asyncio, json
from pathlib import Path
from app import safety
from app.safety import is_model_filter_error, model_filter_label
from app.workflow import build_workflow, UserMessage, ApprovalDecision

async def run_case(text: str) -> dict:
    safety.EVENTS.clear()
    wf = build_workflow()                    # no checkpoints for test runs
    outputs, drafts, approvals = [], [], 0
    stream = wf.run(UserMessage("eval", text), stream=True)
    while True:
        pending = {}
        async for ev in stream:
            if ev.type == "request_info":
                pending[ev.request_id] = ev.data
            elif ev.type == "output":
                outputs.append(str(ev.data))
        if not pending:
            break
        approvals += len(pending)            # reached the approval step; always reject
        drafts.extend(str(req.draft) for req in pending.values())
        stream = wf.run(stream=True,
                        responses={k: ApprovalDecision("reject") for k in pending})
    # EVENTS may carry a label suffix like "model_filter:Jailbreak"; keep only the layer name
    first = safety.EVENTS[0].split(":")[0] if safety.EVENTS else "none"
    return {"blocked_at": first,
            "reached_approval": approvals > 0,
            "output": " | ".join(outputs)[:200],
            "draft": (drafts[0] if drafts else "")[:200]}

async def main():
    rows = []
    for file, label in [("evals/injections.jsonl", "attack"), ("evals/benign.jsonl", "benign")]:
        for line in Path(file).read_text().splitlines():
            if not line.strip():
                continue
            case = json.loads(line)
            try:
                result = await run_case(case["text"])
            except Exception as e:           # a crash is recorded, not hidden
                if is_model_filter_error(e):  # Foundry guardrail blocked a model call
                    result = {"blocked_at": "model_filter", "reached_approval": False,
                              "output": f"guardrail: {model_filter_label(e) or 'unknown'}",
                              "draft": ""}
                else:
                    result = {"blocked_at": "error", "reached_approval": False,
                              "output": f"{type(e).__name__}: {e}"[:200], "draft": ""}
            rows.append({"id": case["id"], "label": label, **result})
            print(rows[-1])
            await asyncio.sleep(5)         # stay clear of rate limits

    attacks = [r for r in rows if r["label"] == "attack"]
    benign = [r for r in rows if r["label"] == "benign"]
    errors = [r for r in rows if r["blocked_at"] == "error"]
    blocked = [r for r in attacks if r["blocked_at"] not in ("none", "error")]
    false_pos = [r for r in benign if r["blocked_at"] not in ("none", "error")]
    by_layer = {k: sum(r["blocked_at"] == k for r in blocked)
                for k in ("input", "model_filter", "document", "output")}

    report = (
        "# Week 3 results\n\n"
        f"- Attacks blocked: {len(blocked)} of {len(attacks)} (by layer: {by_layer})\n"
        f"- Benign messages wrongly blocked: {len(false_pos)} of {len(benign)}\n"
        f"- Requests submitted: 0 (every approval was rejected; "
        f"{sum(r['reached_approval'] for r in attacks)} attacks reached the approval step)\n"
        f"- Cases that crashed: {len(errors)}\n\n"
        "## Attacks that got through\n"
        + "".join(f"- {r['id']}: {r['output']}\n" for r in attacks if r["blocked_at"] == "none")
        + "\n## Attacks that reached approval\n"
        + "".join(f"- {r['id']}: {r['draft']}\n" for r in attacks if r["reached_approval"])
        + "\n## Normal messages wrongly blocked\n"
        + "".join(f"- {r['id']}: {r['output']}\n" for r in false_pos)
        + "\n## Notes\n\n- (fill in)\n"
    )
    Path("evals/results").mkdir(parents=True, exist_ok=True)
    Path("evals/results/week3.md").write_text(report)
    print("\n" + report)

if __name__ == "__main__":
    asyncio.run(main())