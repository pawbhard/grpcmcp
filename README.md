# gRPC Transport for MCP

> [!WARNING]
> **Experimental / Proof of Concept**
>
> This package is a Proof of Concept for experimentation purposes. It is not intended for production use.

This module provides a gRPC transport implementation for the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) using a custom `GRPCDispatcher` that integrates with MCP's `ServerSession` machinery. Proto definitions are sourced from [mcp-grpc-transport-proto](https://github.com/GoogleCloudPlatform/mcp-grpc-transport-proto).

## Features

- Tool listing and calling over gRPC
- Full MCP session integration via `GRPCDispatcher` — tools that use `ctx: Context` receive a real request context
- Optional gRPC server reflection for use with tools like `grpcurl`

## Usage

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

Run the example server:

```bash
uv run example/grpc_example_server.py
```

See [example/README.md](example/README.md) for testing with `grpcurl`.

## Requirements

- Python >= 3.10
- grpcio >= 1.78.0
- protobuf >= 5.26.1
- mcp (from [pawbhard/python-sdk](https://github.com/pawbhard/python-sdk), branch `extract-dispatcher-from-base-session`)
- mcp-transport-proto (from [GoogleCloudPlatform/mcp-grpc-transport-proto](https://github.com/GoogleCloudPlatform/mcp-grpc-transport-proto))
