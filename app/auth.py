"""An async Entra ID credential that reuses tokens, safe to share across calls and event loops."""
import time
from azure.identity.aio import DefaultAzureCredential


class CachedCredential:
    """Gets a token per scope once and reuses it until 5 minutes before it expires.

    DefaultAzureCredential locally runs `az` for every new credential (about 1-2 s).
    This opens one only when a token is missing or nearly expired, then closes it,
    so nothing stays bound to an event loop.
    """

    def __init__(self):
        self._tokens = {}

    async def get_token(self, *scopes, **kwargs):
        key = " ".join(scopes)
        token = self._tokens.get(key)
        if token is None or token.expires_on - 300 < time.time():
            async with DefaultAzureCredential() as cred:
                token = await cred.get_token(*scopes, **kwargs)
            self._tokens[key] = token
        return token

    async def close(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass


credential = CachedCredential()
