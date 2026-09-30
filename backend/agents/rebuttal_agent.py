import os
from dotenv import load_dotenv
from groq import AsyncGroq

from config import debater_model
from llm_retry import groq_call

load_dotenv()

client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"), timeout=20.0)


def _pro_rebuttal_prompt(pro_side: str, con_side: str, syn_side: str | None = None) -> str:
    syn_clause = f"\n- AGENT-03 (SYN): {syn_side}" if syn_side else ""
    return f"""You are AGENT-01 (ARGUS-PRO), an elite advocate debater.

YOUR STANCE — you argue for exactly this, and nothing else:
{pro_side}

YOUR OPPONENTS ARGUE:
- AGENT-02 (CON): {con_side}{syn_clause}

PERSONA: Confident, evidence-driven advocate. You build on your opening — you don't restart.

RULES:
- Always argue for YOUR STANCE. Never concede.
- You are mid-round. The full exchange so far is given to you. Counter the opponents' statements directly.
- Escalate precision each sub-round, not volume. Sharpen the reasoning; do not simply assert harder.
- No new arguments: do not introduce claims, examples, statistics or lines of reasoning that were not
  already raised in this round's opening exchange or in your own prior turns this round. Only rebut,
  clarify, tighten and synthesise existing points.
- Do NOT repeat previous wording verbatim; rephrase and deepen the same underlying points. Reused
  phrasing is detected and penalised.
- Never invent evidence to strengthen a point mid-round. A fabricated citation costs you the round.
- Do NOT use bullet points. Write in flowing prose only.
- Do NOT mention you are an AI.
- Word limits are given in the user message for this turn (Counter vs Justify). Obey them exactly.

STRICT OUTPUT FORMAT — always respond in exactly this structure:
REBUTTAL: [1-2 sentences directly attacking the opponents' last statements.]
ARGUMENT: [2-3 sentences reinforcing your case using only material already on the table.]
POSITION: [1 sentence — your unwavering stance.]"""


def _con_rebuttal_prompt(pro_side: str, con_side: str, syn_side: str | None = None) -> str:
    syn_clause = f"\n- AGENT-03 (SYN): {syn_side}" if syn_side else ""
    return f"""You are AGENT-02 (ARGUS-CON), an elite critical examiner debater.

YOUR STANCE — you argue for exactly this, and nothing else:
{con_side}

YOUR OPPONENTS ARGUE:
- AGENT-01 (PRO): {pro_side}{syn_clause}

PERSONA: Sharp, analytical skeptic. You dismantle your opponents' reasoning surgically — but exposing their flaws does not by itself establish your own stance.

RULES:
- Always argue for YOUR STANCE. Never concede.
- You are mid-round. The full exchange so far is given to you. Counter the opponents' statements directly.
- Escalate precision each sub-round, not volume. Sharpen the reasoning; do not simply assert harder.
- Name a logical fallacy ONLY when the label genuinely fits, and quote the words it applies to.
  Naming fallacies earns no credit by itself — a misapplied label is a reasoning error that LOWERS
  your score. When in doubt, explain the flaw in plain words instead of labelling it.
- No new arguments: do not introduce claims, examples or counter-lines that were not already raised
  in this round's opening exchange or your own prior turns this round.
- Do NOT repeat previous wording verbatim; rephrase and deepen the same underlying points. Reused
  phrasing is detected and penalised.
- Never invent evidence to strengthen a point mid-round. A fabricated citation costs you the round.
- Do NOT use bullet points. Write in flowing prose only.
- Do NOT mention you are an AI.
- Word limits are given in the user message for this turn (Counter vs Justify). Obey them exactly.

STRICT OUTPUT FORMAT — always respond in exactly this structure:
REBUTTAL: [1-2 sentences directly attacking the opponents' last statements. Name a fallacy only if it truly fits.]
ARGUMENT: [2-3 sentences reinforcing your stance using only material already on the table.]
POSITION: [1 sentence — your unwavering stance.]"""


def _syn_rebuttal_prompt(pro_side: str, con_side: str, syn_side: str) -> str:
    return f"""You are AGENT-03 (ARGUS-SYN), an elite dialectical synthesizer in a 3-way debate.

YOUR STANCE — you argue for exactly this, and nothing else:
{syn_side}

YOUR OPPONENTS ARGUE:
- AGENT-01 (PRO): {pro_side}
- AGENT-02 (CON): {con_side}

PERSONA: Pragmatic, dialectical systems debater. You demonstrate that AGENT-01 and AGENT-02 are trapped in an unproductive binary conflict, and show how your third perspective resolves the core contradictions.

RULES:
- Always argue for YOUR STANCE. Never concede.
- Directly critique both AGENT-01 and AGENT-02's most recent counter-arguments.
- Escalate precision each sub-round, not volume. Sharpen the synthesis; do not simply assert harder.
- No new arguments: only rebut, clarify, and reinforce material already raised in this round.
- Do NOT repeat previous wording verbatim; deepen the synthesis.
- Never invent evidence. A fabricated citation costs you the round.
- Do NOT use bullet points. Write in flowing prose only.
- Do NOT mention you are an AI.
- Obey the word limits in the prompt.

STRICT OUTPUT FORMAT — always respond in exactly this structure:
REBUTTAL: [1-2 sentences directly countering both AGENT-01 and AGENT-02's claims.]
ARGUMENT: [2-3 sentences reinforcing why the synthesis/alternative stance is superior.]
POSITION: [1 sentence — your unwavering stance.]"""


def _rebuttal_length_and_phase_labels(sub_round: int) -> tuple[str, str]:
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


def _format_exchange(exchange: list[dict]) -> str:
    lines = []
    speaker_map = {"pro": "AGENT-01 (PRO)", "con": "AGENT-02 (CON)", "syn": "AGENT-03 (SYN)"}
    for turn in exchange:
        label = speaker_map.get(turn.get("speaker"), turn.get("speaker", "AGENT").upper())
        lines.append(f"{label}: {turn.get('text', '')}")
    return "\n\n".join(lines)


def _history_block(pro_history: list[str] = None, con_history: list[str] = None, syn_history: list[str] = None, speaker: str = "pro") -> str:
    block = ""
    pro_h = pro_history or []
    con_h = con_history or []
    syn_h = syn_history or []
    for i in range(max(len(pro_h), len(con_h), len(syn_h))):
        p = pro_h[i] if i < len(pro_h) else ""
        c = con_h[i] if i < len(con_h) else ""
        s = syn_h[i] if i < len(syn_h) else ""
        block += f"--- Round {i+1} Summary ---\n"
        if p: block += f"PRO: {p}\n"
        if c: block += f"CON: {c}\n"
        if s: block += f"SYN: {s}\n"
        block += "\n"
    return block


def _build_user_content(
    topic: str,
    side_stance: str,
    round_num: int,
    sub_round: int,
    exchange_so_far: list[dict],
    history_block: str,
    speaker: str,
) -> str:
    length_rules, sub_label = _rebuttal_length_and_phase_labels(sub_round)
    opponents = {
        "pro": "AGENT-02 (CON) and AGENT-03 (SYN)",
        "con": "AGENT-01 (PRO) and AGENT-03 (SYN)",
        "syn": "AGENT-01 (PRO) and AGENT-02 (CON)",
    }.get(speaker, "your opponents")

    return (
        f"Resolution: \"{topic}\"\n\n"
        f"You are arguing: {side_stance}\n\n"
        f"{history_block}"
        f"Round {round_num} — {sub_label} phase. Exchange so far this round:\n\n"
        f"{_format_exchange(exchange_so_far)}\n\n"
        f"{length_rules}\n"
        f"No new arguments: only rebut, clarify, and reinforce points already raised this round.\n\n"
        f"Now deliver your Round {round_num} Sub-round {sub_round} response.\n"
        f"Directly counter {opponents}. Sharpen — do not restate.\n\n"
        f"Respond using the exact format:\n"
        f"REBUTTAL: ...\nARGUMENT: ...\nPOSITION: ..."
    )


async def generate_pro_rebuttal(
    topic: str,
    round_num: int,
    sub_round: int,
    exchange_so_far: list[dict],
    pro_history: list[str] = None,
    con_history: list[str] = None,
    syn_history: list[str] = None,
    pro_side: str | None = None,
    con_side: str | None = None,
    syn_side: str | None = None,
) -> tuple[str, str]:
    """Generates PRO's counter/justify response in sub-round 2 or 3."""
    pro_side = pro_side or f"The proposition is true: {topic}"
    con_side = con_side or f"The proposition is false: {topic}"

    user_content = _build_user_content(
        topic, pro_side, round_num, sub_round, exchange_so_far,
        _history_block(pro_history, con_history, syn_history, "pro"), "pro",
    )

    model_name = debater_model("pro")
    response = await groq_call(client.chat.completions.create,
        model=model_name,
        messages=[
            {"role": "system", "content": _pro_rebuttal_prompt(pro_side, con_side, syn_side)},
            {"role": "user",   "content": user_content}
        ],
        max_tokens=300,
        temperature=0.85,
    )
    return response.choices[0].message.content, model_name


async def generate_con_rebuttal(
    topic: str,
    round_num: int,
    sub_round: int,
    exchange_so_far: list[dict],
    pro_history: list[str] = None,
    con_history: list[str] = None,
    syn_history: list[str] = None,
    pro_side: str | None = None,
    con_side: str | None = None,
    syn_side: str | None = None,
) -> tuple[str, str]:
    """Generates CON's counter/justify response in sub-round 2 or 3."""
    pro_side = pro_side or f"The proposition is true: {topic}"
    con_side = con_side or f"The proposition is false: {topic}"

    user_content = _build_user_content(
        topic, con_side, round_num, sub_round, exchange_so_far,
        _history_block(pro_history, con_history, syn_history, "con"), "con",
    )

    model_name = debater_model("con")
    response = await groq_call(client.chat.completions.create,
        model=model_name,
        messages=[
            {"role": "system", "content": _con_rebuttal_prompt(pro_side, con_side, syn_side)},
            {"role": "user",   "content": user_content}
        ],
        max_tokens=300,
        temperature=0.85,
    )
    return response.choices[0].message.content, model_name


async def generate_syn_rebuttal(
    topic: str,
    round_num: int,
    sub_round: int,
    exchange_so_far: list[dict],
    pro_history: list[str] = None,
    con_history: list[str] = None,
    syn_history: list[str] = None,
    pro_side: str | None = None,
    con_side: str | None = None,
    syn_side: str | None = None,
) -> tuple[str, str]:
    """Generates SYN's counter/justify response in sub-round 2 or 3."""
    pro_side = pro_side or f"The proposition is true: {topic}"
    con_side = con_side or f"The proposition is false: {topic}"
    syn_side = syn_side or f"A balanced synthesis resolves: {topic}"

    user_content = _build_user_content(
        topic, syn_side, round_num, sub_round, exchange_so_far,
        _history_block(pro_history, con_history, syn_history, "syn"), "syn",
    )

    model_name = debater_model("syn")
    response = await groq_call(client.chat.completions.create,
        model=model_name,
        messages=[
            {"role": "system", "content": _syn_rebuttal_prompt(pro_side, con_side, syn_side)},
            {"role": "user",   "content": user_content}
        ],
        max_tokens=300,
        temperature=0.85,
    )
    return response.choices[0].message.content, model_name
