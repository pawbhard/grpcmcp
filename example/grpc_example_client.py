"""Example gRPC MCP client.

Run the server first:
    uv run python example/grpc_example_server.py

Then run this client:
    uv run python example/grpc_example_client.py
"""

import asyncio

from grpcmcp import GRPCClient


async def main():
    async with GRPCClient("localhost", 50051) as client:
        tools = await client.list_tools()
        print("Available tools:")
        for tool in tools.tools:
            print(f"  {tool.name}: {tool.description}")

        result = await client.call_tool("slow_count", {"n": 3})
        print("\ncall_tool slow_count(n=3):")
        for content in result.content:
            if content.type == "text":
                print(f"  {content.text}")


if __name__ == "__main__":
    asyncio.run(main())
