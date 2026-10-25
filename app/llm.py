from openai import AsyncAzureOpenAI
from app import config

oai = AsyncAzureOpenAI(azure_endpoint=config.APIM_URL,api_key=config.APIM_KEY,api_version=config.API_VERSION)

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
