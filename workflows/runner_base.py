"""The interface every channel (CLI, web API, chat, evals) uses to run a workflow.

Each framework gets an adapter that implements WorkflowRunner:
  - workflows/langgraph/runner.py        LangGraphRunner (checkpoints in Postgres)
  - workflows/agent_framework/runner.py  AgentFrameworkRunner (Step 6.4, checkpoints in Cosmos)
Channels depend only on this file, so they work with either framework.
"""
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Status = Literal["done", "waiting", "not_found", "already_exists"]

# What a person can answer to an approval: {"action": one of these, "edited_draft": "..."}
DECISIONS = ("approve", "edit", "reject")


@dataclass
class Outcome:
    thread_id: str
    status: Status
    result: str | None = None          # what the user sees, when done
    pending: Any = None                # what the person must decide on, when waiting (e.g. the draft)
    events: list[str] = field(default_factory=list)   # safety layers that fired in this call


class WorkflowRunner(Protocol):
    async def start(self, thread_id: str, inputs: dict) -> Outcome:
        """Run a new thread until it finishes or pauses. An existing thread gives already_exists."""
        ...

    async def resume(self, thread_id: str, decision: Any) -> Outcome:
        """Continue a waiting thread with a person's decision. Any other thread is returned as is."""
        ...

    async def status(self, thread_id: str) -> Outcome:
        """Where the thread is now: done, waiting or not_found."""
        ...
