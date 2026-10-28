from pathlib import Path
from typing import Annotated
from agent_framework.openai import OpenAIChatCompletionClient
from app import config
from app.memory import save_pref

client = OpenAIChatCompletionClient(
    azure_endpoint = config.APIM_URL
    ,api_key = config.APIM_KEY
    ,model = config.CHAT
    ,api_version = config.API_VERSION
)

def search_docs(query: Annotated[str, "Keywords to search for"]) -> str:
    """
    Search the FAA documentation for relevant articles, guides, and policies.
    Use this tool whenever the user asks 'how to' questions regarding the documentation in scope for this tool.
    """
    words = [w.lower() for w in query.split() if len(w) > 3]
    scored = []
    for f in Path("data/text").glob("*.txt"):
        for para in f.read_text(encoding="utf-8").split("\n\n"):
            score = sum(para.lower().count(w) for w in words)
            if score:
                scored.append((score, f"[{f.stem}] {para[:1000]}"))
    scored.sort(reverse=True)
    return "\n\n".join(p for _, p in scored[:4]) or "No matches."




ROUTER_PROMPT = (
    "Classify the user's message. Reply with exactly one word: "
    "QUESTION for questions about rules, procedures or documents; "
    "REQUEST for asking for fuel, hangar space or catering."
)

ANSWER_PROMPT = (
    "You answer questions about aviation ground operations. Always call search_docs first. "
    "Answer only from the passages it returns and name the source in brackets. "
    "If nothing relevant comes back, say you don't know."
)

REQUEST_PROMPT = (
    "Turn the user's message into a service request. Return only JSON with keys: "
    "service (fuel, hangar or catering), tail_number, airport, when, details. Use null for unknowns."
)

router_agent = client.as_agent(name="router",instructions = ROUTER_PROMPT)
answer_agent = client.as_agent(name="answer",instructions= ANSWER_PROMPT,tools=[search_docs])
#request_agent = client.as_agent(name="request", instructions=REQUEST_PROMPT)


def make_request_agent(user_id:str,profile:dict):
    """Build a request agent for one user: their preferences in the prompt, a remember tool bound to them."""
    async def remember(key: Annotated[str, "Preference name, e.g. home_base or fuel_type"],
                       value: Annotated[str, "Preference value"]) -> str:
        """Save a lasting preference the user stated, such as their home airport."""
        await save_pref(user_id, key, value)
        return f"Saved {key}."

    instructions = (
            REQUEST_PROMPT
            + f" Known saved preferences for this user: {profile.get('prefs', {})}. "
            "Use them to fill missing fields. If the user states a lasting preference "
            "(for example 'my home base is KFDK'), call remember before answering."
        )

    return client.as_agent(name="request", instructions=instructions, tools=[remember])

