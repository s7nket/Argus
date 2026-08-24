import asyncio
from groq import AsyncGroq

async def main():
    client = AsyncGroq(api_key='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')
    res = await client.models.list()
    print([m.id for m in res.data])

asyncio.run(main())
