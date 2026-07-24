import asyncio
import os
import json
import httpx

from agents.judge_agent import judge_round, judge_final_verdict

async def main():
    print("--- 1. Pinging Kaggle Backend Health ---")
    url = "https://viewer-backboned-jellied.ngrok-free.dev/health"
    headers = {"ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=10.0)
            print("Status:", resp.status_code)
            print("Body:", resp.text)
    except Exception as e:
        print("Ping failed:", e)

    print("\n--- 2. Generating Scores from Kaggle Model & Groq ---")
    topic = "Artificial Intelligence is a threat to humanity."
    exchange = [
        {"speaker": "pro", "text": "AI will take our jobs and eventually rebel against us. Without regulation, it's an existential risk.", "sub_round": 1},
        {"speaker": "con", "text": "AI is just a tool. It depends on how humans use it. It has the potential to solve diseases and climate change.", "sub_round": 1},
    ]
    try:
        round_result = await judge_round(topic, 1, exchange)
        print("Round result:")
        print(json.dumps(round_result, indent=2))
        
        print("\n--- 3. Generating Final Verdict from Groq ---")
        verdict = await judge_final_verdict(topic, [round_result])
        print("Verdict:")
        print(json.dumps(verdict, indent=2))
        
    except Exception as e:
        print("Generation failed:", e)

if __name__ == "__main__":
    asyncio.run(main())
