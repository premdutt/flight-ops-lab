import asyncio
from app.workflow import build_workflow

async def run(text:str):
    wf=build_workflow()
    async for ev in wf.run(text,stream=True):
        if ev.type == "output":
            print(f"\n{text}\nOUTPUT:{ev.data}")


async def main():
    await run("What are the requirements for fuel quality control?")
    await run("I need fuel for N123AB at KFDK tomorrow at 9am")

asyncio.run(main())
    