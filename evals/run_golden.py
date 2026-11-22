# evals/run_golden.py
# usage: python -m evals.run_golden --run-name baseline-v2 --note "keyword search, prompt v1"
#        add --per-type 1 for a quick check with one case of each type
import argparse, asyncio, hashlib, json, re
from pathlib import Path
import mlflow
from app import config, safety
from app.agents import RETRIEVED, ANSWER_PROMPT
from app.llm import complete
from app.llm_utils import extract_json
from app.safety import is_model_filter_error, model_filter_label
from app.tracing import start_tracing, flush_tracing
from app.workflow import build_workflow, UserMessage, ApprovalDecision

JUDGE_SYSTEM = (
    "You grade an assistant's answer. Be strict. Reply with JSON only: "
    '{"facts_found": [true or false for each required fact, in order], '
    '"groundedness": an integer 1-5 where 5 means every claim is supported by the passages, '
    '"reason": "one sentence"}'
)

# ---------- small helpers ----------

def norm(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()

def squash(s: str) -> str:
    """Letters and digits only, so 'AC 150/5210-20A' matches the file name 'AC-150-5210-20A'."""
    return re.sub(r"[^a-z0-9]", "", s.lower())

def passages_seen() -> list[str]:
    """Passages the model saw, without repeats from multiple searches."""
    return list(dict.fromkeys(RETRIEVED))

def sources_seen() -> list[str]:
    """File names of the passages the model saw, e.g. '[AC_103-6] text' -> 'AC_103-6'."""
    return sorted({p[1:p.index("]")] for p in RETRIEVED})

def sha(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:8]

async def with_retry(make_call, waits=(20, 40, 60)):
    """Run an async call; on a rate limit (429) wait and try again. Other errors are raised at once."""
    for wait in waits:
        try:
            return await make_call()
        except Exception as e:
            if not re.search(r"\b429\b|RateLimit", str(e)):
                raise
            print(f"  rate limited, waiting {wait}s")
            await asyncio.sleep(wait)
    return await make_call()                 # last try: let any error through

# ---------- run one case through the real workflow ----------

async def run_case(text: str) -> dict:
    safety.EVENTS.clear()
    RETRIEVED.clear()
    wf = build_workflow()
    outputs, drafts = [], []
    stream = wf.run(UserMessage("golden", text), stream=True)
    while True:
        pending = {}
        async for ev in stream:
            if ev.type == "request_info":
                pending[ev.request_id] = ev.data
            elif ev.type == "output":
                outputs.append(str(ev.data))
        if not pending:
            break
        drafts.extend(str(req.draft) for req in pending.values())
        stream = wf.run(stream=True,         # always reject, so nothing is submitted
                        responses={k: ApprovalDecision("reject") for k in pending})

    layers = [e.split(":")[0] for e in safety.EVENTS]
    if drafts:
        intent = "request"
    elif "input" in layers or "model_filter" in layers:
        intent = "refuse"
    else:
        intent = "question"
    return {"intent": intent, "events": layers, "output": " | ".join(outputs),
            "draft": drafts[0] if drafts else "",
            "sources": sources_seen(), "passages": passages_seen()}

async def run_case_safely(text: str) -> dict:
    """Like run_case, but turns errors into a result so one bad case can't stop the run."""
    try:
        return await with_retry(lambda: run_case(text))
    except Exception as e:
        blocked = is_model_filter_error(e)   # Foundry guardrail blocked a model call
        return {"intent": "refuse" if blocked else "error",
                "events": ["model_filter" if blocked else "error"],
                "output": f"guardrail: {model_filter_label(e) or 'unknown'}" if blocked
                          else f"{type(e).__name__}: {e}",
                "draft": "", "sources": sources_seen(), "passages": passages_seen()}

# ---------- scoring ----------

async def judge(system: str, answer: str, passages: list[str], facts: list[str]) -> dict:
    """Ask the judge model to grade one answer. Raises ValueError if its reply is unusable."""
    user = (f"Passages:\n{chr(10).join(passages) or '(none)'}\n\nAnswer:\n{answer}\n\n"
            f"Required facts:\n{json.dumps(facts)}")
    raw = await with_retry(lambda: complete(system, user, deployment=config.JUDGE,
                                            response_format={"type": "json_object"}))
    grade = json.loads(extract_json(raw))
    found, score = grade.get("facts_found"), grade.get("groundedness")
    if not (isinstance(found, list) and len(found) == len(facts)
            and all(isinstance(x, bool) for x in found)):
        raise ValueError(f"bad facts_found: {found}")
    if type(score) is not int or not 1 <= score <= 5:
        raise ValueError(f"bad groundedness: {score}")
    return grade

def fields_share(draft: str, expect: dict) -> float:
    """Share of expected fields that match the JSON draft."""
    try:
        parsed = json.loads(extract_json(draft))
    except ValueError:
        return 0.0
    if not isinstance(parsed, dict):
        return 0.0
    return sum(norm(parsed.get(k)) == norm(v) for k, v in expect.items()) / len(expect)

async def score(case: dict, r: dict) -> dict:
    """Scores for one case. Misrouted or crashed cases get 0; a judge failure gets None."""
    s = {"routing_ok": float(r["intent"] == case["type"])}
    if case["type"] == "question":
        s["source_retrieved"] = float(case["source"] in r["sources"])
        s.update(source_ok=0.0, facts_recall=0.0, groundedness=0.0)
        if r["intent"] == "question":
            s["source_ok"] = float(squash(case["source"]) in squash(r["output"]))
            try:
                g = await judge(JUDGE_SYSTEM, r["output"], r["passages"], case["must_mention"])
                s["facts_found"] = g["facts_found"]
                s["facts_recall"] = sum(g["facts_found"]) / len(g["facts_found"])
                s["groundedness"] = float(g["groundedness"])
                s["judge_reason"] = g.get("reason", "")
            except Exception as e:
                s.update(facts_recall=None, groundedness=None,
                         judge_error=f"{type(e).__name__}: {e}")
    elif case["type"] == "request":
        s["fields_ok"] = fields_share(r["draft"], case["expect"])
    elif case["type"] == "refuse":
        s["refused_ok"] = float(r["intent"] == "refuse")
    return s

def mean(rows: list[dict], key: str) -> float:
    values = [r[key] for r in rows if r.get(key) is not None]
    return sum(values) / len(values) if values else 0.0

def summarize(rows: list[dict]) -> dict:
    return {
        "routing_acc": mean(rows, "routing_ok"),
        "source_ok": mean(rows, "source_ok"),
        "facts_recall": mean(rows, "facts_recall"),
        "groundedness": mean(rows, "groundedness"),
        "fields_ok": mean(rows, "fields_ok"),
        "refused_ok": mean(rows, "refused_ok"),
        "source_retrieved": mean(rows, "source_retrieved"),
        "crashes": sum(r["intent"] == "error" for r in rows),
        "judge_errors": sum("judge_error" in r for r in rows),
    }

def problems(r: dict) -> list[str]:
    """Why a case needs a look. Empty list means it's fine."""
    out = []
    if not r["routing_ok"]:
        out.append(f"routed to {r['intent']}")
    if "judge_error" in r:
        out.append(f"judge failed: {r['judge_error'][:100]}")
    for key, want in [("facts_recall", 1), ("groundedness", 4), ("source_ok", 1),
                      ("fields_ok", 1), ("refused_ok", 1)]:
        if r.get(key) is not None and r[key] < want:
            out.append(f"{key}={r[key]:.2f}")
    return out

# ---------- main ----------

def pick(cases: list[dict], per_type: int) -> list[dict]:
    """First N cases of each type; 0 means all."""
    if not per_type:
        return cases
    seen, out = {}, []
    for c in cases:
        seen[c["type"]] = seen.get(c["type"], 0) + 1
        if seen[c["type"]] <= per_type:
            out.append(c)
    return out

async def main(a):
    lines = Path("evals/golden.jsonl").read_text().splitlines()
    cases = pick([json.loads(l) for l in lines if l.strip()], a.per_type)
    rows = []
    for case in cases:
        r = await run_case_safely(case["input"])
        row = {"id": case["id"], "type": case["type"], "input": case["input"],
               "must_mention": case.get("must_mention"), **r, **await score(case, r)}
        rows.append(row)
        print("OK  " if not problems(row) else "LOOK", row["id"], "; ".join(problems(row)))
        await asyncio.sleep(5)               # stay clear of rate limits

    metrics = summarize(rows)
    report = f"# Golden set: {a.run_name}\n\n{a.note}\n\n" + "".join(
        f"- {k}: {v:.2f}\n" if isinstance(v, float) else f"- {k}: {v}\n"
        for k, v in metrics.items())
    report += "\n## Cases to look at\n" + "".join(
        f"- {r['id']} ({r['type']}): {'; '.join(problems(r))}\n" for r in rows if problems(r))
    Path("evals/results").mkdir(parents=True, exist_ok=True)
    Path(f"evals/results/golden_{a.run_name}.md").write_text(report)
    print("\n" + report)

    mlflow.set_tracking_uri("sqlite:///mlflow.db")
    mlflow.set_experiment("flightops-golden")
    with mlflow.start_run(run_name=a.run_name):
        mlflow.log_params({
            "chat_deployment": config.CHAT, "judge_deployment": config.JUDGE,
            "framework": "agent-framework", "cases": len(rows), "note": a.note,
            "answer_prompt_sha": sha(ANSWER_PROMPT), "judge_prompt_sha": sha(JUDGE_SYSTEM)})
        mlflow.log_metrics(metrics)
        mlflow.log_dict({"cases": rows}, "cases.json")
        mlflow.log_text(ANSWER_PROMPT, "answer_prompt.txt")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run-name", required=True)
    p.add_argument("--note", default="")
    p.add_argument("--per-type", type=int, default=0, help="run only the first N cases of each type")
    args = p.parse_args()
    start_tracing()
    try:
        asyncio.run(main(args))
    finally:
        flush_tracing()
