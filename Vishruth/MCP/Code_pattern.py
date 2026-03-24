import asyncio
from langchain_ollama import ChatOllama
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

async def main():
    mcp_client = MultiServerMCPClient({
        "filesystem": {
            "command": "/Volumes/MacSSD/miniforge3/envs/gdg-ai/bin/python",
            "args": ["MCP/fileserver.py"],
            "transport": "stdio",
        }
    })

    tools = await mcp_client.get_tools()
    print("Tools loaded:", [t.name for t in tools])

    llm = ChatOllama(model = "qwen3:8b")
    agent = create_react_agent(llm, tools)

    response = await agent.ainvoke({
        "messages": [{"role": "user", "content": "List the files in /Volumes/MacSSD"}]
    })

    print(response["messages"][-1].content)

asyncio.run(main())