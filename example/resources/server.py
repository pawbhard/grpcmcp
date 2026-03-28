"""Resource example — gRPC MCP server exposing static notes as resources.

Run this server:
    uv run example/resources/server.py

Then run the matching client:
    uv run example/resources/client.py
"""

import asyncio

from mcp.server.mcpserver.server import MCPServer

from grpcmcp import serve_grpc

mcp = MCPServer("Resources Example Server")

NOTES: dict[str, str] = {
    "welcome": "Welcome to the gRPC MCP resource example!",
    "shopping": "Milk, eggs, bread, coffee",
    "ideas": "1. Build a gRPC MCP server\n2. Add resources\n3. ???\n4. Profit",
}


@mcp.resource("notes://list", name="notes_index", description="Index of all notes")
def notes_index() -> str:
    return "\n".join(f"{k}: {v[:40]}..." for k, v in NOTES.items())


@mcp.resource(
    "notes://{note_id}",
    name="note",
    description="A single note by ID",
    mime_type="text/plain",
)
def get_note(note_id: str) -> str:
    if note_id not in NOTES:
        raise ValueError(f"Note '{note_id}' not found. Available: {list(NOTES)}")
    return NOTES[note_id]


if __name__ == "__main__":
    asyncio.run(serve_grpc(mcp, enable_reflection=True))
