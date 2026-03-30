# gRPC Transport for MCP

> [!WARNING]
> **Experimental / Proof of Concept**
>
> This package is a proof of concept for experimentation purposes. It is not intended for production use.
> The official Python package is being developed at **[GoogleCloudPlatform/mcp-grpc-transport-py](https://github.com/GoogleCloudPlatform/mcp-grpc-transport-py)** — please follow/star that repo to stay updated.

A gRPC transport implementation for the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) using FastMCP.

## Background

- **SEP**: [gRPC as a native MCP transport](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1352) — the specification enhancement proposal
- **Blog**: [gRPC as a Native Transport for MCP](https://cloud.google.com/blog/products/networking/grpc-as-a-native-transport-for-mcp)

## Features

- **Server**: expose a FastMCP server over gRPC
- **Client**: call a gRPC MCP server and get back native `mcp.types` objects
- Tool calls with text and image content, structured output, and progress reporting
- Proto definitions sourced from [GoogleCloudPlatform/mcp-grpc-transport-proto](https://github.com/GoogleCloudPlatform/mcp-grpc-transport-proto)

## Installation

```bash
uv sync
```

The proto package (`mcp-transport-proto`) is fetched directly from GitHub via `[tool.uv.sources]` — no manual proto compilation needed.

## Server

```python
import asyncio
from mcp.server.fastmcp import FastMCP
from grpcmcp import serve_grpc

mcp = FastMCP("My Server")

@mcp.tool()
async def my_tool(x: int) -> str:
    """Does something useful."""
    return str(x)

if __name__ == "__main__":
    asyncio.run(serve_grpc(mcp))          # default: 0.0.0.0:50051
    # asyncio.run(serve_grpc(mcp, port=9090))
```

## Client

```python
import asyncio
from grpcmcp import GRPCClient

async def main():
    async with GRPCClient("localhost", 50051) as client:
        tools = await client.list_tools()
        for tool in tools.tools:
            print(f"{tool.name}: {tool.description}")

        result = await client.call_tool("my_tool", {"x": 42})
        for content in result.content:
            if content.type == "text":
                print(content.text)

asyncio.run(main())
```

### `GRPCClient` reference

| Parameter | Type | Description |
|---|---|---|
| `host` | `str` | Server hostname |
| `port` | `int` | Server port |
| `timeout` | `float \| None` | Default per-call timeout in seconds |
| `channel_options` | `list[tuple] \| None` | Raw gRPC channel options |

| Method | Returns |
|---|---|
| `list_tools()` | `types.ListToolsResult` |
| `call_tool(name, arguments)` | `types.CallToolResult` |

## Running the examples

Start the server:

```bash
uv run python example/grpc_example_server.py
```

In another terminal, run the client:

```bash
uv run python example/grpc_example_client.py
```

## Requirements

- Python >= 3.10
- grpcio >= 1.78.0
- protobuf >= 4.25.0
- mcp == 1.25.0
