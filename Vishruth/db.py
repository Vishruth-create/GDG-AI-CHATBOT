"""
db.py — Supabase database layer for GDG WhatsApp AI Assistant

Matches the actual Supabase schema exactly:

    public.whatsapp_users   (id uuid PK, wa_id UNIQUE, display_name, phone_number, created_at, updated_at)
    public.messages          (id uuid PK, wa_id FK, wamid UNIQUE nullable, role, content, timestamp NOT NULL, metadata jsonb, created_at)
    public.long_term_memory  (id uuid PK, wa_id UNIQUE FK, summary, message_count, last_summarized_at, created_at)

Environment variables needed in .env:
    SUPABASE_URL=...
    SUPABASE_ANON_KEY=...
"""

import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────

SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str = os.environ["SUPABASE_ANON_KEY"]

SHORT_TERM_LIMIT: int = 3   # rolling context window size
SUMMARIZE_AFTER:  int = 10   # new messages since last summary before re-summarizing

_supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _now_iso() -> str:
    """Current UTC time as an ISO-8601 string — used wherever a timestamp is required."""
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────
# 1. Users  →  public.whatsapp_users
# ──────────────────────────────────────────────────────────────

def upsert_user(phone_number: str, name: str) -> dict:
    """
    Insert or update a user row in whatsapp_users.

    wa_id        — the WhatsApp phone number string (e.g. '919414001035')
    display_name — human-readable name from the WhatsApp contact profile
    phone_number — same value stored in the dedicated phone_number column

    Safe to call on every incoming message — fully idempotent.
    The updated_at trigger on the table handles the timestamp automatically.
    """
    payload = {
        "wa_id":        phone_number,
        "display_name": name,
        "phone_number": phone_number,   # whatsapp_users has a separate phone_number column
    }
    result = (
        _supabase
        .table("whatsapp_users")
        .upsert(payload, on_conflict="wa_id")   # wa_id has a UNIQUE constraint
        .execute()
    )
    return result.data[0] if result.data else {}


def get_user(phone_number: str) -> dict | None:
    """Fetch a single user row by wa_id, or None if not found."""
    result = (
        _supabase
        .table("whatsapp_users")
        .select("*")
        .eq("wa_id", phone_number)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


# ──────────────────────────────────────────────────────────────
# 2. Messages  →  public.messages
# ──────────────────────────────────────────────────────────────

def save_message(
    phone_number: str,
    role:         str,
    content:      str,
    wamid:        str | None = None,
    msg_type:     str = "text",
    metadata:     dict | None = None,
) -> dict:
    """
    Save one message to the messages table.

    IMPORTANT — timestamp is NOT NULL with no default in the schema,
    so we always supply it explicitly.

    Column mapping:
        wa_id     ← phone_number
        wamid     ← WhatsApp message ID (only present for inbound user messages)
        role      ← 'user' | 'assistant'  (enforced by DB CHECK constraint)
        content   ← message text
        timestamp ← current UTC time (required, no DB default)
        metadata  ← optional jsonb bag (replaces the old 'raw' column name)
                    stores {"type": msg_type} by default; pass extra info as needed

    Idempotency:
        User messages  → upsert on_conflict="wamid"  (duplicate WhatsApp IDs silently ignored)
        Bot replies    → plain insert (no wamid, no conflict key needed)
    """
    payload: dict = {
        "wa_id":     phone_number,
        "role":      role,
        "content":   content,
        "timestamp": _now_iso(),                    # required — no DB default
        "metadata":  metadata or {"type": msg_type},
    }

    if wamid is not None:
        payload["wamid"] = wamid
        # Silently ignore if this WhatsApp message ID was already stored
        result = (
            _supabase
            .table("messages")
            .upsert(payload, on_conflict="wamid")
            .execute()
        )
    else:
        # Bot replies have no wamid — plain insert
        result = (
            _supabase
            .table("messages")
            .insert(payload)
            .execute()
        )

    return result.data[0] if result.data else {}


def get_recent_messages(phone_number: str, limit: int = SHORT_TERM_LIMIT) -> list[dict]:
    """
    Fetch the most recent `limit` messages for a user in chronological order
    (oldest first — correct direction for an LLM messages array).

    The composite index on (wa_id, timestamp DESC) makes this fast.
    Returns [] for unknown users — never raises.
    """
    result = (
        _supabase
        .table("messages")
        .select("role, content, timestamp")
        .eq("wa_id", phone_number)
        .order("timestamp", desc=True)   # newest first so LIMIT captures the right tail
        .limit(limit)
        .execute()
    )
    messages = result.data or []
    messages.reverse()   # flip to chronological (oldest → newest) for the LLM
    return messages


def get_message_count(phone_number: str) -> int:
    """Total number of stored messages (user + assistant) for this user."""
    result = (
        _supabase
        .table("messages")
        .select("id", count="exact")
        .eq("wa_id", phone_number)
        .execute()
    )
    return result.count or 0


def delete_all_messages(phone_number: str) -> None:
    """Hard-delete all messages for a user. Useful for test teardown."""
    _supabase.table("messages").delete().eq("wa_id", phone_number).execute()


# ──────────────────────────────────────────────────────────────
# 3. Long-Term Memory  →  public.long_term_memory
# ──────────────────────────────────────────────────────────────

def get_long_term_memory(phone_number: str) -> dict | None:
    """
    Fetch the stored long-term summary for a user.
    Returns None if no summary has been generated yet.
    """
    result = (
        _supabase
        .table("long_term_memory")
        .select("*")
        .eq("wa_id", phone_number)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def upsert_long_term_memory(phone_number: str, summary: str, message_count: int) -> dict:
    """
    Insert or overwrite the long-term summary for a user.

    IMPORTANT — the PK in long_term_memory is `id` (uuid), but the UNIQUE
    constraint is on `wa_id`. Supabase upsert must target the UNIQUE column
    (wa_id), NOT the PK, otherwise it will always insert a new row.
    """
    payload = {
        "wa_id":              phone_number,
        "summary":            summary,
        "message_count":      message_count,
        "last_summarized_at": _now_iso(),
    }
    result = (
        _supabase
        .table("long_term_memory")
        .upsert(payload, on_conflict="wa_id")   # wa_id is UNIQUE but NOT the PK
        .execute()
    )
    return result.data[0] if result.data else {}


# ──────────────────────────────────────────────────────────────
# 4. Context Builder
# ──────────────────────────────────────────────────────────────

def build_llm_context(phone_number: str) -> dict:
    """
    Assemble the full context object that app.py passes to the LLM.

    Returns:
        {
            "system_context":       str,   — system prompt (includes summary if available)
            "messages":             list,  — [{role, content, timestamp}, ...] oldest-first
            "has_long_term_memory": bool,
        }
    """
    memory   = get_long_term_memory(phone_number)
    messages = get_recent_messages(phone_number, limit=SHORT_TERM_LIMIT)

    if memory:
        system_context = (
            "You are a helpful WhatsApp assistant for the Google Developer "
            "Students Group of IIT Indore.\n\n"
            "What you know about this user from past conversations:\n"
            f"{memory['summary']}"
        )
        has_long_term_memory = True
    else:
        system_context = (
            "You are a helpful WhatsApp assistant for the Google Developer "
            "Students Group of IIT Indore."
        )
        has_long_term_memory = False

    return {
        "system_context":       system_context,
        "messages":             messages,
        "has_long_term_memory": has_long_term_memory,
    }


# ──────────────────────────────────────────────────────────────
# 5. Memory Management
# ──────────────────────────────────────────────────────────────

def maybe_update_long_term_memory(phone_number: str, summarizer_fn) -> dict:
    """
    Decide whether to re-summarize and, if so, do it.

    Logic:
      1. Count total messages for this user.
      2. Look up how many messages existed at the last summarization.
      3. If delta < SUMMARIZE_AFTER (10), skip.
      4. Otherwise: pull full history → call summarizer_fn → store new summary.

    Args:
        phone_number:  wa_id of the user
        summarizer_fn: callable(history_text: str) -> str
                       In production: brain.summarize_conversation
                       In tests: any mock that accepts a string and returns a string

    Returns:
        {"skipped": True,  "reason": str}
        {"skipped": False, "summary": str, "message_count": int}
    """
    total_count           = get_message_count(phone_number)
    memory                = get_long_term_memory(phone_number)
    last_summarized_count = memory["message_count"] if memory else 0

    new_since_last = total_count - last_summarized_count

    if new_since_last < SUMMARIZE_AFTER:
        return {
            "skipped": True,
            "reason": (
                f"Only {new_since_last} new messages since last summary "
                f"(threshold: {SUMMARIZE_AFTER})"
            ),
        }

    # Fetch a broad window for the summarizer
    messages     = get_recent_messages(phone_number, limit=200)
    history_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )

    summary = summarizer_fn(history_text)
    upsert_long_term_memory(phone_number, summary, total_count)

    print(
        f"[db] Long-term memory updated for {phone_number} "
        f"({total_count} total, {new_since_last} new since last summary)"
    )

    return {
        "skipped":       False,
        "summary":       summary,
        "message_count": total_count,
    }