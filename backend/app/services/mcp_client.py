import asyncio
import logging
import os
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]


class MCPToolError(Exception):
    pass


def _client() -> MultiServerMCPClient:
    return MultiServerMCPClient({
        "nikosh": {
            "transport": "stdio",
            "command": sys.executable,
            "args": ["-m", "app.mcp_server.server"],
            "cwd": str(BACKEND_DIR),
            "env": dict(os.environ),
        }
    })


def _as_text(result) -> str:
    if isinstance(result, list):
        return "".join(part.get("text", "") for part in result if isinstance(part, dict))
    return str(result)


async def _call(name: str, args: dict) -> str:
    tools = await _client().get_tools()
    tool = next((t for t in tools if t.name == name), None)
    if tool is None:
        raise MCPToolError(f"MCP tool not found: {name}")
    return _as_text(await tool.ainvoke(args))


def call_tool(name: str, **args) -> str:
    """Call a tool on the nikosh-tools MCP server and return its text result."""
    try:
        result = asyncio.run(_call(name, args))
    except MCPToolError:
        raise
    except Exception as exc:
        logger.error("MCP tool %s failed: %s", name, exc)
        raise MCPToolError(str(exc)) from None
    logger.info("MCP tool %s succeeded", name)
    return result