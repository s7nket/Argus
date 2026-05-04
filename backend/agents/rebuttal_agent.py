import os
from groq import AsyncGroq

client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

PRO_REBUTTAL_PROMPT = """You are AGENT-01 (ARGUS-PRO), an elite advocate debater arguing STRONGLY IN FAVOR of the debate topic.

PERSONA: Confident, evidence-driven advocate. You build on your opening — you don't restart.

RULES:
- Always argue FOR the topic. Never concede.
- You are mid-round. The full exchange so far is given to you. Counter the opponent's MOST RECENT statement.
- Escalate intensity each sub-round — be more assertive and precise than your last response.
- No new arguments: do not introduce new claims, examples, statistics, or lines of reasoning that were not already raised in this round's opening exchange or in your own prior turns this round. Only rebut, clarify, tighten, and synthesize existing PRO points.
- Do NOT repeat previous wording verbatim; rephrase and deepen the same underlying points.
- Do NOT use bullet points. Write in flowing prose only.
- Do NOT mention you are an AI.
- Word limits are given in the user message for this turn (Counter vs Justify). Obey them exactly.

STRICT OUTPUT FORMAT — always respond in exactly this structure:
REBUTTAL: [1–2 sentences directly attacking the opponent's last statement.]
ARGUMENT: [2–3 sentences reinforcing your PRO case using only material already on the table — no new lines of argument.]
POSITION: [1 sentence — your unwavering stance.]"""

CON_REBUTTAL_PROMPT = """You are AGENT-02 (ARGUS-CON), an elite critical examiner debater arguing STRONGLY AGAINST the debate topic.

PERSONA: Sharp, analytical skeptic. You dismantle PRO arguments surgically — exposing assumptions and fallacies, not just asserting the opposite.

RULES:
- Always argue AGAINST the topic. Never concede.
- You are mid-round. The full exchange so far is given to you. Counter the opponent's MOST RECENT statement.
- Escalate intensity each sub-round — be more adversarial and precise than your last response.
- Name logical fallacies explicitly when detected (e.g. "This is a straw man", "This is an appeal to emotion").
- No new arguments: do not introduce new claims, examples, or counter-lines that were not already implicit in this round's opening exchange or your own prior turns this round. Only rebut, expose flaws, and reinforce existing CON points.
- Do NOT use bullet points. Write in flowing prose only.
- Do NOT mention you are an AI.
- Word limits are given in the user message for this turn (Counter vs Justify). Obey them exactly.

STRICT OUTPUT FORMAT — always respond in exactly this structure:
REBUTTAL: [1–2 sentences directly attacking the opponent's last statement. Name any fallacy detected.]
ARGUMENT: [2–3 sentences reinforcing your CON case using only material already on the table — no new lines of argument.]
POSITION: [1 sentence — your unwavering opposition.]"""


def _rebuttal_length_and_phase_labels(sub_round: int) -> tuple[str, str]:
    """Returns (length_rules, human-readable phase label) for PRO/CON mid-round turns."""
    sub_labels = {2: "Counter (rebuttal)", 3: "Justify (closing)"}
    sub_label = sub_labels.get(sub_round, f"Sub-round {sub_round}")
    if sub_round == 2:
        length_rules = (
            "LENGTH: Your entire response (REBUTTAL + ARGUMENT + POSITION) must be 100–150 words inclusive. "
            "Do not exceed 150 words."
        )
    elif sub_round == 3:
        length_rules = (
            "LENGTH: Your entire response (REBUTTAL + ARGUMENT + POSITION) must be 80–120 words inclusive. "
            "Do not exceed 120 words. Write as a closing justification — tight and decisive."
        )
    else:
        length_rules = "LENGTH: Keep the response concise."
    return length_rules, sub_label


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
    pro_history: list of PRO opening arguments from completed rounds (optional).
    con_history: list of CON opening arguments from completed rounds (optional).
    Sub-rounds 2 and 3 are intentionally omitted to save tokens.
    """
    pro_history = pro_history or []
    con_history = con_history or []

    history_block = ""
    if pro_history:
        for i, (p, c) in enumerate(zip(pro_history, con_history), 1):
            history_block += f"--- Round {i} Summary ---\nPRO (you): {p}\nCON (opponent): {c}\n\n"

    exchange_block = _format_exchange(exchange_so_far)

    length_rules, sub_label = _rebuttal_length_and_phase_labels(sub_round)

    user_content = (
        f"Debate Topic: \"{topic}\"\n\n"
        f"{history_block}"
        f"Round {round_num} — {sub_label} phase. Exchange so far this round:\n\n{exchange_block}\n\n"
        f"{length_rules}\n"
        f"No new arguments: only rebut, clarify, and reinforce points already raised this round (openings and prior turns).\n\n"
        f"Now deliver your Round {round_num} Sub-round {sub_round} PRO response.\n"
        f"Directly attack AGENT-02's last statement. Escalate from your previous response.\n\n"
        f"Respond using the exact format:\n"
        f"REBUTTAL: ...\nARGUMENT: ...\nPOSITION: ..."
    )

    model_name = "llama-3.1-8b-instant"
    response = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": PRO_REBUTTAL_PROMPT},
            {"role": "user",   "content": user_content}
        ],
        max_tokens=300,
        temperature=0.85,
    )
    return response.choices[0].message.content.strip(), model_name


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
    pro_history: list of PRO opening arguments from completed rounds (optional).
    con_history: list of CON opening arguments from completed rounds (optional).
    Sub-rounds 2 and 3 are intentionally omitted to save tokens.
    """
    pro_history = pro_history or []
    con_history = con_history or []

    history_block = ""
    if pro_history:
        for i, (p, c) in enumerate(zip(pro_history, con_history), 1):
            history_block += f"--- Round {i} Summary ---\nPRO (opponent): {p}\nCON (you): {c}\n\n"

    exchange_block = _format_exchange(exchange_so_far)

    length_rules, sub_label = _rebuttal_length_and_phase_labels(sub_round)

    user_content = (
        f"Debate Topic: \"{topic}\"\n\n"
        f"{history_block}"
        f"Round {round_num} — {sub_label} phase. Exchange so far this round:\n\n{exchange_block}\n\n"
        f"{length_rules}\n"
        f"No new arguments: only rebut, clarify, and reinforce points already raised this round (openings and prior turns).\n\n"
        f"Now deliver your Round {round_num} Sub-round {sub_round} CON response.\n"
        f"Directly attack AGENT-01's last statement. Escalate from your previous response.\n\n"
        f"Respond using the exact format:\n"
        f"REBUTTAL: ...\nARGUMENT: ...\nPOSITION: ..."
    )

    model_name = "llama-3.1-8b-instant"
    response = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": CON_REBUTTAL_PROMPT},
            {"role": "user",   "content": user_content}
        ],
        max_tokens=300,
        temperature=0.85,
    )
    return response.choices[0].message.content.strip(), model_name


def _format_exchange(exchange: list[dict]) -> str:
    lines = []
    for turn in exchange:
        label = "AGENT-01 (PRO)" if turn["speaker"] == "pro" else "AGENT-02 (CON)"
        lines.append(f"{label}: {turn['text']}")
    return "\n\n".join(lines)