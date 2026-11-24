import os
import asyncio
from dotenv import load_dotenv

load_dotenv()
from groq import AsyncGroq

async def main():
    client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"), timeout=20.0)
    for model in ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b", "allam-2-7b"]:
        try:
            print(f"Testing model {model}...")
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a debater."},
                    {"role": "user",   "content": "Tell me a short argument for why cats are better than dogs."}
                ],
                max_tokens=50,
            )
            print(f"[{model}] RES: {repr(response.choices[0].message.content)}")
        except Exception as e:
            print(f"[{model}] ERR: {e}")

if __name__ == '__main__':
    asyncio.run(main())
