# app/workflow.py
import json
import uuid
from dataclasses import dataclass
from typing import Never
from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler, response_handler
from app.agents import router_agent, answer_agent, make_request_agent
from app.llm_utils import extract_json, final_text
from app.memory import load_profile, submit_request
from azure.cosmos.exceptions import CosmosResourceExistsError

WORKFLOW_NAME = "flightops"   # fixed: checkpoints are stored and listed by this name

@dataclass
class UserMessage:
    user_id: str
    text: str

@dataclass
class Routed:
    intent: str        # "question" or "request"
    user_id: str
    text: str

@dataclass
class ApprovalRequest:
    user_id: str
    draft: str
    draft_id: str = ""        # stable id; replays of this checkpoint reuse it

@dataclass
class ApprovalDecision:
    action: str               # "approve", "edit" or "reject"
    edited_draft: str = ""

class Router(Executor):
    def __init__(self):
        super().__init__(id="router")

    @handler
    async def route(self, msg: UserMessage, ctx: WorkflowContext[Routed]) -> None:
        label = (await router_agent.run(msg.text)).text.strip().upper()
        intent = "request" if "REQUEST" in label else "question"
        await ctx.send_message(Routed(intent, msg.user_id, msg.text))

class Answer(Executor):
    def __init__(self):
        super().__init__(id="answer")

    @handler
    async def answer(self, msg: Routed, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output(final_text(await answer_agent.run(msg.text)))

class DraftRequest(Executor):
    def __init__(self):
        super().__init__(id="request")

    @handler
    async def draft(self, msg: Routed, ctx: WorkflowContext[Never, str]) -> None:
        profile = await load_profile(msg.user_id)
        agent = make_request_agent(msg.user_id, profile)
        draft = extract_json(final_text(await agent.run(msg.text)))
        # Pause here: the workflow emits a request_info event and waits for a decision.
        await ctx.request_info(
            request_data=ApprovalRequest(user_id=msg.user_id, draft=draft, draft_id=str(uuid.uuid4())),
            response_type=ApprovalDecision,
        )

    @response_handler
    async def on_decision(self, original_request: ApprovalRequest,
                          response: ApprovalDecision,
                          ctx: WorkflowContext[Never, str]) -> None:
        if response.action == "reject":
            await ctx.yield_output("Request rejected. Nothing was submitted.")
            return
        final = response.edited_draft if response.action == "edit" else original_request.draft
        try:
            request_id = await submit_request(original_request.user_id, final, original_request.draft_id)
        except CosmosResourceExistsError:
            await ctx.yield_output(f"Request {original_request.draft_id} was already submitted. Nothing new was submitted.")
            return
        await ctx.yield_output(f"Submitted request {request_id}: {final}")


def build_workflow(checkpoint_storage=None):
    router, answer, request = Router(), Answer(), DraftRequest()
    builder = WorkflowBuilder(name=WORKFLOW_NAME, start_executor=router,
                              checkpoint_storage=checkpoint_storage)
    builder.add_edge(router, answer, condition=lambda m: m.intent == "question")
    builder.add_edge(router, request, condition=lambda m: m.intent == "request")
    return builder.build()