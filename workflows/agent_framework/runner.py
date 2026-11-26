"""Agent Framework adapter for the WorkflowRunner interface (workflows/runner_base.py).

Agent Framework has no thread id: checkpoints are grouped by workflow name, which is also
the Cosmos partition key. Each thread therefore gets its own workflow name, flightops-<thread>,
and the thread's position is its latest checkpoint:
  - no checkpoint                         -> not_found
  - latest has pending request_info       -> waiting (the request id to answer is in it)
  - latest has none                       -> done
Checkpoints from the shared name "flightops" (app/run_cli.py, smoke scripts) are not touched.

Limit: Agent Framework does not keep outputs in checkpoints, so status() of a finished
thread has result None. start() and resume() return the result of the run they made.
"""
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any, AsyncIterator

from app import safety
from app.storage import checkpoint_storage
from workflows.agent_framework.workflow import (WORKFLOW_NAME, ApprovalDecision, UserMessage,
                                                build_workflow)
from workflows.runner_base import Outcome


class AgentFrameworkRunner:
    def __init__(self, storage):
        """storage: Agent Framework checkpoint storage (Cosmos in this lab)."""
        self.storage = storage

    @staticmethod
    def _name(thread_id: str) -> str:
        return f"{WORKFLOW_NAME}-{thread_id}"

    async def status(self, thread_id: str) -> Outcome:
        latest = await self.storage.get_latest(workflow_name=self._name(thread_id))
        if latest is None:
            return Outcome(thread_id, "not_found")
        if latest.pending_request_info_events:
            event = next(iter(latest.pending_request_info_events.values()))
            return Outcome(thread_id, "waiting", pending=asdict(event.data))
        return Outcome(thread_id, "done")

    async def start(self, thread_id: str, inputs: dict) -> Outcome:
        """Run a new thread until it finishes or pauses."""
        if (await self.status(thread_id)).status != "not_found":
            return Outcome(thread_id, "already_exists")
        msg = UserMessage(inputs["user_id"], inputs["text"])
        return await self._run(thread_id, lambda wf: wf.run(msg))

    async def resume(self, thread_id: str, decision: Any) -> Outcome:
        """Answer the thread's pending approval. Any other thread is returned as is."""
        latest = await self.storage.get_latest(workflow_name=self._name(thread_id))
        if latest is None or not latest.pending_request_info_events:
            return await self.status(thread_id)
        request_id = next(iter(latest.pending_request_info_events))
        answer = ApprovalDecision(action=decision.get("action", ""),
                                  edited_draft=decision.get("edited_draft", ""))
        # Restore the checkpoint and deliver the answer in one call, on a fresh workflow
        return await self._run(thread_id, lambda wf: wf.run(
            checkpoint_id=latest.checkpoint_id, responses={request_id: answer}))

    async def _run(self, thread_id: str, call) -> Outcome:
        # safety.EVENTS is a module-level list: fine for one call at a time (CLI, evals),
        # needs to be per request before this serves several users at once
        safety.EVENTS.clear()
        wf = build_workflow(self.storage, name=self._name(thread_id))
        result = await call(wf)
        events = list(safety.EVENTS)
        requests = result.get_request_info_events()
        if requests:
            return Outcome(thread_id, "waiting", pending=asdict(requests[0].data), events=events)
        outputs = [str(o) for o in result.get_outputs()]
        return Outcome(thread_id, "done", result="\n".join(outputs) or None, events=events)


@asynccontextmanager
async def cosmos_runner() -> AsyncIterator[AgentFrameworkRunner]:
    """An AgentFrameworkRunner whose checkpoints are saved in Cosmos (flightops/checkpoints)."""
    async with checkpoint_storage() as storage:
        yield AgentFrameworkRunner(storage)
