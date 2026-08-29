"""
Topic parsing.

A debate topic is not always a single proposition. "Ancient Athens or Sparta:
which was the better place to live?" is comparative — CON's job is to DEFEND
SPARTA, not to attack Athens. The old code passed the raw topic string to both
agents with "argue AGAINST the topic", so CON attacked Athens, nobody argued
for Sparta, and half the resolution silently disappeared from the debate.

This module resolves a topic into two explicit stances before any agent runs.
"""

import json
import os
import re

from dotenv import load_dotenv
from groq import AsyncGroq
from llm_retry import groq_call

load_dotenv()

PARSER_MODEL = os.getenv("PARSER_MODEL", "llama-3.3-70b-versatile")

_client = AsyncGroq(
    api_key=os.getenv("JUDGE_GROQ_API_KEY") or os.getenv("GROQ_API_KEY"),
    timeout=20.0,
)

TOPIC_PARSER_PROMPT = """You split a debate topic into the two stances that will actually be argued.

A topic is COMPARATIVE if it asks which of two named alternatives is better/worse/preferable
("X or Y: which is better?", "X vs Y", "Is X or Y the stronger choice?").
For comparative topics the second debater must ARGUE FOR the second alternative — not merely
attack the first. Attacking X is not the same as defending Y.

A topic is a PROPOSITION if it asserts one claim to be affirmed or denied
("Remote work is better than office work", "AI should be regulated").

Return ONLY valid JSON, no markdown:
{
  "type": "comparative" | "proposition",
  "pro_side": "the full stance the first debater must argue, as a complete sentence",
  "con_side": "the full stance the second debater must argue, as a complete sentence",
  "resolution": "the question being settled, as a single clear sentence"
}

Each stance must be self-contained: a debater reading only their own stance must know exactly
what to argue without seeing the original topic."""


def _fallback(topic: str) -> dict:
    """Regex split for comparative topics when the LLM parse is unavailable."""
    stripped = topic.strip()
    body = re.split(r"[:?]", stripped, maxsplit=1)[0].strip()
    m = re.match(r"^\s*(.+?)\s+(?:or|vs\.?|versus)\s+(.+?)\s*$", body, flags=re.IGNORECASE)
    if m:
        a, b = m.group(1).strip(), m.group(2).strip()
        return {
            "type": "comparative",
            "pro_side": f"{a} is the better answer to: {stripped}",
            "con_side": f"{b} is the better answer to: {stripped}",
            "resolution": stripped,
        }
    return {
        "type": "proposition",
        "pro_side": f"The following is true: {stripped}",
        "con_side": f"The following is false: {stripped}",
        "resolution": stripped,
    }


async def parse_topic(topic: str) -> dict:
    """Resolve a raw topic string into explicit PRO and CON stances."""
    try:
        response = await groq_call(_client.chat.completions.create,
            model=PARSER_MODEL,
            messages=[
                {"role": "system", "content": TOPIC_PARSER_PROMPT},
                {"role": "user", "content": f'Topic: "{topic}"\n\nReturn ONLY the JSON object.'},
            ],
            max_tokens=1000,
            temperature=0,
        )
        raw = response.choices[0].message.content
        raw = raw.replace("```json", "").replace("```", "").strip()
        start, end = raw.find("{"), raw.rfind("}")
        parsed = json.loads(raw[start:end + 1])

        if parsed.get("pro_side") and parsed.get("con_side"):
            parsed.setdefault("type", "proposition")
            parsed.setdefault("resolution", topic)
            return parsed
    except Exception as e:
        print(f"Topic parse failed, using regex fallback: {e}")

    return _fallback(topic)
