# app/safety.py
import time
import httpx
from azure.identity.aio import DefaultAzureCredential
from app.config import env

API_VERSION = "2024-09-01"
SCOPE = "https://cognitiveservices.azure.com/.default"
EVENTS: list[str] = []

_token = None

async def _bearer() -> str:
    """Reuse the token until 5 minutes before it expires."""
    global _token
    if _token is None or _token.expires_on - 300 < time.time():
        async with DefaultAzureCredential() as cred:
            _token = await cred.get_token(SCOPE)
    return _token.token

async def _post(path:str,body:dict) -> dict:
    url = f"{env('CONTENT_SAFETY_ENDPOINT').rstrip('/')}/contentsafety/{path}?api-version={API_VERSION}"
    async with httpx.AsyncClient(timeout=15) as http:
        r = await http.post(url, json=body, headers={"Authorization": f"Bearer {await _bearer()}"})
        if r.status_code >= 400:
            print("CS ERROR:", r.status_code, r.headers.get("www-authenticate"), r.text)
        return r.json()

async def shield(user_prompt: str, documents: list[str] | None = None) -> tuple[bool, list[bool]]:
    """Prompt Shields. Returns (attack in the user prompt, attack flag for each document)."""
    res = await _post("text:shieldPrompt",
                      {"userPrompt": user_prompt[:10000], "documents": documents or []})
    user_attack = res["userPromptAnalysis"]["attackDetected"]
    doc_flags = [d["attackDetected"] for d in res.get("documentsAnalysis", [])]
    return user_attack, doc_flags

async def moderate(text: str, max_severity: int = 2) -> bool:
    """True if the text is safe to show (every harm category at or below max_severity)."""
    res = await _post("text:analyze", {"text": text[:10000]})
    return all(c["severity"] <= max_severity for c in res["categoriesAnalysis"])