# scripts/smoke_memory.py: per-user memory in Cosmos
import asyncio
from app.memory import save_pref, load_profile

async def main():
    await save_pref("test-user", "home_base", "KFDK")
    profile = await load_profile("test-user")
    print("test-user:", profile["prefs"])
    assert profile["prefs"].get("home_base") == "KFDK", "preference was not saved"

    other = await load_profile("someone-else")
    print("someone-else:", other["prefs"])
    assert "home_base" not in other["prefs"], "memory leaked across users"
    print("PASS")

asyncio.run(main())