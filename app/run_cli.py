# app/run_cli.py
import argparse, asyncio
from app.workflow import build_workflow, WORKFLOW_NAME, UserMessage, ApprovalDecision
from app.storage import checkpoint_storage

async def drive(stream) -> dict:
    """Print outputs; collect any approval requests the workflow is waiting on."""
    pending = {}
    async for ev in stream:
        if ev.type == "request_info":
            pending[ev.request_id] = ev.data
        elif ev.type == "output":
            print("\nOUTPUT:", ev.data)
    return pending

def ask(pending: dict) -> dict:
    """Show each waiting draft and collect the person's decision."""
    responses = {}
    for request_id, req in pending.items():
        print(f"\n--- APPROVAL NEEDED (user {req.user_id}) ---\n{req.draft}")
        choice = ""
        while choice not in ("approve", "edit", "reject"):
            choice = input("approve / edit / reject: ").strip().lower()
        edited = input("Paste the edited JSON on one line: ") if choice == "edit" else ""
        responses[request_id] = ApprovalDecision(action=choice, edited_draft=edited)
    return responses

async def main():
    p = argparse.ArgumentParser(description="Flight-ops workflow with approvals and Cosmos checkpoints")
    p.add_argument("command", choices=["run", "list", "resume","pending"])
    p.add_argument("value", nargs="?", help="message text for run, checkpoint id for resume")
    p.add_argument("--user", default="pg", help="who is asking (selects their memory)")
    a = p.parse_args()

    async with checkpoint_storage() as storage:
        wf = build_workflow(storage)

        if a.command == "list":
            for c in await storage.list_checkpoints(workflow_name=WORKFLOW_NAME):
                print(c.checkpoint_id, c.timestamp)
            return
        if a.command == "pending":
            for c in await storage.list_checkpoints(workflow_name=WORKFLOW_NAME):
                waiting = "  <- WAITING FOR APPROVAL" if c.pending_request_info_events else ""
                print(c.checkpoint_id, c.timestamp,waiting)
            return
        
        if a.command == "run":
            pending = await drive(wf.run(UserMessage(a.user, a.value), stream=True))
        else:
            pending = await drive(wf.run(checkpoint_id=a.value, stream=True))

        while pending:
            pending = await drive(wf.run(stream=True, responses=ask(pending)))

if __name__ == "__main__":
    asyncio.run(main())