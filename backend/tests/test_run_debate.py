import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir.parent))

load_dotenv(backend_dir / ".env")

from debate.history import store_name
from backend.debate.orchestrator import run_debate
from motor.motor_asyncio import AsyncIOMotorClient

class MockWebSocket:
    def __init__(self):
        self.events = []
        self.final_verdict = None

    async def send_json(self, data: dict):
        event_type = data.get("type")
        self.events.append(event_type)
        if event_type == "sub_round_start":
            print(f"  [Round {data.get('round')}] Sub-round {data.get('sub_round')}: {data.get('label')}")
        elif event_type == "pro_argument":
            text = data.get("text", "")
            preview = text[:90].replace('\n', ' ')
            print(f"    PRO: {preview}...")
        elif event_type == "con_argument":
            text = data.get("text", "")
            preview = text[:90].replace('\n', ' ')
            print(f"    CON: {preview}...")
        elif event_type == "fact_check":
            d = data.get("data", {})
            print(f"    [FACT-CHECK]: {d.get('summary')} (PRO checked: {d.get('pro', {}).get('claims_checked')}, CON checked: {d.get('con', {}).get('claims_checked')})")
        elif event_type == "agent_status":
            active = [a['name'] for a in data.get('agents', []) if a.get('status') == 'active']
            if active:
                print(f"    [PIPELINE]: Active -> {active}")
        elif event_type == "round_verdict":
            verdict = data.get("data", {})
            print(f"  --> Round verdict: Winner={verdict.get('round_winner')}, Pro={verdict.get('pro_scores', {}).get('total')}, Con={verdict.get('con_scores', {}).get('total')}")
        elif event_type == "final_verdict":
            self.final_verdict = data.get("data")
            print(f"  --> Final verdict: Overall Winner={self.final_verdict.get('overall_winner')}")
        elif event_type == "error":
            print(f"  [ERROR]: {data.get('message')}")

async def main():
    print(f"Using history store: {store_name()}")
    
    # 1. Connect to MongoDB to check count before debate
    mongo_uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB", "argus")
    col_name = os.getenv("MONGODB_COLLECTION", "debates")
    client = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=5000)
    col = client[db_name][col_name]
    
    initial_count = await col.count_documents({})
    print(f"Initial debates count in MongoDB ({db_name}.{col_name}): {initial_count}")
    
    # 2. Run a 1-round debate
    topic = "Is nuclear energy essential for clean energy transition?"
    print(f"\nStarting debate on: '{topic}' (rounds=1)...")
    ws = MockWebSocket()
    await run_debate(ws, topic, rounds=1)
    
    # 3. Verify in MongoDB
    print("\nDebate finished! Verifying storage in MongoDB...")
    new_count = await col.count_documents({})
    print(f"New debates count in MongoDB: {new_count}")
    
    if new_count > initial_count:
        latest = await col.find({}, {"_id": 0}).sort("created_at", -1).to_list(length=1)
        if latest:
            doc = latest[0]
            print("\n=== VERIFIED DOCUMENT IN MONGODB ATLAS ===")
            print(f"  ID: {doc.get('id')}")
            print(f"  Topic: {doc.get('topic')}")
            print(f"  Created At: {doc.get('created_at')}")
            print(f"  Rounds stored: {len(doc.get('rounds', []))}")
            final = doc.get("final_verdict", {})
            print(f"  Winner: {final.get('overall_winner')}")
            print(f"  Pro Total: {final.get('pro_total')} | Con Total: {final.get('con_total')}")
            print("  Judge Reasoning Preview:", str(doc.get('rounds', [{}])[0].get('reasoning', ''))[:150], "...")
            print("\nSUCCESS: The debate and judge logs were successfully stored in MongoDB Atlas!")
    else:
        print("ERROR: Document count did not increase in MongoDB!")

if __name__ == "__main__":
    asyncio.run(main())
