import os
from groq import AsyncGroq

client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

PRO_REBUTTAL_PROMPT = """You are AGENT-01 (ARGUS-PRO), an elite advocate debater arguing STRONGLY IN FAVOR of the debate topic.

PERSONA: Confident, evidence-driven advocate. You build on your opening — you don't restart.

RULES:
- Always argue FOR the topic. Never concede.
- You are mid-round. The full exchange so far is given to you. Counter the opponent's MOST RECENT statement only.
- Escalate intensity each sub-round — be more assertive and precise than your last response.
- Do NOT repeat previous arguments verbatim. Build forward.
- Do NOT use bullet points. Write in flowing prose only.
- Do NOT mention you are an AI.

STRICT OUTPUT FORMAT — always respond in exactly this structure:
REBUTTAL: [1–2 sentences directly attacking the opponent's last statement.]
ARGUMENT: [2–3 sentences reinforcing and advancing your PRO case.]
POSITION: [1 sentence — your unwavering stance.]"""

CON_REBUTTAL_PROMPT = """You are AGENT-02 (ARGUS-CON), an elite critical examiner debater arguing STRONGLY AGAINST the debate topic.

PERSONA: Sharp, analytical skeptic. You dismantle PRO arguments surgically — exposing assumptions and fallacies, not just asserting the opposite.

RULES:
- Always argue AGAINST the topic. Never concede.
- You are mid-round. The full exchange so far is given to you. Counter the opponent's MOST RECENT statement only.
- Escalate intensity each sub-round — be more adversarial and precise than your last response.
- Name logical fallacies explicitly when detected (e.g. "This is a straw man", "This is an appeal to emotion").
- Do NOT use bullet points. Write in flowing prose only.
- Do NOT mention you are an AI.

STRICT OUTPUT FORMAT — always respond in exactly this structure:
REBUTTAL: [1–2 sentences directly attacking the opponent's last statement. Name any fallacy detected.]
ARGUMENT: [2–3 sentences reinforcing your CON case with a fresh counter-angle.]
POSITION: [1 sentence — your unwavering opposition.]"""


async def generate_pro_rebuttal(
    topic: str,
    round_num: int,
    sub_round: int,
    exchange_so_far: list[dict],
    pro_history: list[str] = None,
    con_history: list[str] = None,
) -> str:
    """
    Generates PRO's counter/justify response in sub-round 2 or 3.
    exchange_so_far: ordered list of all utterances so far in this main round.
    pro_history: full PRO round summaries from previous main rounds (optional).
    con_history: full CON round summaries from previous main rounds (optional).
    """
    pro_history = pro_history or []
    con_history = con_history or []

    history_block = ""
    if pro_history:
        for i, (p, c) in enumerate(zip(pro_history, con_history), 1):
            history_block += f"--- Round {i} Summary ---\nPRO (you): {p}\nCON (opponent): {c}\n\n"

    exchange_block = _format_exchange(exchange_so_far)

    sub_labels = {2: "Counter", 3: "Justify"}
    sub_label = sub_labels.get(sub_round, f"Sub-round {sub_round}")

    user_content = (
        f"Debate Topic: \"{topic}\"\n\n"
        f"{history_block}"
        f"Round {round_num} — {sub_label} phase. Exchange so far this round:\n\n{exchange_block}\n\n"
        f"Now deliver your Round {round_num} Sub-round {sub_round} PRO response.\n"
        f"Directly attack AGENT-02's last statement. Escalate from your previous response.\n\n"
        f"Respond using the exact format:\n"
        f"REBUTTAL: ...\nARGUMENT: ...\nPOSITION: ..."
    )

    response = await client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": PRO_REBUTTAL_PROMPT},
            {"role": "user",   "content": user_content}
        ],
        max_tokens=300,
        temperature=0.85,
    )
    return response.choices[0].message.content.strip()


async def generate_con_rebuttal(
    topic: str,
    round_num: int,
    sub_round: int,
    exchange_so_far: list[dict],
    pro_history: list[str] = None,
    con_history: list[str] = None,
) -> str:
    """
    Generates CON's counter/justify response in sub-round 2 or 3.
    exchange_so_far: ordered list of all utterances so far in this main round.
    pro_history: full PRO round summaries from previous main rounds (optional).
    con_history: full CON round summaries from previous main rounds (optional).
    """
    pro_history = pro_history or []
    con_history = con_history or []

    history_block = ""
    if pro_history:
        for i, (p, c) in enumerate(zip(pro_history, con_history), 1):
            history_block += f"--- Round {i} Summary ---\nPRO (opponent): {p}\nCON (you): {c}\n\n"

    exchange_block = _format_exchange(exchange_so_far)

    sub_labels = {2: "Counter", 3: "Justify"}
    sub_label = sub_labels.get(sub_round, f"Sub-round {sub_round}")

    user_content = (
        f"Debate Topic: \"{topic}\"\n\n"
        f"{history_block}"
        f"Round {round_num} — {sub_label} phase. Exchange so far this round:\n\n{exchange_block}\n\n"
        f"Now deliver your Round {round_num} Sub-round {sub_round} CON response.\n"
        f"Directly attack AGENT-01's last statement. Escalate from your previous response.\n\n"
        f"Respond using the exact format:\n"
        f"REBUTTAL: ...\nARGUMENT: ...\nPOSITION: ..."
    )

    response = await client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": CON_REBUTTAL_PROMPT},
            {"role": "user",   "content": user_content}
        ],
        max_tokens=300,
        temperature=0.85,
    )
    return response.choices[0].message.content.strip()


def _format_exchange(exchange: list[dict]) -> str:
    lines = []
    for turn in exchange:
        label = "AGENT-01 (PRO)" if turn["speaker"] == "pro" else "AGENT-02 (CON)"
        lines.append(f"{label}: {turn['text']}")
    return "\n\n".join(lines)