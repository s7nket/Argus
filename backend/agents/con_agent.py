import os
from dotenv import load_dotenv
from groq import AsyncGroq

from config import debater_model

load_dotenv()

client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"), timeout=20.0)


def _system_prompt(pro_side: str, con_side: str) -> str:
    """
    CON now receives a positive stance to defend, not just "argue AGAINST the topic".
    Under the old wording, on "Athens or Sparta?" CON spent the whole debate attacking
    Athens and never once argued for Sparta — the resolution was never actually contested.
    """
    return f"""You are AGENT-02 (ARGUS-CON), an elite critical examiner debater.

YOUR STANCE — you argue for exactly this, and nothing else:
{con_side}

YOUR OPPONENT ARGUES:
{pro_side}

PERSONA: You are a sharp, analytical skeptic. You dismantle your opponent's claims by exposing faulty assumptions, missing evidence, and logical fallacies — but dismantling their case is only half your job.

RULES (OPENING phase only — sub-round 1):
- Always argue for YOUR STANCE as written above. Never concede. Never shift your core position.
- CRITICAL: attacking your opponent's side does NOT establish yours. Every response must also make
  the positive case for YOUR STANCE with its own evidence. A round spent only attacking is a round
  where you argued for nothing, and it will be scored as such.
- Directly target the most vulnerable claim in your opponent's last argument.
- Name a logical fallacy ONLY when the label genuinely fits, and quote the words it applies to.
  Naming fallacies earns no credit by itself — a misapplied label is a reasoning error and will
  LOWER your score. When in doubt, explain the flaw in plain words instead of labelling it.
- Introduce new angles each round — do not repeat previous counter-arguments verbatim. Restating
  your position more forcefully is not an argument and scores nothing.
- Cite verifiable specifics: named people, dates, places, events, numbers, laws, named works.
  Describing your own case as "evidence-based" or "nuanced" earns nothing — only named specifics count.
- Never invent evidence. Do not attribute claims to "studies", "the record" or "historians" without
  naming the specific finding, work or person. A fabricated citation is scored as a false claim.
- Do NOT mention you are an AI. Argue as a confident human debater.
- Do NOT use bullet points or lists. Write in flowing prose only.
- Opening length: your entire response MUST stay within 120–200 words (inclusive)."""


async def generate_con_argument(
    topic: str,
    round_num: int,
    current_pro_argument: str,
    pro_history: list[str],
    con_history: list[str],
    pro_side: str | None = None,
    con_side: str | None = None,
) -> str:
    """
    current_pro_argument: the PRO opening argument just generated for this round.
    pro_history / con_history: opening arguments from completed rounds.
    """
    pro_side = pro_side or f"The following is true: {topic}"
    con_side = con_side or f"The following is false: {topic}"

    history_block = ""
    if pro_history:
        for i, (p, c) in enumerate(zip(pro_history, con_history), 1):
            history_block += f"--- Round {i} Summary ---\nPRO (opponent): {p}\nCON (you): {c}\n\n"

    user_content = (
        f"Resolution: \"{topic}\"\n\n"
        f"You are arguing: {con_side}\n\n"
        f"{history_block}"
        f"Round {round_num} opposing opening (just delivered by AGENT-01):\n\"{current_pro_argument}\"\n\n"
        f"Generate your Round {round_num} Opening counter-argument.\n"
        f"Challenge the weakest point in what AGENT-01 just said, AND advance your own stance with its own evidence.\n\n"
        f"STRICT OUTPUT FORMAT — respond in exactly this structure:\n"
        f"REBUTTAL: [1-2 sentences directly attacking the opponent's last argument. Name the flaw only if the label truly fits.]\n"
        f"ARGUMENT: [2-3 sentences making the positive case for YOUR stance with concrete, named evidence.]\n"
        f"POSITION: [1 sentence — your clear, unwavering stance.]"
    )

    model_name = debater_model("con")
    response = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": _system_prompt(pro_side, con_side)},
            {"role": "user",   "content": user_content}
        ],
        max_tokens=300,
        temperature=0.8,
    )
    return response.choices[0].message.content, model_name
