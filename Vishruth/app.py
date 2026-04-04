"""
app.py — GDG WhatsApp AI Assistant (Flask entry point)

Full 8-step pipeline on every incoming message:

  1. Parse      — extract sender info and message text from the webhook
  2. User Sync  — upsert the user into Supabase
  3. Save Input — store the incoming message in the messages table
  4. Context    — fetch long-term summary + last 15 short-term messages
  5. LLM        — call local Ollama with the full context
  6. Save Output— store the bot reply in the messages table
  7. Reply      — send the reply via the WhatsApp Cloud API
  8. Memory     — (background thread) check threshold; re-summarize if needed

Threading contract (important):
  Meta's webhook requires a 200 OK within ~20 s or it will retry.
  We return 200 immediately in the Flask route and hand off all
  database + LLM work to a daemon thread so we never block.
  That daemon thread is a plain synchronous function — no asyncio needed,
  because supabase-py and requests are both synchronous libraries.

  If you integrate an MCP/asyncio pipeline inside generate_response,
  replace the direct brain.generate_response() call with:
      import asyncio
      reply = asyncio.run(your_async_mcp_function(messages, system_context))
  inside handle_message_pipeline(). The rest of the file stays the same.

Environment variables needed (.env):
  SUPABASE_URL=...
  SUPABASE_ANON_KEY=...
  WA_PHONE_NUMBER_ID=917780508094662
  WA_ACCESS_TOKEN=EAAUq...
  VERIFY_TOKEN=GDG_AI_2026_CHATBOT
"""

import os
import threading
from flask import Flask, request, jsonify
from dotenv import load_dotenv

import db
from brain import generate_response, summarize_conversation
from send import send_message

load_dotenv()

# ──────────────────────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────────────────────

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "GDG_AI_2026_CHATBOT")


# ──────────────────────────────────────────────────────────────
# Webhook parsing
# ──────────────────────────────────────────────────────────────

def parse_whatsapp_webhook(data: dict) -> dict | None:
    """
    Extract the relevant fields from a WhatsApp Cloud API webhook payload.

    Returns a dict with keys:
        phone_number, sender_name, message_text, wamid, msg_type, raw_value
    Returns None if the payload is not a text message event (e.g. status update).

    Mirrors the JS parseWhatsAppWebhook() function from parser.js.
    """
    try:
        value = data["entry"][0]["changes"][0]["value"]
    except (KeyError, IndexError, TypeError):
        return None

    # Status updates, reactions, etc. — no "messages" key
    if "messages" not in value:
        return None

    message = value["messages"][0]
    contact = value["contacts"][0]

    # Only handle text messages for now
    if message.get("type") != "text":
        print(f"[webhook] Skipping non-text message type: {message.get('type')}")
        return None

    return {
        "phone_number": message["from"],
        "sender_name":  contact["profile"]["name"],
        "message_text": message["text"]["body"],
        "wamid":        message["id"],
        "msg_type":     message["type"],
        "raw_value":    value,
    }


# ──────────────────────────────────────────────────────────────
# The full 8-step pipeline (runs in a background daemon thread)
# ──────────────────────────────────────────────────────────────

def handle_message_pipeline(
    phone_number: str,
    sender_name:  str,
    message_text: str,
    wamid:        str,
    raw_value:    dict,
) -> None:
    """
    Executes the complete message-handling pipeline sequentially.
    This function is always called from a daemon Thread, never from
    the Flask route directly, so it can take as long as it needs.

    Steps 1 (parsing) already happened in the route handler.
    """

    # ── Step 2: User Sync ──────────────────────────────────────
    try:
        db.upsert_user(phone_number, sender_name)
    except Exception as e:
        print(f"[pipeline] upsert_user failed for {phone_number}: {e}")
        return  # can't proceed without a valid user row


    # ── Step 3: Save incoming user message ────────────────────
    try:
        db.save_message(
            phone_number=phone_number,
            role="user",
            content=message_text,
            wamid=wamid,
            msg_type="text",
            metadata={"type": "text", "raw": raw_value},
        )
    except Exception as e:
        print(f"[pipeline] save_message (user) failed: {e}")
        # Non-fatal: continue — we can still generate and send a reply


    # ── Step 4: Build LLM context ─────────────────────────────
    try:
        context = db.build_llm_context(phone_number)
        #   context = {
        #       "system_context":       str,
        #       "messages":             [{role, content, timestamp}, ...],
        #       "has_long_term_memory": bool,
        #   }
    except Exception as e:
        print(f"[pipeline] build_llm_context failed: {e}")
        context = {
            "system_context": (
                "You are a helpful WhatsApp assistant for the Google Developer "
                "Students Group of IIT Indore."
            ),
            "messages": [{"role": "user", "content": message_text}],
            "has_long_term_memory": False,
        }

    # The context already includes the message we just saved as the last entry,
    # so we pass the full messages list directly to the LLM.
    print(
        f"[pipeline] Context for {sender_name} ({phone_number}): "
        f"{len(context['messages'])} messages, "
        f"long-term={'yes' if context['has_long_term_memory'] else 'no'}"
    )


    # ── Step 5: Generate LLM response ─────────────────────────
    # ┌─────────────────────────────────────────────────────────┐
    # │  MCP / asyncio hook                                     │
    # │  If you have an async MCP pipeline, replace the call    │
    # │  below with:                                            │
    # │                                                         │
    # │      import asyncio                                     │
    # │      reply = asyncio.run(                               │
    # │          your_mcp_pipeline(                             │
    # │              messages=context["messages"],              │
    # │              system_context=context["system_context"],  │
    # │          )                                              │
    # │      )                                                  │
    # │                                                         │
    # │  Everything else in this function stays exactly the     │
    # │  same — asyncio.run() is safe inside a daemon thread.   │
    # └─────────────────────────────────────────────────────────┘
    try:
        reply = generate_response(
            messages=context["messages"],
            system_context=context["system_context"],
        )
    except Exception as e:
        print(f"[pipeline] generate_response failed: {e}")
        reply = "Sorry, I couldn't generate a response right now. Please try again!"


    # ── Step 6: Save bot reply ────────────────────────────────
    try:
        db.save_message(
            phone_number=phone_number,
            role="assistant",
            content=reply,
        )
    except Exception as e:
        print(f"[pipeline] save_message (assistant) failed: {e}")


    # ── Step 7: Send WhatsApp reply ───────────────────────────
    try:
        send_message(phone_number, reply)
        print(f"[pipeline] Reply sent to {sender_name} ({phone_number}): {reply[:60]}...")
    except Exception as e:
        print(f"[pipeline] send_message failed: {e}")


    # ── Step 8: Background memory management ──────────────────
    # Fire-and-forget in its own daemon thread so we don't hold up anything.
    # If the threshold is not met, this returns almost instantly.
    def _update_memory():
        try:
            result = db.maybe_update_long_term_memory(
                phone_number,
                summarize_conversation,    # brain.py's Ollama-powered summarizer
            )
            if not result["skipped"]:
                print(
                    f"[memory] Updated long-term memory for {phone_number} "
                    f"({result['message_count']} total messages)"
                )
            else:
                print(f"[memory] Skipped for {phone_number}: {result['reason']}")
        except Exception as e:
            print(f"[memory] Error updating memory for {phone_number}: {e}")

    memory_thread = threading.Thread(target=_update_memory, daemon=True)
    memory_thread.start()


# ──────────────────────────────────────────────────────────────
# Flask routes
# ──────────────────────────────────────────────────────────────

@app.route("/webhooks", methods=["GET", "POST"])
def whatsapp():

    # ── Webhook verification (GET) ────────────────────────────
    if request.method == "GET":
        mode               = request.args.get("hub.mode")
        verification_token = request.args.get("hub.verify_token")
        challenge          = request.args.get("hub.challenge")

        if mode == "subscribe" and verification_token == VERIFY_TOKEN:
            print("[webhook] Verification successful")
            return challenge, 200

        print(f"[webhook] Verification failed — token mismatch")
        return "Verification Failed", 403


    # ── Incoming message (POST) ───────────────────────────────
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "ok"}), 200

    print(f"[webhook] Received payload: {data}")

    # ── Step 1: Parse ─────────────────────────────────────────
    parsed = parse_whatsapp_webhook(data)

    if parsed is None:
        # Status update, reaction, or unsupported type — acknowledge and ignore
        return jsonify({"status": "ok"}), 200

    # ── Spawn background thread and return 200 immediately ────
    # Meta requires a 200 within ~20 s. All heavy work happens
    # inside handle_message_pipeline() on a daemon thread.
    pipeline_thread = threading.Thread(
        target=handle_message_pipeline,
        kwargs={
            "phone_number": parsed["phone_number"],
            "sender_name":  parsed["sender_name"],
            "message_text": parsed["message_text"],
            "wamid":        parsed["wamid"],
            "raw_value":    parsed["raw_value"],
        },
        daemon=True,
    )
    pipeline_thread.start()

    return jsonify({"status": "ok"}), 200


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Starting GDG WhatsApp AI Assistant...")
    print(f"  Ollama model : {os.getenv('OLLAMA_MODEL', 'llama3.1')}")
    print(f"  Supabase URL : {os.getenv('SUPABASE_URL', '(not set)')[:40]}...")
    app.run(debug=True, port=8000, use_reloader=False)
    # use_reloader=False prevents Flask from spawning a second process
    # which can cause duplicate daemon threads in development.
