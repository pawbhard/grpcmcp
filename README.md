# gRPC Transport for MCP

> [!WARNING]
> **Experimental / Proof of Concept**
>
> This package is a Proof of Concept for experimentation purposes. It is not intended for production use.

This module provides a gRPC transport implementation for the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) using `GRPCDispatcher` and `GRPCClientDispatcher` — both integrate with MCP's session machinery via the `Dispatcher` protocol. Proto definitions are sourced from [mcp-grpc-transport-proto](https://github.com/GoogleCloudPlatform/mcp-grpc-transport-proto).

## Features

- Tool listing and calling over gRPC
- Full MCP session integration — tools that use `ctx: Context` receive a real request context
- Client-side dispatcher (`GRPCClientDispatcher`) composable with `ClientSession`
- Optional gRPC server reflection for use with tools like `grpcurl`

## Server usage

```python
import asyncio
from mcp.server.mcpserver.server import MCPServer
from grpcmcp import serve_grpc

mcp = MCPServer("My Server")

@mcp.tool()
async def my_tool(x: int) -> str:
    return str(x)

if __name__ == "__main__":
    asyncio.run(serve_grpc(mcp))
```

Enable server reflection (useful for `grpcurl` and other tooling):

```python
asyncio.run(serve_grpc(mcp, enable_reflection=True))
```

`serve_grpc` signature:

```python
async def serve_grpc(
    server: MCPServer,
    host: str = "0.0.0.0",
    port: int = 50051,
    enable_reflection: bool = False,
) -> None: ...
```

## Client usage

```python
import asyncio
from mcp.client.session import ClientSession
from grpcmcp import GRPCClientDispatcher

async def main():
    dispatcher = GRPCClientDispatcher("localhost", 50051)
    async with ClientSession(None, None, dispatcher=dispatcher) as session:
        tools = await session.list_tools()
        result = await session.call_tool("my_tool", {"x": 1})

asyncio.run(main())
```

## Running the examples

```bash
# Terminal 1 — start the server
uv run example/grpc_example_server.py

# Terminal 2 — run the client
uv run example/grpc_example_client.py
```

See [example/README.md](example/README.md) for testing with `grpcurl`.

## Requirements

- Python >= 3.10
- grpcio >= 1.78.0
- protobuf >= 5.26.1
- mcp (from [pawbhard/python-sdk](https://github.com/pawbhard/python-sdk), branch `extract-dispatcher-from-base-session`)
- mcp-transport-proto (from [GoogleCloudPlatform/mcp-grpc-transport-proto](https://github.com/GoogleCloudPlatform/mcp-grpc-transport-proto))
