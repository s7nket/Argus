"""
Build the verification corpus from Wikipedia.

Coverage — the share of a debater's claims the corpus can rule on — is the
headline metric of the verification channel, and on the 11 hand-written seed
documents it sat at 0.25-0.50. That number was measuring corpus size, not
argument quality, and calibrating anything on top of it would measure noise.

This fetches plain-text extracts for the topics debates actually cover, splits
them into passages, and indexes them alongside the seed corpus. Wikipedia is the
right source for a first pass: free, no key, broad, and citable in a paper.

Usage:
    python -m debate.build_corpus                # default topic set
    python -m debate.build_corpus --topics a b   # specific articles
    python -m debate.build_corpus --stats        # report and exit
    python -m debate.build_corpus --reset        # drop indexed Wikipedia passages first

Idempotent: passages are keyed by content hash, so re-running adds only what is
new. The seed corpus is never touched.
"""

import argparse
import hashlib
import os
import re
import sys
import time

import httpx

import config
from debate.vector_store import get_vector_store

# Article titles and prose carry characters the default Windows console codepage
# cannot encode; without this a build dies partway on a stray accent.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "https://en.wikipedia.org/w/api.php"

# Wikimedia rejects requests whose User-Agent lacks a machine-readable contact.
# Prose does not satisfy it — "(academic project; contact via github.com/...)"
# returned 403 on every request, as does httpx's default and a bare "Mozilla/5.0".
# A bracketed URL is enough; an email is not required. Override WIKI_CONTACT if
# you fork this, so rate-limit complaints reach you rather than the original repo.
_CONTACT = os.getenv("WIKI_CONTACT", "https://github.com/s7nket/Argus")
HEADERS = {"User-Agent": f"ArgusBot/1.0 ({_CONTACT})"}

# Articles chosen to cover the resolution types the debaters are given: history
# comparisons, policy propositions, and science/technology questions.
DEFAULT_TOPICS = [
    # Classical history — the comparative topics already in use
    "Classical Athens", "Sparta", "Athenian democracy", "Peloponnesian War",
    "Battle of Thermopylae", "Battle of Salamis", "Cleisthenes", "Pericles",
    "Agoge", "Women in ancient Sparta", "Delian League", "Solon",
    # Policy propositions
    "Universal basic income", "Capital punishment", "Nuclear power",
    "Renewable energy", "Carbon tax", "Minimum wage", "Rent control",
    "Universal health care", "Drug liberalization", "Compulsory voting",
    "Gun control", "School voucher", "Four-day week",
    # Technology and AI
    "Artificial intelligence", "Regulation of artificial intelligence",
    "Artificial general intelligence", "Self-driving car", "Cryptocurrency",
    "Social media", "Net neutrality", "Genetically modified food",
    "Nuclear weapon", "Space exploration", "Animal testing",
    # Economics and society
    "Globalization", "Free trade", "Progressive tax", "Wealth inequality",
    "Remote work", "Standardized test", "Homework", "Public transport",
]

# ~180 words keeps a passage small enough that an entailment check is about one
# claim, and large enough to carry the context that makes it checkable.
TARGET_WORDS = 180
MIN_WORDS = 40

_WS = re.compile(r"\s+")
# Reference-only and navigational sections carry no verifiable prose.
_SKIP_SECTION = re.compile(
    r"^(references|external links|further reading|see also|notes|bibliography|"
    r"sources|citations|footnotes|gallery)\s*$",
    re.IGNORECASE,
)


def fetch_extract(client: httpx.Client, title: str) -> str | None:
    """Plain-text extract for one article, following redirects."""
    try:
        r = client.get(API, params={
            "action": "query", "prop": "extracts", "titles": title,
            "explaintext": "1", "redirects": "1", "format": "json",
        }, timeout=30.0)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        for pid, page in pages.items():
            if pid == "-1" or "extract" not in page:
                return None
            return page["extract"]
    except Exception as e:
        print(f"    fetch failed: {type(e).__name__}: {e}")
    return None


def search_titles(client: httpx.Client, query: str, limit: int = 3) -> list[str]:
    """Article titles matching a free-text query.

    The corpus is normally built from titles chosen by hand. A debate resolution
    is not a title — "We should ban factory farming" matches no article — so an
    evaluation over real debate topics needs this step to turn each resolution
    into something fetchable. Returns fewer than `limit` titles, or none, rather
    than guessing: an empty result means the corpus will not cover that debate,
    and it is better to know that before scoring than to discover it afterwards
    in a grounding coverage of zero.
    """
    try:
        r = client.get(API, params={
            "action": "query", "list": "search", "srsearch": query,
            "srlimit": limit, "srnamespace": "0", "format": "json",
        }, timeout=30.0)
        r.raise_for_status()
        return [h["title"] for h in r.json().get("query", {}).get("search", [])]
    except Exception as e:
        print(f"    search failed for {query[:50]!r}: {type(e).__name__}: {e}")
        return []


def split_passages(text: str, title: str) -> list[dict]:
    """
    Split an extract into passages, dropping reference and navigation sections.

    Wikipedia extracts mark sections with "== Heading ==". Paragraphs accumulate
    until the target size so a passage rarely splits mid-argument.
    """
    passages: list[dict] = []
    section = "Introduction"
    buf: list[str] = []
    words = 0

    def flush():
        nonlocal buf, words
        if words >= MIN_WORDS:
            passages.append({"text": _WS.sub(" ", " ".join(buf)).strip(), "section": section})
        buf, words = [], 0

    for block in text.split("\n"):
        block = block.strip()
        if not block:
            continue
        heading = re.match(r"^=+\s*(.+?)\s*=+$", block)
        if heading:
            flush()
            section = heading.group(1)
            continue
        if _SKIP_SECTION.match(section):
            continue
        n = len(block.split())
        if words + n > TARGET_WORDS and words >= MIN_WORDS:
            flush()
        buf.append(block)
        words += n

    flush()
    return passages


def passage_id(text: str) -> str:
    """Content hash — makes re-runs idempotent and drops duplicate prose."""
    return "wiki-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def build(topics: list[str], delay: float = 0.2) -> dict:
    vs = get_vector_store()
    if not vs.is_available:
        print("ChromaDB unavailable — nothing to do.")
        return {}

    existing = set()
    try:
        existing = set(vs.evidence_coll.get(include=[])["ids"])
    except Exception:
        pass
    print(f"corpus currently holds {len(existing)} documents\n")

    added = skipped = failed = 0
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for i, title in enumerate(topics, 1):
            print(f"[{i}/{len(topics)}] {title}")
            extract = fetch_extract(client, title)
            if not extract:
                print("    no extract")
                failed += 1
                continue

            passages = split_passages(extract, title)
            docs, metas, ids = [], [], []
            for p in passages:
                pid = passage_id(p["text"])
                if pid in existing or pid in ids:
                    skipped += 1
                    continue
                ids.append(pid)
                docs.append(p["text"])
                metas.append({
                    "topic": title,
                    "section": p["section"],
                    "source": f"Wikipedia: {title}",
                    "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    "category": "encyclopedia",
                    # The seed corpus assigns pro/con stances by hand. Retrieved
                    # reference prose is not written for a side, and labelling it
                    # would leak a stance into evidence meant to be neutral.
                    "stance": "neutral",
                })

            if docs:
                # Chroma embeds on add; batching keeps memory flat on a laptop.
                for s in range(0, len(docs), 64):
                    vs.add_evidence(documents=docs[s:s + 64], metadatas=metas[s:s + 64], ids=ids[s:s + 64])
                existing.update(ids)
                added += len(docs)
            print(f"    +{len(docs)} passages ({len(passages)} found)")
            time.sleep(delay)          # courtesy to Wikipedia

    return {"added": added, "skipped": skipped, "failed": failed, "total": len(existing)}


def stats() -> None:
    vs = get_vector_store()
    print(vs.get_stats())
    if not vs.is_available:
        return
    try:
        got = vs.evidence_coll.get(include=["metadatas"])
        by_cat: dict[str, int] = {}
        by_topic: dict[str, int] = {}
        for m in got["metadatas"]:
            by_cat[(m or {}).get("category", "?")] = by_cat.get((m or {}).get("category", "?"), 0) + 1
            by_topic[(m or {}).get("topic", "?")] = by_topic.get((m or {}).get("topic", "?"), 0) + 1
        print(f"\nby category: {by_cat}")
        print(f"topics indexed: {len(by_topic)}")
        for t, n in sorted(by_topic.items(), key=lambda kv: -kv[1])[:12]:
            print(f"  {n:>4}  {t}")
    except Exception as e:
        print(f"stats failed: {e}")


def reset_wikipedia() -> None:
    """Drop indexed Wikipedia passages, leaving the hand-written seed corpus."""
    vs = get_vector_store()
    if not vs.is_available:
        return
    got = vs.evidence_coll.get(include=[])
    ids = [i for i in got["ids"] if i.startswith("wiki-")]
    if ids:
        for s in range(0, len(ids), 256):
            vs.evidence_coll.delete(ids=ids[s:s + 256])
    print(f"removed {len(ids)} Wikipedia passages; seed corpus untouched")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build the ARGUS verification corpus from Wikipedia.")
    ap.add_argument("--topics", nargs="*", help="article titles (default: built-in set)")
    ap.add_argument("--stats", action="store_true", help="report corpus composition and exit")
    ap.add_argument("--reset", action="store_true", help="drop indexed Wikipedia passages first")
    ap.add_argument("--delay", type=float, default=0.2, help="seconds between requests")
    ap.add_argument("--search", action="store_true",
                    help="treat --topics as free-text queries (e.g. debate resolutions) "
                         "and index the best-matching articles instead of exact titles")
    ap.add_argument("--per-query", type=int, default=3,
                    help="articles to take per query when --search is used")
    ap.add_argument("--from-file",
                    help="read one query or title per line from this file "
                         "(use with `python -m eval.ddo --topics > topics.txt`)")
    args = ap.parse_args()

    if args.stats:
        stats()
        sys.exit(0)
    if args.reset:
        reset_wikipedia()

    requested = list(args.topics or [])
    if args.from_file:
        with open(args.from_file, encoding="utf-8") as fh:
            requested += [ln.strip() for ln in fh if ln.strip()]

    if args.search:
        if not requested:
            print("--search needs queries via --topics or --from-file")
            sys.exit(1)
        n_queries = len(requested)
        titles, missed = [], []
        with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
            for q in requested:
                hits = search_titles(client, q, args.per_query)
                if hits:
                    titles.extend(hits)
                else:
                    missed.append(q)
                time.sleep(args.delay)
        # Dedupe while keeping order, so repeated topics do not refetch.
        seen, requested = set(), []
        for t in titles:
            if t not in seen:
                seen.add(t)
                requested.append(t)
        print(f"resolved {len(requested)} unique articles from {n_queries} queries")
        if missed:
            print(f"NO MATCH for {len(missed)} quer(ies) — these debates will have no "
                  f"corpus support:")
            for q in missed[:10]:
                print(f"  - {q[:70]}")

    result = build(requested or DEFAULT_TOPICS, delay=args.delay)
    print(f"\n{result}")
    print("\nRe-run `python test_verifier.py` to see coverage against the larger corpus.")
