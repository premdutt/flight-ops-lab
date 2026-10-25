from dataclasses import dataclass
from typing_extensions import Never
from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler
from app.agents import router_agent,answer_agent,request_agent

WORKFLOW_NAME  = "flightops"

@dataclass
class Routed:
    intent: str # "question" or "request"
    text: str

class Router(Executor):
    def __init__(self):
        super().__init__(id="router") # fixed ids are required to resume checkpoints

    @handler
    async def route(self, text:str,ctx:WorkflowContext[Routed]) -> None:
        label = (await router_agent.run(text)).text.strip().upper()
        intent = "request" if "REQUEST" in label else "question"
        await ctx.send_message(Routed(intent=intent,text=text))



class Answer(Executor):
    def __init__(self):
        super().__init__(id="answer") 

    
    @handler    
    async def answer(self, msg: Routed, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output((await answer_agent.run(msg.text)).text)


class DraftRequest(Executor):
    def __init__(self):
        super().__init__(id="request")

    @handler
    async def draft(self, msg: Routed, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output((await request_agent.run(msg.text)).text) 

def build_workflow(checkpoint_storage=None):
    router, answer,request = Router(),Answer(), DraftRequest()
    builder = WorkflowBuilder(name=WORKFLOW_NAME,start_executor=router,checkpoint_storage=checkpoint_storage)
    builder.add_edge(router,answer,condition=lambda m:m.intent == "question")
    builder.add_edge(router,request,condition=lambda m: m.intent == "request")
    return builder.build()


