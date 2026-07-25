import os
from dotenv import load_dotenv
from groq import AsyncGroq

from config import debater_model

load_dotenv()

client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"), timeout=20.0)


def _system_prompt(pro_side: str, con_side: str) -> str:
    """
    The stance is stated explicitly rather than as "argue FOR the topic".
    On a comparative topic ("Athens or Sparta?") "the topic" has no truth value,
    so the old wording left both agents arguing about only one of the two options.
    """
    return f"""You are AGENT-01 (ARGUS-PRO), an elite advocate debater.

YOUR STANCE — you argue for exactly this, and nothing else:
{pro_side}

YOUR OPPONENT ARGUES:
{con_side}

PERSONA: You are a confident, evidence-driven advocate. You build compelling cases using logic, real-world examples, and data — you don't just assert, you prove.

RULES (OPENING phase only — sub-round 1):
- Always argue for YOUR STANCE as written above. Never concede. Never shift your core position.
- Your case must address the comparison directly. Showing your opponent's option is flawed does NOT
  establish yours — you must make the positive case for your own side.
- Each round introduce a fresh angle — do not repeat previous arguments verbatim. Repeating a
  position more forcefully is not an argument and scores nothing.
- Cite verifiable specifics: named people, dates, places, events, numbers, laws, named works.
  Saying your case is "evidence-based" earns nothing — only named specifics count.
- Never invent evidence. Do not attribute claims to "the archaeological record", "studies" or
  "historians" unless you name the specific finding, work or person. A fabricated citation is
  scored as a false claim and costs you the round.
- Do NOT mention you are an AI. Argue as a confident human debater.
- Do NOT use bullet points or lists. Write in flowing prose only.
- Opening length: your entire response MUST stay within 120–200 words (inclusive)."""


OPENING_FORMAT_R1 = (
    "STRICT OUTPUT FORMAT — respond in exactly this structure:\n"
    "ARGUMENT: [3-4 sentences making your strongest opening case with concrete, named evidence.]\n"
    "POSITION: [1 sentence — your clear, unwavering stance.]"
)

OPENING_FORMAT_LATER = (
    "STRICT OUTPUT FORMAT — respond in exactly this structure:\n"
    "REBUTTAL: [1-2 sentences directly attacking the opponent's last argument.]\n"
    "ARGUMENT: [2-3 sentences making your strongest case with a fresh angle and concrete evidence.]\n"
    "POSITION: [1 sentence — your clear, unwavering stance.]"
)


async def generate_pro_argument(
    topic: str,
    round_num: int,
    pro_history: list[str],
    con_history: list[str],
    pro_side: str | None = None,
    con_side: str | None = None,
) -> str:
    pro_side = pro_side or f"The following is true: {topic}"
    con_side = con_side or f"The following is false: {topic}"

    history_block = ""
    if pro_history:
        for i, (p, c) in enumerate(zip(pro_history, con_history), 1):
            history_block += f"--- Round {i} Summary ---\nPRO (you): {p}\nCON (opponent): {c}\n\n"

    # Round 1 has nothing to rebut. Asking for REBUTTAL with an "N/A" escape made
    # the model emit 'N/A, as this is the PRO's opening argument in Round 2' —
    # meta-commentary that leaked into the UI. The field is simply absent instead.
    fmt = OPENING_FORMAT_R1 if round_num == 1 else OPENING_FORMAT_LATER

    user_content = (
        f"Resolution: \"{topic}\"\n\n"
        f"You are arguing: {pro_side}\n\n"
        f"{history_block}"
        f"Generate your Round {round_num} Opening argument.\n"
        f"{'This is the first round — make a strong opening case.' if round_num == 1 else 'Build on previous rounds with a fresh angle and new specifics.'}\n\n"
        f"{fmt}"
    )

    model_name = debater_model("pro")
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
