"""Compatibility only: the workflow moved to workflows/agent_framework/workflow.py.

Cosmos checkpoints saved before the move refer to classes as app.workflow.<Name>.
Keep this file until those checkpoints are deleted, then remove it and the
"app.workflow:" entries in app/storage.py. Import from the new module in new code.
"""
from workflows.agent_framework.workflow import (  # noqa: F401
    ApprovalDecision, ApprovalRequest, Routed, UserMessage, build_workflow, WORKFLOW_NAME)
