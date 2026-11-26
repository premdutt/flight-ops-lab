"""Terminal channel: run or resume a workflow thread, with approval at the prompt.

Works with any framework behind the WorkflowRunner interface (workflows/runner_base.py).
A request pauses at approval; stop the process there (Ctrl+C) and resume the same
thread later, from a new process.

Run:  python -m channels.cli run --thread t1 "What are the requirements for fuel quality control?"
      python -m channels.cli run --thread t2 "Fuel for N123AB Friday morning"
      python -m channels.cli resume --thread t2
      add --framework langgraph (the default) to choose the framework
Settings: PG_URI for langgraph (Postgres connection string).
"""
import argparse
import asyncio
import signal
import sys

from workflows.factory import FRAMEWORKS, open_runner
from workflows.runner_base import DECISIONS, Outcome


def ask(pending: dict) -> dict:
    """Show the draft and ask the person at the terminal for a decision."""
    print(f"\n--- APPROVAL NEEDED (user {pending['user_id']}, request {pending['draft_id']}) ---")
    print(pending["draft"])
    choice = ""
    while choice not in DECISIONS:
        choice = input(f"{' / '.join(DECISIONS)}: ").strip().lower()
    edited = input("Paste the edited JSON on one line: ") if choice == "edit" else ""
    return {"action": choice, "edited_draft": edited}


def show(o: Outcome) -> None:
    if o.result is not None:           # None: a finished thread whose framework keeps no output
        print("\nOUTPUT:", o.result)
    if o.events:
        print("SAFETY EVENTS:", o.events)


async def main() -> None:
    # asyncio.run() turns Ctrl+C into a task cancellation that only fires at the next await,
    # so input() would keep waiting and the next answer would be lost. Restore the default
    # so Ctrl+C raises KeyboardInterrupt inside input() and the thread stays saved as is.
    signal.signal(signal.SIGINT, signal.default_int_handler)

    p = argparse.ArgumentParser(description="Run or resume a workflow thread.")
    p.add_argument("command", choices=["run", "resume"])
    p.add_argument("--thread", required=True, help="conversation id, e.g. t1")
    p.add_argument("--user", default="pg", help="user id for saved preferences")
    p.add_argument("--framework", choices=FRAMEWORKS, default="langgraph")
    p.add_argument("text", nargs="?", help="the message (run only)")
    a = p.parse_intermixed_args()      # lets the text come after --thread
    if a.command == "run" and not a.text:
        p.error("run needs the message text")
    resume_cmd = f"python -m channels.cli resume --thread {a.thread} --framework {a.framework}"

    async with open_runner(a.framework) as runner:
        if a.command == "run":
            o = await runner.start(a.thread, {"user_id": a.user, "text": a.text})
        else:
            o = await runner.status(a.thread)

        if o.status == "already_exists":
            sys.exit(f"Thread {a.thread} already exists. Use a new --thread, "
                     f"or 'resume' if it is waiting for approval.")
        if o.status == "not_found":
            sys.exit(f"Thread {a.thread} not found.")
        if a.command == "resume" and o.status == "done":
            print(f"Thread {a.thread} is already finished.")

        while o.status == "waiting":
            try:
                decision = ask(o.pending)
            except (KeyboardInterrupt, EOFError):
                print(f"\nStopped. The draft is saved; continue with:\n  {resume_cmd}")
                return
            o = await runner.resume(a.thread, decision)

        show(o)


if __name__ == "__main__":
    asyncio.run(main())
