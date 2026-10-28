# scripts/smoke_agents.py: router and answer agents
import asyncio
from app.agents import router_agent, answer_agent
from app.llm_utils import final_text

async def main():
    r1 = await router_agent.run("What does the guidance say about fuel quality control?")
    r2 = await router_agent.run("I need fuel for N123AB at KFDK tomorrow at 9am")
    print("router:", r1.text.strip(), "|", r2.text.strip())

    a = await answer_agent.run("What does the guidance say about fuel quality control?")
    print("\nanswer:\n", final_text(a))

asyncio.run(main())