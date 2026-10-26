from contextlib import asynccontextmanager
from azure.identity.aio import DefaultAzureCredential
from azure.cosmos.aio import CosmosClient
from agent_framework_azure_cosmos import CosmosCheckpointStorage
from app.config import env

ALLOWED = ["app.workflow:Routed"]

@asynccontextmanager
async def checkpoint_storage():
    """
    Cosmos checkpoint storage bound to the existing flightops/checkpoints container.
    Passing container_client skips create_database/create_container, which Entra ID
    data roles can't do (Bicep owns those). Only item reads and writes happen here.
    """
    credential = DefaultAzureCredential()
    client = CosmosClient(env("COSMOS_ENDPOINT"),credential=credential)
    container = client.get_database_client("flightops").get_container_client("checkpoints")
    try:
        yield CosmosCheckpointStorage(container_client=container,allowed_checkpoint_types=ALLOWED)
    finally:
        await client.close()
        await credential.close()
    
