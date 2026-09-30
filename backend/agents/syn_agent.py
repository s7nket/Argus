import os
from dotenv import load_dotenv

from config import debater_model
from llm_retry import groq_call
from agents.debater_client import debater_client, DEBATER_PROVIDER

_here = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(os.path.dirname(_here), ".env"), override=True)

client = debater_client


def _system_prompt(pro_side: str, con_side: str, syn_side: str) -> str:
    return f"""You are AGENT-03 (ARGUS-SYN), an elite dialectical synthesizer and pragmatic systems debater in a 3-way multi-agent debate.

YOUR STANCE — you argue for exactly this, and nothing else:
{syn_side}

YOUR OPPONENTS ARGUE:
- AGENT-01 (PRO): {pro_side}
- AGENT-02 (CON): {con_side}

PERSONA: You are a rigorous, balanced, and evidence-driven systems thinker. You expose the false dilemma between PRO's pure affirmation and CON's pure negation. You present the superior third path, synthesis, or pragmatic alternative that reconciles the valid tensions and avoids the fatal drawbacks of both extremes.

RULES (OPENING phase only — sub-round 1):
- Always argue for YOUR STANCE as written above. Never concede to either opponent.
- Point out why neither AGENT-01 nor AGENT-02 provides a complete answer, then build the affirmative case for YOUR STANCE with concrete evidence.
- Cite verifiable specifics: named people, dates, places, events, numbers, laws, studies, named institutions.
- Never invent evidence. A fabricated citation is scored as a false claim.
- Do NOT mention you are an AI. Argue as a confident human debater.
- Do NOT use bullet points or lists. Write in flowing prose only.
- Opening length: your entire response MUST stay within 120–200 words (inclusive)."""


async def generate_syn_argument(
    topic: str,
    round_num: int,
    current_pro_argument: str,
    current_con_argument: str,
    pro_history: list[str],
    con_history: list[str],
    syn_history: list[str],
    pro_side: str | None = None,
    con_side: str | None = None,
    syn_side: str | None = None,
) -> tuple[str, str]:
    """
    Generate AGENT-03's opening argument in response to PRO and CON openings.
    """
    pro_side = pro_side or f"The proposition is true: {topic}"
    con_side = con_side or f"The proposition is false: {topic}"
    syn_side = syn_side or f"A balanced synthesis and pragmatic alternative resolves: {topic}"

    history_block = ""
    if syn_history:
        for i, (p, c, s) in enumerate(zip(pro_history, con_history, syn_history), 1):
            history_block += (
                f"--- Round {i} Summary ---\n"
                f"PRO: {p}\n"
                f"CON: {c}\n"
                f"SYN (you): {s}\n\n"
            )

    user_content = (
        f"Resolution: \"{topic}\"\n\n"
        f"You are arguing: {syn_side}\n\n"
        f"{history_block}"
        f"Round {round_num} AGENT-01 (PRO) opening:\n\"{current_pro_argument}\"\n\n"
        f"Round {round_num} AGENT-02 (CON) opening:\n\"{current_con_argument}\"\n\n"
        f"Generate your Round {round_num} Opening argument.\n"
        f"Critique the tunnel-vision of both AGENT-01 and AGENT-02, AND advance your own stance with concrete evidence.\n\n"
        f"STRICT OUTPUT FORMAT — respond in exactly this structure:\n"
        f"REBUTTAL: [1-2 sentences highlighting the shortcomings or extremes in what AGENT-01 and AGENT-02 just argued.]\n"
        f"ARGUMENT: [2-3 sentences making the positive case for YOUR stance with concrete, named evidence.]\n"
        f"POSITION: [1 sentence — your clear, unwavering stance.]"
    )

    model_name = debater_model("syn")
    response = await groq_call(client.chat.completions.create,
        model=model_name,
        messages=[
            {"role": "system", "content": _system_prompt(pro_side, con_side, syn_side)},
            {"role": "user",   "content": user_content}
        ],
        max_tokens=300,
        temperature=0.8,
    )
    return response.choices[0].message.content, model_name
