# scripts/smoke_workflow.py: question path through the workflow (no storage)
import asyncio
from app.workflow import build_workflow, UserMessage

async def main():
    text = "What are the requirements for fuel quality control?"
    async for ev in build_workflow().run(UserMessage("smoke", text), stream=True):
        if ev.type == "output":
            print(f"> {text}\nOUTPUT: {ev.data}")

asyncio.run(main())