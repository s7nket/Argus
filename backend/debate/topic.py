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

PARSER_MODEL = os.getenv("PARSER_MODEL", "openai/gpt-oss-20b")

_client = AsyncGroq(
    api_key=os.getenv("JUDGE_GROQ_API_KEY") or os.getenv("GROQ_API_KEY"),
    timeout=20.0,
)

TOPIC_PARSER_PROMPT = """You split a debate topic into three distinct stances that will be argued by three separate debaters in a 3-way multi-agent debate.

Debater 1 (PRO): Argues the affirmative, thesis, or first alternative.
Debater 2 (CON): Argues the negative, antithesis, or second alternative.
Debater 3 (SYN): Argues a distinct third perspective — such as a pragmatic synthesis, nuanced compromise, or independent alternative that resolves the core tension without adopting either extreme.

Return ONLY valid JSON, no markdown:
{
  "type": "tri-way",
  "pro_side": "the full stance the first debater (PRO) must argue, as a complete sentence",
  "con_side": "the full stance the second debater (CON) must argue, as a complete sentence",
  "syn_side": "the full stance the third debater (SYN) must argue, as a complete sentence",
  "resolution": "the question or proposition being settled, as a single clear sentence"
}

Each stance must be self-contained: a debater reading only their own stance must know exactly what to argue without seeing the original topic."""


def _fallback(topic: str) -> dict:
    """Fallback split when the LLM parse is unavailable."""
    stripped = topic.strip()
    body = re.split(r"[:?]", stripped, maxsplit=1)[0].strip()
    m = re.match(r"^\s*(.+?)\s+(?:or|vs\.?|versus)\s+(.+?)\s*$", body, flags=re.IGNORECASE)
    if m:
        a, b = m.group(1).strip(), m.group(2).strip()
        return {
            "type": "tri-way",
            "pro_side": f"{a} is the superior choice regarding: {stripped}",
            "con_side": f"{b} is the superior choice regarding: {stripped}",
            "syn_side": f"A balanced integration combining elements of both {a} and {b} offers the optimal solution for: {stripped}",
            "resolution": stripped,
        }
    return {
        "type": "tri-way",
        "pro_side": f"The proposition is sound and essential: {stripped}",
        "con_side": f"The proposition is fundamentally flawed or counterproductive: {stripped}",
        "syn_side": f"A conditional, hybrid approach with targeted safeguards provides the pragmatic path for: {stripped}",
        "resolution": stripped,
    }


async def parse_topic(topic: str) -> dict:
    """Resolve a raw topic string into explicit PRO, CON, and SYN stances."""
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
            parsed.setdefault("type", "tri-way")
            parsed.setdefault("resolution", topic)
            if not parsed.get("syn_side"):
                parsed["syn_side"] = f"A nuanced synthesis balancing the valid concerns of both sides provides the best framework for: {topic}"
            return parsed
    except Exception as e:
        print(f"Topic parse failed, using fallback: {e}")

    return _fallback(topic)
