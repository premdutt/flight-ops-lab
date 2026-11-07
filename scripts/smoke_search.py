# scripts/smoke_search.py
import asyncio, time
from app.agents import search_docs

async def main():
    t = time.time()
    out = await search_docs("fuel quality control")
    print(f"{time.time() - t:.1f}s")
    print(out[:600])

asyncio.run(main())