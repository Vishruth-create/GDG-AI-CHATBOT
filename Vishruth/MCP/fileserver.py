from mcp.server.fastmcp import FastMCP
import os

mcp = FastMCP("filesystem")

@mcp.tool()
def list_files(directory: str) -> list[str]:
    """List all files in a given directory"""
    return os.listdir(directory)

@mcp.tool()
def read_file(filepath: str) -> str:
    """Read the contents of a file"""
    with open(filepath, "r") as f:
        return f.read()

if __name__ == "__main__":
    mcp.run()