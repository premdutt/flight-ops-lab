# scripts/smoke_judge.py  --  usage: python -m scripts.smoke_judge
# Checks the judge deployment is reachable, returns JSON, and can tell a good answer from a bad one.
import asyncio, json
from app import config
from app.llm import complete

JUDGE_SYSTEM = (
    "You grade an assistant's answer. Be strict. Reply with JSON only: "
    '{"facts_found": [true or false for each required fact, in order], '
    '"groundedness": an integer 1-5 where 5 means every claim is supported by the passages, '
    '"reason": "one sentence"}'
)

PASSAGES = "[sample] Fuel records must be kept for 12 months."
FACTS = ["12 months"]
CASES = [
    ("good (expect facts_found [true], groundedness 4-5)", "Fuel records must be kept for twelve months [sample]."),
    ("bad  (expect facts_found [false], groundedness 1-2)", "Fuel records must be kept for 24 months [sample]."),
]

async def main():
    print("chat:", config.CHAT, "| judge:", config.JUDGE)
    for name, answer in CASES:
        user = f"Passages:\n{PASSAGES}\n\nAnswer:\n{answer}\n\nRequired facts:\n{json.dumps(FACTS)}"
        raw = await complete(JUDGE_SYSTEM, user, deployment=config.JUDGE,
                             response_format={"type": "json_object"})
        print(f"\n{name}")
        try:
            print(json.loads(raw))
        except ValueError:
            print("NOT VALID JSON:", raw)

asyncio.run(main())
