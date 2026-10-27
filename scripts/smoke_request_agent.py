import asyncio
from app.agents import make_request_agent
from app.memory import load_profile
from app.llm_utils import extract_json,final_text

async def draft(user_id: str, text: str) -> str:
    agent = make_request_agent(user_id, await load_profile(user_id))
    r = await agent.run(text)
    return r.messages[-1].text.strip()

async def main():
    print("1:", await draft("pg", "My home base is KFDK. I need fuel for N123AB tomorrow at 9am."))
    print("\n2:", await draft("pg", "Fuel for N123AB on Friday morning"))
    print("\n3:", await draft("test2", "Fuel for N123AB on Friday morning"))
    print("\npg profile:", (await load_profile("pg"))["prefs"])


async def draft(user_id: str, text: str) -> str:
    agent = make_request_agent(user_id, await load_profile(user_id))
    return extract_json(final_text(await agent.run(text)))

asyncio.run(main())
