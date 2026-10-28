# scripts/smoke_checkpoint.py: run -> checkpoints saved in Cosmos -> resume with a fresh workflow
import asyncio
from app.workflow import build_workflow, WORKFLOW_NAME, UserMessage
from app.storage import checkpoint_storage

QUESTION = "What are the requirements for fuel quality control?"

async def outputs(stream) -> list[str]:
    return [ev.data async for ev in stream if ev.type == "output"]

async def main():
    async with checkpoint_storage() as storage:
        before = {c.checkpoint_id for c in await storage.list_checkpoints(workflow_name=WORKFLOW_NAME)}
        first = await outputs(build_workflow(storage).run(UserMessage("smoke", QUESTION), stream=True))
        after = await storage.list_checkpoints(workflow_name=WORKFLOW_NAME)
        new_ids = [c.checkpoint_id for c in after if c.checkpoint_id not in before]

    assert first, "run produced no output"
    assert new_ids, "no checkpoints were saved to Cosmos"
    print(f"run ok: {len(new_ids)} checkpoints saved; output starts: {first[0][:80]!r}")

    async with checkpoint_storage() as storage:
        resumed = await outputs(build_workflow(storage).run(checkpoint_id=new_ids[0], stream=True))

    assert resumed, "resume produced no output"
    print(f"resume ok from {new_ids[0]}; output starts: {resumed[0][:80]!r}")
    print("PASS")

asyncio.run(main())