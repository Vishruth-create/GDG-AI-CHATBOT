"""
brain.py — LLM interface with FastMCP Gmail tool support
"""

import json
import asyncio
import requests
from fastmcp import Client

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────

OLLAMA_BASE     = "http://localhost:11434"
OLLAMA_CHAT     = f"{OLLAMA_BASE}/api/chat"
OLLAMA_MODEL    = "huihui_ai/qwen3.5-abliterated:9b"
REQUEST_TIMEOUT = 90

MCP_SERVER_URL  = "http://localhost:8001/mcp"   # matches server.py


# ──────────────────────────────────────────────────────────────
# MCP helpers  (async, use the fastmcp Client your teammate wrote)
# ──────────────────────────────────────────────────────────────

async def _fetch_mcp_tools() -> list[dict]:
    """
    Ask the FastMCP server for its tool list and convert to Ollama format.

    FastMCP returns Tool objects with .name, .description, .inputSchema.
    Ollama expects: {"type": "function", "function": {name, description, parameters}}
    """
    async with Client(MCP_SERVER_URL) as client:
        mcp_tools = await client.list_tools()

    return [
        {
            "type": "function",
            "function": {
                "name":        t.name,
                "description": t.description or "",
                # inputSchema is already a valid JSON-Schema dict
                "parameters":  t.inputSchema or {"type": "object", "properties": {}},
            },
        }
        for t in mcp_tools
    ]


async def _call_mcp_tool(name: str, arguments: dict) -> str:
    async with Client(MCP_SERVER_URL) as client:
        result = await client.call_tool(name, arguments)

    # result is a CallToolResult — the iterable is result.content
    parts = []
    for block in result.content:              # ← .content is the list
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
    """Single POST to Ollama /api/chat. Returns raw response dict."""
    payload = {
        "model":   OLLAMA_MODEL,
        "messages": messages,
        "stream":  False,
        "options": {"temperature": 0.7, "num_predict": 512},
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
# Core response generator  (called from app.py — sync interface)
# ──────────────────────────────────────────────────────────────

def generate_response(
    messages:       list[dict],
    system_context: str | None = None,
) -> str:
    """
    Public interface — stays synchronous so app.py needs no changes.
    Internally runs the async MCP tool loop via asyncio.run().
    """
    return asyncio.run(_generate_response_async(messages, system_context))


async def _generate_response_async(
    messages:       list[dict],
    system_context: str | None = None,
) -> str:
    """
    Async core: loads MCP tools, sends to Ollama, executes any tool calls,
    loops until Ollama returns a plain text reply.
    """
    MAX_TOOL_ROUNDS = 5

    system = system_context or (
        "You are a helpful WhatsApp assistant for the Google Developer "
        "Students Group of IIT Indore. Be concise and friendly. "
        "You have access to Gmail tools — use them when the user asks "
        "about emails, inbox, sending mail, or Google Classroom."
    )

    # Build working message list (we append tool results to this as we loop)
    working_messages = [{"role": "system", "content": system}]
    for msg in messages:
        working_messages.append({"role": msg["role"], "content": msg["content"]})

    # Load tools from the FastMCP server once per request
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

        # ── No tool calls → Ollama gave us the final reply ────
        if not tool_calls:
            return message.get("content", "").strip()

        # ── Tool calls present → execute each, append results ─
        print(f"[brain] Round {round_num + 1}: Ollama called {len(tool_calls)} tool(s)")

        # Append assistant's tool-call turn to history
        working_messages.append({
            "role":       "assistant",
            "content":    message.get("content", ""),
            "tool_calls": tool_calls,
        })

        for call in tool_calls:
            fn        = call["function"]
            tool_name = fn["name"]
            tool_args = fn.get("arguments", {})

            # Ollama sometimes sends arguments as a JSON string
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

            # Append tool result so Ollama can see it in the next round
            working_messages.append({
                "role":    "tool",
                "name":    tool_name,
                "content": result_text,
            })

    return "I ran into trouble processing that. Please try rephrasing!"


# ──────────────────────────────────────────────────────────────
# Summarizer  (unchanged — no tools needed here)
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
