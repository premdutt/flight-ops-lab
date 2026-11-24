# app/workflow.py
import json, uuid
from dataclasses import dataclass
from typing import Never
from azure.cosmos.exceptions import CosmosResourceExistsError
from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler, response_handler
from app.agents import router_agent, answer_agent, make_request_agent
from app.llm_utils import extract_json, final_text
from app.memory import load_profile, submit_request
from app.safety import shield, moderate, EVENTS, is_model_filter_error,model_filter_label

WORKFLOW_NAME = "flightops"
REFUSAL = "Sorry, I can't help with that request."

@dataclass
class UserMessage:
    user_id: str
    text: str

@dataclass
class Routed:
    intent: str
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
    async def route(self, msg: UserMessage, ctx: WorkflowContext[Routed, str]) -> None:
        # Layer 1: input shield
        attacked, _ = await shield(msg.text)          # ASSUMPTION: True = attack detected
        if attacked:
            EVENTS.append("input")
            await ctx.yield_output(REFUSAL)
            return

        # Layer 2: Foundry guardrail on the router call
        try:
            response = await router_agent.run(msg.text)
        except Exception as e:
            if is_model_filter_error(e):
                EVENTS.append(f"model_filter:{model_filter_label(e) or 'unknown'}")
                await ctx.yield_output(REFUSAL)
                return
            raise

        label = response.text.strip().upper()
        intent = "request" if "REQUEST" in label else "question"
        await ctx.send_message(Routed(intent, msg.user_id, msg.text))

class Answer(Executor):
    def __init__(self):
        super().__init__(id="answer")

    @handler
    async def answer(self, msg: Routed, ctx: WorkflowContext[Never, str]) -> None:
        text = final_text(await answer_agent.run(msg.text))
        # Layer 4: output moderation
        if not await moderate(text):                      # ASSUMPTION: True = unsafe
            EVENTS.append("output")
            text = "I can't share that answer."
        await ctx.yield_output(text)

class DraftRequest(Executor):
    def __init__(self):
        super().__init__(id="request")

    @handler
    async def draft(self, msg: Routed, ctx: WorkflowContext[Never, str]) -> None:
        agent = make_request_agent(msg.user_id, await load_profile(msg.user_id))
        draft = extract_json(final_text(await agent.run(msg.text)))
        await ctx.request_info(                       # Layer 5: pause until a person decides
            request_data=ApprovalRequest(user_id=msg.user_id, draft=draft, draft_id=str(uuid.uuid4())),
            response_type=ApprovalDecision,
        )

    @response_handler
    async def on_decision(self, original_request: ApprovalRequest, response: ApprovalDecision,
                          ctx: WorkflowContext[Never, str]) -> None:
        if response.action == "reject":
            await ctx.yield_output("Request rejected. Nothing was submitted.")
            return
        final = response.edited_draft if response.action == "edit" else original_request.draft
        try:
            json.loads(final)
        except ValueError:
            await ctx.yield_output("The request is not valid JSON. Nothing was submitted.")
            return
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