"""The one place that knows which workflow frameworks exist. Channels call open_runner()."""
from contextlib import asynccontextmanager
from typing import AsyncIterator

from workflows.runner_base import WorkflowRunner

FRAMEWORKS = ("langgraph",)          # agent_framework is added in Step 6.4


@asynccontextmanager
async def open_runner(framework: str) -> AsyncIterator[WorkflowRunner]:
    """A runner for the chosen framework, with its checkpoint storage open."""
    # Imports are inside the branches so a channel loads only the framework it uses
    if framework == "langgraph":
        from workflows.langgraph.graph import build_graph
        from workflows.langgraph.runner import postgres_runner
        async with postgres_runner(build_graph) as runner:
            yield runner
    else:
        raise ValueError(f"Unknown framework {framework!r}; choose from {FRAMEWORKS}")
