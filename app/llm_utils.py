# app/llm_utils.py: generic helpers for handling model output (no project-specific imports)
import json, re

def extract_json(text: str) -> str:
    """Return the JSON object in a model reply as clean one-line JSON.
    Handles code fences and text before or after it. Returns the text unchanged if no valid JSON is found."""
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = fenced[::-1] or [text[text.find("{"): text.rfind("}") + 1]]
    for c in candidates:
        try:
            return json.dumps(json.loads(c))
        except ValueError:
            continue
    return text.strip()

def final_text(response) -> str:
    """The agent's final answer only, without the notes some models write between tool calls."""
    return response.messages[-1].text.strip()