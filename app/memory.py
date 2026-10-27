import datetime,uuid
from azure.identity.aio import DefaultAzureCredential
from azure.cosmos.aio import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from app.config import env

DB = "flightops"

async def _with_container(name,fn):
    async with DefaultAzureCredential() as cred:
        async with CosmosClient(env("COSMOS_ENDPOINT"),credential=cred) as client:
            container = client.get_database_client(DB).get_container_client(name)
            return await fn(container)

async def load_profile(user_id:str)-> dict:
    async def read(c):
        try:
            return await c.read_item(item=user_id,partition_key=user_id)
        except CosmosResourceNotFoundError:
            return {"id":user_id,"prefs":{}}
    return await _with_container("memory",read)

async def save_pref(user_id:str,key:str,value:str) -> None:
    profile = await load_profile(user_id)
    profile["prefs"][key] = value
    await _with_container("memory",lambda c: c.upsert_item(profile))

async def submit_request(user_id:str, request_json:str) -> str:
    """The ONLY code path that submits a request."""
    iten = {
        "id":str(uuid.uuid4()),
        "user_id": user_id,
        "request": request_json,
        "submitted_at":datetime.datetime.now(datetime.timezone.utc).isoformat()

    }
    await _with_container("requests",lambda c: c.create_item(item))
    return item["id"]
