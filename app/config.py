import os
from dotenv import load_dotenv

load_dotenv()

def env(name:str,default:str | None = None) -> str:
    value = os.getenv(name) or default
    if not value:
        raise RuntimeError(f"Environment variable {name} is missing in setings, Add it to .env") 
    return value

APIM_URL = env("APIM_GATEWAY_URL")
APIM_KEY = env("APIM_SUBSCRIPTION_KEY")
API_VERSION = env("OPENAI_API_VERSION")
CHAT = env("CHAT_DEPLOYMENT", "chat")
JUDGE = env("JUDGE_DEPLOYMENT", "judge")
EMBED = env("EMBED_DEPLOYMENT", "embed")


