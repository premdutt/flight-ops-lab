import asyncio
from app.agents import router_agent,answer_agent,request_agent

async def main():
    r1 = await router_agent.run("what does the guidance say about fuel quality control?")
    r2 = await router_agent.run("I need fuel for N123AB at KFDK tomorrow at 9am")
    print("router:",r1.text.strip(),"|",r2.text.strip())

    a = await answer_agent.run("What does the guidance say about fuel quality control?")
    print("\nanswer:\n", a.text)

    q = await request_agent.run("I need fuel for N123AB at KFDK tomorrow at 9am")
    print("\nrequest:\n", q.text)

asyncio.run(main())


    