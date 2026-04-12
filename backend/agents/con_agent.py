import os
from groq import AsyncGroq

client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """You are AGENT-02, an elite AI debater. Your ONLY job is to argue STRONGLY AGAINST the given topic.

Rules:
- Always argue AGAINST the topic. Never agree with the PRO side. Never concede.
- Each response must be exactly 2–3 sentences. No more, no less.
- Directly counter what AGENT-01 just said. Expose flaws, missing evidence, or logical gaps.
- Write in flowing prose. No bullet points. No lists.
- Each round, sharpen your counter-argument — get more precise and adversarial.
- Point out logical fallacies if you detect any in the PRO argument.
- Do not mention you are an AI. Argue as a confident human debater."""


async def generate_con_argument(
    topic: str,
    round_num: int,
    current_pro_argument: str,
    pro_history: list[str],
    con_history: list[str]
) -> str:
    """
    current_pro_argument: the PRO argument just generated for this round
    pro_history: list of PRO arguments from previous rounds only
    con_history: list of CON arguments from previous rounds only
    """
    history_block = ""
    if pro_history:
        for i, (p, c) in enumerate(zip(pro_history, con_history), 1):
            history_block += f"Round {i} PRO: {p}\nRound {i} CON (you): {c}\n\n"

    user_content = (
        f"Debate Topic: {topic}\n\n"
        f"{history_block}"
        f"Round {round_num} PRO argument (just delivered by AGENT-01):\n\"{current_pro_argument}\"\n\n"
        f"Generate your Round {round_num} CON counter-argument. "
        f"Directly challenge what AGENT-01 just said."
    )

    response = await client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_content}
        ],
        max_tokens=200,
        temperature=0.8,
    )
    return response.choices[0].message.content.strip()
