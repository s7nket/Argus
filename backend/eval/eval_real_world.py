import asyncio
import json
import os
import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv

_backend_dir = Path(__file__).resolve().parent.parent
_project_root = _backend_dir.parent
for _p in (str(_project_root), str(_backend_dir)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv(_backend_dir / ".env")

from eval import metrics
from backend.debate.orchestrator import run_debate

class MockWebSocket:
    def __init__(self):
        self.messages = []
        self.final_verdict = None
        self.error = None

    async def send_json(self, data: dict):
        self.messages.append(data)
        if data.get("type") == "final_verdict":
            self.final_verdict = data.get("data")
        elif data.get("type") == "error":
            self.error = data.get("message")

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="eval/data/real_world_debates.json", help="Path to JSON dataset")
    ap.add_argument("--rounds", type=int, default=1, help="Number of debate rounds to simulate")
    ap.add_argument("--limit", type=int, default=0, help="Only evaluate first N debates")
    args = ap.parse_args()

    if not os.path.exists(args.path):
        print(f"Dataset not found at {args.path}")
        return

    with open(args.path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    debates = dataset.get("debates", [])
    if args.limit > 0:
        debates = debates[:args.limit]

    print(f"Starting evaluation on {len(debates)} real-world debates.")
    print(f"Rounds per debate: {args.rounds}")
    print("-" * 80)

    preds = []
    golds = []
    successful = 0
    failed = 0

    # Process debates one by one to avoid overwhelming rate limits
    for i, debate in enumerate(debates):
        topic = debate["topic"]
        gold_winner = debate["winner"].lower()
        
        print(f"[{i+1}/{len(debates)}] Topic: {topic}")
        print(f"  Gold Winner: {gold_winner.upper()}")
        
        ws = MockWebSocket()
        
        try:
            # Run the debate using the backend's orchestrator
            # Note: run_debate catches its own exceptions and sends error messages
            # over the websocket, but we wrap it just in case.
            await run_debate(ws, topic, rounds=args.rounds)
            
            if ws.error:
                print(f"  FAILED: {ws.error}")
                failed += 1
                continue
                
            if not ws.final_verdict:
                print("  FAILED: No final verdict received.")
                failed += 1
                continue
                
            winner_raw = ws.final_verdict.get("overall_winner") or ws.final_verdict.get("winner")
            if isinstance(winner_raw, dict):
                winner_raw = ws.final_verdict.get("overall_winner") or "unknown"
            predicted_winner = str(winner_raw or "unknown").strip().lower()
            
            # Print intermediate result
            match = "[MATCH]" if predicted_winner == gold_winner else "[MISMATCH]"
            print(f"  Predicted: {predicted_winner.upper()} -> {match}", flush=True)
            
            # Diagnostic: show per-round scores and scorer
            for msg in ws.messages:
                if msg.get("type") == "round_verdict":
                    rd = msg.get("data", {})
                    pro_s = rd.get("pro_scores", {})
                    con_s = rd.get("con_scores", {})
                    audit = rd.get("audit", {})
                    print(f"    R{msg.get('round', '?')}: PRO={pro_s.get('total', '?')} CON={con_s.get('total', '?')} "
                          f"winner={rd.get('round_winner', '?')} scorer={audit.get('scorer', '?')}")
                    print(f"      PRO scores: E={pro_s.get('evidence','?')} L={pro_s.get('logic','?')} R={pro_s.get('relevance','?')}")
                    print(f"      CON scores: E={con_s.get('evidence','?')} L={con_s.get('logic','?')} R={con_s.get('relevance','?')}")

            # Store for metrics
            if predicted_winner in ["pro", "con", "tie"]:
                preds.append(predicted_winner)
                golds.append(gold_winner)
                successful += 1
            else:
                print(f"  WARNING: Invalid winner format: {predicted_winner}")
                failed += 1

        except Exception as e:
            print(f"  EXCEPTION: {e}")
            failed += 1

    print("\n" + "=" * 80)
    print("EVALUATION RESULTS")
    print("=" * 80)
    print(f"Total processed : {len(debates)}")
    print(f"Successful runs : {successful}")
    print(f"Failed runs     : {failed}")
    
    if successful > 0:
        print("-" * 80)
        print(f"Accuracy (Agreement) : {metrics.agreement(preds, golds):.1%}")
        if len(set(golds)) > 1: # Kappa needs at least some variance in gold labels to be meaningful
            print(f"Cohen's Kappa        : {metrics.cohens_kappa(preds, golds):.2f}")
        print("-" * 80)
        
        # Distribution
        pro_rate = preds.count("pro") / len(preds)
        con_rate = preds.count("con") / len(preds)
        tie_rate = preds.count("tie") / len(preds)
        
        gold_pro = golds.count("pro") / len(golds)
        gold_con = golds.count("con") / len(golds)
        
        print(f"Predicted Distribution : PRO: {pro_rate:.1%} | CON: {con_rate:.1%} | TIE: {tie_rate:.1%}")
        print(f"Gold Distribution      : PRO: {gold_pro:.1%} | CON: {gold_con:.1%}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
