import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent

load_dotenv()

print(f"DEBUG: Key found? {os.getenv('GROQ_API_KEY') is not None}")

llm = ChatGroq(
    model="llama-3.3-70b-versatile", 
    groq_api_key=os.getenv("GROQ_API_KEY") 
)

async def process_message(user_id: str, text: str)->str:
    """Connects to MCP server, runs the agent, and returns a reply."""

    client = MultiServerMCPClient(
        {
        "gmail": {
            "transport": "stdio",
            "command": "python",
            "args": ["server.py"]
            }
        
        "classroom":{
            "transport": "stdio",
            "command": "python,"
            "args": ["classroom.py"]
            }
        }
    )
    
    tools = await client.get_tools()

    agent = create_agent(llm, tools)

    inputs = {"messages": [("user", text)]}
    result = await agent.ainvoke(inputs)

    return result["messages"][-1].content
