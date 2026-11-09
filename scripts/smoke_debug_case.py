# scripts/debug_case.py
import asyncio, sys
from app.workflow import build_workflow, UserMessage

async def main():
    try:
        async for ev in build_workflow().run(UserMessage("eval", sys.argv[1]), stream=True):
            if ev.type == "output":
                print(ev.data)
    except Exception as e:
        print(type(e).__name__)
        print(str(e))
        print("cause:", repr(e.__cause__))

asyncio.run(main())