"""Example MCP client using GRPCClientDispatcher.

Run the example server first:
    uv run example/grpc_example_server.py

Then run this client:
    uv run example/grpc_example_client.py
"""
import asyncio

from mcp.client.session import ClientSession
from mcp.types import TextContent

from grpcmcp import GRPCClientDispatcher


async def main() -> None:
    dispatcher = GRPCClientDispatcher("localhost", 50051)
    async with ClientSession(
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        dispatcher=dispatcher,
    ) as session:
        # List available tools
        tools_result = await session.list_tools()
        print(f"Available tools ({len(tools_result.tools)}):")
        for tool in tools_result.tools:
            print(f"  - {tool.name}: {tool.description}")

        # Call a tool
        if tools_result.tools:
            tool_name = tools_result.tools[0].name
            print(f"\nCalling tool '{tool_name}' with n=3 ...")
            result = await session.call_tool(tool_name, {"n": 3})
            print(f"is_error: {result.is_error}")
            for content in result.content:
                if isinstance(content, TextContent):
                    print(f"Result: {content.text}")
            if result.structured_content:
                print(f"Structured: {result.structured_content}")


if __name__ == "__main__":
    asyncio.run(main())
