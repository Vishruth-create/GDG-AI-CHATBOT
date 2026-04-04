import os
import asyncio
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient
from openai import OpenAI
from elevenlabs.client import ElevenLabs
from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage

load_dotenv()

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    groq_api_key=os.getenv("GROQ_API_KEY")
)

MCP_CONFIG = {
    "gmail": {
        "transport": "stdio",
        "command": "python",
        "args": ["server.py"]
    },
    "classroom": {
        "transport": "stdio",
        "command": "python",
        "args": ["classroom.py"]
    }
}

async def process_message(user_id: str, text: str) -> str:
    """Handles multi-turn tool calling for complex requests."""

    client = MultiServerMCPClient(MCP_CONFIG)
    tools = await client.get_tools()

    if not tools:
        return "Error: Could not load any tools from MCP servers."

    print(f"DEBUG: Loaded {len(tools)} tools: {[t.name for t in tools]}")

    tool_map={tool.name: tool for tool in tools}

    llm_with_tools = llm.bind_tools(tools)

    messages = [
        SystemMessage(content=(
            "You are a precise personal assistant with access to Gmail and Google Classroom. "
            "When you need data, call the appropriate tool immediately — no filler text before tool calls. "
            "After receiving tool results, summarize them clearly for the user."
        )),
        HumanMessage(content=text)
    ]

    for step in range(5):
        print(f"DEBUG: ReAct step {step + 1}")
        response = await llm_with_tools.ainvoke(messages)

        if not response.tool_calls:
            print(f"DEBUG: Final answer reached at step {step + 1}")
            return response.content

        messages.append(response)

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            print(f"DEBUG: Calling tool '{tool_name}' with args: {tool_args}")

            try:
                # FIX: Invoke the tool object directly instead of client.call_tool()
                tool = tool_map.get(tool_name)
                if tool is None:
                    raise ValueError(f"Tool '{tool_name}' not found in tool_map")

                result = await tool.ainvoke(tool_args)
                result_text = str(result)

                print(f"DEBUG: Tool result (first 300 chars): {result_text[:300]}")

                messages.append(ToolMessage(
                    content=result_text,
                    tool_call_id=tool_call["id"]
                ))
            except Exception as e:
                print(f"DEBUG: Tool '{tool_name}' failed: {e}")
                messages.append(ToolMessage(
                    content=f"Tool error: {str(e)}",
                    tool_call_id=tool_call["id"]
                ))

    return "I'm sorry, I couldn't complete that request within the allowed steps."


def speech_to_text(file_path: str) -> str:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    with open(file_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file
        )
    return transcript.text


def text_to_speech(text: str, file_path: str) -> str:
    client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
    audio_generator = client.generate(
        text=text,
        voice="Adam",
        model="eleven_multilingual_v2"
    )
    with open(file_path, "wb") as f:
        for chunk in audio_generator:
            f.write(chunk)
    return file_path

