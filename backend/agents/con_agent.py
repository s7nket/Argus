import os
from dotenv import load_dotenv
from groq import AsyncGroq

load_dotenv()

client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"), timeout=20.0)

SYSTEM_PROMPT = """You are AGENT-02 (ARGUS-CON), an elite critical examiner debater. Your ONLY job is to argue STRONGLY AGAINST the given topic.

PERSONA: You are a sharp, analytical skeptic. You dismantle PRO claims by exposing faulty assumptions, missing evidence, and logical fallacies — you don't just assert the opposite, you surgically dismantle the case FOR.

RULES (OPENING phase only — sub-round 1):
- Always argue AGAINST the topic. Never concede. Never shift your core position.
- Directly target the most vulnerable claim in your opponent's last argument.
- Expose logical fallacies, unsupported assumptions, and overgeneralizations by name when detected (e.g. "This is a false dichotomy", "This is an appeal to authority").
- Introduce new angles and perspectives each round — do not repeat previous counter-arguments verbatim.
- Do NOT mention you are an AI. Argue as a confident human debater.
- Do NOT use bullet points or lists. Write in flowing prose only.
- Opening length: your entire response MUST stay within 120–200 words (inclusive). Do not exceed 200 words.

STRICT OUTPUT FORMAT — always respond in exactly this structure:
REBUTTAL: [1–2 sentences directly attacking the opponent's last argument. Name the flaw explicitly.]
ARGUMENT: [2–3 sentences reinforcing your CON position with a fresh counter-angle.]
POSITION: [1 sentence — your clear, unwavering opposition to the topic.]"""


async def generate_con_argument(
    topic: str,
    round_num: int,
    current_pro_argument: str,
    pro_history: list[str],
    con_history: list[str]
) -> str:
    """
    current_pro_argument: the PRO opening argument just generated for this round.
    pro_history: list of PRO opening arguments from completed rounds.
    con_history: list of CON opening arguments from completed rounds.
    Sub-rounds 2 and 3 are intentionally omitted to save tokens.
    """
    history_block = ""
    if pro_history:
        for i, (p, c) in enumerate(zip(pro_history, con_history), 1):
            history_block += f"--- Round {i} Summary ---\nPRO (opponent): {p}\nCON (you): {c}\n\n"

    user_content = (
        f"Debate Topic: \"{topic}\"\n\n"
        f"{history_block}"
        f"Round {round_num} PRO Opening (just delivered by AGENT-01):\n\"{current_pro_argument}\"\n\n"
        f"Generate your Round {round_num} Opening CON counter-argument.\n"
        f"Directly challenge the weakest point in what AGENT-01 just said.\n\n"
        f"Respond using the exact format:\n"
        f"REBUTTAL: ...\nARGUMENT: ...\nPOSITION: ..."
    )

    model_name = "llama-3.1-8b-instant"
    response = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_content}
        ],
        max_tokens=300,
        temperature=0.8,
    )
    text = response.choices[0].message.content
    return text.replace("REBUTTAL:", "").replace("ARGUMENT:", "").replace("POSITION:", "").strip(), model_name