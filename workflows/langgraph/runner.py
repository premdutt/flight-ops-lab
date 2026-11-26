"""LangGraph adapter for the WorkflowRunner interface (workflows/runner_base.py).

No print() or input() here: every call returns an Outcome, and the channel decides how to
show it. A thread paused at interrupt() comes back as status "waiting" with the interrupt's
value in `pending`; the channel gets a decision from a person (now or hours later, in another
process) and calls resume().

Generic on purpose: it works with any compiled LangGraph graph, so it can move to the
reusable library later. Flight-Ops specifics stay in graph.py.
"""
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from app import safety
from app.config import env
from workflows.runner_base import Outcome


class LangGraphRunner:
    def __init__(self, graph, result_key: str = "result"):
        """graph: compiled with a checkpointer. result_key: the state field shown to the user."""
        self.graph = graph
        self.result_key = result_key

    @staticmethod
    def _cfg(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    async def status(self, thread_id: str) -> Outcome:
        """The thread's current position, read from the checkpointer."""
        state = await self.graph.aget_state(self._cfg(thread_id))
        if not state.values:
            return Outcome(thread_id, "not_found")
        if state.next:                                   # paused at an interrupt
            return Outcome(thread_id, "waiting", pending=state.tasks[0].interrupts[0].value)
        return Outcome(thread_id, "done", result=state.values.get(self.result_key))

    async def start(self, thread_id: str, inputs: dict) -> Outcome:
        """Run a new thread until it finishes or pauses.

        One message per thread: fields from an earlier run (such as an old draft) would stay
        in the state and could reach the approval step again.
        """
        if (await self.status(thread_id)).status != "not_found":
            return Outcome(thread_id, "already_exists")
        return await self._invoke(thread_id, inputs)

    async def resume(self, thread_id: str, decision: Any) -> Outcome:
        """Continue a paused thread with a person's decision. Any other thread is returned as is."""
        current = await self.status(thread_id)
        if current.status != "waiting":
            return current
        return await self._invoke(thread_id, Command(resume=decision))

    async def _invoke(self, thread_id: str, payload: Any) -> Outcome:
        # safety.EVENTS is a module-level list: fine for one call at a time (CLI, evals),
        # needs to be per request before this serves several users at once
        safety.EVENTS.clear()
        await self.graph.ainvoke(payload, self._cfg(thread_id))
        outcome = await self.status(thread_id)
        outcome.events = list(safety.EVENTS)
        return outcome


@asynccontextmanager
async def postgres_runner(graph_builder, pg_uri: str | None = None) -> AsyncIterator[LangGraphRunner]:
    """A LangGraphRunner whose checkpoints are saved in Postgres (PG_URI by default)."""
    async with AsyncPostgresSaver.from_conn_string(pg_uri or env("PG_URI")) as checkpointer:
        await checkpointer.setup()                       # creates the tables the first time
        yield LangGraphRunner(graph_builder().compile(checkpointer=checkpointer))
