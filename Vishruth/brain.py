"""
brain.py — LLM interface for GDG WhatsApp AI Assistant

Replaces the original single-shot brain.py with a context-aware version
that accepts conversation history and a system prompt (long-term memory).

Uses the local Ollama /api/chat endpoint (NOT /api/generate) because
/api/chat supports multi-turn message arrays natively.

Model: llama3.1  (change OLLAMA_MODEL below if needed)
"""

import json
import requests

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────

OLLAMA_BASE   = "http://localhost:11434"
OLLAMA_CHAT   = f"{OLLAMA_BASE}/api/chat"
OLLAMA_MODEL  = "llama3.1"          # swap to "llama3", "mistral", etc. as needed
REQUEST_TIMEOUT = 90                # seconds — increase for slow hardware


# ──────────────────────────────────────────────────────────────
# Core response generator
# ──────────────────────────────────────────────────────────────

def generate_response(
    messages: list[dict],
    system_context: str | None = None,
) -> str:
    """
    Generate an AI reply using the local Ollama /api/chat endpoint.

    Args:
        messages:       Full conversation in chronological order.
                        Each item: {"role": "user"|"assistant", "content": str}
                        This list is produced by db.build_llm_context() and
                        already includes the user's latest message as the
                        final entry — do NOT add it again.

        system_context: System prompt string. When long-term memory exists
                        this contains the compressed user summary.
                        When None, a sensible default is used.

    Returns:
        The LLM's reply as a plain string.
    """
    system = system_context or (
        "You are a helpful WhatsApp assistant for the Google Developer "
        "Students Group of IIT Indore. Be concise — WhatsApp messages "
        "should be short and friendly, not like essays."
    )

    # Ollama chat format: system message first, then the history
    ollama_messages = [{"role": "system", "content": system}]
    for msg in messages:
        ollama_messages.append({
            "role":    msg["role"],      # 'user' | 'assistant'
            "content": msg["content"],
        })

    payload = {
        "model":    OLLAMA_MODEL,
        "messages": ollama_messages,
        "stream":   False,
        "options": {
            "temperature": 0.7,
            "num_predict": 512,    # max tokens in reply
        },
    }

    try:
        resp = requests.post(
            OLLAMA_CHAT,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()

    except requests.exceptions.Timeout:
        print("[brain] Ollama request timed out")
        return "Sorry, I'm thinking too hard right now — please try again in a moment!"

    except requests.exceptions.ConnectionError:
        print("[brain] Could not connect to Ollama. Is it running on port 11434?")
        return "My brain is offline right now. Please try again shortly!"

    except Exception as e:
        print(f"[brain] Unexpected error calling Ollama: {e}")
        return "Something went wrong on my end. Please try again!"


# ──────────────────────────────────────────────────────────────
# Summarizer  (used by db.maybe_update_long_term_memory)
# ──────────────────────────────────────────────────────────────

def summarize_conversation(history_text: str) -> str:
    """
    Compress a full conversation transcript into a concise user profile.
    This is passed as the `summarizer_fn` argument to
    db.maybe_update_long_term_memory().

    Args:
        history_text: Plain-text transcript produced by db.py, e.g.:
                      "USER: Hello\\nASSISTANT: Hi!\\n..."

    Returns:
        A short summary string (≤ 150 words) describing the user.
    """
    ollama_messages = [
        {
            "role": "system",
            "content": (
                "You are a conversation analyst. Your job is to read a "
                "WhatsApp chat history and produce a concise user profile "
                "that will help a future AI assistant give more relevant "
                "replies. Focus on: interests, expertise level, recurring "
                "topics, communication style, and any personal details "
                "the user has shared. Maximum 150 words. Plain text only, "
                "no bullet points."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Here is the conversation history:\n\n{history_text}\n\n"
                "Now write the user profile summary."
            ),
        },
    ]

    payload = {
        "model":    OLLAMA_MODEL,
        "messages": ollama_messages,
        "stream":   False,
        "options": {
            "temperature": 0.3,    # lower temp → more deterministic summaries
            "num_predict": 256,
        },
    }

    try:
        resp = requests.post(
            OLLAMA_CHAT,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT * 2,   # summarization needs more time
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()

    except Exception as e:
        print(f"[brain] Summarizer error: {e}")
        return "User has had a conversation. Interests and preferences are still being established."
