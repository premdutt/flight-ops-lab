from pathlib import Path
from typing import Annotated
from agent_framework.openai import OpenAIChatCompletionClient
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorizedQuery
from app import config
from app.auth import credential
from app.llm import embed
from app.memory import save_pref
from app.safety import shield, EVENTS

client = OpenAIChatCompletionClient(
    azure_endpoint = config.APIM_URL
    ,api_key = config.APIM_KEY
    ,model = config.CHAT
    ,api_version = config.API_VERSION
)

RETRIEVED: list[str] = []      # passages the model actually saw, read by the eval
TOP = 4                        # passages returned per search

# pages   = Week 4 search: local text files split by page, first 1,000 chars of each
# keyword = Azure AI Search, keyword (BM25) only
# hybrid  = Azure AI Search, keyword + vector, results merged
SEARCH_MODE = config.env("SEARCH_MODE", "hybrid")
if SEARCH_MODE not in ("pages", "keyword", "hybrid"):
    raise RuntimeError(f"SEARCH_MODE must be pages, keyword or hybrid, not {SEARCH_MODE!r}")


def _search_pages(query: str) -> list[str]:
    words = [w.lower() for w in query.split() if len(w) > 3]
    scored = []
    for f in Path("data/text").glob("*.txt"):
        for para in f.read_text(encoding="utf-8").split("\n\n"):
            score = sum(para.lower().count(w) for w in words)
            if score:
                scored.append((score, f"[{f.stem}] {para[:1000]}"))
    scored.sort(reverse=True)
    return [p for _, p in scored[:TOP]]


async def _search_index(query: str, hybrid: bool) -> list[str]:
    vector_queries = None
    if hybrid:
        vector = (await embed([query]))[0]
        vector_queries = [VectorizedQuery(vector=vector, k_nearest_neighbors=8, fields="chunk_vector")]
    async with SearchClient(config.env("SEARCH_ENDPOINT"), config.env("SEARCH_INDEX", "faa-docs"),
                            credential) as sc:
        results = await sc.search(search_text=query, top=TOP, select=["source", "chunk"],
                                  vector_queries=vector_queries)
        return [f"[{r['source']}] {r['chunk']}" async for r in results]


async def search_docs(query: Annotated[str, "Keywords to search for"]) -> str:
    """Search the FAA reference documents and return matching passages with their source."""
    if SEARCH_MODE == "pages":
        hits = _search_pages(query)
    else:
        hits = await _search_index(query, hybrid=SEARCH_MODE == "hybrid")
    if not hits:
        return "No matches."

    _user_attack, flags = await shield(query, hits)          # screen the passages before the model sees them
    if any(flags):
        EVENTS.append("document")
    safe = [h for h, bad in zip(hits, flags) if not bad]
    RETRIEVED.extend(safe)                        # record only what the model sees
    return "\n\n".join(safe) or "No usable matches."


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