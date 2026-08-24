import asyncio
import os
from openai import AsyncOpenAI

async def main():
    client = AsyncOpenAI(
        api_key="csk-xmpk3rk2wjf2k5rtpd9v282vxfv8cj445mdf5e3pdxn2tevv",
        base_url="https://api.cerebras.ai/v1",
    )
    
    models = await client.models.list()
    for m in models.data:
        print("Model:", m.id)

asyncio.run(main())
