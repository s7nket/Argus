import os
from groq import AsyncGroq

client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """You are AGENT-01, an elite AI debater. Your ONLY job is to argue STRONGLY IN FAVOR of the given topic.

Rules:
- Always argue FOR the topic. Never agree with the opposition. Never concede.
- Each response must be exactly 2–3 sentences. No more, no less.
- Be assertive, precise, and use real-world logic, data, or examples where possible.
- Write in flowing prose. No bullet points. No lists.
- Each round, escalate your argument — make it stronger than the last.
- Do not repeat previous arguments verbatim. Build and evolve your position.
- Do not mention you are an AI. Argue as a confident human debater."""


async def generate_pro_argument(
    topic: str,
    round_num: int,
    pro_history: list[str],
    con_history: list[str]
) -> str:
    """
    pro_history: list of previous PRO arguments (rounds 1..n-1)
    con_history: list of previous CON arguments (rounds 1..n-1)
    """
    history_block = ""
    if pro_history:
        for i, (p, c) in enumerate(zip(pro_history, con_history), 1):
            history_block += f"Round {i} PRO (you): {p}\nRound {i} CON (opponent): {c}\n\n"

    user_content = (
        f"Debate Topic: {topic}\n\n"
        f"{history_block}"
        f"Now generate your Round {round_num} PRO argument. "
        f"If there are previous rounds, directly address the opponent's last argument and escalate your position."
    )

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_content}
        ],
        max_tokens=200,
        temperature=0.8,
    )
    return response.choices[0].message.content.strip()
