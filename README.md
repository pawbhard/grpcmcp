# gRPC Transport for MCP

This module provides a gRPC transport implementation for Model Context Protocol (MCP) using FastMCP.

## Features

- Tool call support with progress reporting
- gRPC streaming for tool calls
- Easy integration with FastMCP

## Usage

The module depends on `fastmcp`. You can run the example server using `uv`:

```bash
uv run example/grpc_example_server.py
```

Or if you have installed the module:

```python
from fastmcp import FastMCP
from grpcmcp import serve_grpc

mcp = FastMCP("My Server")

@mcp.tool()
async def my_tool(x: int) -> str:
    return str(x)

if __name__ == "__main__":
    import asyncio
    asyncio.run(serve_grpc(mcp))
```

## Requirements

- grpcio
- protobuf
- mcp
- fastmcp
