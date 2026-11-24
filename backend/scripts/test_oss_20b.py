import os
import asyncio
from dotenv import load_dotenv

load_dotenv()
from agents.pro_agent import generate_pro_argument
from agents.debater_client import debater_client

async def main():
    print(f"Testing PRO agent with model {os.getenv('PRO_MODEL')}")
    client = debater_client
    res, model = await generate_pro_argument("The UN should admit Palestine", "No it shouldn't", "Hello, begin.", "")
    print(f"RAW RES: {repr(res)}")

if __name__ == '__main__':
    asyncio.run(main())
