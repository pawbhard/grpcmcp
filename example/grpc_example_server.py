import asyncio

from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.server import MCPServer

from grpcmcp import serve_grpc

mcp = MCPServer("gRPC Example Server")


@mcp.tool()
async def slow_count(n: int, ctx: Context) -> str:
    """Counts to n slowly, reporting progress."""
    for i in range(n):
        await asyncio.sleep(1)
        await ctx.report_progress(i + 1, n, message=f"Counting {i + 1}/{n}")
    return f"Finished counting to {n}"


if __name__ == "__main__":
    try:
        asyncio.run(serve_grpc(mcp, enable_reflection=True))
    except Exception:
        import traceback

        traceback.print_exc()
        raise
