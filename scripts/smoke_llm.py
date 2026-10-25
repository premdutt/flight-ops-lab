import asyncio
from app.llm import complete, embed

async def main():
    print(await complete('Be brief.', 'Say OK'))
    print(len((await embed(['test']))[0]))

asyncio.run(main())