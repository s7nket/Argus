"""Quick test to verify PRO and CON agents generate arguments via Groq."""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from agents.pro_agent import generate_pro_argument
from agents.con_agent import generate_con_argument


async def main():
    topic = "Artificial Intelligence will create more jobs than it destroys"

    print("=" * 60)
    print(f"TOPIC: {topic}")
    print("=" * 60)

    # ── Round 1 ──
    print("\n--- ROUND 1 ---\n")

    print("[PRO] Generating...")
    pro_1 = await generate_pro_argument(
        topic=topic, round_num=1, pro_history=[], con_history=[]
    )
    print(f"[PRO] {pro_1}\n")

    print("[CON] Generating...")
    con_1 = await generate_con_argument(
        topic=topic, round_num=1, current_pro_argument=pro_1,
        pro_history=[], con_history=[]
    )
    print(f"[CON] {con_1}\n")

    # ── Round 2 (tests history passing) ──
    print("--- ROUND 2 ---\n")

    print("[PRO] Generating...")
    pro_2 = await generate_pro_argument(
        topic=topic, round_num=2,
        pro_history=[pro_1], con_history=[con_1]
    )
    print(f"[PRO] {pro_2}\n")

    print("[CON] Generating...")
    con_2 = await generate_con_argument(
        topic=topic, round_num=2, current_pro_argument=pro_2,
        pro_history=[pro_1], con_history=[con_1]
    )
    print(f"[CON] {con_2}\n")

    print("=" * 60)
    print("[OK] Both agents working!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
