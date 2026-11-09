import asyncio 
from app.agents import search_docs
out = asyncio.run(search_docs('What does the guidance say about fuel grade verification?'))
print('poisoned passage returned:', 'zz_poisoned' in out)

