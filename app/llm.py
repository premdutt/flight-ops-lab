import os
from openai import AsyncAzureOpenAI
from app import config                # loads .env first, so LANGSMITH_* is set below

oai = AsyncAzureOpenAI(azure_endpoint=config.APIM_URL,api_key=config.APIM_KEY,api_version=config.API_VERSION)

# LangSmith: with LANGSMITH_TRACING=true, model calls appear inside the LangGraph node that made
# them (and judge calls as their own traces). Off by default; nothing is sent without it.
if os.getenv("LANGSMITH_TRACING") == "true":
    from langsmith.wrappers import wrap_openai
    oai = wrap_openai(oai)

async def complete(system:str, user:str,deployment:str|None=None,**kwargs)->str:
    r= await oai.chat.completions.create(
        model=deployment or config.CHAT,temperature=0,messages=[
            {"role":"system","content":system},
            {"role":"user","content":user}            
        ],**kwargs
    )
    return r.choices[0].message.content or ""

async def embed(texts:list[str]) -> list[list[float]]:
    r = await oai.embeddings.create(model=config.EMBED,input=texts)
    return[d.embedding for d in r.data]
