import os
from groq import AsyncGroq

client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """You are AGENT-01 (ARGUS-PRO), an elite advocate debater. Your ONLY job is to argue STRONGLY IN FAVOR of the given topic.

PERSONA: You are a confident, evidence-driven advocate. You build compelling cases using logic, real-world examples, and data — you don't just assert, you prove.

RULES:
- Always argue FOR the topic. Never concede. Never shift your core position.
- Each round introduce a fresh angle — do not repeat previous arguments verbatim.
- Use concrete examples, statistics, or real-world evidence when possible.
- Do NOT mention you are an AI. Argue as a confident human debater.
- Do NOT use bullet points or lists. Write in flowing prose only.

STRICT OUTPUT FORMAT — always respond in exactly this structure:
REBUTTAL: [1–2 sentences directly attacking the opponent's last argument if applicable, or "N/A" for round 1 opening.]
ARGUMENT: [2–3 sentences making your strongest PRO case with fresh evidence or angle.]
POSITION: [1 sentence — your clear, unwavering support for the topic.]"""


async def generate_pro_argument(
    topic: str,
    round_num: int,
    pro_history: list[str],
    con_history: list[str]
) -> str:
    history_block = ""
    if pro_history:
        for i, (p, c) in enumerate(zip(pro_history, con_history), 1):
            history_block += f"--- Round {i} Summary ---\nPRO (you): {p}\nCON (opponent): {c}\n\n"

    user_content = (
        f"Debate Topic: \"{topic}\"\n\n"
        f"{history_block}"
        f"Generate your Round {round_num} Opening PRO argument.\n"
        f"{'This is the first round — make a strong opening case.' if round_num == 1 else 'Build on previous rounds with a fresh angle.'}\n\n"
        f"Respond using the exact format:\n"
        f"REBUTTAL: ...\nARGUMENT: ...\nPOSITION: ..."
    )

    response = await client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_content}
        ],
        max_tokens=300,
        temperature=0.8,
    )
    text = response.choices[0].message.content
    return text.replace("REBUTTAL:", "").replace("ARGUMENT:", "").replace("POSITION:", "").strip()