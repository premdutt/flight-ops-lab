import argparse, asyncio
from app.workflow import build_workflow,WORKFLOW_NAME
from app.storage import checkpoint_storage

async def print_events(stream):
    async for ev in stream:
        if ev.type == "output":
            print("\nOUTPUT:",ev.data)

async def main():
    p = argparse.ArgumentParser(description="Run the flight-ops workflow with Cosmos checkpoints")
    p.add_argument("command",choices=["run","list","resume"])
    p.add_argument("value",nargs="?",help="message text for run, checkpoint id for resume")
    a = p.parse_args()
    
    async with checkpoint_storage() as storage:
        wf = build_workflow(storage)
        if a.command == "run":
            await print_events(wf.run(a.value,stream = True))
        elif a.command == "list":
            for c in await storage.list_checkpoints(workflow_name=WORKFLOW_NAME):
                print(c.checkpoint_id,c.timestamp)
        elif a.command == "resume":
            await print_events(wf.run(checkpoint_id=a.value,stream=True))


if __name__ == "__main__":
    asyncio.run(main())
