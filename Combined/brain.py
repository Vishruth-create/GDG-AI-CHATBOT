"""
brain.py — LLM interface with FastMCP Gmail tool support
"""

import json
import asyncio
import requests
from fastmcp import Client
from send import send_document
import base64

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────

OLLAMA_BASE     = "http://localhost:11434"
OLLAMA_CHAT     = f"{OLLAMA_BASE}/api/chat"
OLLAMA_MODEL    = "huihui_ai/qwen3.5-abliterated:9b"
REQUEST_TIMEOUT = 90

MCP_SERVER_URL  = "http://localhost:8001/mcp"


# ──────────────────────────────────────────────────────────────
# MCP helpers
# ──────────────────────────────────────────────────────────────

async def _fetch_mcp_tools() -> list[dict]:
    async with Client(MCP_SERVER_URL) as client:
        mcp_tools = await client.list_tools()

    return [
        {
            "type": "function",
            "function": {
                "name":        t.name,
                "description": t.description or "",
                "parameters":  t.inputSchema or {"type": "object", "properties": {}},
            },
        }
        for t in mcp_tools
    ]


async def _call_mcp_tool(name: str, arguments: dict) -> str:
    async with Client(MCP_SERVER_URL) as client:
        result = await client.call_tool(name, arguments)

    parts = []
    for block in result.content:
        if hasattr(block, "text"):
            parts.append(block.text)
        else:
            parts.append(
                json.dumps(block.model_dump())
                if hasattr(block, "model_dump")
                else str(block)
            )
    return "\n".join(parts) or "(no output)"


# ──────────────────────────────────────────────────────────────
# Low-level Ollama call
# ──────────────────────────────────────────────────────────────

def _ollama_chat(messages: list[dict], tools: list[dict] | None = None) -> dict:
    payload = {
        "model":    OLLAMA_MODEL,
        "messages": messages,
        "stream":   False,
        "options":  {"temperature": 0.7, "num_predict": 512},
    }
    if tools:
        payload["tools"] = tools

    resp = requests.post(
        OLLAMA_CHAT,
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


# ──────────────────────────────────────────────────────────────
# Core response generator  (sync interface for app.py)
# ──────────────────────────────────────────────────────────────

def generate_response(
    messages:       list[dict],
    system_context: str | None = None,
    phone_number:   str | None = None,
) -> str:
    return asyncio.run(_generate_response_async(messages, system_context, phone_number))


async def _generate_response_async(
    messages:       list[dict],
    system_context: str | None = None,
    phone_number:   str | None = None,
) -> str:
    MAX_TOOL_ROUNDS = 5

    system = system_context or (
        "You are a helpful WhatsApp assistant for the Google Developer "
        "Students Group of IIT Indore. Be concise and friendly. "
        "You have access to Gmail tools — use them when the user asks "
        "about emails, inbox, sending mail, or Google Classroom."
    )

    # ── Build the working message list ────────────────────────
    working_messages = [{"role": "system", "content": system}]
    for msg in messages:
        working_messages.append({"role": msg["role"], "content": msg["content"]})

    # ── Load MCP tools once per request ───────────────────────
    tools = []
    try:
        tools = await _fetch_mcp_tools()
        print(f"[brain] Loaded {len(tools)} MCP tools: {[t['function']['name'] for t in tools]}")
    except Exception as e:
        print(f"[brain] Could not load MCP tools (continuing without them): {e}")

    # ── Agentic loop ──────────────────────────────────────────
    for round_num in range(MAX_TOOL_ROUNDS):
        try:
            raw = _ollama_chat(working_messages, tools=tools or None)
        except requests.exceptions.Timeout:
            return "Sorry, I'm thinking too hard — please try again in a moment!"
        except requests.exceptions.ConnectionError:
            return "My brain is offline right now. Please try again shortly!"
        except Exception as e:
            print(f"[brain] Ollama error: {e}")
            return "Something went wrong on my end. Please try again!"

        message    = raw.get("message", {})
        tool_calls = message.get("tool_calls", [])

        # ── No tool calls → final reply ───────────────────────
        if not tool_calls:
            return message.get("content", "").strip()

        # ── Tool calls → execute each, append results ─────────
        print(f"[brain] Round {round_num + 1}: Ollama called {len(tool_calls)} tool(s)")

        working_messages.append({
            "role":       "assistant",
            "content":    message.get("content", ""),
            "tool_calls": tool_calls,
        })

        for call in tool_calls:
            fn        = call["function"]
            tool_name = fn["name"]
            tool_args = fn.get("arguments", {})

            if isinstance(tool_args, str):
                try:
                    tool_args = json.loads(tool_args)
                except json.JSONDecodeError:
                    tool_args = {}

            print(f"[brain] → Calling MCP tool: {tool_name}({tool_args})")
            try:
                result_text = await _call_mcp_tool(tool_name, tool_args)
            except Exception as e:
                result_text = f"Tool error: {e}"
            print(f"[brain] ← Tool result: {result_text[:120]}...")

            # ── Detect attachment results and forward to WhatsApp
            if tool_name == "gmail_sent_attachments_to_whatsapp" and phone_number:
                try:
                    att_payload  = json.loads(result_text)
                    attachments  = att_payload.get("attachments", [])
                    for att in attachments:
                        file_bytes = base64.b64decode(att["data_b64"])
                        send_document(phone_number, file_bytes, att["filename"], att["mime_type"])
                    result_text = (
                        f"Sent {len(attachments)} attachment(s) to WhatsApp: "
                        + ", ".join(a["filename"] for a in attachments)
                    ) if attachments else "No attachments found."
                except Exception as e:
                    print(f"[brain] Attachment forwarding error: {e}")

            working_messages.append({
                "role":    "tool",
                "name":    tool_name,
                "content": result_text,
            })

    return "I ran into trouble processing that. Please try rephrasing!"


# ──────────────────────────────────────────────────────────────
# Summarizer
# ──────────────────────────────────────────────────────────────

def summarize_conversation(history_text: str) -> str:
    ollama_messages = [
        {
            "role": "system",
            "content": (
                "You are a conversation analyst. Produce a concise user profile "
                "from the chat history. Focus on interests, expertise, recurring "
                "topics, communication style, personal details. Max 150 words. "
                "Plain text only, no bullet points."
            ),
        },
        {
            "role": "user",
            "content": f"Conversation history:\n\n{history_text}\n\nWrite the user profile summary.",
        },
    ]
    payload = {
        "model":    OLLAMA_MODEL,
        "messages": ollama_messages,
        "stream":   False,
        "options":  {"temperature": 0.3, "num_predict": 256},
    }
    try:
        resp = requests.post(
            OLLAMA_CHAT,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT * 2,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()
    except Exception as e:
        print(f"[brain] Summarizer error: {e}")
        return "User has had a conversation. Interests and preferences are still being established."