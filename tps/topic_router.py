from __future__ import annotations

import logging
import re

from tps.db import Database

log = logging.getLogger(__name__)

# Short conversational replies that always continue the active topic.
_FOLLOW_UP = re.compile(
    r"^(yes|no|ok|okay|sure|continue|go on|do it|do that|why|explain|"
    r"show me|tell me more|what else|go ahead|exactly|correct|right|"
    r"please|thanks|thank you|yep|nope|agreed|makes sense|sounds good|"
    r"perfect|can you|could you|how about|what about)[.?!,]*$",
    re.IGNORECASE,
)

# Explicit "switch / work on <topic>" command.
_SWITCH_RE = re.compile(
    r"^(?:please\s+|hey\s+)?(?:can you\s+|could you\s+)?(?:now\s+|then\s+)?"
    r"(?:let'?s\s+)?(?:work on|switch to|move to|go to|change to|focus on|"
    r"continue with|resume|open|go back to)\s+"
    r"(?:the\s+)?(?:existing\s+)?(?:this\s+)?(?:topic\s+)?(.+)$",
    re.IGNORECASE,
)

# Explicit "create a new topic [called X]" command.
_CREATE_RE = re.compile(
    r"^(?:please\s+)?(?:can you\s+|could you\s+)?"
    r"(?:create|start|open|make|begin|add)\s+(?:a\s+)?(?:new\s+)?topic"
    r"(?:\s+(?:called|named|for|about|titled|:)\s+(.+))?[.?!]*$",
    re.IGNORECASE,
)


def route_prompt(db: Database, partner_id: str, session: dict,
                 prompt: str) -> dict:
    """Decide which topic a prompt belongs to.

    Policy: the user drives topic selection. TPS never creates or switches a
    topic on its own — it either continues the active topic or asks the user.

    Returns a dict with:
      decision   — continue | use_existing | create | confirm
      topic_id   — target topic for continue/use_existing (else None)
      title      — proposed title for create (else None)
      routed_by  — how the decision was reached
      confidence — 0..1
      reason     — (confirm only) why we're asking
      candidates — (confirm only) topics to offer the user
    """
    active_id = session.get("active_topic_id")
    stripped = prompt.strip()

    # 1. Explicit user commands win — this *is* the user's verification.
    switch = _SWITCH_RE.match(stripped)
    if switch:
        target = _clean_target(switch.group(1))
        if target:
            match = _find_topic(db, partner_id, target)
            if match:
                return {
                    "decision": "use_existing",
                    "topic_id": match["id"],
                    "title": match["title"],
                    "routed_by": "command",
                    "confidence": 0.95,
                }
            # Named a topic we don't have — ask before creating it.
            return _confirm(db, partner_id, active_id,
                            reason="switch_no_match", proposed_title=target)

    create = _CREATE_RE.match(stripped)
    if create:
        title = _clean_target(create.group(1) or "")
        if title:
            return {
                "decision": "create",
                "topic_id": None,
                "title": title,
                "routed_by": "command",
                "confidence": 0.95,
            }
        # "create a new topic" with no name — ask for one.
        return _confirm(db, partner_id, active_id, reason="create_needs_name")

    # 2. Short conversational follow-up stays on the active topic.
    if active_id and _is_follow_up(stripped):
        return _continue(active_id)

    # 3. A topic is active → keep logging there. TPS does not switch on its own.
    if active_id:
        return _continue(active_id)

    # 4. No active topic yet → do NOT create silently. Ask the user which topic.
    return _confirm(db, partner_id, active_id, reason="no_active_topic",
                    proposed_title=_derive_title(stripped))


def _continue(active_id: str) -> dict:
    return {
        "decision": "continue",
        "topic_id": active_id,
        "title": None,
        "routed_by": "active",
        "confidence": 0.9,
    }


def _confirm(db: Database, partner_id: str, active_id: str | None,
             reason: str, proposed_title: str | None = None) -> dict:
    return {
        "decision": "confirm",
        "topic_id": None,
        "title": proposed_title,
        "routed_by": "deterministic",
        "confidence": 0.5,
        "reason": reason,
        "candidates": _recent_open_topics(db, partner_id, active_id),
    }


def _is_follow_up(prompt: str) -> bool:
    if _FOLLOW_UP.match(prompt):
        return True
    words = prompt.split()
    # Very short, non-question replies are conversational follow-ups.
    if len(words) <= 3 and "?" not in prompt:
        return True
    return False


def _clean_target(text: str) -> str:
    """Normalise the topic name captured from a command."""
    t = text.strip().strip("\"'“”").strip()
    t = re.sub(r"[.?!]+$", "", t).strip()
    # Drop leading filler the regex may have left behind.
    t = re.sub(r"^(the|this|that|my|our)\s+", "", t, flags=re.IGNORECASE).strip()
    return t


def _find_topic(db: Database, partner_id: str, target: str) -> dict | None:
    """Best existing-topic match for an explicit switch command, or None."""
    try:
        rows = db.search_topics_fts(partner_id, target, limit=3)
    except Exception:
        log.exception("FTS search failed")
        rows = []
    if rows:
        best = rows[0]
        # FTS5 bm25 rank is negative; MORE negative = better. Real matches for a
        # named topic land around -5..-7; false hits are ~-1..-2. Require a
        # clearly strong match so an explicit switch never lands on the wrong one.
        if best.get("rank", 0) <= -3.0:
            return best
    # Fall back to a case-insensitive substring match on the title.
    tl = target.lower()
    for t in db.list_topics(partner_id):
        if tl in t["title"].lower() or t["title"].lower() in tl:
            return t
    return None


def _recent_open_topics(db: Database, partner_id: str,
                        active_id: str | None, limit: int = 8) -> list[dict]:
    """Recent non-resolved topics to offer the user, active one first."""
    out: list[dict] = []
    seen: set[str] = set()
    if active_id:
        a = db.get_topic(active_id)
        if a:
            out.append({"id": a["id"], "title": a["title"],
                        "status": a.get("status", "open")})
            seen.add(a["id"])
    for t in db.list_topics(partner_id):
        if t["id"] in seen or t.get("status") == "resolved":
            continue
        out.append({"id": t["id"], "title": t["title"],
                    "status": t.get("status", "open")})
        if len(out) >= limit:
            break
    return out


def _derive_title(prompt: str) -> str:
    # First sentence or first 80 chars, whichever is shorter
    title = prompt.split("\n")[0].strip()
    for sep in ".!?":
        if sep in title:
            title = title[:title.index(sep) + 1]
            break
    if len(title) > 80:
        title = title[:77] + "..."
    return title or "Untitled topic"
