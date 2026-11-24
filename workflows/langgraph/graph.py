"""LangGraph version of the Flight-Ops workflow.

Same safety layers and approval rules as workflows/agent_framework/workflow.py, built from
the shared code in app/. Differences, kept on purpose for the comparison:
  - answer: one search with the user's text, then one model call (no tool-calling agent)
  - draft: reads saved preferences but has no remember tool, so it never saves new ones

    START -> route --question--> answer -> END
                   --request---> draft --> approve (interrupt: waits for a person) -> END
                   --blocked---> END
"""
import json
import uuid
from typing import TypedDict

from azure.cosmos.exceptions import CosmosResourceExistsError
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents import REQUEST_PROMPT, ROUTER_PROMPT, search_docs
from app.llm import complete
from app.llm_utils import extract_json
from app.memory import load_profile, submit_request
from app.safety import EVENTS, is_model_filter_error, model_filter_label, moderate, shield

REFUSAL = "Sorry, I can't help with that request."
DECISIONS = ("approve", "edit", "reject")

ANSWER_SYSTEM = (
    "You answer questions about aviation ground operations. "
    "Answer only from the passages below and name the source in brackets. "
    "If they don't answer the question, say you don't know.\n\nPassages:\n{ctx}"
)


class State(TypedDict, total=False):
    user_id: str
    text: str
    intent: str        # question, request or blocked
    draft: str         # request JSON from the model
    draft_id: str      # fixed when the draft is made; makes submission happen at most once
    result: str        # what the user sees


async def _complete_guarded(system: str, user: str) -> str | None:
    """A model call; None if the Foundry guardrail rejected it (recorded as a model_filter event)."""
    try:
        return await complete(system, user)
    except Exception as e:
        if is_model_filter_error(e):
            EVENTS.append(f"model_filter:{model_filter_label(e) or 'unknown'}")
            return None
        raise


# ---------- nodes ----------

async def route(s: State) -> dict:
    attacked, _ = await shield(s["text"])                    # layer 1: input shield
    if attacked:
        EVENTS.append("input")
        return {"intent": "blocked", "result": REFUSAL}
    label = await _complete_guarded(ROUTER_PROMPT, s["text"])  # layer 2: Foundry guardrail
    if label is None:
        return {"intent": "blocked", "result": REFUSAL}
    return {"intent": "request" if "REQUEST" in label.upper() else "question"}


async def answer(s: State) -> dict:
    passages = await search_docs(s["text"])                  # layer 3: passages screened inside
    text = await _complete_guarded(ANSWER_SYSTEM.format(ctx=passages), s["text"])
    if text is None:
        return {"result": REFUSAL}
    if not await moderate(text):                             # layer 4: output moderation
        EVENTS.append("output")
        text = "I can't share that answer."
    return {"result": text}


async def draft(s: State) -> dict:
    profile = await load_profile(s["user_id"])
    system = (REQUEST_PROMPT + f" Known saved preferences for this user: {profile.get('prefs', {})}. "
              "Use them to fill missing fields.")
    raw = await _complete_guarded(system, s["text"])
    if raw is None:
        return {"intent": "blocked", "result": REFUSAL}
    # The id is saved with this node's output, so a resumed run reuses it
    return {"draft": extract_json(raw), "draft_id": str(uuid.uuid4())}


async def approve(s: State) -> dict:
    # Layer 5: pause for a person. On resume this node runs again from the top and
    # interrupt() returns the decision, so nothing with side effects may come before it.
    decision = interrupt({"user_id": s["user_id"], "draft": s["draft"], "draft_id": s["draft_id"]})

    action = (decision or {}).get("action")
    if action not in DECISIONS:                              # only an explicit approve submits
        return {"result": f"Unknown decision {action!r}. Nothing was submitted."}
    if action == "reject":
        return {"result": "Request rejected. Nothing was submitted."}
    final = s["draft"] if action == "approve" else (decision.get("edited_draft") or "").strip()
    try:
        json.loads(final)
    except ValueError:
        return {"result": "The request is not valid JSON. Nothing was submitted."}
    try:
        request_id = await submit_request(s["user_id"], final, s["draft_id"])
    except CosmosResourceExistsError:                        # resumed after an earlier submit
        return {"result": f"Request {s['draft_id']} was already submitted. Nothing new was submitted."}
    return {"result": f"Submitted request {request_id}: {final}"}


# ---------- graph ----------

def build_graph() -> StateGraph:
    """The uncompiled graph. Compile it with a checkpointer to run it."""
    g = StateGraph(State)
    g.add_node("route", route)
    g.add_node("answer", answer)
    g.add_node("draft", draft)
    g.add_node("approve", approve)
    g.add_edge(START, "route")
    g.add_conditional_edges("route", lambda s: s["intent"],
                            {"question": "answer", "request": "draft", "blocked": END})
    g.add_edge("answer", END)
    g.add_conditional_edges("draft", lambda s: "approve" if s.get("draft") else END,
                            {"approve": "approve", END: END})
    g.add_edge("approve", END)
    return g
