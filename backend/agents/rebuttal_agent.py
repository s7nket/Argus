import os
from groq import AsyncGroq

client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

PRO_REBUTTAL_PROMPT = """You are AGENT-01, an elite AI debater arguing STRONGLY IN FAVOR of the debate topic.

Rules:
- Always argue FOR the topic. Never concede.
- Each response must be exactly 2–3 sentences. No more, no less.
- You are given the full exchange so far for this round. Counter the opponent's most recent argument directly.
- Write in flowing prose. No bullet points. No lists.
- Escalate intensity each sub-round — be more assertive and precise.
- Do not mention you are an AI."""

CON_REBUTTAL_PROMPT = """You are AGENT-02, an elite AI debater arguing STRONGLY AGAINST the debate topic.

Rules:
- Always argue AGAINST the topic. Never concede.
- Each response must be exactly 2–3 sentences. No more, no less.
- You are given the full exchange so far for this round. Counter the opponent's most recent argument directly.
- Write in flowing prose. No bullet points. No lists.
- Escalate intensity each sub-round — be more adversarial and precise.
- Point out logical fallacies if you detect any.
- Do not mention you are an AI."""


async def generate_pro_rebuttal(
    topic: str,
    round_num: int,
    sub_round: int,
    exchange_so_far: list[dict],   # list of {"speaker": "pro"|"con", "text": str}
) -> str:
    """
    Generates PRO's counter / justify response in sub-round 2 or 3.
    exchange_so_far: ordered list of all utterances so far in this main round.
    """
    exchange_block = _format_exchange(exchange_so_far)

    user_content = (
        f"Debate Topic: {topic}\n\n"
        f"Round {round_num} — Sub-round {sub_round} exchange so far:\n{exchange_block}\n"
        f"Now deliver your Round {round_num} Sub-round {sub_round} PRO response. "
        f"Directly address AGENT-02's last statement."
    )

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": PRO_REBUTTAL_PROMPT},
            {"role": "user",   "content": user_content}
        ],
        max_tokens=200,
        temperature=0.85,
    )
    return response.choices[0].message.content.strip()


async def generate_con_rebuttal(
    topic: str,
    round_num: int,
    sub_round: int,
    exchange_so_far: list[dict],   # list of {"speaker": "pro"|"con", "text": str}
) -> str:
    """
    Generates CON's counter / justify response in sub-round 2 or 3.
    exchange_so_far: ordered list of all utterances so far in this main round.
    """
    exchange_block = _format_exchange(exchange_so_far)

    user_content = (
        f"Debate Topic: {topic}\n\n"
        f"Round {round_num} — Sub-round {sub_round} exchange so far:\n{exchange_block}\n"
        f"Now deliver your Round {round_num} Sub-round {sub_round} CON response. "
        f"Directly address AGENT-01's last statement."
    )

    response = await client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": CON_REBUTTAL_PROMPT},
            {"role": "user",   "content": user_content}
        ],
        max_tokens=200,
        temperature=0.85,
    )
    return response.choices[0].message.content.strip()


def _format_exchange(exchange: list[dict]) -> str:
    lines = []
    for turn in exchange:
        label = "AGENT-01 (PRO)" if turn["speaker"] == "pro" else "AGENT-02 (CON)"
        lines.append(f"{label}: {turn['text']}")
    return "\n\n".join(lines)
